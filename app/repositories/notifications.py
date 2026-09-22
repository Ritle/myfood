from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NotificationLog, User


async def try_create_notification(
    session: AsyncSession,
    *,
    user_id: int,
    notification_type: str,
    local_date: date,
    deduplication_key: str,
    scheduled_for: datetime | None = None,
) -> NotificationLog | None:
    """Create a pending notification unless its logical key already exists."""
    log = NotificationLog(
        user_id=user_id,
        notification_type=notification_type,
        local_date=local_date,
        deduplication_key=deduplication_key,
        status="pending",
        scheduled_for=scheduled_for or datetime.now(UTC),
    )
    try:
        async with session.begin_nested():
            session.add(log)
            await session.flush()
    except IntegrityError:
        await session.commit()
        return None
    await session.commit()
    await session.refresh(log)
    return log


async def mark_notification_sent(session: AsyncSession, log_id: int) -> None:
    """Mark a successfully delivered notification."""
    log = await session.get(NotificationLog, log_id)
    if log is None:
        return
    log.status = "sent"
    log.sent_at = datetime.now(UTC)
    await session.commit()


async def mark_notification_suppressed(session: AsyncSession, log_id: int) -> None:
    """Mark a lower-priority claimed notification that should not be delivered."""
    log = await session.get(NotificationLog, log_id)
    if log is None:
        return
    log.status = "suppressed"
    await session.commit()


async def record_notification_failure(
    session: AsyncSession,
    log_id: int,
    *,
    error: str,
    now: datetime,
    max_attempts: int,
    retry_delay: timedelta,
) -> None:
    """Record a failed attempt and either reschedule or stop retrying."""
    log = await session.get(NotificationLog, log_id)
    if log is None:
        return
    log.attempt_count += 1
    log.last_error = error[:500]
    if log.attempt_count >= max_attempts:
        log.status = "failed"
    else:
        log.scheduled_for = now + retry_delay
    await session.commit()


async def get_owned_notification(
    session: AsyncSession, *, log_id: int, user_id: int
) -> NotificationLog | None:
    """Load a notification only when it belongs to the user."""
    return await session.scalar(
        select(NotificationLog).where(
            NotificationLog.id == log_id, NotificationLog.user_id == user_id
        )
    )


async def notification_key_exists(session: AsyncSession, key: str) -> bool:
    """Report whether a logical notification key was already recorded."""
    return (
        await session.scalar(
            select(NotificationLog.id).where(NotificationLog.deduplication_key == key)
        )
        is not None
    )


async def list_due_notifications(
    session: AsyncSession, *, now: datetime
) -> list[tuple[NotificationLog, User]]:
    """Return due scheduled notifications and their Telegram recipients."""
    rows = await session.execute(
        select(NotificationLog, User)
        .join(User, User.id == NotificationLog.user_id)
        .where(
            NotificationLog.status == "pending",
            NotificationLog.scheduled_for <= now,
            NotificationLog.notification_type.in_(
                [
                    "meal:breakfast",
                    "meal:lunch",
                    "meal:dinner",
                    "meal_snooze:breakfast",
                    "meal_snooze:lunch",
                    "meal_snooze:dinner",
                    "water",
                    "movement",
                    "morning_report",
                    "nutrition_meal:breakfast",
                    "nutrition_meal:lunch",
                    "nutrition_meal:dinner",
                    "nutrition_summary",
                ]
            ),
        )
        .order_by(NotificationLog.scheduled_for, NotificationLog.id)
    )
    return list(rows.tuples())


async def suppress_pending_meal_notifications(
    session: AsyncSession, *, user_id: int, local_date: date, meal_type: str
) -> None:
    """Suppress pending initial and snoozed reminders for one meal and day."""
    await session.execute(
        update(NotificationLog)
        .where(
            NotificationLog.user_id == user_id,
            NotificationLog.local_date == local_date,
            NotificationLog.status == "pending",
            NotificationLog.notification_type.in_(
                [f"meal:{meal_type}", f"meal_snooze:{meal_type}"]
            ),
        )
        .values(status="suppressed")
    )
    await session.commit()



async def record_nutrition_meal_review_sent(
    session: AsyncSession,
    *,
    user_id: int,
    local_date: date,
    meal_type: str,
    latest_eaten_at: datetime,
) -> NotificationLog:
    """Record an explicit meal review and suppress pending automatic duplicates."""
    notification_type = f"nutrition_meal:{meal_type}"
    deduplication_key = (
        f"nutrition_meal:{user_id}:{local_date.isoformat()}:"
        f"{int(latest_eaten_at.timestamp())}"
    )

    await session.execute(
        update(NotificationLog)
        .where(
            NotificationLog.user_id == user_id,
            NotificationLog.local_date == local_date,
            NotificationLog.status == "pending",
            NotificationLog.notification_type == notification_type,
        )
        .values(status="suppressed")
    )

    log = await session.scalar(
        select(NotificationLog).where(
            NotificationLog.deduplication_key == deduplication_key
        )
    )
    now = datetime.now(UTC)
    if log is None:
        log = NotificationLog(
            user_id=user_id,
            notification_type=notification_type,
            local_date=local_date,
            deduplication_key=deduplication_key,
            status="sent",
            scheduled_for=now,
            sent_at=now,
        )
        session.add(log)
    else:
        log.status = "sent"
        log.sent_at = now
        log.last_error = None
    await session.commit()
    await session.refresh(log)
    return log
