import io
import json

import fitz
import pytest
from PIL import Image


def make_text_pdf(rotation=0):
    with fitz.open() as doc:
        page = doc.new_page(width=420, height=260)
        page.draw_rect(fitz.Rect(30, 42, 250, 82), color=(0.1, 0.4, 0.2), fill=(0.86, 0.94, 0.88))
        page.insert_text((40, 68), "Valor antigo", fontname="hebo", fontsize=16, color=(0.12, 0.26, 0.18))
        page.insert_text((280, 68), "Vizinho", fontsize=12)
        page.set_rotation(rotation)
        return doc.tobytes()


def inspect(client, content):
    response = client.post(
        "/api/text/inspect",
        files={"file": ("texto.pdf", content, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def replace(client, content, span, text):
    payload = [{
        "id": span["id"],
        "page": span["page"],
        "original": span["text"],
        "text": text,
    }]
    return client.post(
        "/api/text/replace",
        files={"file": ("texto.pdf", content, "application/pdf")},
        data={"replacements": json.dumps(payload)},
    )


def test_inspect_and_replace_existing_text(client):
    content = make_text_pdf()
    result = inspect(client, content)
    assert result["pages"] == 1
    assert result["text_pages"] == 1
    target = next(span for span in result["spans"] if span["text"] == "Valor antigo")
    assert target["editable"] is True
    assert target["font"]
    assert target["size"] == 16
    assert all(0 <= target[key] <= 1 for key in ("x", "y", "w", "h"))

    response = replace(client, content, target, "Valor novo")
    assert response.status_code == 200, response.text
    with fitz.open(stream=response.content, filetype="pdf") as doc:
        text = doc[0].get_text()
        assert "Valor novo" in text
        assert "Valor antigo" not in text
        assert "Vizinho" in text
        assert doc[0].get_drawings(), "the background vector must survive text replacement"


def test_replace_shrinks_longer_text_and_can_delete(client):
    content = make_text_pdf()
    target = next(span for span in inspect(client, content)["spans"] if span["text"] == "Valor antigo")
    response = replace(client, content, target, "Valor atualizado")
    assert response.status_code == 200, response.text
    with fitz.open(stream=response.content, filetype="pdf") as doc:
        spans = [span for block in doc[0].get_text("dict")["blocks"] for line in block.get("lines", []) for span in line["spans"]]
        replacement = next(span for span in spans if span["text"] == "Valor atualizado")
        assert 4 <= replacement["size"] <= 16

    response = replace(client, content, target, "")
    assert response.status_code == 200, response.text
    with fitz.open(stream=response.content, filetype="pdf") as doc:
        assert "Valor antigo" not in doc[0].get_text()
        assert "Vizinho" in doc[0].get_text()


def test_replace_preserves_portuguese_characters(client):
    content = make_text_pdf()
    target = next(span for span in inspect(client, content)["spans"] if span["text"] == "Valor antigo")
    response = replace(client, content, target, "Preço atualizado")
    assert response.status_code == 200, response.text
    with fitz.open(stream=response.content, filetype="pdf") as doc:
        assert "Preço atualizado" in doc[0].get_text()
        assert "Valor antigo" not in doc[0].get_text()


def test_replace_text_on_rotated_page(client):
    content = make_text_pdf(rotation=90)
    target = next(span for span in inspect(client, content)["spans"] if span["text"] == "Valor antigo")
    assert all(0 <= target[key] <= 1 for key in ("x", "y", "w", "h"))
    response = replace(client, content, target, "Valor novo")
    assert response.status_code == 200, response.text
    with fitz.open(stream=response.content, filetype="pdf") as doc:
        assert doc[0].rotation == 90
        assert "Valor novo" in doc[0].get_text()


def test_replace_rejects_stale_or_forged_selection(client):
    content = make_text_pdf()
    target = next(span for span in inspect(client, content)["spans"] if span["text"] == "Valor antigo")
    target["text"] = "Outro texto"
    response = replace(client, content, target, "Novo")
    assert response.status_code == 409


def test_inspect_reports_scanned_page_without_text(client):
    image = io.BytesIO()
    Image.new("RGB", (180, 100), "white").save(image, "PNG")
    with fitz.open() as doc:
        page = doc.new_page(width=180, height=100)
        page.insert_image(page.rect, stream=image.getvalue())
        content = doc.tobytes()
    result = inspect(client, content)
    assert result["spans"] == []
    assert result["empty_pages"] == [1]


@pytest.mark.parametrize("neighbor_baseline", [53, 83])
@pytest.mark.parametrize("replacement", ["Valor novo", ""])
def test_replace_preserves_tightly_spaced_lines(client, neighbor_baseline, replacement):
    with fitz.open() as doc:
        page = doc.new_page(width=420, height=260)
        page.insert_text((40, 68), "Valor antigo", fontname="hebo", fontsize=16)
        page.insert_text((40, neighbor_baseline), "Vizinho", fontsize=16)
        content = doc.tobytes()
    target = next(span for span in inspect(client, content)["spans"] if span["text"] == "Valor antigo")
    response = replace(client, content, target, replacement)
    assert response.status_code == 200, response.text
    with fitz.open(stream=response.content, filetype="pdf") as doc:
        assert "Valor antigo" not in doc[0].get_text()
        assert "Vizinho" in doc[0].get_text()
        if replacement:
            assert replacement in doc[0].get_text()


def test_replace_rejects_overlapping_text_instead_of_deleting_it(client):
    with fitz.open() as doc:
        page = doc.new_page(width=420, height=260)
        page.insert_text((40, 68), "Valor antigo", fontname="hebo", fontsize=16)
        page.insert_text((40, 68), "Vizinho", fontsize=16)
        content = doc.tobytes()
    target = next(span for span in inspect(client, content)["spans"] if span["text"] == "Valor antigo")
    response = replace(client, content, target, "Valor novo")
    assert response.status_code == 400, response.text
    assert "sem alterar outros textos" in response.json()["detail"]


def test_replace_does_not_apply_existing_redaction_annotations(client):
    with fitz.open(stream=make_text_pdf(), filetype="pdf") as doc:
        doc[0].add_redact_annot(fitz.Rect(300, 160, 350, 200))
        content = doc.tobytes()
    target = next(span for span in inspect(client, content)["spans"] if span["text"] == "Valor antigo")
    response = replace(client, content, target, "Valor novo")
    assert response.status_code == 400, response.text
    assert "ocultações pendentes" in response.json()["detail"]
