from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BaseFood:
    """One packaged catalog item, with values per 100 grams."""

    source_ref: str
    name: str
    calories: Decimal
    protein: Decimal
    fat: Decimal
    carbs: Decimal
    source: str = "USDA_FDC"
    catalog_section: str = "food"


def food(
    source_ref: int | str,
    name: str,
    calories: str,
    protein: str,
    fat: str,
    carbs: str,
    *,
    source: str = "USDA_FDC",
    catalog_section: str = "food",
) -> BaseFood:
    """Create an exact decimal catalog item from compact source literals."""
    return BaseFood(
        source_ref=str(source_ref),
        name=name,
        calories=Decimal(calories),
        protein=Decimal(protein),
        fat=Decimal(fat),
        carbs=Decimal(carbs),
        source=source,
        catalog_section=catalog_section,
    )


# USDA FoodData Central Foundation Foods, April 2026 release. Energy uses
# Atwater-specific kcal (nutrient 2048) when available and Energy kcal (1008) otherwise.
BASE_FOODS: tuple[BaseFood, ...] = (
    food(1750341, "Яблоко Гала, сырое, с кожурой", "54.9", "0.133", "0.15", "14.8"),
    food(1105314, "Банан, сырой", "97", "0.74", "0.29", "23"),
    food(1999634, "Томат Рома, сырой", "19", "0.696", "0.425", "3.84"),
    food(2346406, "Огурец с кожурой, сырой", "13.9", "0.625", "0.178", "2.95"),
    food(2258586, "Морковь, сырая", "45", "0.941", "0.351", "10.3"),
    food(747447, "Брокколи, сырая", "31", "2.57", "0.34", "6.27"),
    food(2710824, "Авокадо Хасс, сырой", "206", "1.81", "20.3", "8.32"),
    food(2346401, "Картофель Рассет без кожуры, сырой", "81", "2.27", "0.36", "17.8"),
    food(2346396, "Овсяные хлопья, сухие", "379", "13.5", "5.89", "68.7"),
    food(2512378, "Гречка, сухая крупа", "332", "11.1", "3.04", "71.1"),
    food(2512381, "Рис белый длиннозерный, сухой", "370", "7.04", "1.03", "80.3"),
    food(2512380, "Рис бурый длиннозерный, сухой", "368", "7.25", "3.31", "76.7"),
    food(2644282, "Нут, сухой", "372", "21.3", "6.27", "60.4"),
    food(2644288, "Нут консервированный, промытый", "133", "7.02", "3.1", "20.3"),
    food(2644283, "Чечевица, сухая", "351", "23.6", "1.92", "62.2"),
    food(2646170, "Куриная грудка без кожи, сырая", "112", "22.5", "1.93", "0"),
    food(331960, "Куриная грудка без кожи, тушеная", "166", "32.1", "3.24", "0"),
    food(2514743, "Говяжий фарш 90/10, сырой", "190", "18.2", "12.8", "0"),
    food(2684441, "Лосось атлантический, сырой", "203", "20.3", "13.1", "0"),
    food(748967, "Яйцо куриное, сырое", "148", "12.4", "9.96", "0.96"),
    food(746782, "Молоко цельное 3,25%", "60", "3.27", "3.2", "4.63"),
    food(330137, "Йогурт греческий обезжиренный", "61", "10.3", "0.37", "3.64"),
    food(2346384, "Творог зерненый, жирный", "105", "11.6", "4.22", "4.6"),
    food(328637, "Сыр чеддер", "408", "23.3", "34", "2.44"),
    food(2346393, "Миндаль, сырой", "584", "21.5", "51.1", "20"),
)
