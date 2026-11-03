"""Echte, synthetische PDF-Verbraucher ohne produktive Daten oder OCR-Dienst."""
from io import BytesIO
import ssl

import certifi
from fpdf import FPDF
from PIL import Image
from pypdf import PdfReader, PdfWriter
import pytest

from utils.pdf_kopie import _overlay_kopie
from utils.pdfa_konverter import _bild_zu_pdf


def test_pdf_copy_keeps_pages_text_and_attachment():
    pdf = FPDF()
    for text in ("Synthetische Rechnung 123", "Zweite Seite"):
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.text(15, 20, text)
    source = bytes(pdf.output())
    stamped = PdfReader(BytesIO(_overlay_kopie(source)))
    assert len(stamped.pages) == 2
    assert "Synthetische Rechnung 123" in stamped.pages[0].extract_text()
    assert "KOPIE" in stamped.pages[0].extract_text()
    assert "Zweite Seite" in stamped.pages[1].extract_text()
    writer = PdfWriter(clone_from=BytesIO(source))
    xml = b'<?xml version="1.0"?><invoice>synthetic</invoice>'
    writer.add_attachment("factur-x.xml", xml)
    output = BytesIO()
    writer.write(output)
    reader = PdfReader(BytesIO(output.getvalue()))
    assert reader.attachments["factur-x.xml"] == [xml]


@pytest.mark.parametrize("mode,fmt", [("RGB", "JPEG"), ("RGBA", "PNG"), ("P", "PNG"), ("LA", "PNG"), ("RGB", "TIFF")])
def test_actual_image_to_pdf_consumer(tmp_path, mode, fmt):
    source = tmp_path / ("synthetic." + fmt.lower())
    Image.new(mode, (96, 64)).save(source, format=fmt)
    destination = tmp_path / "converted.pdf"
    _bild_zu_pdf(source, destination)
    reader = PdfReader(destination)
    assert len(reader.pages) == 1
    assert len(reader.pages[0].images) == 1
    assert reader.pages[0].images[0].image is not None
    assert reader.pages[0].images[0].image.size == (96, 64)


def test_certifi_bundle_loads_in_ssl_context():
    context = ssl.create_default_context(cafile=certifi.where())
    assert context.cert_store_stats()["x509_ca"] > 0
    assert not any("emSign" in str(ca.get("subject", "")) for ca in context.get_ca_certs())
