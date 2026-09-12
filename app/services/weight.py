from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, WeightEntry
from app.repositories.weight_entries import get_owned_weight_entry, list_weight_entries
from app.utils.numbers import parse_decimal

MIN_WEIGHT_KG = Decimal(30)
MAX_WEIGHT_KG = Decimal(350)
WEIGHT_STEP = Decimal("0.01")


def parse_weight(value: str | None) -> Decimal | None:
    """Parse and validate a weight in kilograms."""
    weight = parse_decimal(value)
    if weight is None or not MIN_WEIGHT_KG <= weight <= MAX_WEIGHT_KG:
        return None
    return weight.quantize(WEIGHT_STEP, rounding=ROUND_HALF_UP)


def weight_progress_percent(start: Decimal, current: Decimal, target: Decimal) -> int:
    """Calculate bounded progress from the first measurement to the target."""
    distance = target - start
    if distance == 0:
        return 100 if current == target else 0
    progress = ((current - start) / distance * Decimal(100)).quantize(
        Decimal(1), rounding=ROUND_HALF_UP
    )
    return min(100, max(0, int(progress)))


async def add_weight(
    session: AsyncSession,
    *,
    user: User,
    weight_kg: Decimal,
    measured_at: datetime | None = None,
) -> WeightEntry:
    """Add a measurement and update the user's current weight atomically."""
    normalized = require_weight(weight_kg)
    entry = WeightEntry(
        user_id=user.id,
        weight_kg=normalized,
        measured_at=measured_at or datetime.now(UTC),
    )
    session.add(entry)
    user.current_weight_kg = normalized
    await session.commit()
    await session.refresh(entry)
    await session.refresh(user)
    return entry


async def get_weight_history(session: AsyncSession, *, user_id: int) -> list[WeightEntry]:
    """Load all measurements for progress calculation and history."""
    return await list_weight_entries(session, user_id=user_id)


async def load_owned_weight(
    session: AsyncSession, *, user_id: int, entry_id: int
) -> WeightEntry | None:
    """Load one measurement after checking ownership."""
    return await get_owned_weight_entry(session, entry_id=entry_id, user_id=user_id)


async def change_weight(
    session: AsyncSession,
    *,
    user: User,
    entry_id: int,
    weight_kg: Decimal,
) -> WeightEntry | None:
    """Change an owned measurement and synchronize the current weight if needed."""
    normalized = require_weight(weight_kg)
    entry = await get_owned_weight_entry(session, entry_id=entry_id, user_id=user.id)
    if entry is None:
        return None
    history = await list_weight_entries(session, user_id=user.id)
    is_latest = bool(history and history[0].id == entry.id)
    entry.weight_kg = normalized
    if is_latest:
        user.current_weight_kg = normalized
    await session.commit()
    await session.refresh(entry)
    await session.refresh(user)
    return entry


async def remove_weight(session: AsyncSession, *, user: User, entry_id: int) -> bool:
    """Delete an owned measurement and synchronize the current weight."""
    entry = await get_owned_weight_entry(session, entry_id=entry_id, user_id=user.id)
    if entry is None:
        return False
    await session.delete(entry)
    await session.flush()
    history = await list_weight_entries(session, user_id=user.id)
    user.current_weight_kg = history[0].weight_kg if history else None
    await session.commit()
    await session.refresh(user)
    return True


def require_weight(weight_kg: Decimal) -> Decimal:
    """Validate and normalize a programmatic weight value."""
    if not weight_kg.is_finite() or not MIN_WEIGHT_KG <= weight_kg <= MAX_WEIGHT_KG:
        raise ValueError("Вес должен быть от 30 до 350 кг")
    return weight_kg.quantize(WEIGHT_STEP, rounding=ROUND_HALF_UP)
