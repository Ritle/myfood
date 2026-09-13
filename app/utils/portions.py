"""Parsing helpers for quick food portion measurements."""

import re
from decimal import Decimal

from app.utils.numbers import parse_decimal

QUICK_PORTIONS: tuple[tuple[str, Decimal], ...] = (
    ("🥛 1 стакан ≈200 г", Decimal(200)),
    ("🥛 ½ стакана ≈100 г", Decimal(100)),
    ("🥄 1 столовая ложка ≈15 г", Decimal(15)),
    ("🥄 1 чайная ложка ≈5 г", Decimal(5)),
    ("🍽 1 порция ≈150 г", Decimal(150)),
    ("🍲 1 тарелка ≈250 г", Decimal(250)),
    ("🍎 1 средняя штука ≈100 г", Decimal(100)),
    ("100 г", Decimal(100)),
    ("150 г", Decimal(150)),
    ("200 г", Decimal(200)),
)

_UNIT_GRAMS = {
    "г": Decimal(1),
    "гр": Decimal(1),
    "грамм": Decimal(1),
    "грамма": Decimal(1),
    "граммов": Decimal(1),
    "стакан": Decimal(200),
    "стакана": Decimal(200),
    "стаканов": Decimal(200),
    "ст л": Decimal(15),
    "ст ложка": Decimal(15),
    "ст ложки": Decimal(15),
    "столовая ложка": Decimal(15),
    "столовую ложку": Decimal(15),
    "столовой ложки": Decimal(15),
    "столовые ложки": Decimal(15),
    "столовых ложки": Decimal(15),
    "столовых ложек": Decimal(15),
    "ч л": Decimal(5),
    "ч ложка": Decimal(5),
    "ч ложки": Decimal(5),
    "чайная ложка": Decimal(5),
    "чайную ложку": Decimal(5),
    "чайной ложки": Decimal(5),
    "чайные ложки": Decimal(5),
    "чайных ложки": Decimal(5),
    "чайных ложек": Decimal(5),
    "порция": Decimal(150),
    "порции": Decimal(150),
    "порций": Decimal(150),
    "тарелка": Decimal(250),
    "тарелки": Decimal(250),
    "тарелок": Decimal(250),
    "шт": Decimal(100),
    "штука": Decimal(100),
    "штуки": Decimal(100),
    "штук": Decimal(100),
}


def parse_portion_input(raw: str | None) -> Decimal | None:
    """Parse grams, a quick-keyboard label, or a count of familiar measures."""
    if raw is None:
        return None
    cleaned = " ".join(raw.strip().casefold().split())
    for label, grams in QUICK_PORTIONS:
        if cleaned == label.casefold():
            return grams
    numeric = parse_decimal(raw)
    if numeric is not None:
        return numeric

    normalized = re.sub(r"[^\w\s,]+", " ", cleaned, flags=re.UNICODE)
    normalized = " ".join(normalized.split())
    if normalized in {"полстакана", "половина стакана"}:
        return Decimal(100)

    match = re.fullmatch(r"(\d+(?:[,.]\d+)?)\s*(.+)", normalized)
    if match is None:
        return parse_decimal(raw)
    quantity = parse_decimal(match.group(1))
    unit = match.group(2)
    grams_per_unit = _UNIT_GRAMS.get(unit)
    if quantity is None or grams_per_unit is None:
        return None
    return quantity * grams_per_unit
