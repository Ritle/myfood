import logging
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.keyboards.notifications import meal_reminder_actions
from app.models import NotificationLog, NotificationSettings, User
from app.repositories.notification_settings import (
    get_or_create_notification_settings,
    list_users_with_notification_settings,
)
from app.repositories.notifications import (
    list_due_notifications,
    mark_notification_sent,
    mark_notification_suppressed,
    notification_key_exists,
    record_notification_failure,
    try_create_notification,
)
from app.services.diary import MEAL_LABELS, get_entries_for_day, local_today
from app.services.today import format_today
from app.services.water import get_water_for_day, total_water

logger = logging.getLogger(__name__)
MEAL_TIMES = {
    "breakfast": "breakfast_time",
    "lunch": "lunch_time",
    "dinner": "dinner_time",
}
MEAL_GRACE = timedelta(hours=2)
REPORT_GRACE = timedelta(hours=4)
MAX_DELIVERY_ATTEMPTS = 5
RETRY_DELAY = timedelta(minutes=5)


def is_quiet_time(value: time, start: time, end: time) -> bool:
    """Return whether a local time falls in possibly overnight quiet hours."""
    if start < end:
        return start <= value < end
    return value >= start or value < end


def latest_water_slot(
    local_now: datetime, *, start: time, end: time, interval_minutes: int
) -> datetime | None:
    """Return the most recent water slot in a same-day active window."""
    if interval_minutes <= 0 or start >= end or not start <= local_now.time() <= end:
        return None
    window_start = datetime.combine(local_now.date(), start, tzinfo=local_now.tzinfo)
    elapsed_minutes = int((local_now - window_start).total_seconds() // 60)
    return window_start + timedelta(minutes=(elapsed_minutes // interval_minutes) * interval_minutes)


def latest_movement_slot(
    local_now: datetime, *, interval_minutes: int
) -> datetime | None:
    """Return the latest daily movement slot at a fixed local interval."""
    if interval_minutes <= 0:
        return None
    day_start = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
    elapsed_minutes = int((local_now - day_start).total_seconds() // 60)
    return day_start + timedelta(minutes=(elapsed_minutes // interval_minutes) * interval_minutes)


def event_is_due(
    local_now: datetime, *, scheduled_time: time, grace: timedelta
) -> datetime | None:
    """Return today's scheduled instant when it is inside the delivery window."""
    scheduled = datetime.combine(
        local_now.date(), scheduled_time, tzinfo=local_now.tzinfo
    )
    return scheduled if scheduled <= local_now < scheduled + grace else None


async def plan_user_notifications(
    session: AsyncSession,
    *,
    user: User,
    settings: NotificationSettings,
    now: datetime,
) -> None:
    """Claim currently due logical events for one user."""
    zone = ZoneInfo(user.timezone)
    local_now = now.astimezone(zone)
    local_day = local_today(
        user.timezone, day_boundary_time=user.day_boundary_time, now=now
    )
    if is_quiet_time(
        local_now.time(), settings.quiet_start_time, settings.quiet_end_time
    ):
        return
    if settings.meal_reminders_enabled:
        entries = await get_entries_for_day(
            session,
            user_id=user.id,
            day=local_day,
            timezone_name=user.timezone,
            day_boundary_time=user.day_boundary_time,
        )
        recorded_meals = {entry.meal_type for entry in entries}
        for meal_type, field in MEAL_TIMES.items():
            scheduled_local = event_is_due(
                local_now, scheduled_time=getattr(settings, field), grace=MEAL_GRACE
            )
            skip_key = meal_skip_key(user.id, local_day, meal_type)
            if (
                scheduled_local is None
                or meal_type in recorded_meals
                or await notification_key_exists(session, skip_key)
            ):
                continue
            await try_create_notification(
                session,
                user_id=user.id,
                notification_type=f"meal:{meal_type}",
                local_date=local_day,
                deduplication_key=f"meal:{user.id}:{local_day.isoformat()}:{meal_type}",
                scheduled_for=scheduled_local.astimezone(UTC),
            )

    if settings.water_reminders_enabled:
        slot = latest_water_slot(
            local_now,
            start=settings.water_start_time,
            end=settings.water_end_time,
            interval_minutes=settings.water_interval_minutes,
        )
        if slot is not None:
            water_entries = await get_water_for_day(
                session,
                user_id=user.id,
                day=local_day,
                timezone_name=user.timezone,
                day_boundary_time=user.day_boundary_time,
            )
            consumed = total_water(water_entries)
            if user.daily_water_target_ml is None or consumed < user.daily_water_target_ml:
                await try_create_notification(
                    session,
                    user_id=user.id,
                    notification_type="water",
                    local_date=local_day,
                    deduplication_key=(
                        f"water:{user.id}:{local_day.isoformat()}:{slot:%H%M}"
                    ),
                    scheduled_for=slot.astimezone(UTC),
                )

    if settings.movement_reminders_enabled:
        slot = latest_movement_slot(
            local_now, interval_minutes=settings.movement_interval_minutes
        )
        if slot is not None:
            await try_create_notification(
                session,
                user_id=user.id,
                notification_type="movement",
                local_date=local_day,
                deduplication_key=(
                    f"movement:{user.id}:{local_day.isoformat()}:{slot:%H%M}"
                ),
                scheduled_for=slot.astimezone(UTC),
            )

    if settings.morning_report_enabled:
        scheduled_local = event_is_due(
            local_now,
            scheduled_time=settings.morning_report_time,
            grace=REPORT_GRACE,
        )
        if scheduled_local is not None:
            await try_create_notification(
                session,
                user_id=user.id,
                notification_type="morning_report",
                local_date=local_day,
                deduplication_key=f"report:{user.id}:{local_day.isoformat()}",
                scheduled_for=scheduled_local.astimezone(UTC),
            )


async def run_notification_cycle(
    bot: Bot, session_factory: async_sessionmaker, *, now: datetime | None = None
) -> None:
    """Plan due events, recover pending events, and deliver eligible messages."""
    current = now or datetime.now(UTC)
    try:
        async with session_factory() as session:
            recipients = await list_users_with_notification_settings(session)
            for user, settings in recipients:
                await plan_user_notifications(
                    session, user=user, settings=settings, now=current
                )
            due = await list_due_notifications(session, now=current)
            for log, user in due:
                await deliver_scheduled_notification(
                    bot, session, log=log, user=user, now=current
                )
    except Exception:
        logger.exception("Notification cycle failed")


async def deliver_scheduled_notification(
    bot: Bot,
    session: AsyncSession,
    *,
    log: NotificationLog,
    user: User,
    now: datetime,
) -> None:
    """Re-check current state, deliver one event, and record success."""
    settings = await get_or_create_notification_settings(session, user_id=user.id)
    local_now = now.astimezone(ZoneInfo(user.timezone))
    if is_quiet_time(
        local_now.time(), settings.quiet_start_time, settings.quiet_end_time
    ):
        return
    current_day = local_today(
        user.timezone, day_boundary_time=user.day_boundary_time, now=now
    )
    if log.local_date != current_day:
        await mark_notification_suppressed(session, log.id)
        return
    text, reply_markup = await build_notification(
        session, log=log, user=user, settings=settings
    )
    if text is None:
        await mark_notification_suppressed(session, log.id)
        return
    try:
        await bot.send_message(user.telegram_id, text, reply_markup=reply_markup)
    except Exception as error:
        logger.exception(
            "Telegram notification delivery failed",
            extra={"notification_log_id": log.id, "user_id": user.id},
        )
        await record_notification_failure(
            session,
            log.id,
            error=f"{type(error).__name__}: {error}",
            now=now,
            max_attempts=MAX_DELIVERY_ATTEMPTS,
            retry_delay=RETRY_DELAY,
        )
        return
    await mark_notification_sent(session, log.id)


async def build_notification(
    session: AsyncSession,
    *,
    log: NotificationLog,
    user: User,
    settings: NotificationSettings,
):
    """Build a notification after checking goals and diary state."""
    if log.notification_type.startswith(("meal:", "meal_snooze:")):
        if not settings.meal_reminders_enabled:
            return None, None
        meal_type = log.notification_type.rsplit(":", 1)[-1]
        skip_key = meal_skip_key(user.id, log.local_date, meal_type)
        entries = await get_entries_for_day(
            session,
            user_id=user.id,
            day=log.local_date,
            timezone_name=user.timezone,
            day_boundary_time=user.day_boundary_time,
        )
        if any(entry.meal_type == meal_type for entry in entries) or await notification_key_exists(
            session, skip_key
        ):
            return None, None
        label = MEAL_LABELS[meal_type]
        return (
            f"{label}: в дневнике пока нет записей. Добавим прием пищи?",
            meal_reminder_actions(log.id, meal_type),
        )
    if log.notification_type == "water":
        if not settings.water_reminders_enabled:
            return None, None
        entries = await get_water_for_day(
            session,
            user_id=user.id,
            day=log.local_date,
            timezone_name=user.timezone,
            day_boundary_time=user.day_boundary_time,
        )
        consumed = total_water(entries)
        if user.daily_water_target_ml is not None and consumed >= user.daily_water_target_ml:
            return None, None
        target = (
            f" из {user.daily_water_target_ml} мл" if user.daily_water_target_ml else ""
        )
        return f"💧 Пора выпить воды. Сегодня записано {consumed} мл{target}.", None
    if log.notification_type == "movement":
        if not settings.movement_reminders_enabled:
            return None, None
        text = (
            "🧍 Пора размяться! Встаньте, потянитесь и немного пройдитесь, "
            "если сейчас удобно."
        )
        return text, None
    if log.notification_type == "morning_report":
        if not settings.morning_report_enabled:
            return None, None
        report_day = log.local_date - timedelta(days=1)
        food_entries = await get_entries_for_day(
            session,
            user_id=user.id,
            day=report_day,
            timezone_name=user.timezone,
            day_boundary_time=user.day_boundary_time,
        )
        water_entries = await get_water_for_day(
            session,
            user_id=user.id,
            day=report_day,
            timezone_name=user.timezone,
            day_boundary_time=user.day_boundary_time,
        )
        report = format_today(user, food_entries, water_ml=total_water(water_entries))
        return report.replace("📊 Сегодня", f"📅 Итоги за {report_day:%d.%m.%Y}", 1), None
    return None, None


def meal_skip_key(user_id: int, local_date: date, meal_type: str) -> str:
    """Build the durable key used for a skipped meal reminder."""
    return f"meal_skip:{user_id}:{local_date.isoformat()}:{meal_type}"
