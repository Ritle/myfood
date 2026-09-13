from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.keyboards.diary import diary_source_actions
from app.keyboards.history import history_keyboard
from app.models import Base, Food, FoodEntry, User
from app.services.foods import normalize_food_text
from app.services.meal_templates import (
    create_meal_template,
    delete_owned_meal_template,
    list_user_meal_templates,
    load_owned_meal_template,
    validate_template_name,
)


def make_food(name: str) -> Food:
    return Food(
        name=name,
        name_normalized=normalize_food_text(name),
        calories_per_100g=Decimal(100),
        protein_per_100g=Decimal(5),
        fat_per_100g=Decimal(2),
        carbs_per_100g=Decimal(15),
        is_public=True,
    )


def test_template_name_collapses_whitespace_and_is_case_insensitive() -> None:
    assert validate_template_name("  Овсянка   с бананом ") == (
        "Овсянка с бананом",
        "овсянка с бананом",
    )
    with pytest.raises(ValueError, match="от 2 до 50"):
        validate_template_name(" ")
    with pytest.raises(ValueError, match="от 2 до 50"):
        validate_template_name("x" * 51)


@pytest.mark.asyncio
async def test_templates_preserve_portions_and_enforce_owner_access() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=301, first_name="Owner")
            stranger = User(telegram_id=302, first_name="Stranger")
            foods = [make_food("Овсянка"), make_food("Банан")]
            session.add_all([owner, stranger, *foods])
            await session.commit()
            await session.refresh(owner)
            await session.refresh(stranger)
            for food in foods:
                await session.refresh(food)

            template = await create_meal_template(
                session,
                user_id=owner.id,
                name="Завтрак",
                meal_type="breakfast",
                items=[(foods[0], Decimal(180)), (foods[1], Decimal(80))],
            )
            loaded = await load_owned_meal_template(
                session, user_id=owner.id, template_id=template.id
            )
            assert loaded is not None
            assert [(item.food.name, item.weight_grams) for item in loaded.items] == [
                ("Овсянка", Decimal("180.00")),
                ("Банан", Decimal("80.00")),
            ]
            assert await load_owned_meal_template(
                session, user_id=stranger.id, template_id=template.id
            ) is None
            assert not await delete_owned_meal_template(
                session, user_id=stranger.id, template_id=template.id
            )
            assert [item.name for item in await list_user_meal_templates(
                session, user_id=owner.id
            )] == ["Завтрак"]

            with pytest.raises(ValueError, match="уже есть шаблон"):
                await create_meal_template(
                    session,
                    user_id=owner.id,
                    name="  ЗАВТРАК ",
                    meal_type="breakfast",
                    items=[(foods[0], Decimal(100))],
                )

            assert await delete_owned_meal_template(
                session, user_id=owner.id, template_id=template.id
            )
            assert await list_user_meal_templates(session, user_id=owner.id) == []
    finally:
        await engine.dispose()


def test_template_controls_are_attached_to_history_and_diary() -> None:
    food = make_food("Каша")
    entry = FoodEntry(id=5, meal_type="breakfast", food=food)
    history = history_keyboard(
        day=date(2026, 9, 13),
        today=date(2026, 9, 13),
        visible_entries=[entry],
        all_entries=[entry],
        page=0,
        total_pages=1,
    )
    history_callbacks = {
        button.callback_data
        for row in history.inline_keyboard
        for button in row
    }
    assert "history:save_meal:2026-09-13:breakfast" in history_callbacks

    diary = diary_source_actions("breakfast")
    diary_callbacks = {
        button.callback_data
        for row in diary.inline_keyboard
        for button in row
    }
    assert "diary:source:templates:breakfast" in diary_callbacks
