from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WaterEntry


async def create_water_entry(session: AsyncSession, entry: WaterEntry) -> WaterEntry:
    """Persist one water entry."""
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def list_water_entries(
    session: AsyncSession,
    *,
    user_id: int,
    start_at: datetime,
    end_at: datetime,
) -> list[WaterEntry]:
    """Return a user's water entries inside a UTC half-open interval."""
    result = await session.scalars(
        select(WaterEntry)
        .where(
            WaterEntry.user_id == user_id,
            WaterEntry.drunk_at >= start_at,
            WaterEntry.drunk_at < end_at,
        )
        .order_by(WaterEntry.drunk_at, WaterEntry.id)
    )
    return list(result)


async def get_owned_water_entry(
    session: AsyncSession, *, entry_id: int, user_id: int
) -> WaterEntry | None:
    """Load a water entry only when it belongs to the user."""
    return await session.scalar(
        select(WaterEntry).where(WaterEntry.id == entry_id, WaterEntry.user_id == user_id)
    )


async def save_water_entry(session: AsyncSession, entry: WaterEntry) -> WaterEntry:
    """Commit changes to a water entry."""
    await session.commit()
    await session.refresh(entry)
    return entry


async def delete_water_entry(session: AsyncSession, entry: WaterEntry) -> None:
    """Delete one water entry."""
    await session.delete(entry)
    await session.commit()
