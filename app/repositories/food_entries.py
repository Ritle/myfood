from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Food, FoodEntry


async def create_food_entry(session: AsyncSession, entry: FoodEntry) -> FoodEntry:
    """Persist one diary entry."""
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def list_food_entries(
    session: AsyncSession,
    *,
    user_id: int,
    start_at: datetime,
    end_at: datetime,
) -> list[FoodEntry]:
    """Return a user's entries inside a UTC half-open interval."""
    result = await session.scalars(
        select(FoodEntry)
        .where(
            FoodEntry.user_id == user_id,
            FoodEntry.eaten_at >= start_at,
            FoodEntry.eaten_at < end_at,
        )
        .order_by(FoodEntry.eaten_at, FoodEntry.id)
    )
    return list(result.unique())


async def get_owned_food_entry(
    session: AsyncSession, *, entry_id: int, user_id: int
) -> FoodEntry | None:
    """Load a diary entry only when it belongs to the user."""
    return await session.scalar(
        select(FoodEntry).where(FoodEntry.id == entry_id, FoodEntry.user_id == user_id)
    )


async def save_food_entry(session: AsyncSession, entry: FoodEntry) -> FoodEntry:
    """Commit changes to an existing diary entry."""
    await session.commit()
    await session.refresh(entry)
    return entry


async def delete_food_entry(session: AsyncSession, entry: FoodEntry) -> None:
    """Delete one owned diary entry."""
    await session.delete(entry)
    await session.commit()


async def list_recent_foods(
    session: AsyncSession, *, user_id: int, limit: int = 10
) -> list[Food]:
    """Return unique active products from the user's latest diary entries."""
    result = await session.scalars(
        select(Food)
        .join(FoodEntry, FoodEntry.food_id == Food.id)
        .where(FoodEntry.user_id == user_id, Food.is_archived.is_(False))
        .order_by(FoodEntry.eaten_at.desc(), FoodEntry.id.desc())
        .limit(max(limit * 10, limit))
    )
    unique: list[Food] = []
    seen: set[int] = set()
    for food in result:
        if food.id in seen:
            continue
        seen.add(food.id)
        unique.append(food)
        if len(unique) == limit:
            break
    return unique
