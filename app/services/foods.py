import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data import BASE_FOODS
from app.models import Food, FoodEntry
from app.repositories.favorite_foods import (
    add_favorite,
    is_favorite,
    list_favorite_foods,
    remove_favorite,
)
from app.repositories.food_entries import (
    get_latest_food_entry,
    list_recent_food_entries,
    list_recent_foods,
)
from app.repositories.foods import (
    count_foods,
    create_food,
    find_foods,
    get_owned_food,
    get_visible_food,
)


@dataclass(frozen=True, slots=True)
class FoodSearchPage:
    """One page of catalog search results."""

    items: list[Food]
    page: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class RecentFoodPortion:
    """A recently used product and the diary entry containing its latest portion."""

    entry_id: int
    food: Food
    weight_grams: Decimal


FoodEditableField = Literal["name", "brand", "calories", "protein", "fat", "carbs"]
CatalogSection = Literal["food", "dish"]


def normalize_food_text(value: str) -> str:
    """Normalize product text for deterministic Unicode-aware lookup."""
    return " ".join(value.casefold().strip().split())


def validate_food_name(value: str, *, field: str = "Название", maximum_length: int = 200) -> str:
    """Normalize whitespace and validate a human-readable name or brand."""
    cleaned = " ".join(value.strip().split())
    if not 2 <= len(cleaned) <= maximum_length:
        raise ValueError(f"{field} должно содержать от 2 до {maximum_length} символов")
    return cleaned


def validate_nutrient(value: Decimal, *, calories: bool = False) -> Decimal:
    """Validate a finite per-100-gram nutrient value."""
    maximum = Decimal(1000) if calories else Decimal(100)
    if not value.is_finite() or value < 0 or value > maximum:
        raise ValueError(f"значение должно быть от 0 до {maximum}")
    return value.quantize(Decimal("0.01"))


async def add_user_food(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    brand: str | None,
    calories: Decimal,
    protein: Decimal,
    fat: Decimal,
    carbs: Decimal,
    catalog_section: CatalogSection = "food",
) -> Food:
    """Validate and add a private product or dish owned by one user."""
    if catalog_section not in {"food", "dish"}:
        raise ValueError("Неизвестный раздел каталога")
    clean_name = validate_food_name(name)
    clean_brand = validate_food_name(brand, field="Бренд", maximum_length=120) if brand else None
    return await create_food(
        session,
        Food(
            name=clean_name,
            name_normalized=normalize_food_text(clean_name),
            brand=clean_brand,
            brand_normalized=normalize_food_text(clean_brand) if clean_brand else None,
            calories_per_100g=validate_nutrient(calories, calories=True),
            protein_per_100g=validate_nutrient(protein),
            fat_per_100g=validate_nutrient(fat),
            carbs_per_100g=validate_nutrient(carbs),
            created_by_user_id=user_id,
            is_public=False,
            catalog_section=catalog_section,
        ),
    )


async def search_foods(
    session: AsyncSession, *, user_id: int, query: str, limit: int = 10
) -> list[Food]:
    """Search products visible to a user by name and brand."""
    normalized = normalize_food_text(query)
    if len(normalized) < 2 or not re.search(r"\w", normalized, flags=re.UNICODE):
        raise ValueError("Введите не менее двух букв или цифр")
    return await find_foods(session, user_id=user_id, normalized_query=normalized, limit=limit)


async def search_foods_page(
    session: AsyncSession,
    *,
    user_id: int,
    query: str,
    page: int,
    page_size: int = 8,
) -> FoodSearchPage:
    """Search a validated catalog query with bounded pagination."""
    if page < 0 or not 1 <= page_size <= 20:
        raise ValueError("invalid search page")
    normalized = normalize_food_text(query)
    if len(normalized) < 2 or not re.search(r"\w", normalized, flags=re.UNICODE):
        raise ValueError("Введите не менее двух букв или цифр")
    total = await count_foods(
        session, user_id=user_id, normalized_query=normalized
    )
    total_pages = max(1, (total + page_size - 1) // page_size)
    actual_page = min(page, total_pages - 1)
    items = await find_foods(
        session,
        user_id=user_id,
        normalized_query=normalized,
        limit=page_size,
        offset=actual_page * page_size,
    )
    return FoodSearchPage(items=items, page=actual_page, total_pages=total_pages)


async def dish_catalog_page(
    session: AsyncSession,
    *,
    user_id: int,
    page: int,
    page_size: int = 8,
) -> FoodSearchPage:
    """Return one page of visible dishes; ordinary product search stays unfiltered."""
    if page < 0 or not 1 <= page_size <= 20:
        raise ValueError("invalid catalog page")
    total = await count_foods(session, user_id=user_id, catalog_section="dish")
    total_pages = max(1, (total + page_size - 1) // page_size)
    actual_page = min(page, total_pages - 1)
    items = await find_foods(
        session,
        user_id=user_id,
        normalized_query="",
        catalog_section="dish",
        limit=page_size,
        offset=actual_page * page_size,
    )
    return FoodSearchPage(items=items, page=actual_page, total_pages=total_pages)


async def load_food(session: AsyncSession, *, user_id: int, food_id: int) -> Food | None:
    """Load a visible catalog product."""
    return await get_visible_food(session, food_id=food_id, user_id=user_id)


async def update_user_food(
    session: AsyncSession,
    *,
    user_id: int,
    food_id: int,
    field: FoodEditableField,
    value: str | Decimal | None,
) -> Food | None:
    """Update one field of an active private product owned by the user."""
    food = await get_owned_food(session, food_id=food_id, user_id=user_id)
    if food is None:
        return None

    if field == "name":
        if not isinstance(value, str):
            raise ValueError("Название должно быть текстом")
        food.name = validate_food_name(value)
        food.name_normalized = normalize_food_text(food.name)
    elif field == "brand":
        if value is not None and not isinstance(value, str):
            raise ValueError("Бренд должен быть текстом")
        food.brand = (
            validate_food_name(value, field="Бренд", maximum_length=120)
            if value
            else None
        )
        food.brand_normalized = normalize_food_text(food.brand) if food.brand else None
    elif field in {"calories", "protein", "fat", "carbs"}:
        if not isinstance(value, Decimal):
            raise ValueError("Пищевая ценность должна быть числом")
        nutrient = validate_nutrient(value, calories=field == "calories")
        attribute = {
            "calories": "calories_per_100g",
            "protein": "protein_per_100g",
            "fat": "fat_per_100g",
            "carbs": "carbs_per_100g",
        }[field]
        setattr(food, attribute, nutrient)
    else:
        raise ValueError("Неизвестное поле продукта")

    await session.commit()
    await session.refresh(food)
    return food


async def toggle_food_favorite(
    session: AsyncSession, *, user_id: int, food_id: int
) -> bool | None:
    """Toggle a visible product bookmark and return its new state."""
    food = await get_visible_food(session, food_id=food_id, user_id=user_id)
    if food is None:
        return None
    if await is_favorite(session, user_id=user_id, food_id=food_id):
        await remove_favorite(session, user_id=user_id, food_id=food_id)
        return False
    await add_favorite(session, user_id=user_id, food_id=food_id)
    return True


async def food_is_favorite(
    session: AsyncSession, *, user_id: int, food_id: int
) -> bool:
    """Return whether a visible product is bookmarked."""
    if await get_visible_food(session, food_id=food_id, user_id=user_id) is None:
        return False
    return await is_favorite(session, user_id=user_id, food_id=food_id)


async def favorite_foods(session: AsyncSession, *, user_id: int) -> list[Food]:
    """Load a user's favorite visible products."""
    return await list_favorite_foods(session, user_id=user_id)


async def recent_foods(
    session: AsyncSession, *, user_id: int, limit: int = 10
) -> list[Food]:
    """Load unique products from recent diary entries."""
    return await list_recent_foods(session, user_id=user_id, limit=limit)


async def recent_food_portions(
    session: AsyncSession, *, user_id: int, limit: int = 10
) -> list[RecentFoodPortion]:
    """Load recent products with the weight from each product's latest diary entry."""
    entries = await list_recent_food_entries(session, user_id=user_id, limit=limit)
    return [
        RecentFoodPortion(
            entry_id=entry.id,
            food=entry.food,
            weight_grams=entry.weight_grams,
        )
        for entry in entries
    ]


async def latest_food_portion_entry(
    session: AsyncSession, *, user_id: int, food_id: int
) -> FoodEntry | None:
    """Load the latest portion entry for a user's product."""
    return await get_latest_food_entry(session, user_id=user_id, food_id=food_id)


async def seed_base_foods(session: AsyncSession) -> tuple[int, int]:
    """Insert or update the packaged product catalog without creating duplicates."""
    created = 0
    updated = 0
    sources = {item.source for item in BASE_FOODS}
    existing = {
        (product.source, product.source_ref): product
        for product in await session.scalars(select(Food).where(Food.source.in_(sources)))
    }
    for item in BASE_FOODS:
        product = existing.get((item.source, item.source_ref))
        if product is None:
            product = Food(
                source=item.source,
                source_ref=item.source_ref,
                catalog_section=item.catalog_section,
            )
            session.add(product)
            created += 1
        else:
            updated += 1
        product.name = item.name
        product.name_normalized = normalize_food_text(item.name)
        product.brand = None
        product.brand_normalized = None
        product.calories_per_100g = item.calories
        product.protein_per_100g = item.protein
        product.fat_per_100g = item.fat
        product.carbs_per_100g = item.carbs
        product.created_by_user_id = None
        product.is_public = True
        product.is_archived = False
        product.catalog_section = item.catalog_section
    await session.commit()
    return created, updated
