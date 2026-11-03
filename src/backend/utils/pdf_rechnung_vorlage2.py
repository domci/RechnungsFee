"""Vorlage 2: helles Inter-Layout mit DC.-Monogramm und Navy/Blau/Lavendel-Akzenten.

Weißes Blatt, feine Linien statt Flächen (druckerfreundlich). Die Betrags-/Steuerlogik,
Rechtshinweise und Schluss-/Notizblöcke bleiben in RechnungPDFBase; hier werden nur
Briefkopf, Positionsraster und Zahlungsblock gestaltet.
"""
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from fpdf.enums import TextEmphasis
from utils.pdf_rechnung_base import (
    RechnungPDFBase, _fmt_euro, _iso_zu_de, _adresszeilen, _logo_abmessungen,
    _person_bezeichnung, L_MARGIN, PAGE_W, R_MARGIN, NUTZ_W, FOOTER_H,
)
from utils.pdf_rechnung import RechnungPDF
from utils.pdf_shared import build_hr_zeile, epc_qr_bytes

NAVY = (11, 22, 48)
INK = (22, 32, 54)
MUTED = (92, 104, 128)
BLUE = (41, 102, 230)          # Elektrisch-Blau, dunkel genug für Text auf Papier
BLUE_LIGHT = (101, 170, 255)   # Website-Blau, nur für Akzentlinien
LAVENDER = (178, 170, 255)
LAVENDER_INK = (104, 92, 210)
RULE = (222, 227, 238)

RIGHT = PAGE_W - R_MARGIN
SUM_X = 115                    # linke Kante von Summen- und Gesamtbetragsblock
SUM_W = RIGHT - SUM_X

_TITEL = {"Gutschrift": "Gutschrift", "Lieferschein": "Lieferschein", "Angebot": "Angebot",
          "Proforma": "Proforma-Rechnung", "Auftrag": "Auftragsbestätigung"}
_DATUM = {"Angebot": "Angebotsdatum", "Auftrag": "Auftragsdatum", "Proforma": "Proformadatum",
          "Lieferschein": "Lieferdatum", "Gutschrift": "Gutschriftdatum"}


class RechnungPDFVorlage2(RechnungPDFBase):
    _ln_nach_positionen = 5
    _ln_nach_summen = 5
    _ln_nach_19 = 3

    def __init__(self, unternehmen, rechnung, ist_kopie=False, ist_entwurf=False, ist_netto=True):
        super().__init__(unternehmen, rechnung, ist_kopie, ist_entwurf, ist_netto)
        import sys
        bundle_dir = getattr(sys, "_MEIPASS", None)
        font_dir = Path(bundle_dir) / "fonts" if bundle_dir else Path(__file__).parent.parent / "fonts"
        for style, filename in (("", "Inter-Regular.ttf"), ("B", "Inter-Bold.ttf"),
                                ("I", "Inter-Italic.ttf"), ("BI", "Inter-BoldItalic.ttf")):
            self.add_font("Inter", style=style, fname=str(font_dir / filename))

    def set_font(self, family: str | None = None, style: str | TextEmphasis = "", size: float = 0) -> None:
        # Shared legal text and totals inherit their typography without changing templates 0/1.
        super().set_font("Inter" if family == "DejaVu" else family, style, size)

    # -- Helfer -----------------------------------------------------------------

    def _dok_typ(self):
        return getattr(self._r, "dokument_typ", "Rechnung") or "Rechnung"

    def _ist_storno(self):
        return bool(getattr(self._r, "storniert", False)) and self._dok_typ() == "Rechnung"

    def _titel(self):
        if self._ist_storno():
            return "Stornorechnung"
        if self._dok_typ() in _TITEL:
            return _TITEL[self._dok_typ()]
        return "Rechnung" if self._r.typ == "ausgang" else "Eingangsrechnung"

    def _nummer(self):
        storno_nr = getattr(self._r, "storno_rechnungsnummer", None) if self._ist_storno() else None
        return storno_nr or self._r.rechnungsnummer or ""

    def _name(self):
        unt = self._unt
        return unt.get("firmenname") or " ".join(filter(None, [unt.get("vorname"), unt.get("nachname")])) or "RechnungsFee"

    def _label(self, text, x, y, w, align="L", color=MUTED):
        """Kleine Versal-Beschriftung mit leichter Sperrung."""
        self.set_xy(x, y)
        self.set_font("Inter", "B", 6.8)
        self.set_text_color(*color)
        self.set_char_spacing(0.5)
        self.cell(w, 4, text.upper(), align=align)
        self.set_char_spacing(0)

    def _monogramm(self, x, y, size):
        """DC.-Monogramm aus den Initialen (bzw. das hinterlegte Logo, falls vorhanden)."""
        logo = self._unt.get("logo_pfad") or ""
        if logo and Path(logo).exists():
            try:
                w, h = _logo_abmessungen(logo, max_h=size * 0.5, max_w=40)
                if w > 0:
                    self.image(logo, x=x, y=y, w=w, h=h)
                    return w
            except Exception:
                pass
        unt = self._unt
        quelle = " ".join(filter(None, [unt.get("vorname"), unt.get("nachname")])) or self._name()
        initialen = "".join(w[0] for w in quelle.split()[:2]).upper()
        self.set_font("Inter", "B", size)
        self.set_text_color(*NAVY)
        self.set_xy(x, y)
        w = self.get_string_width(initialen)
        self.cell(w, size * 0.4, initialen)
        self.set_text_color(*BLUE)
        self.cell(size * 0.25, size * 0.4, ".")
        return w + size * 0.25

    # -- Seitenrahmen -----------------------------------------------------------

    def header(self):
        unt = self._unt
        if self.page_no() > 1:
            self._monogramm(L_MARGIN, 13, 13)
            self.set_font("Inter", "", 8)
            self.set_text_color(*MUTED)
            self.set_xy(RIGHT - 120, 14)
            self.cell(120, 5, f"{self._titel()} {self._nummer()}  ·  Fortsetzung", align="R")
            self.set_draw_color(*RULE)
            self.set_line_width(0.2)
            self.line(L_MARGIN, 24, RIGHT, 24)
            self.set_y(32)
            return

        w = self._monogramm(L_MARGIN, 13, 24)
        x = L_MARGIN + w + 6
        self.set_draw_color(*RULE)
        self.set_line_width(0.2)
        self.line(x - 3, 14, x - 3, 24)
        self.set_xy(x, 13.6)
        self.set_font("Inter", "B", 10.5)
        self.set_text_color(*NAVY)
        self.cell(80, 5.5, self._name())
        if unt.get("berufsbezeichnung"):
            self._label(unt["berufsbezeichnung"], x, 19.8, 80, color=BLUE)

        kontakt = list(filter(None, [
            f"{unt.get('strasse') or ''} {unt.get('hausnummer') or ''}".strip(),
            f"{unt.get('plz') or ''} {unt.get('ort') or ''}".strip(),
            unt.get("email"), unt.get("webseite"), unt.get("telefon"),
        ]))
        self.set_font("Inter", "", 7.5)
        self.set_text_color(*MUTED)
        for i, zeile in enumerate(kontakt):
            self.set_xy(RIGHT - 70, 13 + i * 3.7)
            self.cell(70, 3.7, zeile, align="R")

        # Hairline mit kurzem Blau/Lavendel-Akzent – die einzige Farbfläche im Briefkopf.
        self.line(L_MARGIN, 36, RIGHT, 36)
        self.set_fill_color(*BLUE_LIGHT)
        self.rect(L_MARGIN, 35.6, 14, 0.8, style="F")
        self.set_fill_color(*LAVENDER)
        self.rect(L_MARGIN + 14, 35.6, 6, 0.8, style="F")
        self.set_y(45)

    def footer(self):
        unt = self._unt
        y = self.h - FOOTER_H
        self.set_draw_color(*RULE)
        self.set_line_width(0.2)
        self.line(L_MARGIN, y + 2, RIGHT, y + 2)

        inhaber = " ".join(filter(None, [unt.get("vorname"), unt.get("nachname")])) if unt.get("firmenname") else ""
        steuer = (f"USt-IdNr. {unt['ust_idnr']}" if unt.get("ust_idnr") else
                  f"St.-Nr. {unt['steuernummer']}" if unt.get("steuernummer") else "")
        spalten = [
            (L_MARGIN, 58, [self._name(),
                            f"{_person_bezeichnung(unt.get('rechtsform') or '')} {inhaber}".strip() if inhaber else "",
                            f"{unt.get('strasse') or ''} {unt.get('hausnummer') or ''}".strip(),
                            f"{unt.get('plz') or ''} {unt.get('ort') or ''}".strip()]),
            (L_MARGIN + 60, 56, [unt.get("email"), unt.get("webseite"), unt.get("telefon")]),
            (L_MARGIN + 118, 46, [steuer, build_hr_zeile(unt), unt.get("kammer_mitgliedschaft")]),
        ]
        for x, w, zeilen in spalten:
            for i, zeile in enumerate(filter(None, zeilen)):
                self.set_xy(x, y + 5.5 + i * 3.6)
                erste = x == L_MARGIN and i == 0
                self.set_font("Inter", "B" if erste else "", 7)
                self.set_text_color(*NAVY if erste else MUTED)
                self.cell(w, 3.6, zeile)
        self.set_xy(RIGHT - 10, y + 5.5)
        self.set_font("Inter", "B", 7)
        self.set_text_color(*LAVENDER_INK)
        self.cell(10, 3.6, f"{self.page_no():02d}", align="R")

    # -- Kopf / Titel -----------------------------------------------------------

    def _render_kopf(self):
        r, unt = self._r, self._unt
        partner = r.kunde if r.typ == "ausgang" else r.lieferant
        lines = _adresszeilen(partner)
        if not lines and getattr(r, "partner_freitext", None):
            lines = [r.partner_freitext]
            street = f"{getattr(r, 'partner_strasse', None) or ''} {getattr(r, 'partner_hausnummer', None) or ''}".strip()
            city = f"{getattr(r, 'partner_plz', None) or ''} {getattr(r, 'partner_ort', None) or ''}".strip()
            lines += list(filter(None, [street, city]))
            land = (getattr(r, "partner_land", None) or "DE").upper()
            if land != "DE":
                lines.append(land)

        # DIN-5008-Fensterzone: Absenderzeile + Empfänger ab 45 mm.
        absender = "  ·  ".join(filter(None, [
            self._name(),
            f"{unt.get('strasse') or ''} {unt.get('hausnummer') or ''}".strip(),
            f"{unt.get('plz') or ''} {unt.get('ort') or ''}".strip(),
        ]))
        self.set_xy(L_MARGIN, 46)
        self.set_font("Inter", "", 6.5)
        self.set_text_color(*MUTED)
        self.cell(88, 4, absender)
        self.set_draw_color(*RULE)
        self.line(L_MARGIN, 50.5, L_MARGIN + 88, 50.5)
        for i, line in enumerate(lines):
            self.set_xy(L_MARGIN, 54 + i * 5.4)
            self.set_font("Inter", "B" if i == 0 else "", 10.5 if i == 0 else 9.5)
            self.set_text_color(*NAVY if i == 0 else INK)
            self.cell(90, 5.4, line)

        meta_x, lbl_w, meta_y = 122, 30, 46.5
        val_w = RIGHT - meta_x - lbl_w

        def meta(label, value, dim=False):
            nonlocal meta_y
            self.set_xy(meta_x, meta_y)
            self.set_font("Inter", "", 8)
            self.set_text_color(*MUTED)
            self.cell(lbl_w, 5.8, label)
            self.set_font("Inter", "" if dim else "B", 8.5)
            self.set_text_color(*MUTED if dim else INK)
            self.cell(val_w, 5.8, str(value))
            meta_y += 5.8

        if self._ist_storno():
            if getattr(r, "storno_datum", None):
                meta("Stornodatum", _iso_zu_de(str(r.storno_datum)))
            meta("Originaldatum", _iso_zu_de(str(r.datum)), dim=True)
        else:
            meta(_DATUM.get(self._dok_typ(), "Rechnungsdatum"), _iso_zu_de(str(r.datum)))
        if r.leistung_von and r.leistung_bis:
            meta("Leistungszeitraum", f"{_iso_zu_de(str(r.leistung_von))} – {_iso_zu_de(str(r.leistung_bis))}")
        elif r.leistung_von and str(r.leistung_von) != str(r.datum):
            meta("Leistungsdatum", _iso_zu_de(str(r.leistung_von)))
        partner_no = getattr(partner, "kundennummer", None) or getattr(partner, "lieferantennummer", None)
        if partner_no:
            meta("Kundennr." if r.typ == "ausgang" else "Lieferantennr.", partner_no)
        if getattr(r, "kunden_bestellnummer", None):
            meta("Bestellnummer", r.kunden_bestellnummer)
        if self._dok_typ() == "Angebot":
            if getattr(r, "gueltig_bis", None):
                meta("Gültig bis", _iso_zu_de(str(r.gueltig_bis)))
        elif r.faellig_am:
            meta("Fällig bis", _iso_zu_de(str(r.faellig_am)))
        delivery = getattr(r, "_lieferadresse", None)
        if delivery:
            meta(delivery.bezeichnung or "Lieferadresse", ", ".join(filter(None, [
                f"{delivery.strasse or ''} {delivery.hausnummer or ''}".strip(),
                f"{delivery.plz or ''} {delivery.ort or ''}".strip(),
            ])))
        for label, val in (("Angebot", getattr(r, "_quell_angebot_nr", None)),
                           ("Auftrag", getattr(r, "_quell_auftrag_nr", None))):
            if val:
                meta(label, val, dim=True)
        # Titel beginnt frühestens unterhalb der Fensterzone.
        return max(54 + len(lines) * 5.4, 74), meta_y

    def _render_titel(self):
        r = self._r
        y = self.get_y()
        self.set_x(L_MARGIN)
        self.set_font("Inter", "B", 26)
        self.set_text_color(*NAVY)
        self.cell(130, 12, self._titel(), new_x="LMARGIN", new_y="NEXT")
        self.set_font("Inter", "B", 11)
        self.set_text_color(*BLUE)
        self.cell(130, 6.5, self._nummer(), new_x="LMARGIN", new_y="NEXT")

        if self._ist_entwurf or self._ist_kopie:
            text = "ENTWURF" if self._ist_entwurf else "KOPIE"
            self.set_font("Inter", "B", 7)
            self.set_char_spacing(0.8)
            w = self.get_string_width(text) + 7
            self.set_draw_color(*LAVENDER_INK)
            self.set_line_width(0.3)
            self.set_text_color(*LAVENDER_INK)
            self.set_xy(RIGHT - w, y + 3.5)
            self.cell(w, 6, text, border=1, align="C")
            self.set_char_spacing(0)
            self.set_line_width(0.2)
            self.set_xy(L_MARGIN, y + 18.5)

        self.set_font("Inter", "", 8.5)
        self.set_text_color(*MUTED)
        if self._ist_storno():
            self.ln(1)
            self.cell(0, 5, f"Stornierung zu Rechnung {r.rechnungsnummer or '–'} vom {_iso_zu_de(str(r.datum))}",
                      new_x="LMARGIN", new_y="NEXT")
            if getattr(r, "storno_grund", None):
                self.multi_cell(0, 5, f"Stornobegründung: {r.storno_grund}", new_x="LMARGIN", new_y="NEXT")
        elif self._dok_typ() == "Gutschrift" and getattr(r, "_gutschrift_original_nr", None):
            self.ln(1)
            self.cell(0, 5, f"Gutschrift zu Rechnung {r._gutschrift_original_nr}", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def _render_nach_titel(self):
        super()._render_nach_titel()
        self.ln(2)

    # -- Positionen -------------------------------------------------------------

    def _table_header(self, widths, headers):
        y = self.get_y()
        self.set_font("Inter", "B", 7.5)
        self.set_text_color(*MUTED)
        self.set_x(L_MARGIN)
        for i, (width, label) in enumerate(zip(widths, headers)):
            self.cell(width, 7, label, align="L" if i in (0, 1) else "R")
        self.set_draw_color(*NAVY)
        self.set_line_width(0.35)
        self.line(L_MARGIN, y + 7.5, RIGHT, y + 7.5)
        self.set_line_width(0.2)
        self.set_y(y + 7.5)

    def _render_positionen(self):
        r = self._r
        lieferschein = self._dok_typ() == "Lieferschein"
        # Pos., Leistung, Menge (inkl. Einheit), Einzelpreis, USt, Betrag
        widths = [10, 81, 24, 25, 12, 23]
        headers = ["Pos.", "Leistung", "Menge", "Einzelpreis", "USt", "Netto" if self._ist_netto else "Brutto"]
        if lieferschein:
            widths = [10, 135, 30]
            headers = headers[:3]
        desc_w = widths[1] - 4
        self._table_header(widths, headers)
        sign = Decimal("-1") if getattr(r, "storniert", False) and not lieferschein else Decimal("1")

        def row_content(pos):
            code = getattr(getattr(pos, "artikel", None), "artikelcode", None)
            description = f"{code}  ·  {pos.beschreibung}" if code else (pos.beschreibung or "")
            self.set_font("Inter", "", 9.5)
            lines = self.multi_cell(desc_w, 5, description, align="L", dry_run=True, output="LINES")
            rabatt = getattr(pos, "rabatt_prozent", None) or Decimal("0")
            height = max(11, len(lines) * 5 + 6) + (4.5 if rabatt and not lieferschein else 0)
            return description, rabatt, height

        for index, pos in enumerate(r.positionen):
            description, rabatt, height = row_content(pos)
            # Keep the final rows and totals/payment together rather than an orphan totals page.
            if not lieferschein and index > 0 and index == len(r.positionen) - 2:
                next_height = row_content(r.positionen[index + 1])[2]
                if self.will_page_break(height + next_height + 78):
                    self.add_page()
                    self._table_header(widths, headers)
            if self.will_page_break(height + 1):
                self.add_page()
                self._table_header(widths, headers)
            y = self.get_y()
            self.set_xy(L_MARGIN, y + 3)
            self.set_font("Inter", "B", 8)
            self.set_text_color(*LAVENDER_INK)
            self.cell(widths[0], 5, f"{getattr(pos, 'position_nr', None) or index + 1:02d}")
            self.set_xy(L_MARGIN + widths[0], y + 3)
            self.set_font("Inter", "", 9.5)
            self.set_text_color(*INK)
            self.multi_cell(desc_w, 5, description, align="L")
            self.set_xy(L_MARGIN + widths[0] + widths[1], y + 3)
            menge = Decimal(str(pos.menge)) * sign
            menge_text = format(menge, "f")
            if "." in menge_text:
                menge_text = menge_text.rstrip("0").rstrip(".")
            menge_text = f"{menge_text.replace('.', ',')} {(pos.einheit or '')[:14]}".strip()
            self.cell(widths[2], 5, menge_text, align="R")
            if not lieferschein:
                price = Decimal(str(pos.netto))
                total = (Decimal(str(pos.brutto)) - Decimal(str(pos.ust_betrag))) if self._ist_netto else Decimal(str(pos.brutto))
                total *= sign
                tax = "§25a" if getattr(pos, "differenzbesteuerung", False) else f"{int(pos.ust_satz)} %"
                self.set_text_color(*MUTED)
                self.cell(widths[3], 5, _fmt_euro(price), align="R")
                self.cell(widths[4], 5, tax, align="R")
                self.set_font("Inter", "B", 9.5)
                self.set_text_color(*NAVY)
                self.cell(widths[5], 5, _fmt_euro(total), align="R")
                if rabatt:
                    self.set_xy(L_MARGIN + widths[0], y + height - 7)
                    self.set_font("Inter", "", 7.5)
                    self.set_text_color(*MUTED)
                    self.cell(100, 4, f"Positionsrabatt {rabatt:.4g} % (im Betrag enthalten)")
            self.set_draw_color(*RULE)
            self.line(L_MARGIN, y + height, RIGHT, y + height)
            self.set_y(y + height)
        self._sum_x = SUM_X
        self._sum_lbl_w = SUM_W - 30
        self._sum_val_w = 30

    # -- Summen / Zahlung -------------------------------------------------------

    def _render_zahlungsblock(self):
        r, unt = self._r, self._unt
        if getattr(r, "zahlungsstatus", "offen") in ("bezahlt", "teilweise") and getattr(r, "journaleintraege", None):
            RechnungPDF._render_zahlungsblock(self)
            return
        if self._dok_typ() == "Gutschrift":
            RechnungPDF._render_zahlungsblock(self)
            return
        iban = unt.get("iban") or ""
        if not (unt.get("zahlungshinweis_aktiv", True) and iban and r.typ == "ausgang"):
            return
        qr = None
        if unt.get("qr_zahlung_aktiv"):
            qr = epc_qr_bytes(iban, unt.get("bic") or "", self._name(), float(r.brutto_gesamt), r.rechnungsnummer or "")
        height = 30
        if self.will_page_break(height + 3):
            self.add_page()
        x, y = L_MARGIN, self.get_y() + 1
        self.set_draw_color(*RULE)
        self.set_line_width(0.25)
        self.rect(x, y, NUTZ_W, height)
        self.set_line_width(0.2)

        self._label("Zahlung  ·  IBAN", x + 6, y + 5, 70, color=BLUE)
        self.set_xy(x + 6, y + 10)
        self.set_font("Inter", "B", 10.5)
        self.set_text_color(*NAVY)
        self.cell(80, 6, iban)
        self.set_xy(x + 6, y + 17)
        self.set_font("Inter", "", 8.5)
        self.set_text_color(*MUTED)
        self.cell(80, 5, "  ·  ".join(filter(None, [unt.get("bank_name"), f"BIC {unt['bic']}" if unt.get("bic") else ""])))

        col = x + 92
        due = _iso_zu_de(str(r.faellig_am)) if r.faellig_am else "sofort"
        for i, (label, value) in enumerate((("Fällig", due), ("Verwendungszweck", r.rechnungsnummer or "—"))):
            self._label(label, col, y + 5 + i * 11, 50)
            self.set_xy(col, y + 9.5 + i * 11)
            self.set_font("Inter", "B", 9)
            self.set_text_color(*INK)
            self.cell(50, 5, value)
        if qr:
            self.image(BytesIO(qr), x=x + NUTZ_W - 26, y=y + 3.5, w=23, h=23)
        self.set_xy(L_MARGIN, y + height + 2)
        if getattr(r, "skonto_prozent", None) and getattr(r, "skonto_tage", None):
            skonto = (r.brutto_gesamt * Decimal(str(r.skonto_prozent)) / 100).quantize(Decimal("0.01"))
            self.set_font("Inter", "", 8)
            self.set_text_color(*MUTED)
            self.cell(0, 5, f"{r.skonto_prozent:.0f} % Skonto bis {_iso_zu_de(str(r.datum + timedelta(days=int(r.skonto_tage))))}: {_fmt_euro(r.brutto_gesamt - skonto)}", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)


def generate_rechnung_pdf_vorlage2(rechnung, unternehmen: dict, ist_kopie=False,
                                    ist_entwurf=False, ist_netto=True,
                                    mit_output_intent=False) -> bytes:
    pdf = RechnungPDFVorlage2(unternehmen, rechnung, ist_kopie, ist_entwurf, ist_netto)
    if mit_output_intent:
        from fpdf.enums import OutputIntentSubType
        from fpdf.output import PDFICCProfile
        from fpdf.util import builtin_srgb2014_bytes
        pdf.add_output_intent(
            OutputIntentSubType.PDFA,
            output_condition_identifier="sRGB", output_condition="IEC 61966-2-1:1999",
            registry_name="http://www.color.org",
            dest_output_profile=PDFICCProfile(contents=builtin_srgb2014_bytes(), n=3, alternate="DeviceRGB"),
            info="sRGB2014 (v2)",
        )
    return pdf.render()
