from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data import BASE_FOODS, FNDDS_FOODS, FOUNDATION_FOODS
from app.data.health_diet import load_health_diet_foods
from app.handlers.food import answer_food_card, food_card_text
from app.keyboards.diary import diary_recent_food_results
from app.keyboards.food import food_card_actions, food_results
from app.models import Base, Food, User
from app.services.diary import add_diary_entry
from app.services.foods import (
    add_user_food,
    dish_catalog_page,
    favorite_foods,
    latest_food_portion_entry,
    load_food,
    recent_food_portions,
    recent_foods,
    search_foods,
    search_foods_page,
    seed_base_foods,
    seed_catalog_foods,
    toggle_food_favorite,
    update_user_food,
)

HEALTH_DIET_FOODS = load_health_diet_foods()


@pytest.mark.asyncio
async def test_seed_is_idempotent_and_catalog_is_searchable() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1, first_name="Owner")
            session.add(owner)
            await session.commit()
            await session.refresh(owner)

            assert await seed_base_foods(session) == (len(BASE_FOODS), 0)
            assert await seed_base_foods(session) == (0, len(BASE_FOODS))
            assert await seed_catalog_foods(session, HEALTH_DIET_FOODS) == (
                len(HEALTH_DIET_FOODS),
                0,
            )
            assert await seed_catalog_foods(session, HEALTH_DIET_FOODS) == (
                0,
                len(HEALTH_DIET_FOODS),
            )
            dish_page = await dish_catalog_page(session, user_id=owner.id, page=0)
            dish_search_results = await search_foods(
                session, user_id=owner.id, query=dish_page.items[0].name
            )
            results = await search_foods(session, user_id=owner.id, query="куриная")
            wildcard_results = await search_foods(session, user_id=owner.id, query="рис%")

        assert any(food.source == "HEALTH_DIET" for food in results)
        assert dish_page.items
        assert all(food.catalog_section == "dish" for food in dish_page.items)
        assert dish_page.items[0] in dish_search_results
        assert all(food.brand is None for food in results)
        assert len(FOUNDATION_FOODS) == 25
        assert len(FNDDS_FOODS) == 134
        assert len(HEALTH_DIET_FOODS) == 12_975
        assert all(food.source == "USDA_FNDDS" for food in FNDDS_FOODS)
        assert all(food.source == "HEALTH_DIET" for food in HEALTH_DIET_FOODS)
        assert all(food.calories <= 1000 for food in HEALTH_DIET_FOODS)
        assert all(
            max(food.protein, food.fat, food.carbs) <= 100 for food in HEALTH_DIET_FOODS
        )
        assert wildcard_results == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_private_food_is_visible_only_to_owner() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1, first_name="Owner")
            stranger = User(telegram_id=2, first_name="Stranger")
            session.add_all([owner, stranger])
            await session.commit()
            await session.refresh(owner)
            await session.refresh(stranger)
            food = await add_user_food(
                session,
                user_id=owner.id,
                name="Творог домашний",
                brand=None,
                calories=Decimal(121),
                protein=Decimal("17.2"),
                fat=Decimal(5),
                carbs=Decimal("1.8"),
            )
            dish = await add_user_food(
                session,
                user_id=owner.id,
                name="Домашняя лазанья",
                brand=None,
                calories=Decimal(175),
                protein=Decimal(10),
                fat=Decimal(8),
                carbs=Decimal(16),
                catalog_section="dish",
            )

            assert await load_food(session, user_id=owner.id, food_id=food.id) is not None
            assert await load_food(session, user_id=stranger.id, food_id=food.id) is None
            assert len(await search_foods(session, user_id=owner.id, query="ТВОРОГ")) == 1
            assert await search_foods(session, user_id=stranger.id, query="творог") == []
            owner_dish_page = await dish_catalog_page(session, user_id=owner.id, page=10_000)
            stranger_dish_page = await dish_catalog_page(session, user_id=stranger.id, page=10_000)
            assert dish in owner_dish_page.items
            assert dish.nutrition_basis == "portion"
            assert "На всё блюдо:" in food_card_text(dish)
            assert dish in await search_foods(session, user_id=owner.id, query="лазанья")
            assert dish not in stranger_dish_page.items
            food_button = food_results([food]).inline_keyboard[0][0]
            assert food_button.text == "Творог домашний · 121 ккал\nБ 17.2 · Ж 5 · У 1.8"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_owner_can_edit_private_food_without_changing_diary_snapshots() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1, first_name="Owner")
            stranger = User(telegram_id=2, first_name="Stranger")
            session.add_all([owner, stranger])
            await session.commit()
            await session.refresh(owner)
            await session.refresh(stranger)
            food = await add_user_food(
                session,
                user_id=owner.id,
                name="Йогурт натуральный",
                brand=None,
                calories=Decimal(80),
                protein=Decimal(4),
                fat=Decimal(3),
                carbs=Decimal(8),
            )
            entry = await add_diary_entry(
                session,
                user_id=owner.id,
                food=food,
                meal_type="breakfast",
                weight_grams=Decimal(100),
            )

            renamed = await update_user_food(
                session,
                user_id=owner.id,
                food_id=food.id,
                field="name",
                value="  Йогурт   греческий ",
            )
            assert renamed is not None and renamed.name == "Йогурт греческий"
            branded = await update_user_food(
                session,
                user_id=owner.id,
                food_id=food.id,
                field="brand",
                value="Домашний",
            )
            assert branded is not None and branded.brand == "Домашний"
            updated = await update_user_food(
                session,
                user_id=owner.id,
                food_id=food.id,
                field="calories",
                value=Decimal("95.5"),
            )
            assert updated is not None and updated.calories_per_100g == Decimal("95.50")
            cleared_brand = await update_user_food(
                session,
                user_id=owner.id,
                food_id=food.id,
                field="brand",
                value=None,
            )
            assert cleared_brand is not None and cleared_brand.brand is None
            unauthorized = await update_user_food(
                session,
                user_id=stranger.id,
                food_id=food.id,
                field="calories",
                value=Decimal(1),
            )

            assert unauthorized is None
            assert entry.calories == Decimal("80.00")
            assert await search_foods(session, user_id=owner.id, query="греческий") == [food]
            assert await search_foods(session, user_id=stranger.id, query="греческий") == []
            with pytest.raises(ValueError):
                await update_user_food(
                    session,
                    user_id=owner.id,
                    food_id=food.id,
                    field="protein",
                    value=Decimal(101),
                )
            current = await load_food(session, user_id=owner.id, food_id=food.id)
            assert current is not None and current.calories_per_100g == Decimal("95.50")

        private_actions = food_card_actions(1, favorite=False, editable=True)
        public_actions = food_card_actions(1, favorite=False)
        assert any(
            button.callback_data == "food:edit:1"
            for row in private_actions.inline_keyboard
            for button in row
        )
        assert all(
            button.callback_data != "food:edit:1"
            for row in public_actions.inline_keyboard
            for button in row
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_private_product_card_shows_edit_action_for_internal_owner_id() -> None:
    owner = User(id=42, telegram_id=987654321, first_name="Owner")
    food = Food(
        id=9,
        name="Мой продукт",
        name_normalized="мой продукт",
        brand=None,
        brand_normalized=None,
        calories_per_100g=Decimal(100),
        protein_per_100g=Decimal(5),
        fat_per_100g=Decimal(2),
        carbs_per_100g=Decimal(10),
        created_by_user_id=owner.id,
        is_public=False,
    )

    class CardMessage:
        reply_markup = None

        async def answer(self, _text: str, **kwargs) -> None:
            self.reply_markup = kwargs["reply_markup"]

    message = CardMessage()
    await answer_food_card(message, food=food, user=owner, favorite=False)

    assert any(
        button.callback_data == "food:edit:9"
        for row in message.reply_markup.inline_keyboard
        for button in row
    )


@pytest.mark.asyncio
async def test_catalog_pagination_favorites_and_recent_foods() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1, first_name="Owner")
            stranger = User(telegram_id=2, first_name="Stranger")
            session.add_all([owner, stranger])
            await session.commit()
            await session.refresh(owner)
            await session.refresh(stranger)
            foods = []
            for index in range(7):
                foods.append(
                    await add_user_food(
                        session,
                        user_id=owner.id,
                        name=f"Тестовый продукт {index}",
                        brand=None,
                        calories=Decimal(100 + index),
                        protein=Decimal(10),
                        fat=Decimal(5),
                        carbs=Decimal(8),
                    )
                )

            first_page = await search_foods_page(
                session, user_id=owner.id, query="тестовый", page=0, page_size=3
            )
            last_page = await search_foods_page(
                session, user_id=owner.id, query="тестовый", page=2, page_size=3
            )
            assert len(first_page.items) == 3
            assert len(last_page.items) == 1
            assert first_page.total_pages == 3

            assert await toggle_food_favorite(
                session, user_id=owner.id, food_id=foods[0].id
            )
            assert [food.id for food in await favorite_foods(session, user_id=owner.id)] == [
                foods[0].id
            ]
            assert await favorite_foods(session, user_id=stranger.id) == []

            await add_diary_entry(
                session,
                user_id=owner.id,
                food=foods[1],
                meal_type="breakfast",
                weight_grams=Decimal(100),
            )
            last_entry = await add_diary_entry(
                session,
                user_id=owner.id,
                food=foods[1],
                meal_type="lunch",
                weight_grams=Decimal(50),
            )
            assert [food.id for food in await recent_foods(session, user_id=owner.id)] == [
                foods[1].id
            ]
            recent_portions = await recent_food_portions(session, user_id=owner.id)
            assert len(recent_portions) == 1
            assert recent_portions[0].food.id == foods[1].id
            assert recent_portions[0].entry_id == last_entry.id
            assert recent_portions[0].weight_grams == Decimal(50)
            assert (
                await latest_food_portion_entry(
                    session, user_id=owner.id, food_id=foods[1].id
                )
            ).id == last_entry.id
            recent_keyboard = diary_recent_food_results(recent_portions, "lunch")
            buttons = [button for row in recent_keyboard.inline_keyboard for button in row]
            assert any(button.text == "↻ 50 г" for button in buttons)
            assert any(
                button.callback_data == f"diary:repeat:lunch:{last_entry.id}"
                for button in buttons
            )
    finally:
        await engine.dispose()
