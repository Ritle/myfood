from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_or_create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None,
    first_name: str,
) -> User:
    """Find a Telegram user or persist a new account record."""
    user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        user = User(telegram_id=telegram_id, username=username, first_name=first_name)
        session.add(user)
    else:
        user.username = username
        user.first_name = first_name
    await session.commit()
    await session.refresh(user)
    return user
