import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Literal

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data import BASE_FOODS
from app.data.base_foods import BaseFood
from app.models import Food, FoodEntry
from app.repositories.favorite_foods import (
    add_favorite,
    is_favorite,
    list_favorite_foods,
    remove_favorite,
)
from app.repositories.food_entries import (
    food_meal_usage_counts,
    get_latest_food_entry,
    list_food_portion_history,
    list_recent_food_entries,
    list_recent_foods,
    list_used_foods,
)
from app.repositories.foods import (
    count_foods,
    create_food,
    find_foods,
    get_owned_food,
    list_food_search_candidates,
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

HABITUAL_PORTION_HISTORY_LIMIT = 12
HABITUAL_PORTION_MIN_SAMPLES = 3
HABITUAL_PORTION_MIN_SHARE = Decimal("0.60")
HABITUAL_PORTION_ABSOLUTE_TOLERANCE_G = Decimal(25)
HABITUAL_PORTION_RELATIVE_TOLERANCE = Decimal("0.20")
HABITUAL_PORTION_ROUND_STEP_G = Decimal(5)

FUZZY_SEARCH_MAX_CANDIDATES = 20_000


def normalize_food_text(value: str) -> str:
    """Normalize product text for deterministic Unicode-aware lookup."""
    return " ".join(value.casefold().strip().split())


def validate_food_name(value: str, *, field: str = "Название", maximum_length: int = 200) -> str:
    """Normalize whitespace and validate a human-readable name or brand."""
    cleaned = " ".join(value.strip().split())
    if not 2 <= len(cleaned) <= maximum_length:
        raise ValueError(f"{field} должно содержать от 2 до {maximum_length} символов")
    return cleaned


def validate_nutrient(
    value: Decimal, *, calories: bool = False, full_serving: bool = False
) -> Decimal:
    """Validate a finite nutrient value for either 100 g or one full serving."""
    if full_serving:
        maximum = Decimal(10000) if calories else Decimal(1000)
    else:
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
    nutrition_basis = "portion" if catalog_section == "dish" else "per_100g"
    clean_name = validate_food_name(name)
    clean_brand = validate_food_name(brand, field="Бренд", maximum_length=120) if brand else None
    return await create_food(
        session,
        Food(
            name=clean_name,
            name_normalized=normalize_food_text(clean_name),
            brand=clean_brand,
            brand_normalized=normalize_food_text(clean_brand) if clean_brand else None,
            calories_per_100g=validate_nutrient(
                calories, calories=True, full_serving=nutrition_basis == "portion"
            ),
            protein_per_100g=validate_nutrient(
                protein, full_serving=nutrition_basis == "portion"
            ),
            fat_per_100g=validate_nutrient(
                fat, full_serving=nutrition_basis == "portion"
            ),
            carbs_per_100g=validate_nutrient(
                carbs, full_serving=nutrition_basis == "portion"
            ),
            created_by_user_id=user_id,
            is_public=False,
            catalog_section=catalog_section,
            nutrition_basis=nutrition_basis,
        ),
    )


async def search_foods(
    session: AsyncSession, *, user_id: int, query: str, limit: int = 10
) -> list[Food]:
    """Search visible foods tolerating word order changes and small typos."""
    if limit < 1:
        return []
    normalized, query_tokens = prepare_food_search_query(query)
    if has_literal_wildcards(normalized):
        return []
    candidates = await list_food_search_candidates(session, user_id=user_id)
    ranked = rank_food_search_candidates(
        candidates,
        user_id=user_id,
        normalized_query=normalized,
        query_tokens=query_tokens,
    )
    return [candidate.food for candidate, _score in ranked[:limit]]


async def search_foods_page(
    session: AsyncSession,
    *,
    user_id: int,
    query: str,
    page: int,
    page_size: int = 8,
) -> FoodSearchPage:
    """Search a validated catalog query with fuzzy ranking and pagination."""
    if page < 0 or not 1 <= page_size <= 20:
        raise ValueError("invalid search page")
    normalized, query_tokens = prepare_food_search_query(query)
    if has_literal_wildcards(normalized):
        return FoodSearchPage(items=[], page=0, total_pages=1)

    candidates = await list_food_search_candidates(session, user_id=user_id)
    ranked = rank_food_search_candidates(
        candidates,
        user_id=user_id,
        normalized_query=normalized,
        query_tokens=query_tokens,
    )
    total = len(ranked)
    total_pages = max(1, (total + page_size - 1) // page_size)
    actual_page = min(page, total_pages - 1)
    start = actual_page * page_size
    items = [
        candidate.food
        for candidate, _score in ranked[start : start + page_size]
    ]
    return FoodSearchPage(items=items, page=actual_page, total_pages=total_pages)


def prepare_food_search_query(query: str) -> tuple[str, tuple[str, ...]]:
    """Normalize a human query and split it into order-independent word tokens."""
    normalized = normalize_food_text(query)
    tokens = tuple(re.findall(r"\w+", normalized, flags=re.UNICODE))
    if len(normalized) < 2 or not tokens:
        raise ValueError("Введите не менее двух букв или цифр")
    return normalized, tokens


def has_literal_wildcards(normalized_query: str) -> bool:
    """Keep SQL-like wildcard characters literal instead of treating them as fuzzy input."""
    return "%" in normalized_query or "_" in normalized_query


def rank_food_search_candidates(
    candidates,
    *,
    user_id: int,
    normalized_query: str,
    query_tokens: tuple[str, ...],
):
    """Filter and rank catalog candidates while preserving personal priority."""
    if len(candidates) > FUZZY_SEARCH_MAX_CANDIDATES:
        candidates = candidates[:FUZZY_SEARCH_MAX_CANDIDATES]

    ranked = []
    for candidate in candidates:
        food = candidate.food
        searchable = " ".join(
            value
            for value in (food.name_normalized, food.brand_normalized)
            if value
        )
        candidate_tokens = tuple(re.findall(r"\w+", searchable, flags=re.UNICODE))
        score = fuzzy_food_match_score(
            normalized_query=normalized_query,
            query_tokens=query_tokens,
            candidate_text=searchable,
            candidate_tokens=candidate_tokens,
        )
        if score is None:
            continue
        ranked.append((candidate, score))

    ranked.sort(
        key=lambda item: (
            food_search_priority(item[0], user_id=user_id),
            -item[1],
            -item[0].usage_count,
            -search_recency_value(item[0].last_used_at),
            item[0].food.name.casefold(),
            item[0].food.id or 0,
        )
    )
    return ranked


def fuzzy_food_match_score(
    *,
    normalized_query: str,
    query_tokens: tuple[str, ...],
    candidate_text: str,
    candidate_tokens: tuple[str, ...],
) -> float | None:
    """Return an order-independent fuzzy score when every query word is represented."""
    if not candidate_tokens:
        return None

    token_scores: list[float] = []
    for query_token in query_tokens:
        best = max(
            food_token_similarity(query_token, candidate_token)
            for candidate_token in candidate_tokens
        )
        if best < fuzzy_token_threshold(query_token):
            return None
        token_scores.append(best)

    token_average = sum(token_scores) / len(token_scores)
    phrase_score = fuzz.token_set_ratio(normalized_query, candidate_text)
    return token_average * 0.75 + phrase_score * 0.25


def food_token_similarity(query_token: str, candidate_token: str) -> float:
    """Compare one word, rewarding exact and prefix matches before edit similarity."""
    if query_token == candidate_token:
        return 100.0
    if candidate_token.startswith(query_token) and len(query_token) >= 2:
        return 96.0
    if query_token.startswith(candidate_token) and len(candidate_token) >= 3:
        return 92.0
    return float(fuzz.ratio(query_token, candidate_token))


def fuzzy_token_threshold(token: str) -> float:
    """Use stricter thresholds for short words to reduce accidental matches."""
    length = len(token)
    if length <= 2:
        return 90.0
    if length == 3:
        return 66.0
    if length == 4:
        return 72.0
    return 75.0


def food_search_priority(candidate, *, user_id: int) -> int:
    """Keep used foods first, then user-created foods, then the public catalog."""
    if candidate.usage_count > 0:
        return 0
    if candidate.food.created_by_user_id == user_id:
        return 1
    return 2


def search_recency_value(value: datetime | None) -> float:
    """Convert a possibly-naive SQLite timestamp into a sortable numeric value."""
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


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
        nutrient = validate_nutrient(
            value,
            calories=field == "calories",
            full_serving=food.nutrition_basis == "portion",
        )
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


async def habitual_food_portion(
    session: AsyncSession,
    *,
    user_id: int,
    food_id: int,
) -> Decimal | None:
    """Infer a stable typical portion from the user's recent weighed history."""
    entries = await list_food_portion_history(
        session,
        user_id=user_id,
        food_id=food_id,
        limit=HABITUAL_PORTION_HISTORY_LIMIT,
    )
    weights = [Decimal(entry.weight_grams) for entry in entries]
    if len(weights) < HABITUAL_PORTION_MIN_SAMPLES:
        return None

    center = Decimal(median(weights))
    tolerance = max(
        HABITUAL_PORTION_ABSOLUTE_TOLERANCE_G,
        center * HABITUAL_PORTION_RELATIVE_TOLERANCE,
    )
    clustered = [
        weight for weight in weights if abs(weight - center) <= tolerance
    ]
    if (
        len(clustered) < HABITUAL_PORTION_MIN_SAMPLES
        or Decimal(len(clustered)) / Decimal(len(weights))
        < HABITUAL_PORTION_MIN_SHARE
    ):
        return None

    typical = Decimal(median(clustered))
    return (
        (typical / HABITUAL_PORTION_ROUND_STEP_G)
        .quantize(Decimal(1), rounding=ROUND_HALF_UP)
        * HABITUAL_PORTION_ROUND_STEP_G
    )


async def latest_food_portion_entry(
    session: AsyncSession, *, user_id: int, food_id: int
) -> FoodEntry | None:
    """Load the latest portion entry for a user's product."""
    return await get_latest_food_entry(session, user_id=user_id, food_id=food_id)


async def seed_base_foods(session: AsyncSession) -> tuple[int, int]:
    """Insert or update the small built-in catalog without creating duplicates."""
    return await seed_catalog_foods(session, BASE_FOODS)


async def seed_catalog_foods(
    session: AsyncSession, foods: tuple[BaseFood, ...]
) -> tuple[int, int]:
    """Insert or update one catalog data set by its stable external identity."""
    created = 0
    updated = 0
    sources = {item.source for item in foods}
    existing = {
        (product.source, product.source_ref): product
        for product in await session.scalars(select(Food).where(Food.source.in_(sources)))
    }
    for item in foods:
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



async def used_foods(session: AsyncSession, *, user_id: int) -> list[Food]:
    """Load all unique active products the user has previously logged."""
    return await list_used_foods(session, user_id=user_id)



async def meal_food_usage_counts(
    session: AsyncSession,
    *,
    user_id: int,
    meal_type: str,
) -> dict[int, int]:
    """Load per-food usage frequency for one meal context."""
    return await food_meal_usage_counts(
        session,
        user_id=user_id,
        meal_type=meal_type,
    )
