from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NotificationSettings, User


async def get_or_create_notification_settings(
    session: AsyncSession, *, user_id: int
) -> NotificationSettings:
    """Load notification preferences or create defaults for a user."""
    settings = await session.scalar(
        select(NotificationSettings).where(NotificationSettings.user_id == user_id)
    )
    if settings is None:
        settings = NotificationSettings(user_id=user_id)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    return settings


async def save_notification_settings(
    session: AsyncSession, settings: NotificationSettings
) -> NotificationSettings:
    """Persist changed notification preferences."""
    await session.commit()
    await session.refresh(settings)
    return settings


async def list_users_with_notification_settings(
    session: AsyncSession,
) -> list[tuple[User, NotificationSettings]]:
    """Return users that have a notification schedule."""
    rows = await session.execute(
        select(User, NotificationSettings).join(
            NotificationSettings, NotificationSettings.user_id == User.id
        )
    )
    return list(rows.tuples())
