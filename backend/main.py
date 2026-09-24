from contextlib import asynccontextmanager
import copy
import io
import json
import os
from pathlib import Path
import zipfile

import fitz
import img2pdf
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pypdf import PdfWriter

from .runtime import (FRONT, MAX_PAGES, IMAGES, OFFICE, JobMiddleware,
                      cleanup_stale, download, job, open_pdf, out, parse_pages,
                      reader_pdf, require_tool, run_tool, save_upload,
                      system_capabilities, tool_path, write_pdf)
from .visual import apply_operations, inspect_forms, update_forms, compare_pdfs
from .conversions import html_to_pdf, pdf_to_office, pdf_a, sign


@asynccontextmanager
async def lifespan(app):
    cleanup_stale()
    yield


app = FastAPI(title="ModuPDF", version="4.3", lifespan=lifespan)
app.add_middleware(JobMiddleware)
app.add_middleware(CORSMiddleware,
    allow_origins=[s.strip() for s in os.getenv("ALLOWED_ORIGINS", "https://shazam006.github.io,http://localhost:8000,http://127.0.0.1:8000,http://localhost:8768,http://127.0.0.1:8768").split(",") if s.strip()],
    allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition", "X-Original-Bytes", "X-Final-Bytes", "X-Reduction-Percent", "X-Target-Met", "X-PDF-Profile", "X-PDFA-Validation", "X-Request-ID"])
app.mount("/assets", StaticFiles(directory=FRONT / "assets"), name="assets")


@app.exception_handler(Exception)
async def processing_error(request: Request, exc: Exception):
    from .runtime import logger
    logger.error("endpoint=%s error=%s", request.url.path, type(exc).__name__)
    return JSONResponse({"detail": "Falha técnica no processamento. Verifique o arquivo e tente novamente."}, 500)


@app.get("/")
def home():
    return FileResponse(FRONT / "index.html", media_type="text/html")


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "4.3", "local": os.getenv("APP_ENV", "local") == "local"}


@app.get("/api/system/capabilities")
def capabilities():
    return system_capabilities()


@app.post("/api/system/cleanup")
def cleanup():
    return {"removed": cleanup_stale()}


@app.post("/api/merge")
def merge(files: list[UploadFile] = File(...)):
    if len(files) < 2:
        raise HTTPException(400, "Envie pelo menos 2 PDFs.")
    writer = PdfWriter()
    for index, file in enumerate(files):
        reader = reader_pdf(file)
        if len(writer.pages) + len(reader.pages) > MAX_PAGES:
            raise HTTPException(400, f"O resultado excede {MAX_PAGES} páginas.")
        if reader.get_fields():
            reader.add_form_topname(f"arquivo_{index+1}")
        writer.append(reader)
    return write_pdf(writer, "pdf_unificado.pdf")


@app.post("/api/organize")
def organize(file: UploadFile = File(...), order: str = Form(...), rotations: str = Form("")):
    reader = reader_pdf(file)
    nums = parse_pages(order, len(reader.pages))
    if sorted(nums) != list(range(1, len(reader.pages)+1)):
        raise HTTPException(400, "A ordem deve conter todas as páginas uma única vez.")
    try:
        rots = dict(map(lambda pair: map(int, pair.split(":")), rotations.split(","))) if rotations else {}
        if any(deg % 90 for deg in rots.values()):
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(400, "Rotações inválidas. Use múltiplos de 90 graus.")
    writer = PdfWriter()
    for number in nums:
        page = copy.copy(reader.pages[number-1])
        page.rotate(rots.get(number, 0) % 360)
        writer.add_page(page)
    return write_pdf(writer, "pdf_organizado.pdf")


@app.post("/api/organize-multi")
def organize_multi(files: list[UploadFile] = File(...), order: str = Form(...), rotations: str = Form("")):
    readers = [reader_pdf(file) for file in files]
    try:
        sequence = json.loads(order)
        legacy = {(int(i["fileIndex"]), int(i["page"])): int(i["rotation"]) for i in json.loads(rotations or "[]")}
        if not isinstance(sequence, list) or not 0 < len(sequence) <= MAX_PAGES:
            raise ValueError
        writer = PdfWriter()
        for item in sequence:
            fi, pg = int(item["fileIndex"]), int(item["page"])
            rotation = int(item.get("rotation", legacy.get((fi, pg), 0)))
            if fi < 0 or fi >= len(readers) or not 1 <= pg <= len(readers[fi].pages) or rotation % 90:
                raise ValueError
            page = copy.copy(readers[fi].pages[pg-1])
            page.rotate(rotation % 360)
            writer.add_page(page)
        return write_pdf(writer, "pdf_organizado.pdf")
    except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError):
        raise HTTPException(400, "Ordem ou rotações de páginas inválidas.")


@app.post("/api/split")
def split(file: UploadFile = File(...), pages: str = Form(...), mode: str = Form("extract")):
    reader = reader_pdf(file)
    nums = parse_pages(pages, len(reader.pages))
    if mode == "individual":
        path = out(".zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, number in enumerate(nums):
                writer = PdfWriter()
                writer.add_page(reader.pages[number-1])
                data = io.BytesIO()
                writer.write(data)
                archive.writestr(f"{index+1:03d}_pagina_{number}.pdf", data.getvalue())
        return download(path, "paginas_separadas.zip", "application/zip")
    if mode != "extract":
        raise HTTPException(400, "Modo de divisão inválido.")
    writer = PdfWriter()
    for number in nums:
        writer.add_page(reader.pages[number-1])
    return write_pdf(writer, "paginas_extraidas.pdf")


@app.post("/api/remove-pages")
def remove_pages(file: UploadFile = File(...), pages: str = Form(...)):
    reader = reader_pdf(file)
    removed = set(parse_pages(pages, len(reader.pages)))
    if len(removed) == len(reader.pages):
        raise HTTPException(400, "Não é possível remover todas as páginas.")
    writer = PdfWriter()
    for number, page in enumerate(reader.pages, 1):
        if number not in removed:
            writer.add_page(page)
    return write_pdf(writer, "pdf_sem_paginas.pdf")


@app.post("/api/rotate")
def rotate(file: UploadFile = File(...), degrees: int = Form(90)):
    if degrees % 90:
        raise HTTPException(400, "Use múltiplos de 90 graus.")
    reader = reader_pdf(file)
    writer = PdfWriter()
    for page in reader.pages:
        page.rotate(degrees % 360)
        writer.add_page(page)
    return write_pdf(writer, "pdf_rotacionado.pdf")


def convert_images(files):
    if not 0 < len(files) <= MAX_PAGES:
        raise HTTPException(400, f"Envie entre 1 e {MAX_PAGES} imagens.")
    paths = [save_upload(file, IMAGES) for file in files]
    normalized=[]
    for source in paths:
        if Path(source).suffix==".webp":
            with Image.open(source) as image:
                if getattr(image,"n_frames",1)>1:
                    raise HTTPException(400,"WebP animado não é aceito. Use uma imagem estática.")
                png=out(".png")
                image.save(png,"PNG")
                normalized.append(png)
        else:
            normalized.append(source)
    path = out()
    try:
        with open(path, "wb") as stream:
            stream.write(img2pdf.convert(normalized))
    except Exception:
        raise HTTPException(400, "Não foi possível converter as imagens.")
    with open_pdf(path):
        pass
    return path


@app.post("/api/images-to-pdf")
def images_to_pdf(files: list[UploadFile] = File(...)):
    return download(convert_images(files), "imagens.pdf")


@app.post("/api/pdf-to-images")
def pdf_to_images(file: UploadFile = File(...), fmt: str = Form("png"), dpi: int = Form(150, ge=72, le=300)):
    if fmt not in {"png", "jpg"}:
        raise HTTPException(400, "Formato de imagem inválido.")
    path = out(".zip")
    with open_pdf(save_upload(file)) as doc, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for number, page in enumerate(doc, 1):
            if page.rect.width * page.rect.height * (dpi/72)**2 > 25_000_000:
                raise HTTPException(400, "Página muito grande para este DPI. Reduza a resolução.")
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            archive.writestr(f"pagina_{number:03d}.{fmt}", pix.tobytes("jpeg" if fmt == "jpg" else "png"))
    return download(path, "pdf_para_imagens.zip", "application/zip")


@app.post("/api/compress")
def compress(file: UploadFile = File(...), level: str = Form("balanced"), target_mb: float | None = Form(None, gt=0)):
    if level not in {"lossless", "balanced", "maximum"}:
        raise HTTPException(400, "Perfil de compressão inválido.")
    source = save_upload(file)
    original = Path(source).stat().st_size
    best, best_size = source, original
    with open_pdf(source) as doc:
        images, text_pages = {}, 0
        for page in doc:
            text_pages += bool(page.get_text().strip())
            for info in page.get_images(full=True):
                images.setdefault(info[0], page.number)
        profile = "scanned" if images and not text_pages else "mixed" if images else "textual"
        lossless = out()
        doc.save(lossless, garbage=4, deflate=True, clean=True)
        if Path(lossless).stat().st_size < best_size:
            best, best_size = lossless, Path(lossless).stat().st_size
    if level != "lossless" and images:
        attempts = [(1600, 80)] if level == "balanced" else [(1600, 75), (1200, 60), (900, 45)]
        for max_dimension, quality in attempts:
            with open_pdf(source) as doc:
                for xref, page_number in images.items():
                    image_data = doc.extract_image(xref)
                    if not image_data or image_data.get("smask"):
                        continue
                    try:
                        with Image.open(io.BytesIO(image_data["image"])) as image:
                            if image.width * image.height > 25_000_000:
                                continue
                            image = image.convert("RGB")
                            image.thumbnail((max_dimension, max_dimension))
                            encoded = io.BytesIO()
                            image.save(encoded, "JPEG", quality=quality, optimize=True)
                            if len(encoded.getvalue()) < len(image_data["image"]):
                                doc[page_number].replace_image(xref, stream=encoded.getvalue())
                    except (OSError, ValueError):
                        continue
                candidate = out()
                doc.save(candidate, garbage=4, deflate=True, clean=True)
                size = Path(candidate).stat().st_size
                if size < best_size:
                    best, best_size = candidate, size
            if target_mb and best_size <= target_mb * 1024**2:
                break
    headers = {"X-Original-Bytes": str(original), "X-Final-Bytes": str(best_size),
               "X-Reduction-Percent": f"{(1-best_size/original)*100:.2f}", "X-PDF-Profile": profile,
               "X-Target-Met": "not-set" if target_mb is None else str(best_size <= target_mb * 1024**2).lower()}
    return download(best, "pdf_comprimido.pdf", headers=headers)


@app.post("/api/watermark")
def watermark(file: UploadFile = File(...), text: str = Form(..., min_length=1, max_length=200)):
    if not text.strip():
        raise HTTPException(400, "Informe o texto da marca d'água.")
    path = out()
    with open_pdf(save_upload(file)) as doc:
        font = fitz.Font("helv")
        for page in doc:
            size = min(32, page.rect.width * .8 / max(font.text_length(text, fontsize=1), 1))
            center = fitz.Point(page.rect.width/2, page.rect.height/2)
            page.insert_text((center.x-font.text_length(text, fontsize=size)/2, center.y), text,
                fontsize=size, color=(.45,.45,.45), fill_opacity=.25, morph=(center, fitz.Matrix(35)))
        doc.save(path, garbage=4, deflate=True)
    return download(path, "pdf_marca_dagua.pdf")


@app.post("/api/protect")
def protect(file: UploadFile = File(...), password: str = Form(..., min_length=1, max_length=256)):
    writer = PdfWriter()
    writer.clone_document_from_reader(reader_pdf(file))
    writer.encrypt(password, algorithm="AES-256")
    return write_pdf(writer, "pdf_protegido.pdf")


@app.post("/api/unlock")
def unlock(file: UploadFile = File(...), password: str = Form("")):
    reader = reader_pdf(file, allow_encrypted=True)
    if reader.is_encrypted and not reader.decrypt(password):
        raise HTTPException(400, "Senha incorreta.")
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    return write_pdf(writer, "pdf_desbloqueado.pdf")


@app.post("/api/add-page-numbers")
def add_page_numbers(file: UploadFile = File(...), start: int = Form(1, ge=0, le=100000)):
    path = out()
    with open_pdf(save_upload(file)) as doc:
        for index, page in enumerate(doc):
            page.insert_text((page.rect.width/2-10, page.rect.height-25), str(start+index), fontsize=10)
        doc.save(path, garbage=4, deflate=True)
    return download(path, "pdf_numerado.pdf")


@app.post("/api/crop")
def crop(file: UploadFile = File(...), margin: float = Form(20, ge=0)):
    path = out()
    with open_pdf(save_upload(file)) as doc:
        for page in doc:
            rect = page.cropbox
            if margin * 2 >= min(rect.width, rect.height):
                raise HTTPException(400, "A margem elimina toda a página. Use um valor menor.")
            page.set_cropbox(fitz.Rect(rect.x0+margin, rect.y0+margin, rect.x1-margin, rect.y1-margin))
        doc.save(path)
    return download(path, "pdf_recortado.pdf")


@app.post("/api/repair")
def repair(file: UploadFile = File(...)):
    path = out()
    with open_pdf(save_upload(file)) as doc:
        doc.save(path, garbage=4, deflate=True, clean=True)
    return download(path, "pdf_reparado.pdf")


def execute_ocr(source, language, output_type="pdf"):
    require_tool("ocr" if output_type == "pdf" else "pdfa")
    if language not in {"por", "eng", "spa", "por+eng", "por+eng+spa"}:
        raise HTTPException(400, "Idioma OCR não suportado.")
    path = out()
    run_tool([tool_path(["ocrmypdf"]), "--skip-text", "--rotate-pages", "--deskew", "--jobs", "1",
              "--output-type", output_type, "-l", language, source, path])
    with open_pdf(path):
        pass
    return path


@app.post("/api/ocr")
def ocr(file: UploadFile = File(...), language: str = Form("por")):
    source = save_upload(file)
    with open_pdf(source):
        pass
    return download(execute_ocr(source, language), "pdf_ocr.pdf")


@app.post("/api/scan-to-pdf")
def scan_to_pdf(files: list[UploadFile] = File(...), run_ocr: bool = Form(False), language: str = Form("por")):
    path = convert_images(files)
    if run_ocr:
        path = execute_ocr(path, language)
    return download(path, "digitalizacao_ocr.pdf" if run_ocr else "digitalizacao.pdf")


@app.post("/api/office-to-pdf")
def office_to_pdf(file: UploadFile = File(...)):
    require_tool("office")
    source = save_upload(file, OFFICE)
    directory = job.get()["directory"]
    profile = Path(directory, "office-profile").as_uri()
    run_tool([tool_path(["soffice", "libreoffice"]), f"-env:UserInstallation={profile}",
              "--headless", "--convert-to", "pdf", "--outdir", directory, source])
    path = str(Path(source).with_suffix(".pdf"))
    if not Path(path).is_file():
        raise HTTPException(400, "O LibreOffice não produziu um PDF.")
    with open_pdf(path):
        pass
    return download(path, "convertido.pdf")


app.post("/api/html-to-pdf")(html_to_pdf)
app.post("/api/pdf-to-office")(pdf_to_office)
app.post("/api/pdf-a")(pdf_a)
app.post("/api/sign")(sign)


@app.post("/api/edit")
def edit(file: UploadFile = File(...), operations: str = Form(...)):
    return apply_operations(file, operations, redaction=False)


@app.post("/api/redact")
def redact(file: UploadFile = File(...), operations: str = Form(...)):
    return apply_operations(file, operations, redaction=True)


@app.post("/api/forms/inspect")
def forms_inspect(file: UploadFile = File(...)):
    return inspect_forms(file)


@app.post("/api/forms")
def forms(file: UploadFile = File(...), values: str = Form("{}"), fields: str = Form("[]")):
    return update_forms(file, values, fields)


@app.post("/api/compare")
def compare(file1: UploadFile = File(...), file2: UploadFile = File(...)):
    return compare_pdfs(file1, file2)
