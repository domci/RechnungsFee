"""0 Tage bedeutet Fälligkeit am Rechnungsdatum, nicht 14 Tage/kein Datum."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.rechnungen import (
    create_rechnung, ersatzrechnung_erstellen, rechnung_aus_angebot,
    auftrag_aus_angebot, rechnung_aus_auftrag, proforma_aus_angebot,
)
from api.schemas_rechnungen import RechnungCreate, RechnungspositionCreate
from api.wiederkehrend import _erstelle_entwurf
from database.connection import Base
from database.models import Rechnung, Rechnungsvorlage, Unternehmen

DATUM = date(2026, 9, 28)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(Unternehmen(
        firmenname="Testfirma GmbH", strasse="Testweg", hausnummer="1",
        plz="12345", ort="Teststadt", steuernummer="12/345/67890",
        standard_zahlungsziel=0,
    ))
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _anlegen(db, dokument_typ="Rechnung", **kwargs):
    daten = dict(
        typ="ausgang", dokument_typ=dokument_typ, datum=DATUM, ist_entwurf=True,
        partner_freitext="Kunde GmbH",
        positionen=[RechnungspositionCreate(
            beschreibung="Beratung", menge=Decimal("1"), netto=Decimal("100"),
            ust_satz=Decimal("0"),
        )],
    )
    daten.update(kwargs)
    return create_rechnung(RechnungCreate(**daten), db)


@pytest.mark.parametrize("standard,tage", [(None, 14), (0, 0), (14, 14)])
def test_neue_ausgangsrechnung_ohne_faelligkeit_uebernimmt_standard(db, standard, tage):
    if standard is None:
        db.query(Unternehmen).delete()
    else:
        db.query(Unternehmen).first().standard_zahlungsziel = standard
    rechnung = _anlegen(db)
    assert rechnung.faellig_am == DATUM + timedelta(days=tage)
    assert rechnung.ist_entwurf and not rechnung.ausgegeben


def test_explizite_faelligkeit_hat_vorrang_und_eingang_bleibt_unveraendert(db):
    explizit = DATUM + timedelta(days=3)
    ausgang = _anlegen(db, faellig_am=explizit)
    eingang = _anlegen(db, typ="eingang", faellig_am=None)
    assert ausgang.faellig_am == explizit
    assert eingang.faellig_am is None


@pytest.mark.parametrize("standard,tage", [(0, 0), (14, 14)])
def test_ersatzrechnung_uebernimmt_standard(db, standard, tage):
    db.query(Unternehmen).first().standard_zahlungsziel = standard
    original = _anlegen(db)
    db.query(Rechnung).filter_by(id=original.id).first().storniert = True
    db.commit()
    ersatz = ersatzrechnung_erstellen(original.id, db)
    assert ersatz.faellig_am == ersatz.datum + timedelta(days=tage)
    assert ersatz.ist_entwurf and not ersatz.ausgegeben


@pytest.mark.parametrize("standard,tage", [(0, 0), (14, 14)])
def test_angebot_auftrag_und_proforma_uebernehmen_standard(db, standard, tage):
    db.query(Unternehmen).first().standard_zahlungsziel = standard
    angebot = _anlegen(db, "Angebot")
    aus_angebot = rechnung_aus_angebot(angebot.id, db)
    assert aus_angebot.faellig_am == aus_angebot.datum + timedelta(days=tage)
    auftrag_angebot = _anlegen(db, "Angebot")
    auftrag = auftrag_aus_angebot(auftrag_angebot.id, db)
    aus_auftrag = rechnung_aus_auftrag(auftrag.id, db)
    assert aus_auftrag.faellig_am == aus_auftrag.datum + timedelta(days=tage)
    proforma = _anlegen(db, "Proforma")
    assert proforma.faellig_am == DATUM + timedelta(days=tage)
    proforma_angebot = _anlegen(db, "Angebot")
    konvertiert = proforma_aus_angebot(proforma_angebot.id, db)
    assert konvertiert.faellig_am == konvertiert.datum + timedelta(days=tage)


@pytest.mark.parametrize("standard,override,tage", [(0, None, 0), (14, None, 14), (14, 0, 0)])
def test_wiederkehrender_entwurf_uebernimmt_standard_oder_null_override(db, standard, override, tage):
    db.query(Unternehmen).first().standard_zahlungsziel = standard
    vorlage = Rechnungsvorlage(
        bezeichnung="Abo", intervall="monatlich", naechstes_datum=DATUM,
        zahlungsziel_tage=override, positionen_json="[]",
    )
    db.add(vorlage)
    db.flush()
    rechnung_id, _, _ = _erstelle_entwurf(vorlage, db)
    rechnung = db.get(Rechnung, rechnung_id)
    assert rechnung.faellig_am == DATUM + timedelta(days=tage)
