import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.base_foods import BASE_FOODS
from app.models import Food
from app.repositories.favorite_foods import (
    add_favorite,
    is_favorite,
    list_favorite_foods,
    remove_favorite,
)
from app.repositories.food_entries import list_recent_foods
from app.repositories.foods import (
    count_foods,
    create_food,
    find_foods,
    get_food_by_source,
    get_visible_food,
)


@dataclass(frozen=True, slots=True)
class FoodSearchPage:
    """One page of catalog search results."""

    items: list[Food]
    page: int
    total_pages: int


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
) -> Food:
    """Validate and add a private product owned by one user."""
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


async def load_food(session: AsyncSession, *, user_id: int, food_id: int) -> Food | None:
    """Load a visible catalog product."""
    return await get_visible_food(session, food_id=food_id, user_id=user_id)


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


async def seed_base_foods(session: AsyncSession) -> tuple[int, int]:
    """Insert or update the packaged USDA base catalog without creating duplicates."""
    created = 0
    updated = 0
    for item in BASE_FOODS:
        source_ref = str(item.fdc_id)
        product = await get_food_by_source(session, source="USDA_FDC", source_ref=source_ref)
        if product is None:
            product = Food(source="USDA_FDC", source_ref=source_ref)
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
    await session.commit()
    return created, updated
