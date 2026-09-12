from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    """Return a user's profile by Telegram account ID."""
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def save_profile(
    session: AsyncSession,
    *,
    telegram_id: int,
    profile: dict[str, date | str | int | Decimal | None],
) -> User:
    """Persist the collected profile values and mark setup complete."""
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        raise LookupError("Telegram user was not initialized; send /start first")
    for field, value in profile.items():
        setattr(user, field, value)
    user.profile_completed_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(user)
    return user
