from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NotificationSettings, User
from app.repositories.notification_settings import (
    get_or_create_notification_settings,
    save_notification_settings,
)

TIME_FIELDS = {
    "breakfast": "breakfast_time",
    "lunch": "lunch_time",
    "dinner": "dinner_time",
    "report": "morning_report_time",
    "nutrition_summary": "nutrition_summary_time",
}
TOGGLE_FIELDS = {
    "meals": "meal_reminders_enabled",
    "water": "water_reminders_enabled",
    "report": "morning_report_enabled",
    "movement": "movement_reminders_enabled",
    "nutrition": "nutrition_monitoring_enabled",
}


def parse_clock(value: str | None) -> time | None:
    """Parse a 24-hour HH:MM value."""
    try:
        hour, minute = (value or "").strip().split(":", 1)
        if len(hour) not in {1, 2} or len(minute) != 2:
            return None
        return time(hour=int(hour), minute=int(minute))
    except (TypeError, ValueError):
        return None


def parse_time_range(value: str | None) -> tuple[time, time] | None:
    """Parse an HH:MM-HH:MM time range."""
    parts = (value or "").strip().replace("–", "-").split("-", 1)
    if len(parts) != 2:
        return None
    start, end = parse_clock(parts[0]), parse_clock(parts[1])
    if start is None or end is None or start == end:
        return None
    return start, end


def parse_timezone(value: str | None) -> str | None:
    """Validate and normalize an IANA timezone name."""
    timezone_name = (value or "").strip()
    if not timezone_name or len(timezone_name) > 64:
        return None
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return None
    return timezone_name


async def load_notification_settings(
    session: AsyncSession, *, user_id: int
) -> NotificationSettings:
    """Load a user's settings, creating defaults when needed."""
    return await get_or_create_notification_settings(session, user_id=user_id)


async def toggle_notification_setting(
    session: AsyncSession, *, settings: NotificationSettings, name: str
) -> NotificationSettings:
    """Toggle one known notification group."""
    field = TOGGLE_FIELDS.get(name)
    if field is None:
        raise ValueError("unknown notification toggle")
    setattr(settings, field, not getattr(settings, field))
    return await save_notification_settings(session, settings)


async def set_notification_time(
    session: AsyncSession,
    *,
    settings: NotificationSettings,
    name: str,
    value: time,
) -> NotificationSettings:
    """Change one known reminder time."""
    field = TIME_FIELDS.get(name)
    if field is None:
        raise ValueError("unknown notification time")
    setattr(settings, field, value)
    return await save_notification_settings(session, settings)


async def set_water_interval(
    session: AsyncSession, *, settings: NotificationSettings, minutes: int
) -> NotificationSettings:
    """Change the water interval within supported limits."""
    if not 30 <= minutes <= 720:
        raise ValueError("water interval must be from 30 to 720 minutes")
    settings.water_interval_minutes = minutes
    return await save_notification_settings(session, settings)


async def set_movement_interval(
    session: AsyncSession, *, settings: NotificationSettings, minutes: int
) -> NotificationSettings:
    """Change the movement reminder interval between 30 minutes and 4 hours."""
    if not 30 <= minutes <= 240:
        raise ValueError("movement interval must be from 30 to 240 minutes")
    settings.movement_interval_minutes = minutes
    return await save_notification_settings(session, settings)


async def set_time_range(
    session: AsyncSession,
    *,
    settings: NotificationSettings,
    name: str,
    start: time,
    end: time,
) -> NotificationSettings:
    """Change the active water window or quiet hours."""
    if start == end:
        raise ValueError("time range cannot be empty")
    if name == "water_window":
        if start > end:
            raise ValueError("water reminder range cannot cross midnight")
        settings.water_start_time = start
        settings.water_end_time = end
    elif name == "quiet":
        settings.quiet_start_time = start
        settings.quiet_end_time = end
    else:
        raise ValueError("unknown time range")
    return await save_notification_settings(session, settings)


async def set_user_timezone(
    session: AsyncSession, *, user: User, timezone_name: str
) -> User:
    """Persist a validated IANA timezone on the user profile."""
    normalized = parse_timezone(timezone_name)
    if normalized is None:
        raise ValueError("unknown timezone")
    user.timezone = normalized
    await session.commit()
    await session.refresh(user)
    return user
