from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
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
    return await save_profile(session, telegram_id=telegram_id, profile=profile)
