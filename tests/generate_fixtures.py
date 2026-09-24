from pathlib import Path
import fitz
from PIL import Image

folder=Path(__file__).resolve().parents[1]/"artifacts"/"fixtures"
folder.mkdir(parents=True,exist_ok=True)
for name,count in [("a",3),("b",2)]:
    with fitz.open() as doc:
        for number in range(1,count+1):
            page=doc.new_page(width=420,height=595)
            page.insert_text((40,60),f"{name.upper()} PAGE {number}",fontsize=16)
            page.draw_rect(fitz.Rect(40,100,180,200),color=(.1,.45,.3))
        doc.save(folder/(name+".pdf"))
Image.new("RGB",(250,350),(26,120,77)).save(folder/"image.png")
(folder/"invalid.pdf").write_text("This is not a PDF",encoding="utf-8")
(folder/"example.html").write_text("<h1>ModuPDF</h1><p>HTML conversion test</p>",encoding="utf-8")
with fitz.open(folder/"a.pdf") as doc:
    widget=fitz.Widget();widget.field_name="Name";widget.field_type=fitz.PDF_WIDGET_TYPE_TEXT
    widget.rect=fitz.Rect(40,250,300,285);widget.field_value="Initial";widget.text_fontsize=12
    doc[0].add_widget(widget);doc.save(folder/"form.pdf")
with fitz.open() as doc:
    page=doc.new_page()
    for y in (100,130,160):page.draw_line((40,y),(340,y))
    for x in (40,190,340):page.draw_line((x,100),(x,160))
    for position,text in [((50,120),"Item"),((200,120),"Value"),((50,150),"Alpha"),((200,150),"42")]:page.insert_text(position,text)
    doc.save(folder/"table.pdf")
from datetime import datetime,timedelta,timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"ModuPDF TEST ONLY")])
now=datetime.now(timezone.utc)
cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=2)).sign(key,hashes.SHA256())
(folder/"test-only.p12").write_bytes(pkcs12.serialize_key_and_certificates(b"test",key,cert,None,serialization.BestAvailableEncryption(b"test-only")))
print(folder)
