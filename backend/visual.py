import base64
import io
import json
from typing import Literal

import fitz
from fastapi import HTTPException
from PIL import Image, ImageChops
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .runtime import download, open_pdf, out, save_upload


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
