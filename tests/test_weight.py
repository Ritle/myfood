from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, User
from app.repositories.users import get_or_create_user
from app.services.profiles import persist_profile
from app.services.weight import (
    add_weight,
    change_weight,
    get_weight_history,
    parse_weight,
    remove_weight,
    weight_progress_percent,
)


def test_parse_weight_and_progress() -> None:
    assert parse_weight("72,555") == Decimal("72.56")
    assert parse_weight("29.9") is None
    assert parse_weight("nan") is None
    assert weight_progress_percent(Decimal(80), Decimal(75), Decimal(70)) == 50
    assert weight_progress_percent(Decimal(60), Decimal(66), Decimal(70)) == 60
    assert weight_progress_percent(Decimal(80), Decimal(82), Decimal(70)) == 0
    assert weight_progress_percent(Decimal(80), Decimal(68), Decimal(70)) == 100


@pytest.mark.asyncio
async def test_weight_crud_synchronizes_profile_and_checks_ownership() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(
                telegram_id=1,
                first_name="Owner",
                current_weight_kg=Decimal(80),
                target_weight_kg=Decimal(70),
            )
            stranger = User(telegram_id=2, first_name="Stranger")
            session.add_all([owner, stranger])
            await session.commit()
            await session.refresh(owner)
            await session.refresh(stranger)

            older = await add_weight(
                session,
                user=owner,
                weight_kg=Decimal("79.5"),
                measured_at=datetime(2026, 9, 1, 8, tzinfo=UTC),
            )
            latest = await add_weight(
                session,
                user=owner,
                weight_kg=Decimal(78),
                measured_at=datetime(2026, 9, 12, 8, tzinfo=UTC),
            )
            assert owner.current_weight_kg == Decimal("78.00")

            assert (
                await change_weight(
                    session,
                    user=stranger,
                    entry_id=older.id,
                    weight_kg=Decimal(77),
                )
                is None
            )
            changed = await change_weight(
                session,
                user=owner,
                entry_id=older.id,
                weight_kg=Decimal(77),
            )
            assert changed is not None
            assert owner.current_weight_kg == Decimal("78.00")
            assert not await remove_weight(session, user=stranger, entry_id=latest.id)
            assert await remove_weight(session, user=owner, entry_id=latest.id)
            assert owner.current_weight_kg == Decimal("77.00")

            history = await get_weight_history(session, user_id=owner.id)
            assert [entry.weight_kg for entry in history] == [Decimal("77.00")]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_profile_weight_changes_create_history_without_duplicates() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = await get_or_create_user(
                session, telegram_id=1, username=None, first_name="User"
            )
            profile = {
                "gender": "male",
                "birth_date": datetime(1990, 1, 1, tzinfo=UTC).date(),
                "height_cm": Decimal(180),
                "current_weight_kg": Decimal(80),
                "target_weight_kg": Decimal(72),
                "activity_level": "moderate",
                "goal": "lose",
                "daily_calorie_target": 2200,
                "daily_protein_target_g": None,
                "daily_fat_target_g": None,
                "daily_carbs_target_g": None,
                "daily_water_target_ml": 2000,
            }

            await persist_profile(session, telegram_id=user.telegram_id, profile=profile)
            await persist_profile(session, telegram_id=user.telegram_id, profile=profile)
            first_history = await get_weight_history(session, user_id=user.id)
            profile["current_weight_kg"] = Decimal(79)
            updated = await persist_profile(
                session, telegram_id=user.telegram_id, profile=profile
            )
            final_history = await get_weight_history(session, user_id=user.id)

            assert len(first_history) == 1
            assert [entry.weight_kg for entry in final_history] == [
                Decimal("79.00"),
                Decimal("80.00"),
            ]
            assert updated.current_weight_kg == Decimal("79.00")
    finally:
        await engine.dispose()
