from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.data.base_foods import BASE_FOODS
from app.models import Base, User
from app.services.foods import add_user_food, load_food, search_foods, seed_base_foods


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
            wildcard_results = await search_foods(session, user_id=owner.id, query="рис%")

        assert {food.source_ref for food in results} == {"2646170", "331960"}
        assert all(food.brand is None for food in results)
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
