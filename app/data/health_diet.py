"""Load the user-provided Health Diet catalog export as packaged seed data."""

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

from app.data.base_foods import BaseFood, food

SOURCE = "HEALTH_DIET"
DATA_DIRECTORY = Path(__file__).resolve().parents[2] / "health_diet_data"
_VALUE_PATTERN = re.compile(r"^\s*(\d+(?:[,.]\d+)?)\s*(?:кКал|г)\s*$", re.IGNORECASE)
_MAX_CALORIES_PER_100G = Decimal(1000)
_MAX_MACRONUTRIENT_PER_100G = Decimal(100)
_DISH_FILENAMES = frozenset(
    {
        "Вторые_блюда",
        "Первые_блюда",
        "Салаты",
        "Ресторанная_еда",
        "Фаст-фуд",
        "KFC_Ростикc",
        "Макдоналдс_McDonalds",
        "Subway",
        "Крошка-Картошка",
    }
)


def _normalized_name(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _nutrient_value(value: object, *, field: str) -> Decimal:
    match = _VALUE_PATTERN.fullmatch(str(value))
    if match is None:
        raise ValueError(f"{field}: недопустимое значение {value!r}")
    return Decimal(match.group(1).replace(",", "."))


def _catalog_section(path: Path) -> str:
    return "dish" if path.stem in _DISH_FILENAMES else "food"


def load_health_diet_foods(directory: Path = DATA_DIRECTORY) -> tuple[BaseFood, ...]:
    """Parse JSON exports, retaining values that can represent 100 grams of food."""
    if not directory.is_dir():
        raise FileNotFoundError(f"Не найдена папка с каталогом: {directory}")

    foods: list[BaseFood] = []
    seen: set[tuple[str, Decimal, Decimal, Decimal, Decimal]] = set()
    for path in sorted(directory.glob("*.json"), key=lambda item: item.name.casefold()):
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise TypeError(f"{path.name}: ожидался JSON-массив")
        for row_number, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise TypeError(f"{path.name}, строка {row_number}: ожидался объект")
            name = " ".join(str(row.get("Продукт", "")).split())
            if not name:
                raise ValueError(f"{path.name}, строка {row_number}: отсутствует название")
            calories = _nutrient_value(row.get("Калорийность"), field="Калорийность")
            protein = _nutrient_value(row.get("Белки"), field="Белки")
            fat = _nutrient_value(row.get("Жиры"), field="Жиры")
            carbs = _nutrient_value(row.get("Углеводы"), field="Углеводы")
            if (
                calories > _MAX_CALORIES_PER_100G
                or protein > _MAX_MACRONUTRIENT_PER_100G
                or fat > _MAX_MACRONUTRIENT_PER_100G
                or carbs > _MAX_MACRONUTRIENT_PER_100G
            ):
                continue
            key = (_normalized_name(name), calories, protein, fat, carbs)
            if key in seen:
                continue
            seen.add(key)
            source_ref = hashlib.sha256(
                "|".join(
                    (key[0], str(calories), str(protein), str(fat), str(carbs))
                ).encode()
            ).hexdigest()[:32]
            foods.append(
                food(
                    source_ref,
                    name,
                    str(calories),
                    str(protein),
                    str(fat),
                    str(carbs),
                    source=SOURCE,
                    catalog_section=_catalog_section(path),
                )
            )
    return tuple(foods)


HEALTH_DIET_FOODS = load_health_diet_foods()
