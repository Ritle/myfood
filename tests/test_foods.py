from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data import BASE_FOODS, FNDDS_FOODS, FOUNDATION_FOODS
from app.models import Base, User
from app.services.diary import add_diary_entry
from app.services.foods import (
    add_user_food,
    favorite_foods,
    load_food,
    recent_foods,
    search_foods,
    search_foods_page,
    seed_base_foods,
    toggle_food_favorite,
)


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
            results = await search_foods(session, user_id=owner.id, query="куриная")
            grain_results = await search_foods(session, user_id=owner.id, query="гречневая")
            wildcard_results = await search_foods(session, user_id=owner.id, query="рис%")

        assert {food.source_ref for food in results} >= {"2646170", "331960"}
        assert all(food.brand is None for food in results)
        assert any(food.source == "USDA_FNDDS" for food in grain_results)
        assert len(FOUNDATION_FOODS) == 25
        assert len(FNDDS_FOODS) == 134
        assert all(food.source == "USDA_FNDDS" for food in FNDDS_FOODS)
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

            assert await load_food(session, user_id=owner.id, food_id=food.id) is not None
            assert await load_food(session, user_id=stranger.id, food_id=food.id) is None
            assert len(await search_foods(session, user_id=owner.id, query="ТВОРОГ")) == 1
            assert await search_foods(session, user_id=stranger.id, query="творог") == []
    finally:
        await engine.dispose()


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
            await add_diary_entry(
                session,
                user_id=owner.id,
                food=foods[1],
                meal_type="lunch",
                weight_grams=Decimal(50),
            )
            assert [food.id for food in await recent_foods(session, user_id=owner.id)] == [
                foods[1].id
            ]
    finally:
        await engine.dispose()
