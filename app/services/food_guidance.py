from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Food, FoodEntry, User
from app.repositories.foods import list_visible_food_candidates
from app.services.diary import DiarySummary, summarize_entries
from app.services.foods import favorite_foods, recent_foods
from app.utils.formatting import format_decimal


class FoodRecommendation:
    """A catalog item with a suggested portion sized to the remaining targets."""

    def __init__(
        self,
        *,
        food: Food,
        amount_label: str,
        calories: Decimal,
        protein: Decimal,
        fat: Decimal,
        carbs: Decimal,
        score: Decimal,
    ) -> None:
        self.food = food
        self.amount_label = amount_label
        self.calories = calories
        self.protein = protein
        self.fat = fat
        self.carbs = carbs
        self.score = score


def remaining_targets(user: User, entries: list[FoodEntry]) -> dict[str, Decimal]:
    """Return positive calorie/macro amounts still available today."""
    total = summarize_entries(entries)
    targets = {
        "calories": Decimal(user.daily_calorie_target)
        if user.daily_calorie_target is not None
        else None,
        "protein": user.daily_protein_target_g,
        "fat": user.daily_fat_target_g,
        "carbs": user.daily_carbs_target_g,
    }
    actual = {
        "calories": total.calories,
        "protein": total.protein,
        "fat": total.fat,
        "carbs": total.carbs,
    }
    return {
        key: max(Decimal(0), Decimal(value) - actual[key])
        for key, value in targets.items()
        if value is not None and Decimal(value) > 0
    }


def dominant_deficit(user: User, entries: list[FoodEntry]) -> str | None:
    """Return the macro with the largest remaining share of its daily target."""
    total = summarize_entries(entries)
    candidates: list[tuple[Decimal, str]] = []
    for key, target, actual in (
        ("protein", user.daily_protein_target_g, total.protein),
        ("fat", user.daily_fat_target_g, total.fat),
        ("carbs", user.daily_carbs_target_g, total.carbs),
    ):
        if target is None or target <= 0:
            continue
        remaining = max(Decimal(0), Decimal(target) - actual)
        if remaining > 0:
            candidates.append((remaining / Decimal(target), key))
    return max(candidates, default=(Decimal(0), ""))[1] or None


def format_remaining_guidance(user: User, entries: list[FoodEntry]) -> str | None:
    """Explain what remains today and which macro deserves the most attention."""
    total = summarize_entries(entries)
    if not any(
        target is not None
        for target in (
            user.daily_calorie_target,
            user.daily_protein_target_g,
            user.daily_fat_target_g,
            user.daily_carbs_target_g,
        )
    ):
        return None

    lines = ["🍽 Что осталось на сегодня:"]
    if user.daily_calorie_target is not None:
        difference = Decimal(user.daily_calorie_target) - total.calories
        if difference > 0:
            lines.append(f"🔥 ~{format_decimal(difference)} ккал")
        elif difference < 0:
            lines.append(f"🔥 калории уже выше цели на {format_decimal(abs(difference))} ккал")
        else:
            lines.append("🔥 калории точно по цели")

    macro_values = (
        ("protein", "Б", user.daily_protein_target_g, total.protein),
        ("fat", "Ж", user.daily_fat_target_g, total.fat),
        ("carbs", "У", user.daily_carbs_target_g, total.carbs),
    )
    for _, short, target, actual in macro_values:
        if target is None:
            continue
        difference = Decimal(target) - actual
        if difference > 0:
            lines.append(f"{short}: ~{format_decimal(difference)} г")
        elif difference < 0:
            lines.append(f"{short}: выше цели на {format_decimal(abs(difference))} г")
        else:
            lines.append(f"{short}: цель закрыта")

    dominant = dominant_deficit(user, entries)
    if dominant is not None:
        labels = {"protein": "белок", "fat": "жиры", "carbs": "углеводы"}
        remaining = remaining_targets(user, entries).get(dominant, Decimal(0))
        lines.extend(
            [
                "",
                f"Ориентир: сейчас сильнее всего не хватает — {labels[dominant]} "
                f"(~{format_decimal(remaining)} г).",
            ]
        )

    cautions: list[str] = []
    for key, label, target, actual in (
        ("protein", "белок", user.daily_protein_target_g, total.protein),
        ("fat", "жиры", user.daily_fat_target_g, total.fat),
        ("carbs", "углеводы", user.daily_carbs_target_g, total.carbs),
    ):
        if target is None or target <= 0:
            continue
        ratio = actual / Decimal(target)
        if ratio >= Decimal("1.0"):
            cautions.append(f"{label} уже закрыты")
        elif ratio >= Decimal("0.9"):
            cautions.append(f"{label} почти закрыты")
    if cautions:
        lines.append("С аккуратностью: " + ", ".join(cautions) + ".")

    return "\n".join(lines)


async def recommend_foods_for_today(
    session: AsyncSession,
    *,
    user: User,
    entries: list[FoodEntry],
    limit: int = 5,
) -> list[FoodRecommendation]:
    """Rank visible catalog foods against the user's current remaining targets."""
    if limit <= 0:
        return []
    remaining = remaining_targets(user, entries)
    dominant = dominant_deficit(user, entries)
    if not remaining or all(value <= 0 for value in remaining.values()):
        return []

    candidates: list[Food] = []
    candidates.extend(await recent_foods(session, user_id=user.id, limit=30))
    candidates.extend(await favorite_foods(session, user_id=user.id))
    candidates.extend(
        await list_visible_food_candidates(
            session,
            user_id=user.id,
            nutrient=dominant or "protein",
            limit=250,
        )
    )

    unique: list[Food] = []
    seen: set[int] = set()
    for food in candidates:
        if food.id is None or food.id in seen:
            continue
        seen.add(food.id)
        unique.append(food)

    ranked = [
        recommendation_for_food(food, remaining=remaining, dominant=dominant)
        for food in unique
    ]
    ranked = [item for item in ranked if item is not None]
    ranked.sort(key=lambda item: (-item.score, item.food.name.casefold()))
    return ranked[:limit]


def recommendation_for_food(
    food: Food,
    *,
    remaining: dict[str, Decimal],
    dominant: str | None,
) -> FoodRecommendation | None:
    """Score one product and choose a practical serving for the current deficit."""
    nutrients = {
        "calories": Decimal(food.calories_per_100g),
        "protein": Decimal(food.protein_per_100g),
        "fat": Decimal(food.fat_per_100g),
        "carbs": Decimal(food.carbs_per_100g),
    }
    if nutrients["calories"] <= 0 or sum(nutrients[key] for key in ("protein", "fat", "carbs")) <= 0:
        return None
    if dominant is not None and nutrients[dominant] <= 0:
        return None

    if food.nutrition_basis == "portion":
        factor = Decimal(1)
        amount_label = "1 порция"
    else:
        factor = Decimal(1)
        if dominant is not None and remaining.get(dominant, Decimal(0)) > 0:
            factor = remaining[dominant] / nutrients[dominant]
        if remaining.get("calories", Decimal(0)) > 0:
            calorie_factor = remaining["calories"] / nutrients["calories"]
            factor = min(factor, calorie_factor)
        factor = min(Decimal("2.5"), max(Decimal("0.5"), factor))
        grams = int(
            (factor * Decimal(100) / Decimal(10)).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            )
            * 10
        )
        factor = Decimal(grams) / Decimal(100)
        amount_label = f"~{grams} г"

    portion = {key: value * factor for key, value in nutrients.items()}
    score = Decimal(0)
    weights = {"calories": Decimal("1.5"), "protein": Decimal(1), "fat": Decimal(1), "carbs": Decimal(1)}
    if dominant is not None:
        weights[dominant] = Decimal(4)

    for key, weight in weights.items():
        target_remaining = remaining.get(key)
        if target_remaining is None or target_remaining <= 0:
            if key != "calories":
                score -= portion[key] / Decimal(20)
            continue
        coverage = min(Decimal(1), portion[key] / target_remaining)
        score += coverage * weight
        if portion[key] > target_remaining:
            score -= (
                (portion[key] - target_remaining)
                / max(target_remaining, Decimal(1))
                * weight
                * Decimal("1.5")
            )

    return FoodRecommendation(
        food=food,
        amount_label=amount_label,
        calories=portion["calories"],
        protein=portion["protein"],
        fat=portion["fat"],
        carbs=portion["carbs"],
        score=score,
    )


def format_food_recommendations(
    user: User,
    entries: list[FoodEntry],
    recommendations: list[FoodRecommendation],
) -> str:
    """Render ranked catalog suggestions for the current daily remainder."""
    dominant = dominant_deficit(user, entries)
    remaining = remaining_targets(user, entries)
    labels = {"protein": "белок", "fat": "жиры", "carbs": "углеводы"}
    lines = ["🍽 Что можно съесть сегодня"]
    if dominant is not None:
        lines.append(
            f"Сейчас приоритет — {labels[dominant]} "
            f"(осталось ~{format_decimal(remaining.get(dominant, Decimal(0)))} г)."
        )
    lines.append("")
    if not recommendations:
        lines.append("Подходящих вариантов в каталоге не найдено.")
        return "\n".join(lines)

    for index, item in enumerate(recommendations, start=1):
        lines.extend(
            [
                f"{index}. {item.food.name} — {item.amount_label}",
                f"   ≈ {format_decimal(item.calories)} ккал · "
                f"Б {format_decimal(item.protein)} · "
                f"Ж {format_decimal(item.fat)} · "
                f"У {format_decimal(item.carbs)}",
            ]
        )
    lines.extend(
        [
            "",
            "Это ориентировочный подбор по текущему остатку КБЖУ, "
            "а не обязательное меню.",
        ]
    )
    return "\n".join(lines)
