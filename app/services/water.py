from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WaterEntry
from app.repositories.water_entries import (
    create_water_entry,
    delete_water_entry,
    get_owned_water_entry,
    list_water_entries,
    save_water_entry,
)
from app.services.days import resolve_diary_day_bounds

MIN_WATER_ML = 1
MAX_WATER_ML = 10000


def parse_water_amount(value: str | None) -> int | None:
    """Parse a whole millilitre amount from Telegram input."""
    normalized = (value or "").strip().lower()
    if normalized.endswith("мл"):
        normalized = normalized[:-2].strip()
    if normalized.startswith("+"):
        normalized = normalized[1:].strip()
    try:
        amount = int(normalized)
    except ValueError:
        return None
    return amount if MIN_WATER_ML <= amount <= MAX_WATER_ML else None


def validate_water_amount(amount_ml: int) -> None:
    """Validate a positive, practical amount of water."""
    if not MIN_WATER_ML <= amount_ml <= MAX_WATER_ML:
        raise ValueError("Объем воды должен быть от 1 до 10000 мл")


async def add_water(
    session: AsyncSession,
    *,
    user_id: int,
    amount_ml: int,
    drunk_at: datetime | None = None,
) -> WaterEntry:
    """Add one serving of water."""
    validate_water_amount(amount_ml)
    return await create_water_entry(
        session,
        WaterEntry(
            user_id=user_id,
            amount_ml=amount_ml,
            drunk_at=drunk_at or datetime.now(UTC),
        ),
    )


async def get_water_for_day(
    session: AsyncSession, *, user_id: int, day: date, timezone_name: str
) -> list[WaterEntry]:
    """Load water entries using manual day bounds when they exist."""
    start_at, end_at = await resolve_diary_day_bounds(
        session,
        user_id=user_id,
        day=day,
        timezone_name=timezone_name,
    )
    return await list_water_entries(
        session, user_id=user_id, start_at=start_at, end_at=end_at
    )


def total_water(entries: list[WaterEntry]) -> int:
    """Return the total amount in millilitres."""
    return sum(entry.amount_ml for entry in entries)


async def change_water_amount(
    session: AsyncSession, *, user_id: int, entry_id: int, amount_ml: int
) -> WaterEntry | None:
    """Change the amount of an owned water entry."""
    validate_water_amount(amount_ml)
    entry = await get_owned_water_entry(session, entry_id=entry_id, user_id=user_id)
    if entry is None:
        return None
    entry.amount_ml = amount_ml
    return await save_water_entry(session, entry)


async def load_owned_water(
    session: AsyncSession, *, user_id: int, entry_id: int
) -> WaterEntry | None:
    """Load one water entry after checking ownership."""
    return await get_owned_water_entry(session, entry_id=entry_id, user_id=user_id)


async def remove_water(session: AsyncSession, *, user_id: int, entry_id: int) -> bool:
    """Delete an owned water entry and report whether it existed."""
    entry = await get_owned_water_entry(session, entry_id=entry_id, user_id=user_id)
    if entry is None:
        return False
    await delete_water_entry(session, entry)
    return True
