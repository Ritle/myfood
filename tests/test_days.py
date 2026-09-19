from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, User
from app.services.days import (
    close_diary_day,
    get_or_create_active_diary_day,
    resolve_diary_day_bounds,
)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@pytest.mark.asyncio
async def test_manual_day_can_cross_midnight_and_close_at_actual_sleep_time() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            user = User(telegram_id=700, first_name="Night owl", timezone="Europe/Moscow")
            session.add(user)
            await session.commit()
            await session.refresh(user)

            opened_at = datetime(2026, 9, 19, 15, 0, tzinfo=UTC)  # 18:00 local
            active = await get_or_create_active_diary_day(
                session, user=user, now=opened_at
            )
            assert active.logical_date == date(2026, 9, 19)
            assert as_utc(active.started_at) == datetime(2026, 9, 18, 21, 0, tzinfo=UTC)

            sleep_time = datetime(2026, 9, 19, 22, 30, tzinfo=UTC)  # 01:30 on Sep 20
            result = await close_diary_day(
                session, user=user, day_id=active.id, now=sleep_time
            )
            assert result is not None
            closed, next_day = result
            assert closed.logical_date == date(2026, 9, 19)
            assert as_utc(closed.ended_at) == sleep_time
            assert next_day.logical_date == date(2026, 9, 20)
            assert as_utc(next_day.started_at) == sleep_time

            bounds = await resolve_diary_day_bounds(
                session,
                user_id=user.id,
                day=date(2026, 9, 19),
                timezone_name=user.timezone,
            )
            assert bounds == (
                datetime(2026, 9, 18, 21, 0, tzinfo=UTC),
                sleep_time,
            )

            assert (
                await close_diary_day(
                    session, user=user, day_id=active.id, now=sleep_time
                )
                is None
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_next_day_skips_forward_if_user_finishes_after_missing_calendar_days() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async with sessions() as session:
            user = User(telegram_id=701, first_name="User", timezone="Europe/Moscow")
            session.add(user)
            await session.commit()
            await session.refresh(user)

            active = await get_or_create_active_diary_day(
                session,
                user=user,
                now=datetime(2026, 9, 19, 10, 0, tzinfo=UTC),
            )
            result = await close_diary_day(
                session,
                user=user,
                day_id=active.id,
                now=datetime(2026, 9, 21, 22, 0, tzinfo=UTC),
            )
            assert result is not None
            _, next_day = result
            assert next_day.logical_date == date(2026, 9, 22)
    finally:
        await engine.dispose()
