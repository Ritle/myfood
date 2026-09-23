from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, DiaryDay, Food, MealComboSuggestion, MealTemplate, User
from app.services.diary import add_diary_entries
from app.services.meal_combo_suggestions import (
    claim_frequent_meal_suggestion,
    dismiss_frequent_combo_suggestion,
    save_frequent_combo_as_template,
)


def make_food(name: str, calories: int) -> Food:
    return Food(
        name=name,
        name_normalized=name.casefold(),
        calories_per_100g=Decimal(calories),
        protein_per_100g=Decimal(10),
        fat_per_100g=Decimal(5),
        carbs_per_100g=Decimal(10),
        is_public=True,
    )


async def add_breakfast_day(
    session,
    *,
    user: User,
    eggs: Food,
    bread: Food,
    day: date,
    egg_weight: Decimal,
    bread_weight: Decimal,
    active: bool = False,
) -> None:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = None if active else start.replace(hour=23, minute=59)
    session.add(
        DiaryDay(
            user_id=user.id,
            logical_date=day,
            started_at=start,
            ended_at=end,
        )
    )
    await session.commit()
    await add_diary_entries(
        session,
        user_id=user.id,
        items=[(eggs, egg_weight), (bread, bread_weight)],
        meal_type="breakfast",
        eaten_at=start.replace(hour=8),
    )


@pytest.mark.asyncio
async def test_combo_is_offered_after_three_similar_meals_and_saves_template() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=501, first_name="User", timezone="UTC")
            eggs = make_food("Яйца", 150)
            bread = make_food("Хлеб", 250)
            session.add_all([user, eggs, bread])
            await session.commit()
            await session.refresh(user)
            await session.refresh(eggs)
            await session.refresh(bread)

            await add_breakfast_day(
                session,
                user=user,
                eggs=eggs,
                bread=bread,
                day=date(2026, 9, 21),
                egg_weight=Decimal(100),
                bread_weight=Decimal(50),
            )
            await add_breakfast_day(
                session,
                user=user,
                eggs=eggs,
                bread=bread,
                day=date(2026, 9, 22),
                egg_weight=Decimal(110),
                bread_weight=Decimal(55),
            )

            before_threshold = await claim_frequent_meal_suggestion(
                session,
                user=user,
                source_day=date(2026, 9, 22),
                meal_type="breakfast",
                snack_number=None,
            )
            assert before_threshold is None

            await add_breakfast_day(
                session,
                user=user,
                eggs=eggs,
                bread=bread,
                day=date(2026, 9, 23),
                egg_weight=Decimal(105),
                bread_weight=Decimal(60),
                active=True,
            )
            suggestion = await claim_frequent_meal_suggestion(
                session,
                user=user,
                source_day=date(2026, 9, 23),
                meal_type="breakfast",
                snack_number=None,
            )

            assert suggestion is not None
            assert suggestion.occurrence_count == 3
            assert suggestion.name == "Завтрак"
            assert {item.name for item in suggestion.items} == {"Яйца", "Хлеб"}

            template = await save_frequent_combo_as_template(
                session,
                user=user,
                suggestion_id=suggestion.suggestion_id,
            )

            assert template is not None
            assert template.name == "Завтрак"
            assert len(template.items) == 2
            stored = await session.scalar(
                select(MealComboSuggestion).where(
                    MealComboSuggestion.id == suggestion.suggestion_id
                )
            )
            assert stored is not None
            assert stored.status == "saved"
            assert (
                await session.scalar(
                    select(MealTemplate).where(MealTemplate.user_id == user.id)
                )
            ) is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dismissed_combo_is_not_offered_again() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=502, first_name="User", timezone="UTC")
            eggs = make_food("Яйца", 150)
            bread = make_food("Хлеб", 250)
            session.add_all([user, eggs, bread])
            await session.commit()
            await session.refresh(user)
            await session.refresh(eggs)
            await session.refresh(bread)

            for index, day in enumerate(
                [date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23)]
            ):
                await add_breakfast_day(
                    session,
                    user=user,
                    eggs=eggs,
                    bread=bread,
                    day=day,
                    egg_weight=Decimal(100 + index * 5),
                    bread_weight=Decimal(50 + index * 5),
                    active=day == date(2026, 9, 23),
                )

            suggestion = await claim_frequent_meal_suggestion(
                session,
                user=user,
                source_day=date(2026, 9, 23),
                meal_type="breakfast",
                snack_number=None,
            )
            assert suggestion is not None

            assert await dismiss_frequent_combo_suggestion(
                session,
                user_id=user.id,
                suggestion_id=suggestion.suggestion_id,
            )

            repeated = await claim_frequent_meal_suggestion(
                session,
                user=user,
                source_day=date(2026, 9, 23),
                meal_type="breakfast",
                snack_number=None,
            )
            assert repeated is None
    finally:
        await engine.dispose()
