from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, User
from app.services.water import (
    add_water,
    change_water_amount,
    get_water_for_day,
    parse_water_amount,
    remove_water,
    total_water,
)


def test_parse_water_amount_accepts_supported_forms() -> None:
    assert parse_water_amount("300") == 300
    assert parse_water_amount("+500 мл") == 500
    assert parse_water_amount("0") is None
    assert parse_water_amount("10.5") is None
    assert parse_water_amount("10001") is None


@pytest.mark.asyncio
async def test_water_crud_uses_local_day_and_checks_ownership() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1, first_name="Owner", timezone="Europe/Moscow")
            stranger = User(telegram_id=2, first_name="Stranger", timezone="Europe/Moscow")
            session.add_all([owner, stranger])
            await session.commit()
            await session.refresh(owner)
            await session.refresh(stranger)

            first = await add_water(
                session,
                user_id=owner.id,
                amount_ml=200,
                drunk_at=datetime(2026, 9, 11, 22, tzinfo=UTC),
            )
            await add_water(
                session,
                user_id=owner.id,
                amount_ml=300,
                drunk_at=datetime(2026, 9, 12, 20, 59, tzinfo=UTC),
            )
            await add_water(
                session,
                user_id=owner.id,
                amount_ml=500,
                drunk_at=datetime(2026, 9, 12, 21, tzinfo=UTC),
            )

            entries = await get_water_for_day(
                session,
                user_id=owner.id,
                day=date(2026, 9, 12),
                timezone_name="Europe/Moscow",
            )
            assert total_water(entries) == 500
            assert (
                await change_water_amount(
                    session,
                    user_id=stranger.id,
                    entry_id=first.id,
                    amount_ml=400,
                )
                is None
            )
            changed = await change_water_amount(
                session,
                user_id=owner.id,
                entry_id=first.id,
                amount_ml=250,
            )
            assert changed is not None
            assert changed.amount_ml == 250
            assert not await remove_water(session, user_id=stranger.id, entry_id=first.id)
            assert await remove_water(session, user_id=owner.id, entry_id=first.id)
    finally:
        await engine.dispose()
