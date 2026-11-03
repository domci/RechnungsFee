"""Einheitlicher Zahlungsziel-Standard für ausgehende Rechnungen."""


def standard_zahlungsziel(unternehmen) -> int:
    """0 = sofort; nur ein fehlender Unternehmenswert fällt auf 14 Tage zurück."""
    wert = getattr(unternehmen, "standard_zahlungsziel", None)
    return 14 if wert is None else int(wert)
