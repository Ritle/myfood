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




@dataclass(frozen=True, slots=True)
class MacroSource:
    """One food's contribution to a selected macro across the logical day."""

    food_name: str
    amount: Decimal
    meal_labels: tuple[str, ...]


MACRO_FIELDS = {
    "protein": ("🥩 Белки", "protein"),
    "fat": ("🥑 Жиры", "fat"),
    "carbs": ("🍞 Углеводы", "carbs"),
}
MAX_MACRO_SOURCES = 20


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



def macro_sources(
    entries: list[FoodEntry],
    *,
    macro: str,
) -> list[MacroSource]:
    """Aggregate one macro by food and retain the meals where it came from."""
    if macro not in MACRO_FIELDS:
        raise ValueError("unknown macro")

    _, field = MACRO_FIELDS[macro]
    grouped: dict[int, tuple[str, Decimal, list[str]]] = {}
    for entry in entries:
        amount = Decimal(getattr(entry, field))
        if amount <= 0:
            continue
        label = meal_label(entry.meal_type, entry.snack_number)
        existing = grouped.get(entry.food_id)
        if existing is None:
            grouped[entry.food_id] = (entry.food.name, amount, [label])
        else:
            name, total, meals = existing
            if label not in meals:
                meals.append(label)
            grouped[entry.food_id] = (name, total + amount, meals)

    sources = [
        MacroSource(
            food_name=name,
            amount=amount,
            meal_labels=tuple(meals),
        )
        for name, amount, meals in grouped.values()
    ]
    return sorted(
        sources,
        key=lambda source: (-source.amount, source.food_name.casefold()),
    )


def format_macro_sources(
    entries: list[FoodEntry],
    *,
    macro: str,
    target: Decimal | None = None,
    day_label: str | None = None,
) -> str:
    """Explain which foods contributed to a day's protein, fat, or carbs."""
    if macro not in MACRO_FIELDS:
        raise ValueError("unknown macro")
    label, _ = MACRO_FIELDS[macro]
    sources = macro_sources(entries, macro=macro)
    total = sum((source.amount for source in sources), Decimal(0))

    title = f"{label} — источники"
    if day_label:
        title += f" · {day_label}"
    lines = [title, ""]
    if target is not None:
        lines.append(
            f"Всего: {format_decimal(total)} / {format_decimal(target)} г"
        )
    else:
        lines.append(f"Всего: {format_decimal(total)} г")

    if total <= 0:
        lines.extend(["", "За этот день источников пока нет."])
        return "\n".join(lines)

    lines.append("")
    visible = sources[:MAX_MACRO_SOURCES]
    for index, source in enumerate(visible, start=1):
        share = (
            source.amount / total * Decimal(100)
        ).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        meals = ", ".join(source.meal_labels)
        lines.append(
            f"{index}. {source.food_name} — "
            f"{format_decimal(source.amount)} г ({share}%) · {meals}"
        )

    hidden = sources[MAX_MACRO_SOURCES:]
    if hidden:
        hidden_total = sum((source.amount for source in hidden), Decimal(0))
        hidden_share = (
            hidden_total / total * Decimal(100)
        ).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        lines.append(
            f"… ещё {len(hidden)} источн. — "
            f"{format_decimal(hidden_total)} г ({hidden_share}%)"
        )

    return "\n".join(lines)


def macro_target(user: User, macro: str) -> Decimal | None:
    """Return the user's target for one supported macro."""
    if macro == "protein":
        return user.daily_protein_target_g
    if macro == "fat":
        return user.daily_fat_target_g
    if macro == "carbs":
        return user.daily_carbs_target_g
    raise ValueError("unknown macro")
