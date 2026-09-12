from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.notifications import mark_notification_suppressed, try_create_notification


@dataclass(frozen=True, slots=True)
class CalorieAlert:
    """A newly claimed calorie alert ready for delivery."""

    log_id: int
    level: str
    total: Decimal
    target: Decimal


def crossed_calorie_levels(
    *,
    previous_total: Decimal,
    current_total: Decimal,
    target: Decimal,
    warning_ratio: Decimal,
) -> list[str]:
    """Return calorie levels crossed by one diary mutation, from low to high."""
    if target <= 0 or not Decimal(0) < warning_ratio < Decimal(1):
        raise ValueError("invalid calorie alert configuration")
    if current_total <= previous_total:
        return []
    levels: list[str] = []
    warning_target = target * warning_ratio
    if previous_total < warning_target <= current_total:
        levels.append("warning")
    if previous_total < target <= current_total:
        levels.append("goal")
    if previous_total <= target < current_total:
        levels.append("exceeded")
    return levels


async def claim_calorie_alert(
    session: AsyncSession,
    *,
    user_id: int,
    local_date: date,
    previous_total: Decimal,
    current_total: Decimal,
    target: Decimal,
    warning_ratio: Decimal,
) -> CalorieAlert | None:
    """Deduplicate crossed thresholds and return only the highest new alert."""
    claimed: list[tuple[str, int]] = []
    for level in crossed_calorie_levels(
        previous_total=previous_total,
        current_total=current_total,
        target=target,
        warning_ratio=warning_ratio,
    ):
        key = f"calorie:{user_id}:{local_date.isoformat()}:{level}"
        log = await try_create_notification(
            session,
            user_id=user_id,
            notification_type=f"calorie_{level}",
            local_date=local_date,
            deduplication_key=key,
        )
        if log is not None:
            claimed.append((level, log.id))
    if not claimed:
        return None
    for _, suppressed_log_id in claimed[:-1]:
        await mark_notification_suppressed(session, suppressed_log_id)
    level, log_id = claimed[-1]
    return CalorieAlert(log_id=log_id, level=level, total=current_total, target=target)
