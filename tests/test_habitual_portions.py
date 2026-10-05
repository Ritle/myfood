from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.keyboards.diary import diary_portion_keyboard
from app.models import Base, Food, User
from app.services.diary import add_diary_entry
from app.services.foods import habitual_food_portion, habitual_food_portions
from app.utils.portions import parse_portion_input


def make_food(name: str = "Творог") -> Food:
    return Food(
        name=name,
        name_normalized=name.casefold(),
        calories_per_100g=Decimal(120),
        protein_per_100g=Decimal(18),
        fat_per_100g=Decimal(5),
        carbs_per_100g=Decimal(3),
        is_public=True,
    )


@pytest.mark.asyncio
async def test_habitual_portion_uses_stable_cluster_and_ignores_outlier() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=601, first_name="User")
            food = make_food()
            session.add_all([user, food])
            await session.commit()
            await session.refresh(user)
            await session.refresh(food)

            start = datetime(2026, 9, 1, 8, tzinfo=UTC)
            for index, weight in enumerate(
                [Decimal(180), Decimal(190), Decimal(200), Decimal(185), Decimal(195), Decimal(400)]
            ):
                await add_diary_entry(
                    session,
                    user_id=user.id,
                    food=food,
                    meal_type="breakfast",
                    weight_grams=weight,
                    eaten_at=start + timedelta(days=index),
                )

            portion = await habitual_food_portion(
                session,
                user_id=user.id,
                food_id=food.id,
            )

        assert portion == Decimal(190)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_habitual_portion_is_not_shown_for_unstable_history() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=602, first_name="User")
            food = make_food("Йогурт")
            session.add_all([user, food])
            await session.commit()
            await session.refresh(user)
            await session.refresh(food)

            start = datetime(2026, 9, 1, 8, tzinfo=UTC)
            for index, weight in enumerate(
                [Decimal(50), Decimal(100), Decimal(200), Decimal(400), Decimal(800)]
            ):
                await add_diary_entry(
                    session,
                    user_id=user.id,
                    food=food,
                    meal_type="snack",
                    snack_number=index + 1,
                    weight_grams=weight,
                    eaten_at=start + timedelta(days=index),
                )

            portion = await habitual_food_portion(
                session,
                user_id=user.id,
                food_id=food.id,
            )

        assert portion is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_habitual_portion_requires_at_least_three_observations() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=603, first_name="User")
            food = make_food("Кефир")
            session.add_all([user, food])
            await session.commit()
            await session.refresh(user)
            await session.refresh(food)

            for weight in (Decimal(180), Decimal(190)):
                await add_diary_entry(
                    session,
                    user_id=user.id,
                    food=food,
                    meal_type="breakfast",
                    weight_grams=weight,
                )

            portion = await habitual_food_portion(
                session,
                user_id=user.id,
                food_id=food.id,
            )

        assert portion is None
    finally:
        await engine.dispose()


def test_habitual_portion_is_first_keyboard_button_and_remains_parseable() -> None:
    keyboard = diary_portion_keyboard(
        "breakfast",
        habitual_portion=Decimal(190),
    )

    assert keyboard.keyboard[0][0].text == "⭐ 190 г"
    assert parse_portion_input(keyboard.keyboard[0][0].text) == Decimal(190)



@pytest.mark.asyncio
async def test_habitual_portions_batch_matches_single_food_logic() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=604, first_name="User")
            cottage = make_food("Творог")
            yogurt = make_food("Йогурт")
            session.add_all([user, cottage, yogurt])
            await session.commit()
            await session.refresh(user)
            await session.refresh(cottage)
            await session.refresh(yogurt)

            start = datetime(2026, 9, 1, 8, tzinfo=UTC)
            for index, weight in enumerate(
                [Decimal(180), Decimal(190), Decimal(200), Decimal(190)]
            ):
                await add_diary_entry(
                    session,
                    user_id=user.id,
                    food=cottage,
                    meal_type="breakfast",
                    weight_grams=weight,
                    eaten_at=start + timedelta(days=index),
                )
            for index, weight in enumerate(
                [Decimal(50), Decimal(100), Decimal(250)]
            ):
                await add_diary_entry(
                    session,
                    user_id=user.id,
                    food=yogurt,
                    meal_type="snack",
                    snack_number=index + 1,
                    weight_grams=weight,
                    eaten_at=start + timedelta(days=index),
                )

            portions = await habitual_food_portions(
                session,
                user_id=user.id,
                foods=[cottage, yogurt],
            )

        assert portions == {cottage.id: Decimal(190)}
    finally:
        await engine.dispose()
