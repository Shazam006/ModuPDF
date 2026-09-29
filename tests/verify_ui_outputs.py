import sys
import io
import json
from pathlib import Path
import fitz
from pypdf import PdfReader

folder=Path(sys.argv[1])
expected={"merge.pdf":5,"split.pdf":2,"remove.pdf":2,"organized.pdf":6,"scan.pdf":1,"comparison.pdf":3}
for name,count in expected.items():
    with fitz.open(folder/name) as doc:
        assert len(doc)==count,(name,len(doc))
with fitz.open(folder/"split.pdf") as doc:
    assert "A PAGE 3" in doc[0].get_text() and "A PAGE 1" in doc[1].get_text()
with fitz.open(folder/"organized.pdf") as doc:
    for page,item in zip(doc,json.loads((folder/"organized-order.json").read_text())):
        assert f"{item['source'][0].upper()} PAGE {item['page']}" in page.get_text()
        assert page.rotation==item["rotation"]
with fitz.open(folder/"edited.pdf") as doc:
    assert "UI ADDED TEXT" in doc[0].get_text()
with fitz.open(folder/"replaced-text.pdf") as doc:
    assert "UI REPLACED TEXT" in doc[0].get_text()
with fitz.open(folder/"redacted.pdf") as doc:
    assert "A PAGE 1" not in doc[0].get_text() and "A PAGE 2" in doc[1].get_text()
with fitz.open(folder/"unlocked.pdf") as doc:
    assert not doc.needs_pass and "A PAGE 1" in doc[0].get_text()
assert PdfReader(folder/"filled.pdf").get_fields()["Name"]["/V"]=="Pedro UI"
assert "UIField" in PdfReader(folder/"created-form.pdf").get_fields()
from pyhanko.pdf_utils.reader import PdfFileReader
with open(folder/"signed.pdf","rb") as stream:
    assert len(PdfFileReader(stream).embedded_signatures)==1
from openpyxl import load_workbook
assert load_workbook(folder/"tables.xlsx").active["A2"].value=="Alpha"
print("Downloaded PDFs reopened: page order, counts, text edits, permanent redaction, password roundtrip and canonical form values verified")
