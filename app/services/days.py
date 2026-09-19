from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DiaryDay, User
from app.repositories.diary_days import (
    get_active_diary_day,
    get_diary_day_by_date,
    get_latest_closed_diary_day,
)


def calendar_day_bounds(day: date, timezone_name: str) -> tuple[datetime, datetime]:
    """Convert a local calendar day to a UTC half-open interval."""
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("unknown user timezone") from error
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def local_calendar_date(timezone_name: str, *, now: datetime | None = None) -> date:
    """Return the current calendar date in the user's timezone."""
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("unknown user timezone") from error
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(zone).date()


async def get_or_create_active_diary_day(
    session: AsyncSession,
    *,
    user: User,
    now: datetime | None = None,
) -> DiaryDay:
    """Return the active logical day, creating an initial day when needed."""
    active = await get_active_diary_day(session, user_id=user.id)
    if active is not None:
        return active

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    latest_closed = await get_latest_closed_diary_day(session, user_id=user.id)
    local_date = local_calendar_date(user.timezone, now=current)
    if latest_closed is None:
        started_at, _ = calendar_day_bounds(local_date, user.timezone)
        logical_date = local_date
    else:
        started_at = latest_closed.ended_at or current
        logical_date = max(latest_closed.logical_date + timedelta(days=1), local_date)

    active = DiaryDay(
        user_id=user.id,
        logical_date=logical_date,
        started_at=started_at,
    )
    session.add(active)
    await session.commit()
    await session.refresh(active)
    return active


async def close_diary_day(
    session: AsyncSession,
    *,
    user: User,
    day_id: int,
    now: datetime | None = None,
) -> tuple[DiaryDay, DiaryDay] | None:
    """Close the requested active day and atomically open the next logical day."""
    active = await get_active_diary_day(session, user_id=user.id)
    if active is None or active.id != day_id:
        return None

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if current <= _as_utc(active.started_at):
        raise ValueError("day end must be after day start")

    active.ended_at = current
    local_date = local_calendar_date(user.timezone, now=current)
    next_date = max(active.logical_date + timedelta(days=1), local_date)
    next_day = DiaryDay(
        user_id=user.id,
        logical_date=next_date,
        started_at=current,
    )
    session.add(next_day)
    await session.commit()
    await session.refresh(active)
    await session.refresh(next_day)
    return active, next_day


async def resolve_diary_day_bounds(
    session: AsyncSession,
    *,
    user_id: int,
    day: date,
    timezone_name: str,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Resolve persisted manual bounds, falling back to legacy calendar-day bounds."""
    diary_day = await get_diary_day_by_date(
        session, user_id=user_id, logical_date=day
    )
    if diary_day is None:
        return calendar_day_bounds(day, timezone_name)

    start_at = _as_utc(diary_day.started_at)
    if diary_day.ended_at is not None:
        return start_at, _as_utc(diary_day.ended_at)

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return start_at, current


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive and timezone-aware database timestamps to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
