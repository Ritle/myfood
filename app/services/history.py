from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FoodEntry
from app.repositories.food_entries import get_owned_food_entry
from app.services.diary import MEAL_TYPES, get_entries_for_day


async def repeat_food_entry(
    session: AsyncSession,
    *,
    user_id: int,
    entry_id: int,
    snack_number: int | None = None,
    eaten_at: datetime | None = None,
) -> FoodEntry | None:
    """Copy one owned nutrient snapshot into the current diary."""
    source = await get_owned_food_entry(session, entry_id=entry_id, user_id=user_id)
    if source is None:
        return None
    copy = clone_entry(source, eaten_at=eaten_at or datetime.now(UTC))
    if source.meal_type == "snack" and snack_number is not None:
        copy.snack_number = snack_number
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
    snack_number: int | None = None,
    target_snack_number: int | None = None,
    eaten_at: datetime | None = None,
) -> list[FoodEntry]:
    """Copy all snapshots from one owned meal into the current diary."""
    if meal_type not in MEAL_TYPES:
        raise ValueError("unknown meal type")
    entries = await get_entries_for_day(
        session, user_id=user_id, day=source_day, timezone_name=timezone_name
    )
    timestamp = eaten_at or datetime.now(UTC)
    selected = [
        entry
        for entry in entries
        if entry.meal_type == meal_type
        and (
            meal_type != "snack"
            or (entry.snack_number or 1) == (snack_number or 1)
        )
    ]
    copies = [clone_entry(entry, eaten_at=timestamp) for entry in selected]
    if meal_type == "snack" and target_snack_number is not None:
        for copy in copies:
            copy.snack_number = target_snack_number
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
        snack_number=source.snack_number,
        weight_grams=source.weight_grams,
        is_full_serving=source.is_full_serving,
        calories=source.calories,
        protein=source.protein,
        fat=source.fat,
        carbs=source.carbs,
        eaten_at=eaten_at,
    )
