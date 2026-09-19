from dataclasses import dataclass
from datetime import UTC, date, datetime
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
from app.services.days import (
    calendar_day_bounds,
    local_calendar_date,
    resolve_diary_day_bounds,
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
    """Backward-compatible calendar-day bounds for legacy history and tests."""
    return calendar_day_bounds(day, timezone_name)


def local_today(timezone_name: str, *, now: datetime | None = None) -> date:
    """Backward-compatible local calendar date helper."""
    return local_calendar_date(timezone_name, now=now)


def suggest_meal_type(timezone_name: str, *, now: datetime | None = None) -> str:
    """Suggest a meal from local time: breakfast 05–11, lunch 11–16, dinner 16–22."""
    try:
        zone = ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError):
        zone = ZoneInfo("Europe/Moscow")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    hour = current.astimezone(zone).hour
    if 5 <= hour < 11:
        return "breakfast"
    if 11 <= hour < 16:
        return "lunch"
    if 16 <= hour < 22:
        return "dinner"
    return "snack"


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


async def add_diary_entries(
    session: AsyncSession,
    *,
    user_id: int,
    items: list[tuple[Food, Decimal]],
    meal_type: str,
    eaten_at: datetime | None = None,
) -> list[FoodEntry]:
    """Store a confirmed group of products atomically with one shared timestamp."""
    if meal_type not in MEAL_TYPES:
        raise ValueError("unknown meal type")
    if not items:
        raise ValueError("at least one food is required")
    timestamp = eaten_at or datetime.now(UTC)
    entries = []
    for food, weight_grams in items:
        portion = calculate_portion(food, weight_grams)
        entries.append(
            FoodEntry(
                user_id=user_id,
                food_id=food.id,
                meal_type=meal_type,
                weight_grams=weight_grams.quantize(NUTRIENT_STEP, rounding=ROUND_HALF_UP),
                calories=portion.calories,
                protein=portion.protein,
                fat=portion.fat,
                carbs=portion.carbs,
                eaten_at=timestamp,
            )
        )
    session.add_all(entries)
    await session.commit()
    for entry in entries:
        await session.refresh(entry)
    return entries


async def get_entries_for_day(
    session: AsyncSession, *, user_id: int, day: date, timezone_name: str
) -> list[FoodEntry]:
    """Load diary entries using manual day bounds when they exist."""
    start_at, end_at = await resolve_diary_day_bounds(
        session,
        user_id=user_id,
        day=day,
        timezone_name=timezone_name,
    )
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
