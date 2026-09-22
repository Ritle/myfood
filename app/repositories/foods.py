from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Food


async def create_food(session: AsyncSession, food: Food) -> Food:
    """Persist a catalog product."""
    session.add(food)
    await session.commit()
    await session.refresh(food)
    return food


async def find_foods(
    session: AsyncSession,
    *,
    user_id: int,
    normalized_query: str,
    limit: int = 10,
    offset: int = 0,
    catalog_section: str | None = None,
) -> list[Food]:
    """Find visible, active foods by normalized name or brand."""
    visibility = or_(Food.is_public.is_(True), Food.created_by_user_id == user_id)
    result = await session.scalars(
        select(Food)
        .where(
            Food.is_archived.is_(False),
            visibility,
            or_(
                Food.name_normalized.contains(normalized_query, autoescape=True),
                Food.brand_normalized.contains(normalized_query, autoescape=True),
            ),
            *([Food.catalog_section == catalog_section] if catalog_section else []),
        )
        .order_by(Food.is_public.desc(), Food.name)
        .offset(offset)
        .limit(limit)
    )
    return list(result)


async def count_foods(
    session: AsyncSession,
    *,
    user_id: int,
    normalized_query: str | None = None,
    catalog_section: str | None = None,
) -> int:
    """Count visible, active products matching an optional query and section."""
    visibility = or_(Food.is_public.is_(True), Food.created_by_user_id == user_id)
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Food)
            .where(
                Food.is_archived.is_(False),
                visibility,
                *(
                    [
                        or_(
                            Food.name_normalized.contains(normalized_query, autoescape=True),
                            Food.brand_normalized.contains(normalized_query, autoescape=True),
                        )
                    ]
                    if normalized_query is not None
                    else []
                ),
                *([Food.catalog_section == catalog_section] if catalog_section else []),
            )
        )
        or 0
    )


async def get_visible_food(session: AsyncSession, *, food_id: int, user_id: int) -> Food | None:
    """Return a product only when it is visible to the requesting user."""
    return await session.scalar(
        select(Food).where(
            Food.id == food_id,
            Food.is_archived.is_(False),
            or_(Food.is_public.is_(True), Food.created_by_user_id == user_id),
        )
    )


async def get_owned_food(session: AsyncSession, *, food_id: int, user_id: int) -> Food | None:
    """Return an active private product only when it is owned by the requesting user."""
    return await session.scalar(
        select(Food).where(
            Food.id == food_id,
            Food.created_by_user_id == user_id,
            Food.is_public.is_(False),
            Food.is_archived.is_(False),
        )
    )


async def get_food_by_source(session: AsyncSession, *, source: str, source_ref: str) -> Food | None:
    """Find an imported product by its stable external identity."""
    return await session.scalar(
        select(Food).where(Food.source == source, Food.source_ref == source_ref)
    )



async def list_visible_food_candidates(
    session: AsyncSession,
    *,
    user_id: int,
    nutrient: str,
    limit: int = 250,
) -> list[Food]:
    """Return nutrient-dense visible foods for recommendation scoring."""
    columns = {
        "protein": Food.protein_per_100g,
        "fat": Food.fat_per_100g,
        "carbs": Food.carbs_per_100g,
    }
    column = columns.get(nutrient)
    if column is None:
        raise ValueError("unknown recommendation nutrient")
    if not 1 <= limit <= 1000:
        raise ValueError("invalid recommendation limit")

    visibility = or_(Food.is_public.is_(True), Food.created_by_user_id == user_id)
    density = column / func.nullif(Food.calories_per_100g, 0)
    result = await session.scalars(
        select(Food)
        .where(
            Food.is_archived.is_(False),
            visibility,
            Food.calories_per_100g > 0,
            column > 0,
        )
        .order_by(
            (Food.created_by_user_id == user_id).desc(),
            density.desc(),
            column.desc(),
            Food.name,
        )
        .limit(limit)
    )
    return list(result)
