from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.models import FoodEntry, NotificationSettings, User
from app.services.diary import MEAL_LABELS, DiarySummary, summarize_entries
from app.utils.formatting import format_decimal

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
    """Scale daily targets to one main meal."""
    fraction = MEAL_TARGET_FRACTIONS.get(meal_type)
    if fraction is None:
        return {}
    return {
        key: NutritionTarget(
            target.key,
            target.label,
            round_value(target.value * fraction),
            target.unit,
        )
        for key, target in daily_targets(user).items()
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
    """Render calorie and macro assessment for one non-snack meal."""
    targets = meal_targets(user, meal_type)
    if not targets:
        return None
    meal_entries = [entry for entry in entries if entry.meal_type == meal_type]
    if not meal_entries:
        return None
    summary = summarize_entries(meal_entries)
    fraction = int(MEAL_TARGET_FRACTIONS[meal_type] * 100)
    lines = [
        f"📌 {MEAL_LABELS[meal_type]} — контроль КБЖУ",
        f"Ориентир: {fraction}% дневной цели.",
        "",
    ]
    lines.extend(format_target_lines(summary, targets))
    return "\n".join(lines)


def format_day_checkpoint(
    user: User,
    entries: list[FoodEntry],
    *,
    settings: NotificationSettings,
    checkpoint: time,
) -> str | None:
    """Render a daytime progress check against targets expected by this time."""
    targets = daily_targets(user)
    if not targets:
        return None
    fraction = expected_fraction_at(settings, checkpoint)
    if fraction <= 0:
        return None
    expected = {
        key: NutritionTarget(
            target.key,
            target.label,
            round_value(target.value * fraction),
            target.unit,
        )
        for key, target in targets.items()
    }
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
    return "\n".join(lines)


def format_target_lines(
    summary: DiarySummary, targets: dict[str, NutritionTarget]
) -> list[str]:
    """Format status lines for configured nutrition metrics."""
    lines: list[str] = []
    summary_fields = {
        key: summary_field for key, _, _, summary_field, _ in _METRICS
    }
    for key, target in targets.items():
        actual = Decimal(getattr(summary, summary_fields[key]))
        status = deviation_status(actual, target.value)
        lines.append(
            f"{status_icon(status)} {target.label}: "
            f"{format_decimal(actual)} / {format_decimal(target.value)} "
            f"{target.unit} — {status_text(status, actual, target.value)}"
        )
    return lines


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
    summary_fields = {
        key: summary_field for key, _, _, summary_field, _ in _METRICS
    }
    parts: list[str] = []
    for key, target in targets.items():
        actual = Decimal(getattr(summary, summary_fields[key]))
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
