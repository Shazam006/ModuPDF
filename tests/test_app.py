from io import BytesIO

import fitz
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def make_pdf(page_count=3):
    doc = fitz.open()
    for i in range(page_count):
        page = doc.new_page(width=300, height=400)
        page.insert_text((30, 40), f"Página {i + 1}")
    data = doc.tobytes()
    doc.close()
    return data


def pdf_page_count(data):
    doc = fitz.open(stream=data, filetype="pdf")
    count = doc.page_count
    doc.close()
    return count


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "4.4"


def test_home():
    response = client.get("/")
    assert response.status_code == 200
    assert "ModuPDF" in response.text


def test_capabilities():
    response = client.get("/api/system/capabilities")
    assert response.status_code == 200
    payload = response.json()
    for key in ("libreoffice", "tesseract", "ocrmypdf", "ghostscript", "verapdf"):
        assert key in payload


def test_merge_endpoint():
    a = make_pdf(2)
    b = make_pdf(1)
    response = client.post(
        "/api/merge",
        files=[
            ("files", ("a.pdf", BytesIO(a), "application/pdf")),
            ("files", ("b.pdf", BytesIO(b), "application/pdf")),
        ],
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert pdf_page_count(response.content) == 3


def test_organize_multi_endpoint_reorders_pages():
    data = make_pdf(3)
    response = client.post(
        "/api/organize-multi",
        data={"order": '[{"fileIndex":0,"page":3},{"fileIndex":0,"page":1},{"fileIndex":0,"page":2}]'},
        files={"files": ("source.pdf", BytesIO(data), "application/pdf")},
    )
    assert response.status_code == 200
    assert pdf_page_count(response.content) == 3
    doc = fitz.open(stream=response.content, filetype="pdf")
    texts = [page.get_text() for page in doc]
    doc.close()
    assert "Página 3" in texts[0]
    assert "Página 1" in texts[1]
    assert "Página 2" in texts[2]


def test_compress_endpoint_returns_valid_pdf():
    data = make_pdf(2)
    response = client.post(
        "/api/compress",
        data={"level": "balanced"},
        files={"file": ("source.pdf", BytesIO(data), "application/pdf")},
    )
    assert response.status_code == 200
    assert pdf_page_count(response.content) == 2


def test_remove_pages_endpoint():
    data = make_pdf(3)
    response = client.post(
        "/api/remove-pages",
        data={"pages": "2"},
        files={"file": ("source.pdf", BytesIO(data), "application/pdf")},
    )
    assert response.status_code == 200
    assert pdf_page_count(response.content) == 2
