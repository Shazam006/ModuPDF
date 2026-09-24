import io
import json
import os
from pathlib import Path
import time
import zipfile

import fitz
import pytest
from PIL import Image
from pypdf import PdfReader
from backend import runtime


def upload(pdf, key="file"):
    return {key: ("document.pdf", pdf, "application/pdf")}


def post(client, endpoint, pdf, **fields):
    return client.post("/api/"+endpoint, files=upload(pdf), data=fields)


def reopen(response):
    assert response.status_code == 200, response.text[:1000] if response.status_code != 200 else ""
    return fitz.open(stream=response.content, filetype="pdf")


@pytest.mark.parametrize("endpoint,fields,expected", [
    ("split", {"pages":"3,1"}, [3,1]), ("remove-pages", {"pages":"2"}, [1,3]),
    ("repair", {}, [1,2,3]), ("rotate", {"degrees":90}, [1,2,3]),
    ("organize", {"order":"3,1,2","rotations":"3:90"}, [3,1,2]),
])
def test_page_operations(client, pdf, endpoint, fields, expected):
    with reopen(post(client,endpoint,pdf,**fields)) as doc:
        assert [int(page.get_text().split()[1]) for page in doc] == expected
        if endpoint == "rotate":
            assert all(page.rotation == 90 for page in doc)


def test_merge_content_order(client,pdf):
    response=client.post("/api/merge",files=[("files",("a.pdf",pdf,"application/pdf")),("files",("b.pdf",pdf,"application/pdf"))])
    with reopen(response) as doc:
        assert [page.get_text().split()[1] for page in doc] == ["1","2","3","1","2","3"]


def test_duplicate_rotations_are_independent(client,pdf):
    order=[{"fileIndex":0,"page":1,"rotation":90},{"fileIndex":0,"page":1,"rotation":180},{"fileIndex":1,"page":3,"rotation":0}]
    response=client.post("/api/organize-multi",files=[("files",("a.pdf",pdf,"application/pdf")),("files",("b.pdf",pdf,"application/pdf"))],data={"order":json.dumps(order)})
    with reopen(response) as doc:
        assert [page.rotation for page in doc] == [90,180,0]
        assert [page.get_text().split()[1] for page in doc] == ["1","1","3"]


@pytest.mark.parametrize("pages",["", "0", "4", "abc", "1-100000000", "1,,2", "1-2-3", "-1"])
def test_invalid_ranges_return_400(client,pdf,pages):
    assert post(client,"split",pdf,pages=pages).status_code in {400,422}


@pytest.mark.parametrize("endpoint,fields",[("remove-pages",{"pages":"1-3"}),("rotate",{"degrees":45}),("crop",{"margin":220}),("crop",{"margin":-1})])
def test_invalid_operations(client,pdf,endpoint,fields):
    assert post(client,endpoint,pdf,**fields).status_code in {400,422}


@pytest.mark.parametrize("filename,content,mime",[("fake.pdf",b"not a pdf","application/pdf"),("fake.pdf",b"%PDF-broken","application/pdf"),("x.txt",b"%PDF-1.7","application/pdf"),("x.pdf",b"","application/pdf"),("x.pdf",b"%PDF-1.7","image/png")])
def test_invalid_uploads(client,filename,content,mime):
    response=client.post("/api/repair",files={"file":(filename,content,mime)})
    assert response.status_code == 400
    assert "detail" in response.json()


def test_size_limit(client,pdf,monkeypatch):
    monkeypatch.setattr(runtime,"MAX_UPLOAD_BYTES",100)
    assert post(client,"repair",pdf).status_code == 413
    assert client.post("/api/repair",content=b"x",headers={"content-length":str(2*1024**2)}).status_code == 413


def test_chunked_size_limit(client,monkeypatch):
    monkeypatch.setattr(runtime,"MAX_UPLOAD_BYTES",100)
    def chunks():
        yield b"--a\r\nContent-Disposition: form-data; name=\"file\"; filename=\"x.pdf\"\r\nContent-Type: application/pdf\r\n\r\n"
        yield b"%PDF-"+b"x"*(2*1024**2)
        yield b"\r\n--a--\r\n"
    response=client.post("/api/repair",content=chunks(),headers={"content-type":"multipart/form-data; boundary=a"})
    assert response.status_code == 413


def test_page_limit(client,monkeypatch,pdf):
    monkeypatch.setattr(runtime,"MAX_PAGES",2)
    assert post(client,"repair",pdf).status_code == 400


def test_split_individual(client,pdf):
    response=post(client,"split",pdf,pages="1,3",mode="individual")
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist())==2
        for name in archive.namelist():
            with fitz.open(stream=archive.read(name),filetype="pdf") as doc:
                assert len(doc)==1


def test_watermark_and_numbers(client,pdf):
    with reopen(post(client,"watermark",pdf,text="CONFIDENTIAL")) as doc:
        assert all("CONFIDENTIAL" in page.get_text() for page in doc)
    with reopen(post(client,"add-page-numbers",pdf,start=7)) as doc:
        assert all(str(index+7) in page.get_text().splitlines() for index,page in enumerate(doc))


def test_crop_geometry(client,pdf):
    with reopen(post(client,"crop",pdf,margin=20)) as doc:
        assert doc[0].rect.width==380 and doc[0].rect.height==555


def test_protect_unlock(client,pdf):
    encrypted=post(client,"protect",pdf,password="test-secret")
    with reopen(encrypted) as doc:
        assert doc.needs_pass
    assert post(client,"unlock",encrypted.content,password="wrong").status_code==400
    with reopen(post(client,"unlock",encrypted.content,password="test-secret")) as doc:
        assert not doc.needs_pass and "PAGE 1" in doc[0].get_text()


@pytest.mark.parametrize("level",["lossless","balanced","maximum"])
def test_compression_preserves_text_and_never_grows(client,pdf,level):
    response=post(client,"compress",pdf,level=level,target_mb=.00001)
    with reopen(response) as doc:
        assert all(f"PAGE {index+1}" in page.get_text() for index,page in enumerate(doc))
    assert len(response.content)<=len(pdf)
    assert response.headers["x-target-met"]=="false"
    assert int(response.headers["x-final-bytes"])==len(response.content)


def test_image_compression(client):
    image=Image.effect_noise((1800,1800),50).convert("RGB")
    stream=io.BytesIO();image.save(stream,"PNG")
    with fitz.open() as doc:
        page=doc.new_page();page.insert_image(page.rect,stream=stream.getvalue());page.insert_text((40,60),"SEARCHABLE TEXT")
        content=doc.tobytes()
    response=post(client,"compress",content,level="maximum",target_mb=1)
    with reopen(response) as doc:
        assert "SEARCHABLE TEXT" in doc[0].get_text()
    assert len(response.content)<len(content)*.7
    assert response.headers["x-target-met"]=="true"


def test_images_and_scan(client):
    stream=io.BytesIO();Image.new("RGB",(200,300),"red").save(stream,"PNG")
    files=[("files",("a.png",stream.getvalue(),"image/png")),("files",("b.png",stream.getvalue(),"image/png"))]
    for endpoint in ("images-to-pdf","scan-to-pdf"):
        with reopen(client.post("/api/"+endpoint,files=files)) as doc:
            assert len(doc)==2


@pytest.mark.parametrize("fmt",["jpg","png"])
def test_pdf_images(client,pdf,fmt):
    response=post(client,"pdf-to-images",pdf,fmt=fmt,dpi=72)
    assert response.status_code==200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist())==3
        with Image.open(io.BytesIO(archive.read(archive.namelist()[0]))) as image:
            assert image.width==420 and image.height==595


def test_no_silent_ocr_fallback(client,monkeypatch):
    monkeypatch.setattr(runtime,"tool_path",lambda names:None)
    stream=io.BytesIO();Image.new("RGB",(100,100),"white").save(stream,"PNG")
    response=client.post("/api/scan-to-pdf",files={"files":("a.png",stream.getvalue(),"image/png")},data={"run_ocr":"true"})
    assert response.status_code==503


def test_edit_and_redact_content(client,pdf):
    operations=[{"type":"text","page":1,"x":.1,"y":.3,"w":.8,"h":.2,"text":"ADDED TEXT"}]
    with reopen(post(client,"edit",pdf,operations=json.dumps(operations))) as doc:
        assert "ADDED TEXT" in doc[0].get_text() and "PAGE 1" in doc[0].get_text()
    operations=[{"type":"redact","page":1,"x":.05,"y":.04,"w":.9,"h":.12}]
    response=post(client,"redact",pdf,operations=json.dumps(operations))
    with reopen(response) as doc:
        assert "PAGE 1" not in doc[0].get_text() and "PAGE 2" in doc[1].get_text()
    assert b"PAGE 1" not in response.content


def test_redact_rotated_page(client,pdf):
    with fitz.open(stream=pdf,filetype="pdf") as doc:
        doc[0].set_rotation(90);rotated=doc.tobytes()
    ops=[{"type":"redact","page":1,"x":.85,"y":0,"w":.14,"h":.99}]
    with reopen(post(client,"redact",rotated,operations=json.dumps(ops))) as doc:
        assert "PAGE 1" not in doc[0].get_text()


def test_form_fields_and_values(client,pdf):
    fields=[{"name":"Name","page":1,"x":.1,"y":.3,"w":.7,"h":.08,"value":"Initial"}]
    created=post(client,"forms",pdf,fields=json.dumps(fields))
    assert created.status_code==200
    reader=PdfReader(io.BytesIO(created.content));assert reader.get_fields()["Name"]["/V"]=="Initial"
    filled=post(client,"forms",created.content,values=json.dumps({"Name":"Pedro"}))
    assert filled.status_code==200
    reader=PdfReader(io.BytesIO(filled.content));assert reader.get_fields()["Name"]["/V"]=="Pedro"
    with reopen(filled) as doc:
        widget=next(doc[0].widgets());assert widget.field_value=="Pedro"
    inspected=post(client,"forms/inspect",filled.content).json()
    assert inspected["fields"][0]["value"]=="Pedro"


def test_visual_validation(client,pdf):
    for operations in ([],[{"type":"redact","page":20,"x":.1,"y":.1,"w":.2,"h":.2}], [{"type":"text","page":1,"x":.9,"y":.1,"w":.4,"h":.2}]):
        assert post(client,"redact",pdf,operations=json.dumps(operations)).status_code==400


def test_compare(client,pdf):
    response=client.post("/api/compare",files={"file1":("a.pdf",pdf,"application/pdf"),"file2":("b.pdf",pdf,"application/pdf")})
    with reopen(response) as doc:
        assert len(doc)==3
        assert "Sem diferencas" in doc[0].get_text()
    assert response.headers["x-changed-pages"]=="0"
    with fitz.open(stream=pdf,filetype="pdf") as doc:
        doc[0].insert_text((40,140),"DIFFERENT");changed=doc.tobytes()
    response=client.post("/api/compare",files={"file1":("a.pdf",pdf,"application/pdf"),"file2":("b.pdf",changed,"application/pdf")})
    assert response.headers["x-changed-pages"]=="1"


def test_html_conversion(client):
    html=b'<html><body><h1>MODUPDF HTML</h1><p>Static content</p><script>alert(1)</script><img src="http://127.0.0.1/private"></body></html>'
    with reopen(client.post("/api/html-to-pdf",files={"file":("a.html",html,"text/html")})) as doc:
        assert "MODUPDF HTML" in doc[0].get_text() and "alert(1)" not in doc[0].get_text()


def test_office_output_containers(client,pdf,table_pdf):
    for target,content,expected in [("docx",pdf,"word/document.xml"),("xlsx",table_pdf,"xl/workbook.xml"),("pptx",pdf,"ppt/presentation.xml")]:
        response=post(client,"pdf-to-office",content,target=target)
        assert response.status_code==200,response.text[:1000] if response.status_code!=200 else ""
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert expected in archive.namelist()
            if target=="docx":assert b"PAGE 1" in archive.read(expected)
    assert post(client,"pdf-to-office",pdf,target="xlsx").status_code==400


@pytest.mark.parametrize("certificate_mime", ["application/x-pkcs12", "application/pkcs12"])
@pytest.mark.parametrize("certificate_extension", ["p12", "pfx"])
def test_signature_is_cryptographically_valid(client,pdf,certificate_mime,certificate_extension):
    from datetime import datetime,timedelta,timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext
    from asn1crypto import x509 as asn1x509
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"MODUPDF TEST")])
    now=datetime.now(timezone.utc)
    cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=2)).add_extension(x509.KeyUsage(True,True,False,False,False,False,False,False,False),critical=True).sign(key,hashes.SHA256())
    bundle=pkcs12.serialize_key_and_certificates(b"test",key,cert,None,serialization.BestAvailableEncryption(b"secret"))
    response=client.post("/api/sign",files={**upload(pdf),"certificate":("test."+certificate_extension,bundle,certificate_mime)},data={"password":"secret"})
    assert response.status_code==200,response.text[:1000] if response.status_code!=200 else ""
    reader=PdfFileReader(io.BytesIO(response.content));assert len(reader.embedded_signatures)==1
    context=ValidationContext(trust_roots=[asn1x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))],allow_fetching=False)
    result=validate_pdf_signature(reader.embedded_signatures[0],signer_validation_context=context)
    assert result.intact and result.valid


def test_cors_restricts_origins(client):
    response=client.options("/api/merge",headers={"origin":"https://shazam006.github.io","access-control-request-method":"POST"})
    assert response.headers["access-control-allow-origin"]=="https://shazam006.github.io"
    response=client.options("/api/merge",headers={"origin":"https://unknown.invalid","access-control-request-method":"POST"})
    assert response.status_code==400 and "access-control-allow-origin" not in response.headers


def test_cleanup_does_not_delete_active_jobs(client):
    directory=runtime.WORK/"stale";directory.mkdir();(directory/"input.pdf").write_bytes(b"test")
    os.utime(directory,(0,0));runtime.active_jobs.add(str(directory))
    assert client.post("/api/system/cleanup").json()["removed"]==0
    assert directory.exists()
    runtime.active_jobs.discard(str(directory))
    assert client.post("/api/system/cleanup").json()["removed"]==1
