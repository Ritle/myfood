from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Food, FoodEntry, User
from app.services.food_guidance import (
    dominant_deficit,
    format_remaining_guidance,
    recommend_foods_for_today,
    remaining_targets,
)


def diary_entry(
    *,
    calories: int,
    protein: int,
    fat: int,
    carbs: int,
) -> FoodEntry:
    return FoodEntry(
        meal_type="lunch",
        weight_grams=Decimal(100),
        is_full_serving=False,
        calories=Decimal(calories),
        protein=Decimal(protein),
        fat=Decimal(fat),
        carbs=Decimal(carbs),
    )


def user_with_targets() -> User:
    return User(
        telegram_id=701,
        first_name="User",
        daily_calorie_target=2000,
        daily_protein_target_g=Decimal(120),
        daily_fat_target_g=Decimal(70),
        daily_carbs_target_g=Decimal(250),
    )


def test_remaining_guidance_prioritizes_largest_relative_macro_deficit() -> None:
    user = user_with_targets()
    entries = [
        diary_entry(
            calories=1200,
            protein=30,
            fat=65,
            carbs=180,
        )
    ]

    remaining = remaining_targets(user, entries)
    text = format_remaining_guidance(user, entries)

    assert remaining == {
        "calories": Decimal(800),
        "protein": Decimal(90),
        "fat": Decimal(5),
        "carbs": Decimal(70),
    }
    assert dominant_deficit(user, entries) == "protein"
    assert text is not None
    assert "🍽 Что осталось на сегодня:" in text
    assert "Б: ~90 г" in text
    assert "сильнее всего не хватает — белок" in text
    assert "жиры почти закрыты" in text


@pytest.mark.asyncio
async def test_recommendations_prefer_lean_protein_when_protein_is_missing() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = user_with_targets()
            chicken = Food(
                name="Куриная грудка",
                name_normalized="куриная грудка",
                calories_per_100g=Decimal(165),
                protein_per_100g=Decimal(31),
                fat_per_100g=Decimal("3.6"),
                carbs_per_100g=Decimal(0),
                is_public=True,
            )
            cheese = Food(
                name="Жирный сыр",
                name_normalized="жирный сыр",
                calories_per_100g=Decimal(400),
                protein_per_100g=Decimal(25),
                fat_per_100g=Decimal(33),
                carbs_per_100g=Decimal(2),
                is_public=True,
            )
            rice = Food(
                name="Рис",
                name_normalized="рис",
                calories_per_100g=Decimal(130),
                protein_per_100g=Decimal("2.7"),
                fat_per_100g=Decimal("0.3"),
                carbs_per_100g=Decimal(28),
                is_public=True,
            )
            unused_ideal = Food(
                name="Идеальный протеин",
                name_normalized="идеальный протеин",
                calories_per_100g=Decimal(100),
                protein_per_100g=Decimal(40),
                fat_per_100g=Decimal(0),
                carbs_per_100g=Decimal(0),
                is_public=True,
            )
            session.add_all([user, chicken, cheese, rice, unused_ideal])
            await session.flush()

            session.add_all(
                [
                    FoodEntry(
                        user_id=user.id,
                        food_id=chicken.id,
                        meal_type="dinner",
                        weight_grams=Decimal(150),
                        is_full_serving=False,
                        calories=Decimal("247.5"),
                        protein=Decimal("46.5"),
                        fat=Decimal("5.4"),
                        carbs=Decimal(0),
                        eaten_at=datetime(2026, 9, 20, 18, 0, tzinfo=UTC),
                    ),
                    FoodEntry(
                        user_id=user.id,
                        food_id=cheese.id,
                        meal_type="snack",
                        snack_number=1,
                        weight_grams=Decimal(50),
                        is_full_serving=False,
                        calories=Decimal(200),
                        protein=Decimal("12.5"),
                        fat=Decimal("16.5"),
                        carbs=Decimal(1),
                        eaten_at=datetime(2026, 9, 21, 14, 0, tzinfo=UTC),
                    ),
                ]
            )
            await session.commit()
            await session.refresh(user)

            entries = [
                diary_entry(
                    calories=1600,
                    protein=40,
                    fat=66,
                    carbs=210,
                )
            ]
            recommendations = await recommend_foods_for_today(
                session,
                user=user,
                entries=entries,
                limit=3,
            )

        assert recommendations
        assert recommendations[0].food.name == "Куриная грудка"
        assert recommendations[0].protein > recommendations[0].fat
        assert {item.food.name for item in recommendations} <= {
            "Куриная грудка",
            "Жирный сыр",
        }
        assert "Идеальный протеин" not in {
            item.food.name for item in recommendations
        }
        assert "Рис" not in {item.food.name for item in recommendations}
    finally:
        await engine.dispose()
