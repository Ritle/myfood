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
KG_ENERGY_KCAL = Decimal(7700)
MAX_WEEKLY_LOSS_KG = Decimal("0.75")
MAX_WEEKLY_GAIN_KG = Decimal("0.50")
PROTEIN_PER_KG: dict[str, Decimal] = {
    "lose": Decimal("1.6"),
    "maintain": Decimal("1.4"),
    "gain": Decimal("1.6"),
}
PROTEIN_ACTIVITY_ADJUSTMENT: dict[str, Decimal] = {
    "minimal": Decimal("-0.2"),
    "light": Decimal("-0.1"),
    "moderate": Decimal(0),
    "high": Decimal("0.2"),
    "very_high": Decimal("0.2"),
}
FAT_PER_KG: dict[str, Decimal] = {
    "lose": Decimal("0.8"),
    "maintain": Decimal("0.9"),
    "gain": Decimal("1.0"),
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
    weekly_weight_change_kg: Decimal | None = None,
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
    tdee = bmr * ACTIVITY_FACTORS[activity_level]
    if weekly_weight_change_kg is None:
        target = tdee * GOAL_FACTORS[goal]
    else:
        pace = Decimal(weekly_weight_change_kg)
        validate_weight_change_pace(goal, pace)
        daily_energy_adjustment = pace * KG_ENERGY_KCAL / Decimal(7)
        target = tdee + daily_energy_adjustment
    if target <= 0:
        raise ValueError("calculated calorie target must be positive")
    return int(target.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def calculate_daily_macronutrient_targets(
    calories: int,
    *,
    weight_kg: Decimal,
    activity_level: str,
    goal: str,
) -> tuple[int, int, int]:
    """Suggest macros from body weight, goal, activity, and calorie target.

    Protein starts from a goal-specific grams-per-kilogram target and rises
    modestly for higher activity. Fat starts from a goal-specific
    grams-per-kilogram target. Both are constrained so the final energy split
    remains inside the adult AMDR ranges: protein 10-35%, fat 20-35%, and
    carbohydrates 45-65%. Carbohydrates receive the remaining calories.
    """
    if calories <= 0:
        raise ValueError("calories must be positive")
    if weight_kg <= 0:
        raise ValueError("weight must be positive")
    if activity_level not in ACTIVITY_FACTORS:
        raise ValueError("unknown activity level")
    if goal not in GOAL_FACTORS:
        raise ValueError("unknown goal")

    energy = Decimal(calories)

    protein_per_kg = (
        PROTEIN_PER_KG[goal] + PROTEIN_ACTIVITY_ADJUSTMENT[activity_level]
    )
    desired_protein_energy = weight_kg * protein_per_kg * Decimal(4)
    protein_energy = clamp(
        desired_protein_energy,
        energy * Decimal("0.10"),
        energy * Decimal("0.35"),
    )

    desired_fat_energy = weight_kg * FAT_PER_KG[goal] * Decimal(9)
    min_fat_energy = max(
        energy * Decimal("0.20"),
        energy * Decimal("0.35") - protein_energy,
    )
    max_fat_energy = min(
        energy * Decimal("0.35"),
        energy * Decimal("0.55") - protein_energy,
    )
    fat_energy = clamp(desired_fat_energy, min_fat_energy, max_fat_energy)

    carbohydrate_energy = energy - protein_energy - fat_energy
    values = (
        protein_energy / Decimal(4),
        fat_energy / Decimal(9),
        carbohydrate_energy / Decimal(4),
    )
    return tuple(
        int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        for value in values
    )


def clamp(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    """Clamp a decimal value to an inclusive range."""
    return min(max(value, minimum), maximum)



def validate_weight_change_pace(goal: str, pace: Decimal) -> None:
    """Validate that a weekly weight-change pace matches the selected goal."""
    if goal == "maintain":
        if pace != 0:
            raise ValueError("maintenance pace must be zero")
        return
    if goal == "lose":
        if not -MAX_WEEKLY_LOSS_KG <= pace < 0:
            raise ValueError("weight-loss pace must be between -0.75 and 0 kg/week")
        return
    if goal == "gain":
        if not Decimal(0) < pace <= MAX_WEEKLY_GAIN_KG:
            raise ValueError("weight-gain pace must be between 0 and 0.50 kg/week")
        return
    raise ValueError("unknown goal")
