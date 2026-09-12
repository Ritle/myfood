from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WeightEntry


async def list_weight_entries(session: AsyncSession, *, user_id: int) -> list[WeightEntry]:
    """Return a user's weight history from newest to oldest."""
    result = await session.scalars(
        select(WeightEntry)
        .where(WeightEntry.user_id == user_id)
        .order_by(WeightEntry.measured_at.desc(), WeightEntry.id.desc())
    )
    return list(result)


async def get_owned_weight_entry(
    session: AsyncSession, *, entry_id: int, user_id: int
) -> WeightEntry | None:
    """Load a weight entry only when it belongs to the user."""
    return await session.scalar(
        select(WeightEntry).where(WeightEntry.id == entry_id, WeightEntry.user_id == user_id)
    )
