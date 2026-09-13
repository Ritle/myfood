from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.keyboards.diary import diary_portion_keyboard
from app.models import Base, Food, User
from app.services.diary import (
    add_diary_entry,
    calculate_portion,
    get_entries_for_day,
    remove_diary_entry,
    resize_diary_entry,
    summarize_entries,
    utc_day_bounds,
)
from app.services.foods import normalize_food_text
from app.utils.portions import parse_portion_input


def sample_food() -> Food:
    return Food(
        name="Творог",
        name_normalized=normalize_food_text("Творог"),
        calories_per_100g=Decimal(145),
        protein_per_100g=Decimal(16),
        fat_per_100g=Decimal(5),
        carbs_per_100g=Decimal(3),
        is_public=True,
    )


def test_calculates_portion_with_consistent_rounding() -> None:
    portion = calculate_portion(sample_food(), Decimal(180))

    assert portion.calories == Decimal("261.00")
    assert portion.protein == Decimal("28.80")
    assert portion.fat == Decimal("9.00")
    assert portion.carbs == Decimal("5.40")


def test_quick_portion_input_supports_common_measures_and_gram_weights() -> None:
    assert parse_portion_input("🥛 1 стакан ≈200 г") == Decimal(200)
    assert parse_portion_input("полстакана") == Decimal(100)
    assert parse_portion_input("2 ст. л.") == Decimal(30)
    assert parse_portion_input("1 чайная ложка") == Decimal(5)
    assert parse_portion_input("1 столовую ложку") == Decimal(15)
    assert parse_portion_input("2 чайных ложки") == Decimal(10)
    assert parse_portion_input("2,5 стакана") == Decimal(500)
    assert parse_portion_input("125,5") == Decimal("125.5")
    assert parse_portion_input("большая тарелка") is None

    button_labels = {
        button.text
        for row in diary_portion_keyboard().keyboard
        for button in row
    }
    assert "🥄 1 чайная ложка ≈5 г" in button_labels
    assert "🥄 1 столовая ложка ≈15 г" in button_labels


def test_utc_day_bounds_use_user_timezone() -> None:
    start, end = utc_day_bounds(date(2026, 9, 12), "Europe/Moscow")

    assert start == datetime(2026, 9, 11, 21, tzinfo=UTC)
    assert end == datetime(2026, 9, 12, 21, tzinfo=UTC)


@pytest.mark.asyncio
async def test_diary_crud_preserves_snapshot_and_checks_ownership() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1, first_name="Owner", timezone="Europe/Moscow")
            stranger = User(telegram_id=2, first_name="Stranger", timezone="Europe/Moscow")
            food = sample_food()
            session.add_all([owner, stranger, food])
            await session.commit()
            await session.refresh(owner)
            await session.refresh(stranger)
            await session.refresh(food)

            entry = await add_diary_entry(
                session,
                user_id=owner.id,
                food=food,
                meal_type="breakfast",
                weight_grams=Decimal(180),
                eaten_at=datetime(2026, 9, 12, 8, tzinfo=UTC),
            )
            food.calories_per_100g = Decimal(999)
            await session.commit()

            entries = await get_entries_for_day(
                session,
                user_id=owner.id,
                day=date(2026, 9, 12),
                timezone_name="Europe/Moscow",
            )
            assert summarize_entries(entries).calories == Decimal("261.00")
            assert (
                await resize_diary_entry(
                    session,
                    user_id=stranger.id,
                    entry_id=entry.id,
                    new_weight_grams=Decimal(200),
                )
                is None
            )
            resized = await resize_diary_entry(
                session,
                user_id=owner.id,
                entry_id=entry.id,
                new_weight_grams=Decimal(200),
            )
            assert resized is not None
            assert resized.calories == Decimal("290.00")
            assert not await remove_diary_entry(session, user_id=stranger.id, entry_id=entry.id)
            assert await remove_diary_entry(session, user_id=owner.id, entry_id=entry.id)
    finally:
        await engine.dispose()
