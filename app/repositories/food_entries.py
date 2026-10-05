from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
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


async def get_latest_food_entry(
    session: AsyncSession, *, user_id: int, food_id: int
) -> FoodEntry | None:
    """Load the latest diary entry for one product owned by a user."""
    return await session.scalar(
        select(FoodEntry)
        .where(FoodEntry.user_id == user_id, FoodEntry.food_id == food_id)
        .order_by(FoodEntry.eaten_at.desc(), FoodEntry.id.desc())
        .limit(1)
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


async def list_recent_food_entries(
    session: AsyncSession, *, user_id: int, limit: int = 10
) -> list[FoodEntry]:
    """Return each recently used active food with its latest diary entry."""
    result = await session.scalars(
        select(FoodEntry)
        .join(Food, FoodEntry.food_id == Food.id)
        .where(FoodEntry.user_id == user_id, Food.is_archived.is_(False))
        .order_by(FoodEntry.eaten_at.desc(), FoodEntry.id.desc())
        .limit(max(limit * 10, limit))
    )
    recent: list[FoodEntry] = []
    seen: set[int] = set()
    for entry in result.unique():
        if entry.food_id in seen:
            continue
        seen.add(entry.food_id)
        recent.append(entry)
        if len(recent) == limit:
            break
    return recent



async def list_used_foods(
    session: AsyncSession, *, user_id: int
) -> list[Food]:
    """Return unique active foods the user has actually added to the diary."""
    result = await session.scalars(
        select(Food)
        .join(FoodEntry, FoodEntry.food_id == Food.id)
        .where(
            FoodEntry.user_id == user_id,
            Food.is_archived.is_(False),
        )
        .order_by(FoodEntry.eaten_at.desc(), FoodEntry.id.desc())
    )
    unique: list[Food] = []
    seen: set[int] = set()
    for food in result:
        if food.id in seen:
            continue
        seen.add(food.id)
        unique.append(food)
    return unique



async def list_food_portion_history(
    session: AsyncSession,
    *,
    user_id: int,
    food_id: int,
    limit: int = 12,
) -> list[FoodEntry]:
    """Return a user's recent weighed portions for one product."""
    result = await session.scalars(
        select(FoodEntry)
        .where(
            FoodEntry.user_id == user_id,
            FoodEntry.food_id == food_id,
            FoodEntry.is_full_serving.is_(False),
        )
        .order_by(FoodEntry.eaten_at.desc(), FoodEntry.id.desc())
        .limit(max(1, min(limit, 100)))
    )
    return list(result)



async def list_food_portion_histories(
    session: AsyncSession,
    *,
    user_id: int,
    food_ids: list[int],
    limit_per_food: int = 12,
) -> dict[int, list[Decimal]]:
    """Return recent weighed portions for several foods in one query."""
    if not food_ids:
        return {}
    limit = max(1, min(limit_per_food, 100))
    ranked = (
        select(
            FoodEntry.food_id.label("food_id"),
            FoodEntry.weight_grams.label("weight_grams"),
            func.row_number()
            .over(
                partition_by=FoodEntry.food_id,
                order_by=(FoodEntry.eaten_at.desc(), FoodEntry.id.desc()),
            )
            .label("row_number"),
        )
        .where(
            FoodEntry.user_id == user_id,
            FoodEntry.food_id.in_(food_ids),
            FoodEntry.is_full_serving.is_(False),
        )
        .subquery()
    )
    rows = await session.execute(
        select(ranked.c.food_id, ranked.c.weight_grams).where(
            ranked.c.row_number <= limit
        )
    )
    histories: dict[int, list[Decimal]] = {food_id: [] for food_id in food_ids}
    for food_id, weight_grams in rows.all():
        histories.setdefault(food_id, []).append(Decimal(weight_grams))
    return histories


async def food_meal_usage_counts(
    session: AsyncSession,
    *,
    user_id: int,
    meal_type: str,
) -> dict[int, int]:
    """Return how often each food was logged in one meal type."""
    rows = await session.execute(
        select(FoodEntry.food_id, func.count(FoodEntry.id))
        .where(
            FoodEntry.user_id == user_id,
            FoodEntry.meal_type == meal_type,
        )
        .group_by(FoodEntry.food_id)
    )
    return {food_id: int(count) for food_id, count in rows.all()}
