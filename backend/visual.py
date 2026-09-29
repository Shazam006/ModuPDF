import base64
import io
import json
import math
import re
from typing import Literal

import fitz
from fastapi import HTTPException
from PIL import Image, ImageChops
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .runtime import FRONT, download, open_pdf, out, save_upload


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text", "rectangle", "image", "redact"]
    page: int = Field(ge=1)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)
    text: str = Field(default="", max_length=2000)
    color: str = "#000000"
    size: float = Field(default=14, ge=5, le=96)
    image: str = Field(default="", max_length=8_000_000)

    @model_validator(mode="after")
    def bounds(self):
        if self.x+self.w > 1.001 or self.y+self.h > 1.001:
            raise ValueError("Selection exceeds page bounds")
        if len(self.color) != 7 or not self.color.startswith("#"):
            raise ValueError("Invalid color")
        int(self.color[1:], 16)
        return self


class TextReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^p\d+-s\d+$", max_length=32)
    page: int = Field(ge=1)
    original: str = Field(max_length=4000)
    text: str = Field(max_length=4000)

    @model_validator(mode="after")
    def single_line(self):
        if "\n" in self.text or "\r" in self.text:
            raise ValueError("Replacement text must be a single line")
        return self


def parse_operations(raw):
    try:
        data = json.loads(raw)
        if not isinstance(data, list) or not 0 < len(data) <= 500:
            raise ValueError
        return [Operation.model_validate(item) for item in data]
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(400, "Seleções inválidas. Adicione pelo menos uma área dentro da página.")


def selection_rect(page, item):
    visible = page.rect
    rect = fitz.Rect(item.x*visible.width, item.y*visible.height,
                     (item.x+item.w)*visible.width, (item.y+item.h)*visible.height)
    return rect * page.derotation_matrix


def _font_label(name):
    return re.sub(r"^[A-Z]{6}\+", "", name or "Fonte do documento")


def _base14_font(span):
    name = span["font"].lower()
    flags = int(span["flags"])
    bold = bool(flags & 16) or "bold" in name
    italic = bool(flags & 2) or any(token in name for token in ("italic", "oblique"))
    if bool(flags & 8) or any(token in name for token in ("courier", "mono", "consol")):
        return ("cobi" if bold and italic else "cobo" if bold else "coit" if italic else "cour")
    if bool(flags & 4) or any(token in name for token in ("times", "serif", "cambria", "georgia")):
        return ("tibi" if bold and italic else "tibo" if bold else "tiit" if italic else "tiro")
    return "hebi" if bold and italic else "hebo" if bold else "heit" if italic else "helv"


def _text_spans(doc, public=False):
    spans = []
    for page_index, page in enumerate(doc):
        visible = page.rect
        rotation = page.rotation_matrix
        span_index = 0
        for block in page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]:
            for line in block.get("lines", []):
                direction = tuple(line.get("dir", (1.0, 0.0)))
                horizontal = math.isclose(direction[0], 1.0, abs_tol=.001) and math.isclose(direction[1], 0.0, abs_tol=.001)
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text or not text.strip():
                        continue
                    span_index += 1
                    rect = fitz.Rect(span["bbox"])
                    displayed = (rect * rotation).normalize()
                    identifier = f"p{page_index + 1}-s{span_index}"
                    visible_text = int(span.get("alpha", 255)) > 0
                    item = {
                        "id": identifier,
                        "page": page_index + 1,
                        "text": text,
                        "font": _font_label(span.get("font", "")),
                        "size": round(float(span.get("size", 11)), 2),
                        "color": f"#{int(span.get('color', 0)) & 0xFFFFFF:06x}",
                        "editable": horizontal and visible_text,
                        "reason": "" if horizontal and visible_text else ("Texto invisível de OCR não pode ser alterado visualmente." if not visible_text else "Texto inclinado ou vertical ainda não pode ser substituído."),
                        "x": max(0, displayed.x0 / visible.width),
                        "y": max(0, displayed.y0 / visible.height),
                        "w": min(1, displayed.width / visible.width),
                        "h": min(1, displayed.height / visible.height),
                    }
                    if not public:
                        item.update({
                            "bbox": rect,
                            "origin": fitz.Point(span.get("origin", (rect.x0, rect.y1))),
                            "flags": int(span.get("flags", 0)),
                            "raw_font": span.get("font", ""),
                            "raw_color": int(span.get("color", 0)),
                        })
                    spans.append(item)
    return spans


def inspect_text(file):
    with open_pdf(save_upload(file)) as doc:
        spans = _text_spans(doc, public=True)
        if len(spans) > 10_000:
            raise HTTPException(400, "Este PDF tem texto demais para edição interativa. Divida o documento em partes menores.")
        counts = [0] * len(doc)
        for span in spans:
            counts[span["page"] - 1] += 1
        return {
            "pages": len(doc),
            "spans": spans,
            "text_pages": sum(count > 0 for count in counts),
            "empty_pages": [index + 1 for index, count in enumerate(counts) if not count],
        }


def _parse_replacements(raw):
    try:
        data = json.loads(raw)
        if not isinstance(data, list) or not 0 < len(data) <= 200:
            raise ValueError
        replacements = [TextReplacement.model_validate(item) for item in data]
        if len({item.id for item in replacements}) != len(replacements):
            raise ValueError
        return replacements
    except (ValueError, TypeError, ValidationError, json.JSONDecodeError):
        raise HTTPException(400, "Alterações de texto inválidas.")


def _fit_font(text, span):
    fontname = _base14_font(span)
    fontfile = None
    set_simple = False
    if any(ord(character) > 127 for character in text):
        flags = int(span["flags"])
        suffix = "BoldItalic" if flags & 16 and flags & 2 else "Bold" if flags & 16 else "Italic" if flags & 2 else "Regular"
        path = FRONT / "assets" / "vendor" / "pdfjs" / "standard_fonts" / f"LiberationSans-{suffix}.ttf"
        font = fitz.Font(fontfile=str(path))
        unsupported = sorted({character for character in text if not character.isspace() and not font.has_glyph(ord(character))})
        if unsupported:
            raise HTTPException(400, f'A fonte disponível não contém: {" ".join(unsupported[:10])}.')
        set_simple = all(ord(character) <= 255 for character in text)
        fontname = f"modu-{suffix.lower()}-{'latin' if set_simple else 'unicode'}"
        fontfile = str(path)
        text_width = font.text_length(text, fontsize=span["size"])
    else:
        text_width = fitz.get_text_length(text, fontname=fontname, fontsize=span["size"])
    original_size = span["size"]
    width = span["bbox"].width
    size = original_size if text_width <= width else original_size * width / max(text_width, .01)
    if size < 4:
        raise HTTPException(400, f'O novo texto "{text[:40]}" não cabe no espaço original. Reduza o conteúdo.')
    return fontname, fontfile, set_simple, max(4, size)


def replace_text(file, raw):
    replacements = _parse_replacements(raw)
    path = out()
    with open_pdf(save_upload(file)) as doc:
        available = {span["id"]: span for span in _text_spans(doc)}
        targets = []
        for replacement in replacements:
            span = available.get(replacement.id)
            if not span or span["page"] != replacement.page or span["text"] != replacement.original:
                raise HTTPException(409, "O texto do documento mudou. Reabra o editor e tente novamente.")
            if not span["editable"]:
                raise HTTPException(400, span["reason"])
            if replacement.text == replacement.original:
                continue
            targets.append((replacement, span))
        if not targets:
            raise HTTPException(400, "Nenhuma alteração de texto foi informada.")

        by_page = {}
        for replacement, span in targets:
            by_page.setdefault(span["page"] - 1, []).append((replacement, span))
        for page_index, page_targets in by_page.items():
            page = doc[page_index]
            for _, span in page_targets:
                page.add_redact_annot(span["bbox"], fill=False, cross_out=False)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                                  graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                  text=fitz.PDF_REDACT_TEXT_REMOVE)
            for replacement, span in page_targets:
                if not replacement.text:
                    continue
                fontname, fontfile, set_simple, fontsize = _fit_font(replacement.text, span)
                color_value = span["raw_color"] & 0xFFFFFF
                color = tuple(((color_value >> shift) & 0xFF) / 255 for shift in (16, 8, 0))
                if fontfile:
                    page.insert_font(fontname=fontname, fontfile=fontfile, set_simple=set_simple)
                page.insert_text(span["origin"], replacement.text, fontname=fontname,
                                 fontsize=fontsize, color=color, overlay=True)
        doc.save(path, garbage=4, deflate=True, clean=True)
    return download(path, "pdf_texto_editado.pdf")


def apply_operations(file, raw, redaction=False):
    operations = parse_operations(raw)
    path = out()
    with open_pdf(save_upload(file)) as doc:
        for item in operations:
            if item.page > len(doc) or (redaction and item.type != "redact") or (not redaction and item.type == "redact"):
                raise HTTPException(400, "Operação incompatível com a ferramenta ou página inexistente.")
            page = doc[item.page-1]
            rect = selection_rect(page, item)
            color = tuple(int(item.color[i:i+2],16)/255 for i in (1,3,5))
            if item.type == "redact":
                for widget in list(page.widgets() or []):
                    if widget.rect.intersects(rect):
                        page.delete_widget(widget)
                page.add_redact_annot(rect, fill=(0,0,0))
            elif item.type == "rectangle":
                page.draw_rect(rect, color=color, width=1.5)
            elif item.type == "text":
                if not item.text.strip():
                    raise HTTPException(400, "Informe o texto a inserir.")
                spare = page.insert_textbox(rect, item.text, fontsize=item.size, color=color, rotate=page.rotation)
                if spare < 0:
                    raise HTTPException(400, "O texto não cabe na área escolhida. Aumente a área ou reduza a fonte.")
            else:
                try:
                    encoded = item.image.split(",",1)[-1]
                    content = base64.b64decode(encoded, validate=True)
                    with Image.open(io.BytesIO(content)) as image:
                        if image.format not in {"PNG", "JPEG"}:
                            raise ValueError
                        if image.width * image.height > Image.MAX_IMAGE_PIXELS:
                            raise ValueError
                        image.verify()
                    page.insert_image(rect, stream=content, rotate=page.rotation)
                except Exception:
                    raise HTTPException(400, "Imagem de edição inválida.")
        if redaction:
            for page in doc:
                page.apply_redactions(images=2, graphics=2, text=0)
            # Remove hidden metadata and attachments along with selected page contents.
            doc.set_metadata({})
            doc.del_xml_metadata()
            for name in doc.embfile_names():
                doc.embfile_del(name)
            doc.scrub(attached_files=True, clean_pages=True, embedded_files=True,
                      hidden_text=True, javascript=True, metadata=True, redactions=True,
                      redact_images=2, remove_links=True, reset_fields=True, reset_responses=True,
                      thumbnails=True, xml_metadata=True)
        doc.save(path, garbage=4, deflate=True, clean=True)
    return download(path, "pdf_ocultado.pdf" if redaction else "pdf_editado.pdf")


def inspect_forms(file):
    result = []
    with open_pdf(save_upload(file)) as doc:
        for number, page in enumerate(doc,1):
            for widget in page.widgets() or []:
                result.append({"name": widget.field_name, "value": widget.field_value or "",
                               "type": widget.field_type_string, "page": number,
                               "options": widget.choice_values or [],
                               "on_state": widget.on_state() if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX else None,
                               "readonly": bool(widget.field_flags & 1)})
    return {"fields": result}


def update_forms(file, values_raw, fields_raw):
    try:
        values, fields = json.loads(values_raw), json.loads(fields_raw)
        if not isinstance(values, dict) or not isinstance(fields, list) or len(fields) > 100:
            raise ValueError
        if any(not isinstance(value,(str,bool,int,float)) or len(str(value)) > 2000 for value in values.values()):
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(400, "Dados do formulário inválidos.")
    path = out()
    with open_pdf(save_upload(file)) as doc:
        names = {widget.field_name for page in doc for widget in (page.widgets() or [])}
        if set(values) - names:
            raise HTTPException(400, "Um dos campos informados não existe no documento.")
        for page in doc:
            for widget in page.widgets() or []:
                if widget.field_name not in values:
                    continue
                if widget.field_flags & 1 or widget.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    raise HTTPException(400, "Um dos campos selecionados não permite edição.")
                value = values[widget.field_name]
                if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                    value = widget.on_state() if value in {True, "true", widget.on_state()} else "Off"
                elif widget.field_type not in {fitz.PDF_WIDGET_TYPE_TEXT, fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX}:
                    raise HTTPException(400, "Tipo de campo ainda não suportado para preenchimento.")
                widget.field_value = str(value)
                widget.update()
        for field in fields:
            try:
                name = str(field["name"]).strip()
                operation = Operation.model_validate({"type":"rectangle", **{k:field[k] for k in ("page","x","y","w","h")}})
                if not name or len(name)>100 or name in names or operation.page > len(doc):
                    raise ValueError
            except (ValueError, KeyError, TypeError, ValidationError):
                raise HTTPException(400, "Campo novo inválido ou nome duplicado.")
            page = doc[operation.page-1]
            widget = fitz.Widget()
            widget.field_name = name
            widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            widget.field_value = str(field.get("value", ""))[:2000]
            widget.rect = selection_rect(page, operation)
            widget.text_fontsize = 0
            widget.border_width = 1
            widget.border_color = (0.3,0.3,0.3)
            page.add_widget(widget)
            names.add(name)
        if not values and not fields:
            raise HTTPException(400, "Não há campos para salvar.")
        doc.save(path, garbage=4, deflate=True)
    return download(path, "pdf_formulario.pdf")


def compare_pdfs(file1, file2):
    path = out()
    with open_pdf(save_upload(file1)) as first, open_pdf(save_upload(file2)) as second, fitz.open() as report:
        changed = 0
        total = max(len(first),len(second))
        for index in range(total):
            page = report.new_page(width=1190, height=842)
            page.insert_text((24,30), f"ModuPDF - Comparacao - Pagina {index+1}", fontsize=16)
            pictures = []
            for document in (first,second):
                if index < len(document):
                    source = document[index]
                    scale = min(1, 1200/max(source.rect.width, source.rect.height))
                    pix = source.get_pixmap(matrix=fitz.Matrix(scale,scale), colorspace=fitz.csRGB, alpha=False)
                    pictures.append(Image.frombytes("RGB", [pix.width,pix.height], pix.samples))
                else:
                    pictures.append(None)
            same = False
            box = None
            if all(pictures):
                width = max(image.width for image in pictures)
                height = max(image.height for image in pictures)
                canvases = []
                for image in pictures:
                    canvas = Image.new("RGB",(width,height),"white")
                    canvas.paste(image,(0,0))
                    canvases.append(canvas)
                difference = ImageChops.difference(*canvases)
                mask = difference.convert("L").point(lambda value: 255 if value > 15 else 0)
                box = mask.getbbox()
                same = box is None and pictures[0].size == pictures[1].size
                pictures = canvases
            changed += not same
            page.insert_text((24,54), "Sem diferencas visuais detectadas" if same else "Diferencas visuais detectadas", fontsize=11, color=(0,.45,.25) if same else (.7,.12,.15))
            for side,image in enumerate(pictures):
                x = 24+side*590
                page.insert_text((x,78), "Original" if side == 0 else "Comparado", fontsize=11)
                if image is None:
                    page.insert_text((x,110), "Pagina ausente nesta versao", fontsize=13)
                    continue
                data = io.BytesIO()
                image.save(data,"PNG")
                frame = fitz.Rect(x,90,x+550,805)
                ratio = min(frame.width/image.width,frame.height/image.height)
                actual = fitz.Rect(x,90,x+image.width*ratio,90+image.height*ratio)
                page.insert_image(actual,stream=data.getvalue())
                if side == 1 and box:
                    page.draw_rect(fitz.Rect(x+box[0]*ratio,90+box[1]*ratio,
                        min(actual.x1,x+box[2]*ratio),min(actual.y1,90+box[3]*ratio)), color=(.85,.1,.15), width=2)
        report.set_metadata({"title": f"ModuPDF: {changed} de {total} páginas diferentes"})
        report.save(path, garbage=4, deflate=True)
    return download(path,"comparacao.pdf", headers={"X-Changed-Pages":str(changed)})
