from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, User
from app.services.nutrition_recalculation import (
    apply_nutrition_recalculation,
    build_nutrition_recalculation,
    mark_nutrition_recalculation_prompted,
    nutrition_recalculation_due,
)


def configured_user(*, weight: Decimal = Decimal(90)) -> User:
    return User(
        telegram_id=9001,
        first_name="User",
        gender="male",
        birth_date=date(1990, 1, 1),
        height_cm=Decimal(180),
        current_weight_kg=weight,
        target_weight_kg=Decimal(80),
        activity_level="moderate",
        goal="lose",
        daily_calorie_target=2200,
        daily_protein_target_g=Decimal(144),
        daily_fat_target_g=Decimal(72),
        daily_carbs_target_g=Decimal(244),
        nutrition_target_weight_kg=Decimal(90),
        nutrition_recalc_prompt_weight_kg=Decimal(90),
    )


def test_recalculation_becomes_due_after_three_kg() -> None:
    user = configured_user()

    assert not nutrition_recalculation_due(user, Decimal("87.01"))
    assert nutrition_recalculation_due(user, Decimal(87))

    preview = build_nutrition_recalculation(
        user,
        Decimal(87),
        today=date(2026, 9, 22),
    )
    assert preview is not None
    assert preview.weight_kg == Decimal(87)
    assert preview.calories != user.daily_calorie_target


@pytest.mark.asyncio
async def test_declined_prompt_anchor_prevents_repeated_prompt_until_next_three_kg() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = configured_user(weight=Decimal(87))
            session.add(user)
            await session.commit()
            await session.refresh(user)

            assert nutrition_recalculation_due(user, Decimal(87))
            await mark_nutrition_recalculation_prompted(
                session,
                user=user,
                weight_kg=Decimal(87),
            )

            assert not nutrition_recalculation_due(user, Decimal(86))
            assert nutrition_recalculation_due(user, Decimal(84))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_confirmed_recalculation_updates_targets_and_rejects_stale_weight() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = configured_user(weight=Decimal(87))
            session.add(user)
            await session.commit()
            await session.refresh(user)

            stale = await apply_nutrition_recalculation(
                session,
                user=user,
                expected_weight_kg=Decimal(86),
            )
            assert stale is None
            assert user.daily_calorie_target == 2200

            result = await apply_nutrition_recalculation(
                session,
                user=user,
                expected_weight_kg=Decimal(87),
            )
            assert result is not None
            assert user.daily_calorie_target == result.calories
            assert user.daily_protein_target_g == Decimal(result.protein)
            assert user.daily_fat_target_g == Decimal(result.fat)
            assert user.daily_carbs_target_g == Decimal(result.carbs)
            assert user.nutrition_target_weight_kg == Decimal("87.00")
            assert user.nutrition_recalc_prompt_weight_kg == Decimal("87.00")
    finally:
        await engine.dispose()
