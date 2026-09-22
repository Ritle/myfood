from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.nutrition import (
    calculate_daily_calorie_target,
    calculate_daily_macronutrient_targets,
)

NUTRITION_RECALC_WEIGHT_DELTA_KG = Decimal(3)


@dataclass(frozen=True, slots=True)
class NutritionRecalculation:
    weight_kg: Decimal
    old_calories: int | None
    old_protein: Decimal | None
    old_fat: Decimal | None
    old_carbs: Decimal | None
    calories: int
    protein: int
    fat: int
    carbs: int


def nutrition_recalculation_due(user: User, weight_kg: Decimal) -> bool:
    """Return whether weight moved enough since the last recalculation prompt."""
    if build_nutrition_recalculation(user, weight_kg) is None:
        return False
    anchor = (
        user.nutrition_recalc_prompt_weight_kg
        or user.nutrition_target_weight_kg
    )
    if anchor is None:
        return False
    return abs(Decimal(weight_kg) - Decimal(anchor)) >= NUTRITION_RECALC_WEIGHT_DELTA_KG


def build_nutrition_recalculation(
    user: User,
    weight_kg: Decimal,
    *,
    today: date | None = None,
) -> NutritionRecalculation | None:
    """Calculate a preview without changing the stored nutrition targets."""
    if (
        user.gender not in {"female", "male"}
        or user.birth_date is None
        or user.height_cm is None
        or user.activity_level is None
        or user.goal is None
        or user.daily_calorie_target is None
    ):
        return None

    calories = calculate_daily_calorie_target(
        gender=user.gender,
        birth_date=user.birth_date,
        height_cm=Decimal(user.height_cm),
        weight_kg=Decimal(weight_kg),
        activity_level=user.activity_level,
        goal=user.goal,
        today=today or datetime.now(UTC).date(),
    )
    protein, fat, carbs = calculate_daily_macronutrient_targets(
        calories,
        weight_kg=Decimal(weight_kg),
        activity_level=user.activity_level,
        goal=user.goal,
    )
    return NutritionRecalculation(
        weight_kg=Decimal(weight_kg),
        old_calories=user.daily_calorie_target,
        old_protein=user.daily_protein_target_g,
        old_fat=user.daily_fat_target_g,
        old_carbs=user.daily_carbs_target_g,
        calories=calories,
        protein=protein,
        fat=fat,
        carbs=carbs,
    )


async def mark_nutrition_recalculation_prompted(
    session: AsyncSession,
    *,
    user: User,
    weight_kg: Decimal,
) -> None:
    """Remember the weight at which the user was last offered recalculation."""
    user.nutrition_recalc_prompt_weight_kg = Decimal(weight_kg)
    await session.commit()
    await session.refresh(user)


async def apply_nutrition_recalculation(
    session: AsyncSession,
    *,
    user: User,
    expected_weight_kg: Decimal,
) -> NutritionRecalculation | None:
    """Apply recalculation only if the confirmation still matches current weight."""
    if (
        user.current_weight_kg is None
        or Decimal(user.current_weight_kg) != Decimal(expected_weight_kg)
    ):
        return None
    result = build_nutrition_recalculation(user, Decimal(expected_weight_kg))
    if result is None:
        return None

    user.daily_calorie_target = result.calories
    user.daily_protein_target_g = Decimal(result.protein)
    user.daily_fat_target_g = Decimal(result.fat)
    user.daily_carbs_target_g = Decimal(result.carbs)
    user.nutrition_target_weight_kg = Decimal(expected_weight_kg)
    user.nutrition_recalc_prompt_weight_kg = Decimal(expected_weight_kg)
    await session.commit()
    await session.refresh(user)
    return result
