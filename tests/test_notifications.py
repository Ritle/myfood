from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, DiaryDay, NotificationLog, NotificationSettings, User
from app.services.notifications import (
    is_quiet_time,
    latest_movement_slot,
    latest_water_slot,
    plan_user_notifications,
    run_notification_cycle,
)


class FakeBot:
    def __init__(self) -> None:
        self.messages = []

    async def send_message(self, chat_id, text, reply_markup=None) -> None:
        self.messages.append((chat_id, text, reply_markup))


class FailingBot:
    def __init__(self) -> None:
        self.attempts = 0

    async def send_message(self, chat_id, text, reply_markup=None) -> None:
        self.attempts += 1
        raise RuntimeError("Telegram unavailable")


def test_quiet_hours_and_water_slots() -> None:
    assert is_quiet_time(time(23), time(22), time(8))
    assert is_quiet_time(time(7, 59), time(22), time(8))
    assert not is_quiet_time(time(12), time(22), time(8))
    local_now = datetime(2026, 9, 12, 15, 37, tzinfo=ZoneInfo("Europe/Moscow"))
    slot = latest_water_slot(
        local_now, start=time(9), end=time(21), interval_minutes=120
    )
    assert slot is not None
    assert slot.time() == time(15)


def test_movement_slots_follow_configured_local_interval() -> None:
    local_now = datetime(2026, 9, 12, 13, 35, tzinfo=ZoneInfo("Europe/Moscow"))

    assert latest_movement_slot(local_now, interval_minutes=60).time() == time(13)
    assert latest_movement_slot(local_now, interval_minutes=90).time() == time(13, 30)
    assert latest_movement_slot(local_now, interval_minutes=0) is None


@pytest.mark.asyncio
async def test_planning_is_deduplicated_for_meal_water_and_report() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(
                telegram_id=1,
                first_name="User",
                timezone="Europe/Moscow",
                daily_water_target_ml=2000,
            )
            settings = NotificationSettings(
                meal_reminders_enabled=True,
                breakfast_time=time(9),
                lunch_time=time(14),
                dinner_time=time(20),
                water_reminders_enabled=True,
                water_interval_minutes=120,
                water_start_time=time(9),
                water_end_time=time(21),
                morning_report_enabled=True,
                morning_report_time=time(8),
                quiet_start_time=time(22),
                quiet_end_time=time(8),
            )
            session.add(user)
            await session.flush()
            settings.user_id = user.id
            session.add(settings)
            session.add(
                DiaryDay(
                    user_id=user.id,
                    logical_date=date(2026, 9, 11),
                    started_at=datetime(2026, 9, 10, 21, 0, tzinfo=UTC),
                    ended_at=datetime(2026, 9, 11, 22, 0, tzinfo=UTC),
                )
            )
            await session.commit()

            now = datetime(2026, 9, 12, 6, 30, tzinfo=UTC)
            await plan_user_notifications(session, user=user, settings=settings, now=now)
            await plan_user_notifications(session, user=user, settings=settings, now=now)
            logs = list(await session.scalars(select(NotificationLog).order_by(NotificationLog.id)))

            assert [log.notification_type for log in logs] == [
                "meal:breakfast",
                "water",
                "morning_report",
            ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cycle_delivers_pending_meal_once() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=77, first_name="User", timezone="Europe/Moscow")
            session.add(user)
            await session.flush()
            session.add(
                NotificationSettings(
                    user_id=user.id,
                    meal_reminders_enabled=True,
                    breakfast_time=time(9),
                    water_reminders_enabled=False,
                    morning_report_enabled=False,
                    quiet_start_time=time(22),
                    quiet_end_time=time(8),
                )
            )
            await session.commit()

        bot = FakeBot()
        now = datetime(2026, 9, 12, 6, 30, tzinfo=UTC)
        await run_notification_cycle(bot, sessions, now=now)
        await run_notification_cycle(bot, sessions, now=now)

        async with sessions() as session:
            logs = list(await session.scalars(select(NotificationLog)))
        assert len(bot.messages) == 1
        assert bot.messages[0][0] == 77
        assert "Завтрак" in bot.messages[0][1]
        assert len(logs) == 1
        assert logs[0].status == "sent"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_movement_reminder_obeys_quiet_hours_and_interval_deduplication() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=78, first_name="User", timezone="Europe/Moscow")
            session.add(user)
            await session.flush()
            session.add(
                NotificationSettings(
                    user_id=user.id,
                    meal_reminders_enabled=False,
                    water_reminders_enabled=False,
                    movement_reminders_enabled=True,
                    movement_interval_minutes=60,
                    morning_report_enabled=False,
                    quiet_start_time=time(22),
                    quiet_end_time=time(8),
                )
            )
            await session.commit()

        bot = FakeBot()
        quiet_time = datetime(2026, 9, 12, 4, 30, tzinfo=UTC)  # 07:30 in Moscow
        await run_notification_cycle(bot, sessions, now=quiet_time)
        async with sessions() as session:
            assert list(await session.scalars(select(NotificationLog))) == []

        now = datetime(2026, 9, 12, 6, 5, tzinfo=UTC)  # 09:05 in Moscow
        await run_notification_cycle(bot, sessions, now=now)
        await run_notification_cycle(bot, sessions, now=now)
        next_interval = datetime(2026, 9, 12, 7, 5, tzinfo=UTC)  # 10:05 in Moscow
        await run_notification_cycle(bot, sessions, now=next_interval)
        await run_notification_cycle(bot, sessions, now=next_interval)
        async with sessions() as session:
            logs = list(await session.scalars(select(NotificationLog)))

        assert len(bot.messages) == 2
        assert "Пора размяться" in bot.messages[0][1]
        assert len(logs) == 2
        assert all(log.notification_type == "movement" for log in logs)
        assert all(log.status == "sent" for log in logs)
        assert [log.scheduled_for.replace(tzinfo=UTC) for log in logs] == [
            datetime(2026, 9, 12, 6, 0, tzinfo=UTC),
            datetime(2026, 9, 12, 7, 0, tzinfo=UTC),
        ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cycle_stops_after_five_delivery_failures() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=88, first_name="User", timezone="Europe/Moscow")
            session.add(user)
            await session.flush()
            session.add(
                NotificationSettings(
                    user_id=user.id,
                    meal_reminders_enabled=True,
                    breakfast_time=time(9),
                    water_reminders_enabled=False,
                    morning_report_enabled=False,
                    quiet_start_time=time(22),
                    quiet_end_time=time(8),
                )
            )
            await session.commit()

        bot = FailingBot()
        first_attempt = datetime(2026, 9, 12, 6, 30, tzinfo=UTC)
        for attempt in range(5):
            await run_notification_cycle(
                bot, sessions, now=first_attempt + timedelta(minutes=5 * attempt)
            )

        async with sessions() as session:
            log = await session.scalar(select(NotificationLog))
        assert log is not None
        assert bot.attempts == 5
        assert log.attempt_count == 5
        assert log.status == "failed"
        assert log.last_error == "RuntimeError: Telegram unavailable"
    finally:
        await engine.dispose()
