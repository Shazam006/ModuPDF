"""Request-scoped storage, input validation and bounded processing."""
import asyncio
import contextvars
import importlib.util
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

import fitz
from fastapi import HTTPException
from fastapi.responses import FileResponse
from PIL import Image
from pypdf import PdfReader
from starlette.responses import JSONResponse

BASE = Path(__file__).resolve().parents[1]
FRONT = BASE / "frontend"
WORK = Path(os.getenv("WORK_DIR", str(BASE / "work"))).resolve()
WORK.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_PAGES = int(os.getenv("MAX_PAGES", "500"))
TOOL_TIMEOUT = int(os.getenv("TOOL_TIMEOUT_SECONDS", "300"))
job = contextvars.ContextVar("pdf_job", default=None)
active_jobs = set()
logger = logging.getLogger("modupdf")
PDF = {".pdf"}
IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
OFFICE = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}
MIMES = {
    ".pdf": {"application/pdf"}, ".png": {"image/png"},
    ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"},
    ".tif": {"image/tiff"}, ".tiff": {"image/tiff"}, ".webp": {"image/webp"},
    ".html": {"text/html"}, ".htm": {"text/html"},
    ".doc": {"application/msword"}, ".xls": {"application/vnd.ms-excel"},
    ".ppt": {"application/vnd.ms-powerpoint"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".pptx": {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".p12": {"application/x-pkcs12", "application/pkcs12"},
    ".pfx": {"application/x-pkcs12", "application/pkcs12"},
}
Image.MAX_IMAGE_PIXELS = 25_000_000


class JobMiddleware:
    def __init__(self, app):
        self.app = app
        self.slots = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_JOBS", "2")))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        body_limit = MAX_UPLOAD_BYTES + 1024 * 1024
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = body_limit + 1
        if length > body_limit:
            return await JSONResponse({"detail": f"Limite total de upload: {MAX_UPLOAD_MB} MB."}, 413)(scope, receive, send)
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=10)
        except asyncio.TimeoutError:
            return await JSONResponse({"detail": "Servidor ocupado. Tente novamente em instantes."}, 429)(scope, receive, send)
        directory = tempfile.mkdtemp(prefix="job-", dir=WORK)
        state = {"directory": directory, "bytes": 0, "id": uuid.uuid4().hex}
        token = job.set(state)
        active_jobs.add(directory)
        started, received, status = time.monotonic(), 0, 500

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > body_limit:
                    raise HTTPException(413, f"Limite total de upload: {MAX_UPLOAD_MB} MB.")
            return message

        async def tracked_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] += [(b"x-request-id", state["id"].encode())]
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        finally:
            shutil.rmtree(directory, ignore_errors=True)
            active_jobs.discard(directory)
            job.reset(token)
            self.slots.release()
            logger.info("endpoint=%s duration=%.3f bytes=%d status=%d job=%s", scope["path"], time.monotonic()-started, received, status, state["id"])


def tool_path(names):
    for name in names:
        if executable := shutil.which(name):
            return executable
        local = Path(sys.executable).parent / (name + ".exe" if os.name == "nt" else name)
        if local.is_file():
            return str(local)
    if os.name == "nt":
        candidates = {"soffice": r"C:\Program Files\LibreOffice\program\soffice.exe",
                      "tesseract": r"C:\Program Files\Tesseract-OCR\tesseract.exe"}
        for name in names:
            if name in candidates and Path(candidates[name]).is_file():
                return candidates[name]
        if "gswin64c" in names or "gs" in names:
            root = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "gs"
            for executable in sorted(root.glob("gs*/bin/gswin64c.exe"), reverse=True):
                if executable.is_file():
                    return str(executable)
    return None


def system_capabilities():
    caps = {"libreoffice": bool(tool_path(["soffice", "libreoffice"])),
            "tesseract": bool(tool_path(["tesseract"])), "ocrmypdf": bool(tool_path(["ocrmypdf"])),
            "ghostscript": bool(tool_path(["gswin64c", "gs"])),
            "qpdf": bool(tool_path(["qpdf"])), "verapdf": bool(tool_path(["verapdf"]))}
    caps.update({"max_upload_mb": MAX_UPLOAD_MB, "max_pages": MAX_PAGES,
                 "tools": {"ocr": caps["ocrmypdf"] and caps["tesseract"] and caps["ghostscript"],
                           "office": caps["libreoffice"],
                           "pdfa": caps["ocrmypdf"] and caps["tesseract"] and caps["ghostscript"],
                           "docx": importlib.util.find_spec("pdf2docx") is not None,
                           "xlsx": importlib.util.find_spec("openpyxl") is not None,
                           "pptx": importlib.util.find_spec("pptx") is not None,
                           "sign": importlib.util.find_spec("pyhanko") is not None}})
    return caps


def out(ext=".pdf"):
    state = job.get()
    if state is None:
        raise RuntimeError("File processing requires a request-scoped job.")
    return str(Path(state["directory"]) / (uuid.uuid4().hex + ext))


def save_upload(upload, allowed=PDF):
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, "Tipo de arquivo incompatível com esta ferramenta.")
    mime = (upload.content_type or "").split(";", 1)[0].lower()
    if mime not in MIMES.get(ext, set()) | {"application/octet-stream", ""}:
        raise HTTPException(400, "O tipo MIME não corresponde ao arquivo.")
    path = out(ext)
    state = job.get()
    with open(path, "wb") as stream:
        while chunk := upload.file.read(1024 * 1024):
            state["bytes"] += len(chunk)
            if state["bytes"] > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"Limite total de upload: {MAX_UPLOAD_MB} MB.")
            stream.write(chunk)
    if not Path(path).stat().st_size:
        raise HTTPException(400, "Arquivo vazio.")
    with open(path, "rb") as stream:
        magic = stream.read(1024)
    if ext == ".pdf" and b"%PDF-" not in magic:
        raise HTTPException(400, "O arquivo não contém uma assinatura PDF válida.")
    if ext in IMAGES:
        try:
            with Image.open(path) as image:
                expected={".png":"PNG", ".jpg":"JPEG", ".jpeg":"JPEG", ".tif":"TIFF", ".tiff":"TIFF", ".webp":"WEBP"}
                if image.format != expected[ext] or getattr(image,"n_frames",1)>MAX_PAGES:
                    raise ValueError
                if image.width * image.height > Image.MAX_IMAGE_PIXELS:
                    raise ValueError
                image.verify()
        except Exception:
            raise HTTPException(400, "Imagem inválida ou acima do limite de resolução.")
    if ext in OFFICE:
        if ext.endswith("x"):
            import zipfile
            folder = {".docx": "word/", ".xlsx": "xl/", ".pptx": "ppt/"}[ext]
            try:
                with zipfile.ZipFile(path) as archive:
                    names = archive.namelist()
                    if "[Content_Types].xml" not in names or not any(n.startswith(folder) for n in names):
                        raise ValueError
                    if sum(i.file_size for i in archive.infolist()) > 500 * 1024 * 1024:
                        raise ValueError
            except Exception:
                raise HTTPException(400, "Documento Office inválido ou excessivamente expandido.")
        elif not magic.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            raise HTTPException(400, "Documento Office inválido.")
    return path


def open_pdf(path, allow_encrypted=False):
    try:
        doc = fitz.open(path)
        if doc.needs_pass and not allow_encrypted:
            doc.close()
            raise HTTPException(400, "PDF protegido. Desbloqueie-o primeiro.")
        if not 0 < doc.page_count <= MAX_PAGES:
            doc.close()
            raise HTTPException(400, f"O PDF deve ter entre 1 e {MAX_PAGES} páginas.")
        return doc
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Não foi possível abrir o PDF. Verifique se está corrompido.")


def reader_pdf(upload, allow_encrypted=False):
    path = save_upload(upload)
    with open_pdf(path, allow_encrypted):
        pass
    try:
        return PdfReader(path)
    except Exception:
        raise HTTPException(400, "A estrutura do PDF é inválida.")


def write_pdf(writer, name):
    path = out()
    with open(path, "wb") as stream:
        writer.write(stream)
    return download(path, name)


def download(path, filename, media="application/pdf", headers=None):
    return FileResponse(path, filename=filename, media_type=media,
                        headers={"Cache-Control": "no-store", **(headers or {})})


def parse_pages(expr, total):
    result = []
    try:
        for part in expr.split(","):
            part = part.strip()
            if not part:
                raise ValueError
            if "-" in part:
                a, b = map(int, part.split("-"))
                if not 1 <= a <= total or not 1 <= b <= total:
                    raise ValueError
                result.extend(range(min(a,b), max(a,b)+1))
            else:
                result.append(int(part))
        if not result or any(n < 1 or n > total for n in result) or len(result) > MAX_PAGES:
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(400, "Páginas inválidas. Use números ou intervalos dentro do documento, como 1,3,5-8.")
    return result


def run_tool(command):
    options={"start_new_session":True} if os.name != "nt" else {"creationflags":subprocess.CREATE_NEW_PROCESS_GROUP}
    # Native OCR dependencies must be visible to child processes without activating the venv.
    paths = [str(Path(sys.executable).parent)]
    for names in (["tesseract"], ["gswin64c", "gs"], ["qpdf"]):
        if executable := tool_path(names):
            paths.append(str(Path(executable).parent))
    environment = {**os.environ, "OMP_THREAD_LIMIT":"2",
                   "PATH":os.pathsep.join(dict.fromkeys(paths)) + os.pathsep + os.environ.get("PATH", "")}
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
            cwd=job.get()["directory"], env=environment, **options) as process:
        try:
            stdout,stderr=process.communicate(timeout=TOOL_TIMEOUT)
        except subprocess.TimeoutExpired:
            # Terminate native engine children as well as the Python/Office parent.
            if os.name == "nt":
                try:
                    subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],capture_output=True,timeout=5)
                except (OSError,subprocess.TimeoutExpired):
                    pass
                if process.poll() is None:
                    process.kill()
            else:
                try:
                    os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.communicate()
            raise HTTPException(504, "O processamento excedeu o tempo permitido.")
        result=subprocess.CompletedProcess(command,process.returncode,stdout,stderr)
    if result.returncode:
        logger.warning("tool=%s exit=%d job=%s", Path(command[0]).name, result.returncode, job.get()["id"])
        raise HTTPException(400, "O motor de conversão não conseguiu processar este arquivo.")
    return result


def require_tool(key):
    if not system_capabilities()["tools"].get(key):
        raise HTTPException(503, "Recurso indisponível neste servidor. Consulte a configuração dos motores de processamento.")


def cleanup_stale():
    removed = 0
    cutoff = time.time() - int(os.getenv("TEMP_TTL_SECONDS", "3600"))
    for path in WORK.iterdir():
        if str(path) in active_jobs or path.stat().st_mtime >= cutoff:
            continue
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
