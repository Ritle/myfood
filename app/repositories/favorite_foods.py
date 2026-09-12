from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FavoriteFood, Food


async def is_favorite(session: AsyncSession, *, user_id: int, food_id: int) -> bool:
    """Return whether a product is bookmarked by the user."""
    return (
        await session.scalar(
            select(FavoriteFood.id).where(
                FavoriteFood.user_id == user_id, FavoriteFood.food_id == food_id
            )
        )
        is not None
    )


async def add_favorite(session: AsyncSession, *, user_id: int, food_id: int) -> None:
    """Bookmark one product."""
    session.add(FavoriteFood(user_id=user_id, food_id=food_id))
    await session.commit()


async def remove_favorite(session: AsyncSession, *, user_id: int, food_id: int) -> None:
    """Remove one product bookmark."""
    await session.execute(
        delete(FavoriteFood).where(
            FavoriteFood.user_id == user_id, FavoriteFood.food_id == food_id
        )
    )
    await session.commit()


async def list_favorite_foods(session: AsyncSession, *, user_id: int) -> list[Food]:
    """Return visible active favorite products, newest bookmarks first."""
    result = await session.scalars(
        select(Food)
        .join(FavoriteFood, FavoriteFood.food_id == Food.id)
        .where(
            FavoriteFood.user_id == user_id,
            Food.is_archived.is_(False),
            or_(Food.is_public.is_(True), Food.created_by_user_id == user_id),
        )
        .order_by(FavoriteFood.created_at.desc(), FavoriteFood.id.desc())
    )
    return list(result)
