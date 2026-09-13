"""Parsing compact multi-food diary messages."""

import re
from dataclasses import dataclass
from decimal import Decimal

from app.utils.portions import parse_portion_input

DEFAULT_BATCH_WEIGHT = Decimal(100)
MAX_BATCH_ITEMS = 8
MEAL_PREFIXES = {
    "завтрак": "breakfast",
    "обед": "lunch",
    "ужин": "dinner",
    "перекус": "snack",
}


@dataclass(frozen=True, slots=True)
class ParsedFoodItem:
    """A product query and its explicit or default portion weight."""

    query: str
    weight_grams: Decimal
    assumed_weight: bool


@dataclass(frozen=True, slots=True)
class ParsedFoodBatch:
    """Items parsed from one message, optionally with a meal override."""

    items: tuple[ParsedFoodItem, ...]
    meal_type: str | None


def parse_food_batch_input(text: str | None) -> ParsedFoodBatch | None:
    """Parse `food 150g, another food`; missing portions default visibly to 100g."""
    raw = (text or "").strip()
    if not raw:
        return None

    meal_type = None
    prefix = re.match(r"^(завтрак|обед|ужин|перекус)\s*:\s*", raw, re.IGNORECASE)
    if prefix is not None:
        meal_type = MEAL_PREFIXES[prefix.group(1).casefold()]
        raw = raw[prefix.end() :].strip()

    parts = [
        " ".join(part.split())
        for part in re.split(r";|\n|,(?=\s*[^\d\s])", raw)
    ]
    has_measure = any(_split_item_portion(part)[1] is not None for part in parts if part)
    if meal_type is None and len(parts) == 1 and not has_measure:
        return None
    if not parts or any(not part for part in parts):
        raise ValueError("Разделите продукты запятыми, точками с запятой или переносами строк.")
    if len(parts) > MAX_BATCH_ITEMS:
        raise ValueError(f"За раз можно добавить не более {MAX_BATCH_ITEMS} продуктов.")

    items = []
    for part in parts:
        query, weight = _split_item_portion(part)
        if len(query) < 2:
            raise ValueError("Укажите название для каждого продукта.")
        assumed = weight is None
        weight = weight or DEFAULT_BATCH_WEIGHT
        if not Decimal("0.01") <= weight <= Decimal(10000):
            raise ValueError("Вес каждого продукта должен быть от 0,01 до 10000 г.")
        items.append(ParsedFoodItem(query=query, weight_grams=weight, assumed_weight=assumed))

    return ParsedFoodBatch(items=tuple(items), meal_type=meal_type)


def _split_item_portion(text: str) -> tuple[str, Decimal | None]:
    """Separate a trailing measure from the product name, if present."""
    words = text.split()
    for start in range(len(words) - 1, 0, -1):
        weight = parse_portion_input(" ".join(words[start:]))
        if weight is not None:
            return " ".join(words[:start]).strip(), weight
    return text.strip(), None
