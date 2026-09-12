from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Food, FoodEntry
from app.repositories.food_entries import (
    create_food_entry,
    delete_food_entry,
    get_owned_food_entry,
    list_food_entries,
    save_food_entry,
)

MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack"}
MEAL_LABELS = {
    "breakfast": "🍳 Завтрак",
    "lunch": "🍲 Обед",
    "dinner": "🍽 Ужин",
    "snack": "🍎 Перекус",
}
NUTRIENT_STEP = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class PortionNutrition:
    """Calculated nutrients for one portion."""

    calories: Decimal
    protein: Decimal
    fat: Decimal
    carbs: Decimal


@dataclass(frozen=True, slots=True)
class DiarySummary:
    """Nutrient totals for a collection of diary entries."""

    calories: Decimal
    protein: Decimal
    fat: Decimal
    carbs: Decimal


def calculate_portion(food: Food, weight_grams: Decimal) -> PortionNutrition:
    """Calculate and round a portion from per-100-gram product values."""
    validate_portion_weight(weight_grams)
    factor = weight_grams / Decimal(100)
    return PortionNutrition(
        calories=round_nutrient(food.calories_per_100g * factor),
        protein=round_nutrient(food.protein_per_100g * factor),
        fat=round_nutrient(food.fat_per_100g * factor),
        carbs=round_nutrient(food.carbs_per_100g * factor),
    )


def summarize_entries(entries: list[FoodEntry]) -> DiarySummary:
    """Sum stored nutrient snapshots without recalculating source products."""
    return DiarySummary(
        calories=round_nutrient(sum((entry.calories for entry in entries), Decimal(0))),
        protein=round_nutrient(sum((entry.protein for entry in entries), Decimal(0))),
        fat=round_nutrient(sum((entry.fat for entry in entries), Decimal(0))),
        carbs=round_nutrient(sum((entry.carbs for entry in entries), Decimal(0))),
    )


def utc_day_bounds(day: date, timezone_name: str) -> tuple[datetime, datetime]:
    """Convert a user's local calendar day to a UTC half-open interval."""
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("unknown user timezone") from error
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def local_today(timezone_name: str, *, now: datetime | None = None) -> date:
    """Return the current calendar date in a user's timezone."""
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("unknown user timezone") from error
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(zone).date()


async def add_diary_entry(
    session: AsyncSession,
    *,
    user_id: int,
    food: Food,
    meal_type: str,
    weight_grams: Decimal,
    eaten_at: datetime | None = None,
) -> FoodEntry:
    """Store a nutrient snapshot for a consumed product portion."""
    if meal_type not in MEAL_TYPES:
        raise ValueError("unknown meal type")
    portion = calculate_portion(food, weight_grams)
    return await create_food_entry(
        session,
        FoodEntry(
            user_id=user_id,
            food_id=food.id,
            meal_type=meal_type,
            weight_grams=weight_grams.quantize(NUTRIENT_STEP, rounding=ROUND_HALF_UP),
            calories=portion.calories,
            protein=portion.protein,
            fat=portion.fat,
            carbs=portion.carbs,
            eaten_at=eaten_at or datetime.now(UTC),
        ),
    )


async def get_entries_for_day(
    session: AsyncSession, *, user_id: int, day: date, timezone_name: str
) -> list[FoodEntry]:
    """Load all diary entries for one user-local calendar day."""
    start_at, end_at = utc_day_bounds(day, timezone_name)
    return await list_food_entries(session, user_id=user_id, start_at=start_at, end_at=end_at)


async def resize_diary_entry(
    session: AsyncSession, *, user_id: int, entry_id: int, new_weight_grams: Decimal
) -> FoodEntry | None:
    """Resize an owned entry while preserving its original nutrient snapshot ratios."""
    validate_portion_weight(new_weight_grams)
    entry = await get_owned_food_entry(session, entry_id=entry_id, user_id=user_id)
    if entry is None:
        return None
    factor = new_weight_grams / entry.weight_grams
    entry.weight_grams = new_weight_grams.quantize(NUTRIENT_STEP, rounding=ROUND_HALF_UP)
    entry.calories = round_nutrient(entry.calories * factor)
    entry.protein = round_nutrient(entry.protein * factor)
    entry.fat = round_nutrient(entry.fat * factor)
    entry.carbs = round_nutrient(entry.carbs * factor)
    return await save_food_entry(session, entry)


async def remove_diary_entry(session: AsyncSession, *, user_id: int, entry_id: int) -> bool:
    """Delete an owned entry and report whether it existed."""
    entry = await get_owned_food_entry(session, entry_id=entry_id, user_id=user_id)
    if entry is None:
        return False
    await delete_food_entry(session, entry)
    return True


async def load_owned_entry(
    session: AsyncSession, *, user_id: int, entry_id: int
) -> FoodEntry | None:
    """Load one owned diary entry."""
    return await get_owned_food_entry(session, entry_id=entry_id, user_id=user_id)


def validate_portion_weight(weight_grams: Decimal) -> None:
    """Validate a practical positive portion weight."""
    if not weight_grams.is_finite() or not Decimal("0.01") <= weight_grams <= Decimal(10000):
        raise ValueError("Вес порции должен быть от 0,01 до 10000 г")


def round_nutrient(value: Decimal) -> Decimal:
    """Round a stored nutrient value consistently."""
    return value.quantize(NUTRIENT_STEP, rounding=ROUND_HALF_UP)
