from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.handlers.diary import is_diary_search_text
from app.keyboards.diary import diary_portion_keyboard
from app.models import Base, Food, User
from app.services.diary import (
    add_diary_entries,
    add_diary_entry,
    calculate_portion,
    get_entries_for_day,
    local_today,
    remove_diary_entry,
    resize_diary_entry,
    suggest_meal_type,
    summarize_entries,
    utc_day_bounds,
)
from app.services.foods import normalize_food_text
from app.utils.food_batches import parse_food_batch_input
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
    assert parse_portion_input("150г") == Decimal(150)
    assert parse_portion_input("большая тарелка") is None

    button_labels = {
        button.text
        for row in diary_portion_keyboard().keyboard
        for button in row
    }
    assert "🥄 1 чайная ложка ≈5 г" in button_labels
    assert "🥄 1 столовая ложка ≈15 г" in button_labels


def test_parses_multi_food_message_with_optional_meal_and_default_weight() -> None:
    batch = parse_food_batch_input("обед: гречка 150г, курица 180г, огурец")

    assert batch is not None
    assert batch.meal_type == "lunch"
    assert [(item.query, item.weight_grams, item.assumed_weight) for item in batch.items] == [
        ("гречка", Decimal(150), False),
        ("курица", Decimal(180), False),
        ("огурец", Decimal(100), True),
    ]
    lines = parse_food_batch_input("рис 125,5г\nсуп 1 тарелка")
    assert lines is not None
    assert [(item.query, item.weight_grams) for item in lines.items] == [
        ("рис", Decimal("125.5")),
        ("суп", Decimal(250)),
    ]
    assert parse_food_batch_input("огурец") is None


@pytest.mark.asyncio
async def test_add_diary_entries_saves_confirmed_batch_together() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=101, first_name="Owner")
            foods = [sample_food(), sample_food()]
            foods[1].name = "Йогурт"
            foods[1].name_normalized = normalize_food_text("Йогурт")
            session.add_all([owner, *foods])
            await session.commit()
            await session.refresh(owner)
            for food in foods:
                await session.refresh(food)

            entries = await add_diary_entries(
                session,
                user_id=owner.id,
                items=[(foods[0], Decimal(150)), (foods[1], Decimal(200))],
                meal_type="lunch",
            )
            assert len(entries) == 2
            assert {entry.food_id for entry in entries} == {food.id for food in foods}
            assert {entry.weight_grams for entry in entries} == {Decimal(150), Decimal(200)}
            assert entries[0].eaten_at == entries[1].eaten_at
    finally:
        await engine.dispose()


def test_utc_day_bounds_use_user_timezone() -> None:
    start, end = utc_day_bounds(date(2026, 9, 12), "Europe/Moscow")

    assert start == datetime(2026, 9, 11, 21, tzinfo=UTC)
    assert end == datetime(2026, 9, 12, 21, tzinfo=UTC)


def test_custom_day_boundary_shifts_logical_day_and_bounds() -> None:
    boundary = time(3)

    assert local_today(
        "Europe/Moscow",
        day_boundary_time=boundary,
        now=datetime(2026, 9, 19, 22, 30, tzinfo=UTC),
    ) == date(2026, 9, 19)
    assert local_today(
        "Europe/Moscow",
        day_boundary_time=boundary,
        now=datetime(2026, 9, 20, 0, 0, tzinfo=UTC),
    ) == date(2026, 9, 20)

    start, end = utc_day_bounds(
        date(2026, 9, 19),
        "Europe/Moscow",
        day_boundary_time=boundary,
    )
    assert start == datetime(2026, 9, 19, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 9, 20, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 9, 12, 1, 59, tzinfo=UTC), "snack"),
        (datetime(2026, 9, 12, 2, 0, tzinfo=UTC), "breakfast"),
        (datetime(2026, 9, 12, 7, 59, tzinfo=UTC), "breakfast"),
        (datetime(2026, 9, 12, 8, 0, tzinfo=UTC), "lunch"),
        (datetime(2026, 9, 12, 13, 0, tzinfo=UTC), "dinner"),
        (datetime(2026, 9, 12, 19, 0, tzinfo=UTC), "snack"),
    ],
)
def test_suggests_meal_type_from_local_time(now: datetime, expected: str) -> None:
    assert suggest_meal_type("Europe/Moscow", now=now) == expected


def test_diary_search_leaves_meal_and_navigation_buttons_for_their_handlers() -> None:
    assert is_diary_search_text("банан")
    assert not is_diary_search_text("🍳 Завтрак")
    assert not is_diary_search_text("📋 Дневник за сегодня")
    assert not is_diary_search_text("📚 Каталог продуктов")
    assert not is_diary_search_text("↩️ Главное меню")
    assert not is_diary_search_text("/today")


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
