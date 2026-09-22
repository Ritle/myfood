from collections import defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.models import FoodEntry, User
from app.services.diary import MEAL_LABELS, DiarySummary, meal_label, summarize_entries
from app.services.food_guidance import format_remaining_guidance
from app.utils.formatting import format_decimal


@dataclass(frozen=True, slots=True)
class DailyView:
    """Data prepared for rendering the Today screen."""

    total: DiarySummary
    meal_calories: dict[str, Decimal]
    snack_calories: dict[int, Decimal]


def build_daily_view(entries: list[FoodEntry]) -> DailyView:
    """Aggregate total nutrients and calories by meal."""
    meal_entries: dict[str, list[FoodEntry]] = defaultdict(list)
    snack_entries: dict[int, list[FoodEntry]] = defaultdict(list)
    for entry in entries:
        meal_entries[entry.meal_type].append(entry)
        if entry.meal_type == "snack":
            snack_entries[entry.snack_number or 1].append(entry)
    return DailyView(
        total=summarize_entries(entries),
        meal_calories={
            meal_type: summarize_entries(meal_entries[meal_type]).calories
            for meal_type in MEAL_LABELS
        },
        snack_calories={
            number: summarize_entries(group).calories
            for number, group in snack_entries.items()
        },
    )


def progress_bar(actual: Decimal, target: Decimal, *, width: int = 10) -> str:
    """Render a bounded text progress bar and an unbounded percentage."""
    if target <= 0 or width <= 0:
        raise ValueError("target and width must be positive")
    ratio = actual / target
    percent = int((ratio * Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    filled = min(width, max(0, int(ratio * width)))
    return f"{'█' * filled}{'░' * (width - filled)} {percent}%"


def format_today(user: User, entries: list[FoodEntry], *, water_ml: int = 0) -> str:
    """Render today's calories, macro targets, progress, and meal distribution."""
    view = build_daily_view(entries)
    total = view.total
    lines = ["📊 Сегодня", "", "🔥 Калории:"]
    if user.daily_calorie_target:
        target = Decimal(user.daily_calorie_target)
        lines.extend(
            [
                progress_bar(total.calories, target),
                f"{format_decimal(total.calories)} / {user.daily_calorie_target} ккал",
            ]
        )
        difference = target - total.calories
        if difference >= 0:
            lines.append(f"Осталось: {format_decimal(difference)} ккал")
        else:
            lines.append(f"Превышение: +{format_decimal(abs(difference))} ккал")
    else:
        lines.append(f"{format_decimal(total.calories)} ккал · цель не задана")

    lines.extend(
        [
            "",
            format_nutrient("🥩 Белки", total.protein, user.daily_protein_target_g),
            format_nutrient("🥑 Жиры", total.fat, user.daily_fat_target_g),
            format_nutrient("🍞 Углеводы", total.carbs, user.daily_carbs_target_g),
            format_water(water_ml, user.daily_water_target_ml),
        ]
    )
    remaining_guidance = format_remaining_guidance(user, entries)
    if remaining_guidance is not None:
        lines.extend(["", remaining_guidance])
    lines.extend(
        [
            "",
            "По приемам пищи:",
        ]
    )
    for meal_type in ("breakfast", "lunch", "dinner"):
        lines.append(
            f"{MEAL_LABELS[meal_type]}: "
            f"{format_decimal(view.meal_calories[meal_type])} ккал"
        )
    if view.snack_calories:
        for number in sorted(view.snack_calories):
            lines.append(
                f"{meal_label('snack', number)}: "
                f"{format_decimal(view.snack_calories[number])} ккал"
            )
    else:
        lines.append(f"{MEAL_LABELS['snack']}: 0 ккал")
    return "\n".join(lines)


def format_nutrient(label: str, actual: Decimal, target: Decimal | None) -> str:
    """Format an actual macro value with an optional target."""
    target_text = format_decimal(target) if target is not None else "—"
    return f"{label}: {format_decimal(actual)} / {target_text} г"


def format_water(actual_ml: int, target_ml: int | None) -> str:
    """Format water intake with an optional target."""
    target_text = str(target_ml) if target_ml is not None else "—"
    return f"💧 Вода: {actual_ml} / {target_text} мл"
