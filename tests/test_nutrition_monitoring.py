from datetime import UTC, datetime, time
from decimal import Decimal

from app.models import FoodEntry, NotificationSettings, User
from app.services.nutrition_monitoring import (
    adaptive_meal_targets,
    deviation_status,
    expected_fraction_at,
    format_day_checkpoint,
    format_meal_review,
    meal_targets,
    remaining_meal_plan,
)


def user_with_targets() -> User:
    return User(
        telegram_id=900,
        first_name="User",
        daily_calorie_target=2100,
        daily_protein_target_g=Decimal(140),
        daily_fat_target_g=Decimal(70),
        daily_carbs_target_g=Decimal(245),
    )


def entry(
    meal_type: str,
    *,
    calories: int,
    protein: int,
    fat: int,
    carbs: int,
    hour: int,
) -> FoodEntry:
    return FoodEntry(
        meal_type=meal_type,
        weight_grams=Decimal(100),
        is_full_serving=False,
        calories=Decimal(calories),
        protein=Decimal(protein),
        fat=Decimal(fat),
        carbs=Decimal(carbs),
        eaten_at=datetime(2026, 9, 22, hour, tzinfo=UTC),
    )


def test_meal_targets_use_30_40_30_distribution() -> None:
    user = user_with_targets()

    breakfast = meal_targets(user, "breakfast")
    lunch = meal_targets(user, "lunch")
    dinner = meal_targets(user, "dinner")

    assert breakfast["calories"].value == Decimal("630.00")
    assert breakfast["protein"].value == Decimal("42.00")
    assert lunch["calories"].value == Decimal("840.00")
    assert lunch["carbs"].value == Decimal("98.00")
    assert dinner["fat"].value == Decimal("21.00")
    assert meal_targets(user, "snack") == {}


def test_adaptive_targets_move_breakfast_underage_to_lunch_and_dinner() -> None:
    user = user_with_targets()
    entries = [
        entry(
            "breakfast",
            calories=300,
            protein=20,
            fat=10,
            carbs=35,
            hour=6,
        )
    ]

    lunch = adaptive_meal_targets(user, entries, "lunch")
    future = remaining_meal_plan(user, entries, ("lunch", "dinner"))

    assert lunch["calories"].value == Decimal("1028.57")
    assert lunch["protein"].value == Decimal("68.57")
    assert future["lunch"]["calories"].value == Decimal("1028.57")
    assert future["dinner"]["calories"].value == Decimal("771.43")


def test_adaptive_targets_reduce_later_meals_after_breakfast_overage() -> None:
    user = user_with_targets()
    entries = [
        entry(
            "breakfast",
            calories=900,
            protein=60,
            fat=30,
            carbs=100,
            hour=6,
        )
    ]

    lunch = adaptive_meal_targets(user, entries, "lunch")

    assert lunch["calories"].value == Decimal("685.71")
    assert lunch["protein"].value == Decimal("45.71")


def test_snack_before_lunch_reduces_adaptive_lunch_target() -> None:
    user = user_with_targets()
    entries = [
        entry(
            "breakfast",
            calories=300,
            protein=20,
            fat=10,
            carbs=35,
            hour=6,
        ),
        entry(
            "snack",
            calories=200,
            protein=10,
            fat=5,
            carbs=25,
            hour=9,
        ),
        entry(
            "lunch",
            calories=500,
            protein=30,
            fat=15,
            carbs=50,
            hour=12,
        ),
    ]

    lunch = adaptive_meal_targets(user, entries, "lunch")

    assert lunch["calories"].value == Decimal("914.29")
    assert lunch["protein"].value == Decimal("62.86")


def test_deviation_status_distinguishes_strong_under_and_over() -> None:
    target = Decimal(100)

    assert deviation_status(Decimal(60), target) == "strong_under"
    assert deviation_status(Decimal(80), target) == "under"
    assert deviation_status(Decimal(100), target) == "ok"
    assert deviation_status(Decimal(120), target) == "over"
    assert deviation_status(Decimal(140), target) == "strong_over"


def test_meal_review_reports_kbju_under_and_over() -> None:
    user = user_with_targets()
    breakfast = [
        entry(
            "breakfast",
            calories=300,
            protein=20,
            fat=30,
            carbs=35,
            hour=6,
        )
    ]

    text = format_meal_review(user, breakfast, meal_type="breakfast")

    assert text is not None
    assert "Завтрак" in text
    assert "Адаптивный ориентир (база 30% дневной цели)" in text
    assert "Калории: 300 / 630 ккал — сильный недобор" in text
    assert "Жиры: 30 / 21 г — сильный перебор" in text
    assert "План на оставшиеся основные приёмы:" in text
    assert "1028.57 ккал" in text
    assert "771.43 ккал" in text


def test_1600_checkpoint_uses_70_percent_and_counts_snacks_in_day_total() -> None:
    user = user_with_targets()
    settings = NotificationSettings(
        breakfast_time=time(9),
        lunch_time=time(14),
        dinner_time=time(20),
        nutrition_summary_time=time(16),
    )
    entries = [
        entry(
            "breakfast",
            calories=500,
            protein=30,
            fat=15,
            carbs=60,
            hour=6,
        ),
        entry(
            "lunch",
            calories=500,
            protein=35,
            fat=15,
            carbs=55,
            hour=11,
        ),
        entry(
            "snack",
            calories=200,
            protein=10,
            fat=5,
            carbs=30,
            hour=12,
        ),
    ]

    assert expected_fraction_at(settings, time(16)) == Decimal("0.70")

    text = format_day_checkpoint(
        user,
        entries,
        settings=settings,
        checkpoint=time(16),
    )

    assert text is not None
    assert "Сводка КБЖУ на 16:00" in text
    assert "около 70% дневной цели" in text
    assert "Калории: 1200 / 1470 ккал" in text
    assert "До полной дневной цели:" in text
    assert "Адаптивный план на оставшиеся основные приёмы:" in text
    assert "900 ккал" in text
    assert "Б 65 г" in text
