from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

ACTIVITY_FACTORS: dict[str, Decimal] = {
    "minimal": Decimal("1.2"),
    "light": Decimal("1.375"),
    "moderate": Decimal("1.55"),
    "high": Decimal("1.725"),
    "very_high": Decimal("1.9"),
}
GOAL_FACTORS: dict[str, Decimal] = {
    "lose": Decimal("0.85"),
    "maintain": Decimal(1),
    "gain": Decimal("1.10"),
}


def age_on(birth_date: date, on_date: date) -> int:
    """Calculate completed years on a given date."""
    return (
        on_date.year
        - birth_date.year
        - ((on_date.month, on_date.day) < (birth_date.month, birth_date.day))
    )


def calculate_daily_calorie_target(
    *,
    gender: str,
    birth_date: date,
    height_cm: Decimal,
    weight_kg: Decimal,
    activity_level: str,
    goal: str,
    today: date | None = None,
) -> int:
    """Calculate a suggested daily calorie target using Mifflin–St Jeor."""
    if gender not in {"female", "male"}:
        raise ValueError("gender must be 'female' or 'male'")
    if activity_level not in ACTIVITY_FACTORS:
        raise ValueError("unknown activity level")
    if goal not in GOAL_FACTORS:
        raise ValueError("unknown goal")
    age = age_on(birth_date, today or datetime.now(UTC).date())
    if age < 18:
        raise ValueError("profile setup is available only to adults")
    if height_cm <= 0 or weight_kg <= 0:
        raise ValueError("height and weight must be positive")

    constant = Decimal(5) if gender == "male" else Decimal(-161)
    bmr = Decimal(10) * weight_kg + Decimal("6.25") * height_cm - Decimal(5) * age + constant
    target = bmr * ACTIVITY_FACTORS[activity_level] * GOAL_FACTORS[goal]
    return int(target.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def calculate_daily_macronutrient_targets(calories: int) -> tuple[int, int, int]:
    """Suggest protein, fat, and carbohydrate grams from a calorie target.

    The starting split is 25% of energy from protein, 30% from fat, and 45%
    from carbohydrates. This transparent baseline is editable by the user.
    """
    if calories <= 0:
        raise ValueError("calories must be positive")

    energy = Decimal(calories)
    protein = energy * Decimal("0.25") / Decimal(4)
    fat = energy * Decimal("0.30") / Decimal(9)
    carbohydrates = energy * Decimal("0.45") / Decimal(4)
    return tuple(
        int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        for value in (protein, fat, carbohydrates)
    )
