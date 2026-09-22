from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.models import FoodEntry, NotificationSettings, User
from app.services.diary import MEAL_LABELS, DiarySummary, summarize_entries
from app.utils.formatting import format_decimal

MAIN_MEALS = ("breakfast", "lunch", "dinner")
MEAL_TARGET_FRACTIONS = {
    "breakfast": Decimal("0.30"),
    "lunch": Decimal("0.40"),
    "dinner": Decimal("0.30"),
}
MEAL_REVIEW_DELAY = timedelta(minutes=10)
MEAL_REVIEW_GRACE = timedelta(hours=1)
NUTRITION_TOLERANCE = Decimal("0.15")
STRONG_DEVIATION = Decimal("0.30")

_METRICS = (
    ("calories", "Калории", "daily_calorie_target", "calories", "ккал"),
    ("protein", "Белки", "daily_protein_target_g", "protein", "г"),
    ("fat", "Жиры", "daily_fat_target_g", "fat", "г"),
    ("carbs", "Углеводы", "daily_carbs_target_g", "carbs", "г"),
)
_SUMMARY_FIELDS = {
    key: summary_field for key, _, _, summary_field, _ in _METRICS
}


@dataclass(frozen=True, slots=True)
class NutritionTarget:
    key: str
    label: str
    value: Decimal
    unit: str


def has_nutrition_targets(user: User) -> bool:
    """Return whether at least one daily calorie/macro target is configured."""
    return bool(daily_targets(user))


def daily_targets(user: User) -> dict[str, NutritionTarget]:
    """Return configured positive daily nutrition targets."""
    result: dict[str, NutritionTarget] = {}
    for key, label, user_field, _, unit in _METRICS:
        raw_value = getattr(user, user_field)
        if raw_value is None:
            continue
        value = Decimal(raw_value)
        if value <= 0:
            continue
        result[key] = NutritionTarget(key, label, value, unit)
    return result


def meal_targets(user: User, meal_type: str) -> dict[str, NutritionTarget]:
    """Return the original fixed 30/40/30 baseline for one main meal."""
    fraction = MEAL_TARGET_FRACTIONS.get(meal_type)
    if fraction is None:
        return {}
    return scale_targets(daily_targets(user), fraction)


def adaptive_meal_targets(
    user: User,
    entries: list[FoodEntry],
    meal_type: str,
) -> dict[str, NutritionTarget]:
    """Calculate a meal target from what was actually eaten before that meal.

    Remaining daily targets are redistributed across the current and later
    main meals using their original 30/40/30 weights. Snacks consumed before
    the meal therefore reduce the remaining plan without becoming a separate
    planned meal.
    """
    if meal_type not in MAIN_MEALS:
        return {}
    targets = daily_targets(user)
    if not targets:
        return {}

    consumed_before = summarize_entries(entries_before_meal(entries, meal_type))
    remaining = remaining_from_summary(targets, consumed_before)
    start = MAIN_MEALS.index(meal_type)
    remaining_meals = MAIN_MEALS[start:]
    weight_sum = sum(
        (MEAL_TARGET_FRACTIONS[item] for item in remaining_meals),
        Decimal(0),
    )
    fraction = MEAL_TARGET_FRACTIONS[meal_type] / weight_sum
    return targets_from_remaining(targets, remaining, fraction)


def remaining_meal_plan(
    user: User,
    entries: list[FoodEntry],
    meal_types: tuple[str, ...],
) -> dict[str, dict[str, NutritionTarget]]:
    """Redistribute today's remaining targets across selected main meals."""
    valid_meals = tuple(meal for meal in meal_types if meal in MAIN_MEALS)
    if not valid_meals:
        return {}
    targets = daily_targets(user)
    if not targets:
        return {}

    consumed = summarize_entries(entries)
    remaining = remaining_from_summary(targets, consumed)
    weight_sum = sum(
        (MEAL_TARGET_FRACTIONS[meal] for meal in valid_meals),
        Decimal(0),
    )
    if weight_sum <= 0:
        return {}

    return {
        meal: targets_from_remaining(
            targets,
            remaining,
            MEAL_TARGET_FRACTIONS[meal] / weight_sum,
        )
        for meal in valid_meals
    }


def entries_before_meal(
    entries: list[FoodEntry],
    meal_type: str,
) -> list[FoodEntry]:
    """Return entries consumed before the reviewed meal started."""
    meal_entries = [entry for entry in entries if entry.meal_type == meal_type]
    if meal_entries:
        cutoff = min(as_utc(entry.eaten_at) for entry in meal_entries)
        return [
            entry
            for entry in entries
            if entry.meal_type != meal_type and as_utc(entry.eaten_at) < cutoff
        ]

    meal_index = MAIN_MEALS.index(meal_type)
    earlier_meals = set(MAIN_MEALS[:meal_index])
    return [
        entry
        for entry in entries
        if entry.meal_type in earlier_meals or entry.meal_type == "snack"
    ]


def remaining_from_summary(
    targets: dict[str, NutritionTarget],
    summary: DiarySummary,
) -> dict[str, Decimal]:
    """Return non-negative remaining values for each configured target."""
    return {
        key: max(
            Decimal(0),
            target.value - Decimal(getattr(summary, _SUMMARY_FIELDS[key])),
        )
        for key, target in targets.items()
    }


def scale_targets(
    targets: dict[str, NutritionTarget],
    fraction: Decimal,
) -> dict[str, NutritionTarget]:
    return {
        key: NutritionTarget(
            target.key,
            target.label,
            round_value(target.value * fraction),
            target.unit,
        )
        for key, target in targets.items()
    }


def targets_from_remaining(
    targets: dict[str, NutritionTarget],
    remaining: dict[str, Decimal],
    fraction: Decimal,
) -> dict[str, NutritionTarget]:
    return {
        key: NutritionTarget(
            target.key,
            target.label,
            round_value(remaining[key] * fraction),
            target.unit,
        )
        for key, target in targets.items()
    }


def latest_meal_eaten_at(
    entries: list[FoodEntry], meal_type: str
) -> datetime | None:
    """Return the latest timestamp for one main meal."""
    values = [
        as_utc(entry.eaten_at)
        for entry in entries
        if entry.meal_type == meal_type
    ]
    return max(values, default=None)


def expected_fraction_at(
    settings: NotificationSettings, checkpoint: time
) -> Decimal:
    """Return the share of daily targets expected by a local checkpoint."""
    fraction = Decimal(0)
    for meal_type, settings_field in (
        ("breakfast", "breakfast_time"),
        ("lunch", "lunch_time"),
        ("dinner", "dinner_time"),
    ):
        if getattr(settings, settings_field) <= checkpoint:
            fraction += MEAL_TARGET_FRACTIONS[meal_type]
    return fraction


def format_meal_review(
    user: User,
    entries: list[FoodEntry],
    *,
    meal_type: str,
) -> str | None:
    """Render adaptive calorie and macro assessment for one non-snack meal."""
    targets = adaptive_meal_targets(user, entries, meal_type)
    if not targets:
        return None
    meal_entries = [entry for entry in entries if entry.meal_type == meal_type]
    if not meal_entries:
        return None

    summary = summarize_entries(meal_entries)
    base_fraction = int(MEAL_TARGET_FRACTIONS[meal_type] * 100)
    lines = [
        f"📌 {MEAL_LABELS[meal_type]} — контроль КБЖУ",
        (
            f"Адаптивный ориентир (база {base_fraction}% дневной цели): "
            "учтено всё, что было съедено раньше."
        ),
        "",
    ]
    lines.extend(format_target_lines(summary, targets))

    current_index = MAIN_MEALS.index(meal_type)
    future_meals = MAIN_MEALS[current_index + 1 :]
    future_plan = remaining_meal_plan(user, entries, future_meals)
    if future_plan:
        lines.extend(["", "План на оставшиеся основные приёмы:"])
        for future_meal in future_meals:
            lines.append(
                format_meal_plan_line(
                    future_meal,
                    future_plan[future_meal],
                )
            )
    return "\n".join(lines)


def format_day_checkpoint(
    user: User,
    entries: list[FoodEntry],
    *,
    settings: NotificationSettings,
    checkpoint: time,
) -> str | None:
    """Render daytime progress and an adaptive plan for meals still ahead."""
    targets = daily_targets(user)
    if not targets:
        return None
    fraction = expected_fraction_at(settings, checkpoint)
    if fraction <= 0:
        return None
    expected = scale_targets(targets, fraction)
    summary = summarize_entries(entries)
    percent = int(fraction * 100)
    lines = [
        f"📊 Сводка КБЖУ на {checkpoint:%H:%M}",
        f"К этому времени ориентир — около {percent}% дневной цели.",
        "",
    ]
    lines.extend(format_target_lines(summary, expected))
    remaining = format_remaining(summary, targets)
    if remaining:
        lines.extend(["", f"До полной дневной цели: {remaining}"])

    recorded_meals = {
        entry.meal_type
        for entry in entries
        if entry.meal_type in MAIN_MEALS
    }
    pending_meals = tuple(
        meal for meal in MAIN_MEALS if meal not in recorded_meals
    )
    pending_plan = remaining_meal_plan(user, entries, pending_meals)
    if pending_plan:
        lines.extend(["", "Адаптивный план на оставшиеся основные приёмы:"])
        for meal in pending_meals:
            lines.append(format_meal_plan_line(meal, pending_plan[meal]))
    return "\n".join(lines)


def format_target_lines(
    summary: DiarySummary, targets: dict[str, NutritionTarget]
) -> list[str]:
    """Format status lines for configured nutrition metrics."""
    lines: list[str] = []
    for key, target in targets.items():
        actual = Decimal(getattr(summary, _SUMMARY_FIELDS[key]))
        if target.value <= 0:
            if actual > 0:
                lines.append(
                    f"⚠️ {target.label}: {format_decimal(actual)} {target.unit} — "
                    "дневная цель была уже закрыта до этого приёма"
                )
            else:
                lines.append(
                    f"✅ {target.label}: 0 {target.unit} — "
                    "дневная цель уже была закрыта"
                )
            continue
        status = deviation_status(actual, target.value)
        lines.append(
            f"{status_icon(status)} {target.label}: "
            f"{format_decimal(actual)} / {format_decimal(target.value)} "
            f"{target.unit} — {status_text(status, actual, target.value)}"
        )
    return lines


def format_meal_plan_line(
    meal_type: str,
    targets: dict[str, NutritionTarget],
) -> str:
    """Format one compact adaptive target for a future meal."""
    parts: list[str] = []
    for key, short in (
        ("calories", ""),
        ("protein", "Б "),
        ("fat", "Ж "),
        ("carbs", "У "),
    ):
        target = targets.get(key)
        if target is None:
            continue
        parts.append(
            f"{short}{format_decimal(target.value)} {target.unit}"
        )
    return f"{MEAL_LABELS[meal_type]}: " + " · ".join(parts)


def deviation_status(actual: Decimal, target: Decimal) -> str:
    """Classify a value relative to the configured tolerance corridor."""
    if target <= 0:
        return "ok"
    ratio = actual / target
    if ratio < Decimal(1) - STRONG_DEVIATION:
        return "strong_under"
    if ratio < Decimal(1) - NUTRITION_TOLERANCE:
        return "under"
    if ratio > Decimal(1) + STRONG_DEVIATION:
        return "strong_over"
    if ratio > Decimal(1) + NUTRITION_TOLERANCE:
        return "over"
    return "ok"


def status_icon(status: str) -> str:
    if status in {"strong_under", "strong_over"}:
        return "🔴"
    if status in {"under", "over"}:
        return "⚠️"
    return "✅"


def status_text(status: str, actual: Decimal, target: Decimal) -> str:
    if status == "ok":
        return "в пределах плана"
    difference = abs(actual - target)
    percent = int(
        ((difference / target) * Decimal(100)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )
    labels = {
        "strong_under": "сильный недобор",
        "under": "недобор",
        "over": "перебор",
        "strong_over": "сильный перебор",
    }
    return f"{labels[status]} ~{percent}%"


def format_remaining(
    summary: DiarySummary, targets: dict[str, NutritionTarget]
) -> str:
    """Format remaining daily targets compactly; omit already exceeded metrics."""
    parts: list[str] = []
    for key, target in targets.items():
        actual = Decimal(getattr(summary, _SUMMARY_FIELDS[key]))
        remaining = target.value - actual
        if remaining <= 0:
            continue
        short_label = {
            "calories": "",
            "protein": "Б ",
            "fat": "Ж ",
            "carbs": "У ",
        }[key]
        parts.append(
            f"{short_label}{format_decimal(round_value(remaining))} {target.unit}"
        )
    return " · ".join(parts)


def round_value(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive and aware timestamps to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
