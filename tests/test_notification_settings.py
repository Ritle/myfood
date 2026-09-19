from datetime import time

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, NotificationSettings, User
from app.services.notification_settings import (
    parse_clock,
    parse_time_range,
    parse_timezone,
    set_movement_interval,
    set_user_day_boundary,
    toggle_notification_setting,
)


def test_parses_clock_and_time_ranges() -> None:
    assert parse_clock("9:30") == time(9, 30)
    assert parse_clock("23:59") == time(23, 59)
    assert parse_clock("24:00") is None
    assert parse_clock("9:5") is None
    assert parse_time_range("09:00-21:00") == (time(9), time(21))
    assert parse_time_range("22:00–08:00") == (time(22), time(8))
    assert parse_time_range("08:00-08:00") is None
    assert parse_timezone("Europe/Moscow") == "Europe/Moscow"
    assert parse_timezone("Mars/Olympus") is None


@pytest.mark.asyncio
async def test_movement_reminder_can_be_toggled_and_interval_is_bounded() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=501, first_name="User")
            session.add(user)
            await session.flush()
            settings = NotificationSettings(user_id=user.id)
            session.add(settings)
            await session.commit()

            settings = await toggle_notification_setting(
                session, settings=settings, name="movement"
            )
            settings = await set_movement_interval(
                session, settings=settings, minutes=90
            )
            assert settings.movement_reminders_enabled is True
            assert settings.movement_interval_minutes == 90

            for minutes in (29, 241):
                with pytest.raises(ValueError, match="30 to 240"):
                    await set_movement_interval(
                        session, settings=settings, minutes=minutes
                    )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_day_boundary_can_be_changed() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=777, first_name="Night owl")
            session.add(user)
            await session.commit()
            await session.refresh(user)

            updated = await set_user_day_boundary(session, user=user, value=time(3, 30))

            assert updated.day_boundary_time == time(3, 30)
    finally:
        await engine.dispose()
