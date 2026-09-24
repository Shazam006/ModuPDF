import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import runtime


@pytest.fixture
def client(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(runtime, "WORK", work)
    with TestClient(app, raise_server_exceptions=False) as session:
        yield session
    assert not list(work.iterdir()), "Request files must be removed after responses, including errors"


@pytest.fixture
def pdf():
    with fitz.open() as doc:
        for number in range(1,4):
            page = doc.new_page(width=420, height=595)
            page.insert_text((40,60), f"PAGE {number} - ModuPDF", fontsize=14)
        return doc.tobytes()


@pytest.fixture
def table_pdf():
    with fitz.open() as doc:
        page = doc.new_page(width=420, height=595)
        for y in (100,130,160):
            page.draw_line((40,y),(340,y))
        for x in (40,190,340):
            page.draw_line((x,100),(x,160))
        for position,text in [((50,120),"Item"),((200,120),"Value"),((50,150),"Alpha"),((200,150),"42")]:
            page.insert_text(position,text)
        return doc.tobytes()
