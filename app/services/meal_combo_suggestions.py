from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Food, FoodEntry, MealComboSuggestion, MealTemplate, User
from app.repositories.diary_days import list_recent_diary_days
from app.services.diary import get_entries_for_day
from app.services.foods import load_food
from app.services.meal_templates import (
    MAX_MEAL_TEMPLATE_ITEMS,
    create_meal_template,
    list_user_meal_templates,
)
from app.utils.formatting import format_decimal

FREQUENT_COMBO_MIN_OCCURRENCES = 3
FREQUENT_COMBO_HISTORY_DAYS = 30
PORTION_ABSOLUTE_TOLERANCE_G = Decimal(25)
PORTION_RELATIVE_TOLERANCE = Decimal("0.20")
MIN_COMBO_ITEMS = 2

_AUTO_TEMPLATE_NAMES = {
    "breakfast": "Завтрак",
    "lunch": "Обед",
    "dinner": "Ужин",
    "snack": "Перекус",
}


@dataclass(frozen=True, slots=True)
class MealItemProfile:
    food_id: int
    name: str
    amount: Decimal
    is_full_serving: bool


@dataclass(frozen=True, slots=True)
class FrequentMealSuggestion:
    suggestion_id: int
    name: str
    occurrence_count: int
    items: tuple[MealItemProfile, ...]


def meal_group_entries(
    entries: list[FoodEntry],
    *,
    meal_type: str,
    snack_number: int | None,
) -> list[FoodEntry]:
    """Return one main-meal or numbered-snack group."""
    if meal_type != "snack":
        return [entry for entry in entries if entry.meal_type == meal_type]
    number = snack_number or 1
    return [
        entry
        for entry in entries
        if entry.meal_type == "snack" and (entry.snack_number or 1) == number
    ]


def meal_item_profile(entries: list[FoodEntry]) -> tuple[MealItemProfile, ...]:
    """Aggregate duplicate products so repeated additions form one combo profile."""
    grouped: dict[tuple[int, bool], MealItemProfile] = {}
    for entry in entries:
        key = (entry.food_id, entry.is_full_serving)
        existing = grouped.get(key)
        amount = Decimal(entry.weight_grams)
        if existing is None:
            grouped[key] = MealItemProfile(
                food_id=entry.food_id,
                name=entry.food.name,
                amount=amount,
                is_full_serving=entry.is_full_serving,
            )
        else:
            grouped[key] = MealItemProfile(
                food_id=existing.food_id,
                name=existing.name,
                amount=existing.amount + amount,
                is_full_serving=existing.is_full_serving,
            )
    return tuple(sorted(grouped.values(), key=lambda item: (item.food_id, item.is_full_serving)))


def combo_signature(items: tuple[MealItemProfile, ...]) -> str:
    """Build a stable signature by product identity, independent of portion drift."""
    return "|".join(
        f"{item.food_id}:{1 if item.is_full_serving else 0}"
        for item in items
    )


def profiles_are_similar(
    first: tuple[MealItemProfile, ...],
    second: tuple[MealItemProfile, ...],
) -> bool:
    """Compare identical products with practical portion tolerance."""
    if len(first) != len(second):
        return False
    second_by_key = {
        (item.food_id, item.is_full_serving): item for item in second
    }
    for item in first:
        other = second_by_key.get((item.food_id, item.is_full_serving))
        if other is None:
            return False
        if item.is_full_serving:
            if item.amount != other.amount:
                return False
            continue
        tolerance = max(
            PORTION_ABSOLUTE_TOLERANCE_G,
            item.amount * PORTION_RELATIVE_TOLERANCE,
        )
        if abs(item.amount - other.amount) > tolerance:
            return False
    return True


async def claim_frequent_meal_suggestion(
    session: AsyncSession,
    *,
    user: User,
    source_day,
    meal_type: str,
    snack_number: int | None,
) -> FrequentMealSuggestion | None:
    """Claim a recurring meal combo after three similar historical occurrences."""
    current_entries = await get_entries_for_day(
        session,
        user_id=user.id,
        day=source_day,
        timezone_name=user.timezone,
    )
    current_group = meal_group_entries(
        current_entries,
        meal_type=meal_type,
        snack_number=snack_number,
    )
    current = meal_item_profile(current_group)
    if not MIN_COMBO_ITEMS <= len(current) <= MAX_MEAL_TEMPLATE_ITEMS:
        return None

    signature = combo_signature(current)
    existing_suggestion = await session.scalar(
        select(MealComboSuggestion.id).where(
            MealComboSuggestion.user_id == user.id,
            MealComboSuggestion.signature == signature,
        )
    )
    if existing_suggestion is not None:
        return None

    templates = await list_user_meal_templates(session, user_id=user.id)
    if any(template_profile(template) == current for template in templates):
        return None
    if any(profiles_are_similar(current, template_profile(template)) for template in templates):
        return None

    occurrence_count = 0
    recent_days = await list_recent_diary_days(
        session,
        user_id=user.id,
        limit=FREQUENT_COMBO_HISTORY_DAYS,
    )
    for diary_day in recent_days:
        day_entries = await get_entries_for_day(
            session,
            user_id=user.id,
            day=diary_day.logical_date,
            timezone_name=user.timezone,
        )
        if meal_type == "snack":
            numbers = sorted(
                {
                    entry.snack_number or 1
                    for entry in day_entries
                    if entry.meal_type == "snack"
                }
            )
            groups = [
                meal_group_entries(
                    day_entries,
                    meal_type="snack",
                    snack_number=number,
                )
                for number in numbers
            ]
        else:
            groups = [
                meal_group_entries(
                    day_entries,
                    meal_type=meal_type,
                    snack_number=None,
                )
            ]
        for group in groups:
            profile = meal_item_profile(group)
            if profile and profiles_are_similar(current, profile):
                occurrence_count += 1
                break
        if occurrence_count >= FREQUENT_COMBO_MIN_OCCURRENCES:
            break

    if occurrence_count < FREQUENT_COMBO_MIN_OCCURRENCES:
        return None

    suggestion = MealComboSuggestion(
        user_id=user.id,
        signature=signature,
        meal_type=meal_type,
        source_day=source_day,
        snack_number=snack_number if meal_type == "snack" else None,
        occurrence_count=occurrence_count,
        status="pending",
    )
    try:
        async with session.begin_nested():
            session.add(suggestion)
            await session.flush()
    except IntegrityError:
        await session.rollback()
        return None
    await session.commit()
    await session.refresh(suggestion)

    return FrequentMealSuggestion(
        suggestion_id=suggestion.id,
        name=automatic_template_name(templates, meal_type),
        occurrence_count=occurrence_count,
        items=current,
    )


async def save_frequent_combo_as_template(
    session: AsyncSession,
    *,
    user: User,
    suggestion_id: int,
) -> MealTemplate | None:
    """Create a normal reusable template from one still-pending suggestion."""
    suggestion = await session.scalar(
        select(MealComboSuggestion).where(
            MealComboSuggestion.id == suggestion_id,
            MealComboSuggestion.user_id == user.id,
            MealComboSuggestion.status == "pending",
        )
    )
    if suggestion is None:
        return None

    entries = await get_entries_for_day(
        session,
        user_id=user.id,
        day=suggestion.source_day,
        timezone_name=user.timezone,
    )
    group = meal_group_entries(
        entries,
        meal_type=suggestion.meal_type,
        snack_number=suggestion.snack_number,
    )
    profile = meal_item_profile(group)
    if (
        not MIN_COMBO_ITEMS <= len(profile) <= MAX_MEAL_TEMPLATE_ITEMS
        or combo_signature(profile) != suggestion.signature
    ):
        suggestion.status = "dismissed"
        await session.commit()
        return None

    templates = await list_user_meal_templates(session, user_id=user.id)
    if any(profiles_are_similar(profile, template_profile(template)) for template in templates):
        suggestion.status = "saved"
        await session.commit()
        return None

    items: list[tuple[Food, Decimal]] = []
    for item in profile:
        food = await load_food(session, user_id=user.id, food_id=item.food_id)
        if food is None:
            suggestion.status = "dismissed"
            await session.commit()
            return None
        if item.is_full_serving:
            serving_count = int(item.amount)
            if Decimal(serving_count) != item.amount or serving_count < 1:
                suggestion.status = "dismissed"
                await session.commit()
                return None
            items.extend((food, Decimal(1)) for _ in range(serving_count))
        else:
            items.append((food, item.amount))
    if len(items) > MAX_MEAL_TEMPLATE_ITEMS:
        suggestion.status = "dismissed"
        await session.commit()
        return None

    template = await create_meal_template(
        session,
        user_id=user.id,
        name=automatic_template_name(templates, suggestion.meal_type),
        meal_type=suggestion.meal_type,
        items=items,
    )
    suggestion.status = "saved"
    await session.commit()
    return template


async def dismiss_frequent_combo_suggestion(
    session: AsyncSession,
    *,
    user_id: int,
    suggestion_id: int,
) -> bool:
    """Dismiss one suggestion permanently for this product combination."""
    suggestion = await session.scalar(
        select(MealComboSuggestion).where(
            MealComboSuggestion.id == suggestion_id,
            MealComboSuggestion.user_id == user_id,
            MealComboSuggestion.status == "pending",
        )
    )
    if suggestion is None:
        return False
    suggestion.status = "dismissed"
    await session.commit()
    return True


def template_profile(template: MealTemplate) -> tuple[MealItemProfile, ...]:
    """Convert a stored template into the same comparable aggregate profile."""
    grouped: dict[tuple[int, bool], MealItemProfile] = {}
    for item in template.items:
        key = (item.food_id, item.is_full_serving)
        amount = Decimal(item.weight_grams)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = MealItemProfile(
                food_id=item.food_id,
                name=item.food.name,
                amount=amount,
                is_full_serving=item.is_full_serving,
            )
        else:
            grouped[key] = MealItemProfile(
                food_id=existing.food_id,
                name=existing.name,
                amount=existing.amount + amount,
                is_full_serving=existing.is_full_serving,
            )
    return tuple(sorted(grouped.values(), key=lambda item: (item.food_id, item.is_full_serving)))


def automatic_template_name(
    templates: list[MealTemplate],
    meal_type: str,
) -> str:
    """Choose a short meal-based template name without colliding with saved names."""
    base = _AUTO_TEMPLATE_NAMES[meal_type]
    used = {template.name_normalized for template in templates}
    if base.casefold() not in used:
        return base
    for number in range(2, 100):
        candidate = f"{base} {number}"
        if candidate.casefold() not in used:
            return candidate
    return f"{base} авто"


def format_frequent_combo_prompt(suggestion: FrequentMealSuggestion) -> str:
    """Explain the detected combo and proposed reusable template name."""
    lines = [
        f"💡 Вы уже {suggestion.occurrence_count} раза добавляли этот набор вместе:",
    ]
    for item in suggestion.items:
        amount = (
            f"{format_decimal(item.amount)} порц."
            if item.is_full_serving
            else f"{format_decimal(item.amount)} г"
        )
        lines.append(f"• {item.name} — {amount}")
    lines.extend(
        [
            "",
            f"Сохранить как шаблон «{suggestion.name}»?",
            "После сохранения весь набор можно будет добавить одним действием.",
        ]
    )
    return "\n".join(lines)
