from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.handlers.history import parse_meal_callback, parse_user_date
from app.models import Base, Food, User
from app.services.diary import add_diary_entry, get_entries_for_day
from app.services.foods import normalize_food_text
from app.services.history import repeat_food_entry, repeat_meal


def test_parses_numbered_snack_history_callback() -> None:
    assert parse_meal_callback(
        "history:repeat_meal:2026-09-12:snack:2"
    ) == (date(2026, 9, 12), "snack", 2)
    assert parse_meal_callback(
        "history:repeat_meal:2026-09-12:breakfast:0"
    ) == (date(2026, 9, 12), "breakfast", None)
    assert parse_meal_callback(
        "history:repeat_meal:2026-09-12:snack:0"
    ) is None


def test_parses_user_history_date() -> None:
    assert parse_user_date("12.09.2026") == date(2026, 9, 12)
    assert parse_user_date("2026-09-12") is None
    assert parse_user_date("31.02.2026") is None


@pytest.mark.asyncio
async def test_repeating_history_preserves_snapshots_and_ownership() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1, first_name="Owner", timezone="Europe/Moscow")
            stranger = User(telegram_id=2, first_name="Stranger", timezone="Europe/Moscow")
            food = Food(
                name="Каша",
                name_normalized=normalize_food_text("Каша"),
                calories_per_100g=Decimal(100),
                protein_per_100g=Decimal(4),
                fat_per_100g=Decimal(2),
                carbs_per_100g=Decimal(18),
                is_public=True,
            )
            session.add_all([owner, stranger, food])
            await session.commit()
            await session.refresh(owner)
            await session.refresh(stranger)
            await session.refresh(food)
            source = await add_diary_entry(
                session,
                user_id=owner.id,
                food=food,
                meal_type="breakfast",
                weight_grams=Decimal(150),
                eaten_at=datetime(2026, 9, 10, 6, tzinfo=UTC),
            )
            await add_diary_entry(
                session,
                user_id=owner.id,
                food=food,
                meal_type="breakfast",
                weight_grams=Decimal(50),
                eaten_at=datetime(2026, 9, 10, 6, 5, tzinfo=UTC),
            )
            food.calories_per_100g = Decimal(999)
            await session.commit()

            assert (
                await repeat_food_entry(
                    session,
                    user_id=stranger.id,
                    entry_id=source.id,
                    eaten_at=datetime(2026, 9, 12, 8, tzinfo=UTC),
                )
                is None
            )
            copies = await repeat_meal(
                session,
                user_id=owner.id,
                source_day=date(2026, 9, 10),
                meal_type="breakfast",
                timezone_name="Europe/Moscow",
                eaten_at=datetime(2026, 9, 12, 8, tzinfo=UTC),
            )
            current = await get_entries_for_day(
                session,
                user_id=owner.id,
                day=date(2026, 9, 12),
                timezone_name="Europe/Moscow",
            )

            assert len(copies) == 2
            assert [entry.calories for entry in current] == [
                Decimal("150.00"),
                Decimal("50.00"),
            ]
            assert all(entry.user_id == owner.id for entry in current)
    finally:
        await engine.dispose()



@pytest.mark.asyncio
async def test_repeating_one_numbered_snack_can_target_a_new_group() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=11, first_name="Owner")
            food = Food(
                name="Яблоко",
                name_normalized="яблоко",
                calories_per_100g=Decimal(50),
                protein_per_100g=Decimal(0),
                fat_per_100g=Decimal(0),
                carbs_per_100g=Decimal(12),
                is_public=True,
            )
            session.add_all([owner, food])
            await session.commit()
            await session.refresh(owner)
            await session.refresh(food)

            source = await add_diary_entry(
                session,
                user_id=owner.id,
                food=food,
                meal_type="snack",
                snack_number=1,
                weight_grams=Decimal(100),
            )
            copy = await repeat_food_entry(
                session,
                user_id=owner.id,
                entry_id=source.id,
                snack_number=2,
            )

            assert copy is not None
            assert source.snack_number == 1
            assert copy.snack_number == 2
    finally:
        await engine.dispose()
