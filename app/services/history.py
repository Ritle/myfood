from datetime import UTC, date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FoodEntry
from app.repositories.food_entries import get_owned_food_entry
from app.services.diary import MEAL_TYPES, get_entries_for_day


async def repeat_food_entry(
    session: AsyncSession,
    *,
    user_id: int,
    entry_id: int,
    eaten_at: datetime | None = None,
) -> FoodEntry | None:
    """Copy one owned nutrient snapshot into the current diary."""
    source = await get_owned_food_entry(session, entry_id=entry_id, user_id=user_id)
    if source is None:
        return None
    copy = clone_entry(source, eaten_at=eaten_at or datetime.now(UTC))
    session.add(copy)
    await session.commit()
    await session.refresh(copy)
    return copy


async def repeat_meal(
    session: AsyncSession,
    *,
    user_id: int,
    source_day: date,
    meal_type: str,
    timezone_name: str,
    day_boundary_time: time = time.min,
    eaten_at: datetime | None = None,
) -> list[FoodEntry]:
    """Copy all snapshots from one owned meal into the current diary."""
    if meal_type not in MEAL_TYPES:
        raise ValueError("unknown meal type")
    entries = await get_entries_for_day(
        session,
        user_id=user_id,
        day=source_day,
        timezone_name=timezone_name,
        day_boundary_time=day_boundary_time,
    )
    timestamp = eaten_at or datetime.now(UTC)
    copies = [clone_entry(entry, eaten_at=timestamp) for entry in entries if entry.meal_type == meal_type]
    if not copies:
        return []
    session.add_all(copies)
    await session.commit()
    for entry in copies:
        await session.refresh(entry)
    return copies


def clone_entry(source: FoodEntry, *, eaten_at: datetime) -> FoodEntry:
    """Clone a stored nutrition snapshot without recalculating the product."""
    return FoodEntry(
        user_id=source.user_id,
        food_id=source.food_id,
        food=source.food,
        meal_type=source.meal_type,
        weight_grams=source.weight_grams,
        calories=source.calories,
        protein=source.protein,
        fat=source.fat,
        carbs=source.carbs,
        eaten_at=eaten_at,
    )
