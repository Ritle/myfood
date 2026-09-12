import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, NotificationSettings, User
from app.repositories.users import get_or_create_user


@pytest.mark.asyncio
async def test_get_or_create_user_updates_telegram_profile_without_duplicates() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)

        async with session_factory() as session:
            first = await get_or_create_user(
                session, telegram_id=123, username="old_name", first_name="Alex"
            )
            first_id = first.id
            second = await get_or_create_user(
                session, telegram_id=123, username="new_name", first_name="Alexandra"
            )
            count = await session.scalar(
                select(func.count()).select_from(User).where(User.telegram_id == 123)
            )
            settings_count = await session.scalar(
                select(func.count())
                .select_from(NotificationSettings)
                .where(NotificationSettings.user_id == first_id)
            )

        assert second.id == first_id
        assert second.username == "new_name"
        assert second.first_name == "Alexandra"
        assert count == 1
        assert settings_count == 1
    finally:
        await engine.dispose()
