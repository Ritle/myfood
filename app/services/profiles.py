from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, WeightEntry
from app.repositories.profiles import get_user_by_telegram_id, save_profile


async def get_profile(session: AsyncSession, telegram_id: int) -> User | None:
    """Load the stored profile for a Telegram user."""
    return await get_user_by_telegram_id(session, telegram_id)


async def persist_profile(
    session: AsyncSession,
    *,
    telegram_id: int,
    profile: dict[str, date | str | int | Decimal | None],
) -> User:
    """Save a validated profile after the user completes the questionnaire."""
    existing = await get_user_by_telegram_id(session, telegram_id)
    previous_weight = existing.current_weight_kg if existing is not None else None
    user = await save_profile(session, telegram_id=telegram_id, profile=profile)
    current_weight = user.current_weight_kg
    if current_weight is not None and current_weight != previous_weight:
        session.add(
            WeightEntry(
                user_id=user.id,
                weight_kg=current_weight,
                measured_at=datetime.now(UTC),
            )
        )
    await session.commit()
    await session.refresh(user)
    return user
