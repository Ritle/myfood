from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Food, MealTemplate, MealTemplateItem
from app.repositories.foods import get_visible_food
from app.services.diary import MEAL_TYPES, validate_portion_weight

MAX_MEAL_TEMPLATES = 30
MAX_MEAL_TEMPLATE_ITEMS = 8


def validate_template_name(value: str | None) -> tuple[str, str]:
    """Collapse whitespace and return a bounded display name and lookup key."""
    name = " ".join((value or "").strip().split())
    if not 2 <= len(name) <= 50:
        raise ValueError("Название шаблона должно содержать от 2 до 50 символов.")
    return name, name.casefold()


async def list_user_meal_templates(
    session: AsyncSession, *, user_id: int
) -> list[MealTemplate]:
    """Return a user's reusable meals, newest first, with their ordered items."""
    result = await session.scalars(
        select(MealTemplate)
        .options(selectinload(MealTemplate.items).joinedload(MealTemplateItem.food))
        .where(MealTemplate.user_id == user_id)
        .order_by(MealTemplate.created_at.desc(), MealTemplate.id.desc())
    )
    return list(result.unique())


async def count_user_meal_templates(session: AsyncSession, *, user_id: int) -> int:
    """Return the number of saved templates for one user."""
    return int(
        await session.scalar(
            select(func.count()).select_from(MealTemplate).where(MealTemplate.user_id == user_id)
        )
        or 0
    )


async def load_owned_meal_template(
    session: AsyncSession, *, user_id: int, template_id: int
) -> MealTemplate | None:
    """Load a meal template and its products only for its owner."""
    return await session.scalar(
        select(MealTemplate)
        .options(selectinload(MealTemplate.items).joinedload(MealTemplateItem.food))
        .where(MealTemplate.id == template_id, MealTemplate.user_id == user_id)
    )


async def create_meal_template(
    session: AsyncSession,
    *,
    user_id: int,
    name: str,
    meal_type: str,
    items: list[tuple[Food, Decimal]],
) -> MealTemplate:
    """Persist a reusable meal with bounded name, item count, and visible foods."""
    clean_name, normalized_name = validate_template_name(name)
    if meal_type not in MEAL_TYPES:
        raise ValueError("Неизвестный прием пищи.")
    if not 1 <= len(items) <= MAX_MEAL_TEMPLATE_ITEMS:
        raise ValueError(f"В шаблоне должно быть от 1 до {MAX_MEAL_TEMPLATE_ITEMS} продуктов.")

    existing_count = await count_user_meal_templates(session, user_id=user_id)
    if existing_count >= MAX_MEAL_TEMPLATES:
        raise ValueError(f"Можно сохранить не более {MAX_MEAL_TEMPLATES} шаблонов.")
    duplicate = await session.scalar(
        select(MealTemplate.id).where(
            MealTemplate.user_id == user_id,
            MealTemplate.name_normalized == normalized_name,
        )
    )
    if duplicate is not None:
        raise ValueError("У вас уже есть шаблон с таким названием. Выберите другое.")

    visible_items: list[tuple[Food, Decimal]] = []
    for food, weight in items:
        validate_portion_weight(weight)
        visible_food = await get_visible_food(session, food_id=food.id, user_id=user_id)
        if visible_food is None:
            raise ValueError("Один из продуктов шаблона больше недоступен.")
        visible_items.append((visible_food, weight))

    template = MealTemplate(
        user_id=user_id,
        name=clean_name,
        name_normalized=normalized_name,
        meal_type=meal_type,
    )
    template.items = [
        MealTemplateItem(
            food=food,
            weight_grams=Decimal(1) if food.nutrition_basis == "portion" else weight,
            is_full_serving=food.nutrition_basis == "portion",
            position=position,
        )
        for position, (food, weight) in enumerate(visible_items)
    ]
    session.add(template)
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise ValueError("Не удалось сохранить шаблон с таким названием.") from error
    await session.refresh(template)
    return template


async def delete_owned_meal_template(
    session: AsyncSession, *, user_id: int, template_id: int
) -> bool:
    """Delete a meal template only when it belongs to the requesting user."""
    template = await session.scalar(
        select(MealTemplate).where(
            MealTemplate.id == template_id,
            MealTemplate.user_id == user_id,
        )
    )
    if template is None:
        return False
    await session.delete(template)
    await session.commit()
    return True
