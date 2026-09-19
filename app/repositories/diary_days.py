from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diary_day import DiaryDay


async def get_active_diary_day(
    session: AsyncSession, *, user_id: int
) -> DiaryDay | None:
    """Return the user's currently open logical day."""
    return await session.scalar(
        select(DiaryDay)
        .where(DiaryDay.user_id == user_id, DiaryDay.ended_at.is_(None))
        .order_by(DiaryDay.id.desc())
        .limit(1)
    )


async def get_diary_day_by_date(
    session: AsyncSession, *, user_id: int, logical_date: date
) -> DiaryDay | None:
    """Load one persisted logical day by its display date."""
    return await session.scalar(
        select(DiaryDay).where(
            DiaryDay.user_id == user_id,
            DiaryDay.logical_date == logical_date,
        )
    )


async def get_latest_closed_diary_day(
    session: AsyncSession, *, user_id: int
) -> DiaryDay | None:
    """Return the most recently closed logical day."""
    return await session.scalar(
        select(DiaryDay)
        .where(DiaryDay.user_id == user_id, DiaryDay.ended_at.is_not(None))
        .order_by(DiaryDay.ended_at.desc(), DiaryDay.id.desc())
        .limit(1)
    )
