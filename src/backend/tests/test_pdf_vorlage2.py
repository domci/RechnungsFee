"""Brand-Vorlage: Vorschau, Steuer-/Zahlungsangaben und A4-Umbruch."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pymupdf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.pdf_vorlagen import _demo_rechnung, _unt_dict, demo_pdf
from api.rechnungen import rechnung_als_pdf, rechnung_als_zugferd
from api.mail import _pdf_bytes_fuer
from database.connection import Base
from database.models import Unternehmen, Rechnung, Rechnungsposition
from utils.pdf_rechnung_vorlage2 import generate_rechnung_pdf_vorlage2
from utils.zugferd import generate_zugferd_pdf


def _text(pdf):
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    return doc, "\n".join(page.get_text() for page in doc)


def test_template_registered_and_demo_is_inline():
    class DB:
        class Query:
            def first(self):
                return None
        def query(self, _):
            return self.Query()
    response = demo_pdf(vorlage=2, db=DB())
    assert response.headers["content-disposition"].startswith("inline;")
    doc, text = _text(response.body)
    assert len(doc) == 1
    assert "RE-2024-0042" in text
    assert "1.280,00 €" in text
    assert "3 Std" in text and "60,00 €" in text and "180,00 €" in text
    assert "§ 19 UStG" in text
    assert "IBAN" in text
    assert round(doc[0].rect.width) == 595 and round(doc[0].rect.height) == 842
    fonts = {font[3] for font in doc[0].get_fonts(full=True)}
    assert any("Inter" in font for font in fonts)


def test_taxed_gross_invoice_and_draft_watermark():
    unt = _unt_dict(None) | {"ist_kleinunternehmer": False, "qr_zahlung_aktiv": False}
    r = _demo_rechnung(unt)
    pdf = generate_rechnung_pdf_vorlage2(r, unt, ist_entwurf=True, ist_netto=False)
    doc, text = _text(pdf)
    assert len(doc) == 1
    for value in ("ENTWURF", "19 %", "952,00 €", "1.523,20 €", "243,20 €"):
        assert value in text
    assert "§ 19 UStG" not in text


def test_long_descriptions_break_across_pages_without_clipping():
    unt = _unt_dict(None) | {"qr_zahlung_aktiv": False}
    r = _demo_rechnung(unt)
    r.positionen = [SimpleNamespace(
        position_nr=i, beschreibung=f"Leistung {i:02d}: " + "Technische Beratung und Implementierung " * 4,
        menge=Decimal("1"), einheit="Std", netto=Decimal("100"),
        ust_satz=Decimal("0"), ust_betrag=Decimal("0"), brutto=Decimal("100"),
        rabatt_prozent=Decimal("0"),
    ) for i in range(1, 31)]
    r.netto_gesamt = r.brutto_gesamt = Decimal("3000")
    r.ust_gesamt = Decimal("0")
    doc, text = _text(generate_rechnung_pdf_vorlage2(r, unt))
    assert len(doc) > 1
    for i in range(1, 31):
        assert text.count(f"Leistung {i:02d}:") == 1
    assert text.count("Leistung\n") >= len(doc) - 1  # last page may hold only totals/payment
    assert "3.000,00 €" in text
    for page in doc:
        assert f"{page.number + 1:02d}" in page.get_text()
        for block in page.get_text("blocks"):
            if block[6] == 0:  # text, not QR image
                assert block[0] >= 0 and block[2] <= page.rect.width + 1
                assert block[1] >= 0 and block[3] <= page.rect.height + 1


def test_storno_does_not_show_payment_request():
    unt = _unt_dict(None)
    r = _demo_rechnung(unt)
    r.storniert = True
    r.storno_rechnungsnummer = "ST-2026-01"
    r.storno_datum = date(2026, 5, 1)
    doc, text = _text(generate_rechnung_pdf_vorlage2(r, unt))
    assert "Stornorechnung\nST-2026-01" in text
    assert "-1.280,00 €" in text
    assert "ZAHLUNG" not in text


@pytest.mark.parametrize("surface", ["preview", "mail"])
def test_selected_draft_preview_does_not_issue_or_modify_invoice(surface):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Unternehmen(firmenname="Synthetic Design GmbH", strasse="Teststraße", hausnummer="1", plz="20095", ort="Teststadt", pdf_vorlage=2))
    r = Rechnung(typ="ausgang", dokument_typ="Rechnung", ist_entwurf=True,
                rechnungsnummer="RE-260001", datum=date(2026, 9, 27),
                partner_freitext="Synthetic Customer GmbH", netto_gesamt=Decimal("100"),
                ust_gesamt=Decimal("19"), brutto_gesamt=Decimal("119"))
    db.add(r)
    db.flush()
    db.add(Rechnungsposition(rechnung_id=r.id, position_nr=1, beschreibung="AI-Beratung",
                            menge=Decimal("1"), einheit="Std", netto=Decimal("100"),
                            ust_satz=Decimal("19"), ust_betrag=Decimal("19"), brutto=Decimal("119")))
    db.commit()
    if surface == "preview":
        response = rechnung_als_pdf(r.id, nur_ansehen=True, db=db)
        assert response.headers["content-disposition"].startswith("inline;")
        pdf_bytes = response.body
    else:
        pdf_bytes, _ = _pdf_bytes_fuer(r.id, db)
    doc, text = _text(pdf_bytes)
    assert any("Inter" in font[3] for font in doc[0].get_fonts(full=True))
    db.refresh(r)
    assert "Synthetic Design GmbH" in text and "Synthetic Customer GmbH" in text
    assert "AI-Beratung" in text and "ENTWURF" in text
    assert "RE-260001" in text and "119,00 €" in text
    assert r.ist_entwurf and not r.ausgegeben and not r.original_pdf_pfad
    db.close()


@pytest.mark.parametrize("surface", ["generator", "download", "preview", "mail", "fallback-preview", "fallback-mail"])
def test_final_invoice_zugferd_preserves_selected_visual_template(surface, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Unternehmen(firmenname="Synthetic Design GmbH", strasse="Testweg", hausnummer="1",
                       plz="12345", ort="Teststadt", steuernummer="12/345/67890", pdf_vorlage=2))
    r = Rechnung(typ="ausgang", dokument_typ="Rechnung", ist_entwurf=False,
                rechnungsnummer="RE-TEST-1", datum=date(2026, 9, 27),
                netto_gesamt=Decimal("100"), ust_gesamt=Decimal("19"),
                brutto_gesamt=Decimal("119"))
    db.add(r)
    db.flush()
    db.add(Rechnungsposition(rechnung_id=r.id, position_nr=1, beschreibung="Beratung",
                            menge=Decimal("1.000"), einheit="Std", netto=Decimal("100"),
                            ust_satz=Decimal("19"), ust_betrag=Decimal("19"), brutto=Decimal("119")))
    db.commit()
    unt = _unt_dict(None) | {"ist_kleinunternehmer": False, "pdf_vorlage": 2}
    if surface.startswith("fallback"):
        def unavailable(*args, **kwargs):
            raise RuntimeError("Synthetic ZUGFeRD failure")
        target = "api.mail" if surface.endswith("mail") else "api.rechnungen"
        monkeypatch.setattr(target + ".generate_zugferd_pdf", unavailable)
    if surface == "generator":
        pdf = generate_zugferd_pdf(r, unt)
    elif surface == "download":
        pdf = rechnung_als_zugferd(r.id, db=db).body
    elif surface.endswith("mail"):
        pdf, _ = _pdf_bytes_fuer(r.id, db)
    else:
        pdf = rechnung_als_pdf(r.id, nur_ansehen=True, db=db).body
    doc, text = _text(pdf)
    assert "RE-TEST-1" in text and "119,00 €" in text
    assert "1 Std" in text and "1.000 Std" not in text
    if not surface.startswith("fallback"):
        assert "xrechnung.xml" in doc.embfile_names()
        assert b"RE-TEST-1" in doc.embfile_get("xrechnung.xml")
    else:
        assert doc.embfile_names() == []
    assert any("Inter" in font[3] for font in doc[0].get_fonts(full=True))
    db.close()
