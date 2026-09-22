from datetime import date
from decimal import Decimal

import pytest

from app.services.nutrition import (
    age_on,
    calculate_daily_calorie_target,
    calculate_daily_macronutrient_targets,
)


def test_calculates_male_maintenance_target() -> None:
    target = calculate_daily_calorie_target(
        gender="male",
        birth_date=date(1996, 1, 1),
        height_cm=Decimal(180),
        weight_kg=Decimal(80),
        activity_level="moderate",
        goal="maintain",
        today=date(2026, 1, 1),
    )

    assert target == 2759


def test_calculates_female_weight_loss_target() -> None:
    target = calculate_daily_calorie_target(
        gender="female",
        birth_date=date(1996, 1, 1),
        height_cm=Decimal(180),
        weight_kg=Decimal(80),
        activity_level="moderate",
        goal="lose",
        today=date(2026, 1, 1),
    )

    assert target == 2126


def test_age_does_not_advance_before_birthday() -> None:
    assert age_on(date(2000, 10, 1), date(2026, 9, 30)) == 25


def test_calculates_macros_from_weight_goal_and_activity() -> None:
    assert calculate_daily_macronutrient_targets(
        2000,
        weight_kg=Decimal(80),
        activity_level="moderate",
        goal="maintain",
    ) == (112, 72, 226)
    assert calculate_daily_macronutrient_targets(
        2000,
        weight_kg=Decimal(80),
        activity_level="moderate",
        goal="lose",
    ) == (128, 64, 228)


def test_high_activity_macros_stay_inside_energy_ranges() -> None:
    protein, fat, carbs = calculate_daily_macronutrient_targets(
        2000,
        weight_kg=Decimal(80),
        activity_level="high",
        goal="lose",
    )

    assert (protein, fat, carbs) == (144, 58, 225)
    assert Decimal(protein * 4) / Decimal(2000) <= Decimal("0.35")
    assert Decimal(fat * 9) / Decimal(2000) >= Decimal("0.20")
    assert Decimal(carbs * 4) / Decimal(2000) >= Decimal("0.45")


def test_macro_calculator_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="positive"):
        calculate_daily_macronutrient_targets(
            0,
            weight_kg=Decimal(80),
            activity_level="moderate",
            goal="maintain",
        )
    with pytest.raises(ValueError, match="weight"):
        calculate_daily_macronutrient_targets(
            2000,
            weight_kg=Decimal(0),
            activity_level="moderate",
            goal="maintain",
        )


def test_calculator_rejects_minors() -> None:
    with pytest.raises(ValueError, match="adults"):
        calculate_daily_calorie_target(
            gender="male",
            birth_date=date(2010, 1, 1),
            height_cm=Decimal(170),
            weight_kg=Decimal(60),
            activity_level="light",
            goal="maintain",
            today=date(2026, 1, 1),
        )
