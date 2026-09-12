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
        )
        .order_by(Food.is_public.desc(), Food.name)
        .offset(offset)
        .limit(limit)
    )
    return list(result)


async def count_foods(
    session: AsyncSession, *, user_id: int, normalized_query: str
) -> int:
    """Count visible, active products matching a normalized query."""
    visibility = or_(Food.is_public.is_(True), Food.created_by_user_id == user_id)
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Food)
            .where(
                Food.is_archived.is_(False),
                visibility,
                or_(
                    Food.name_normalized.contains(normalized_query, autoescape=True),
                    Food.brand_normalized.contains(normalized_query, autoescape=True),
                ),
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


async def get_food_by_source(session: AsyncSession, *, source: str, source_ref: str) -> Food | None:
    """Find an imported product by its stable external identity."""
    return await session.scalar(
        select(Food).where(Food.source == source, Food.source_ref == source_ref)
    )
