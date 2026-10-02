from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Food, FoodEntry, NotificationLog, User
from app.services.calorie_alerts import claim_calorie_alert, crossed_calorie_levels
from app.keyboards.today import report_macro_details
from app.services.today import format_macro_sources, format_today, macro_sources, progress_bar


def test_progress_bar_shows_unbounded_percentage() -> None:
    assert progress_bar(Decimal(1720), Decimal(2100)) == "████████░░ 82%"
    assert progress_bar(Decimal(2250), Decimal(2100)) == "██████████ 107%"


def test_today_screen_handles_empty_diary() -> None:
    user = User(
        telegram_id=1,
        first_name="User",
        daily_calorie_target=2100,
        daily_protein_target_g=Decimal(140),
        daily_fat_target_g=Decimal(70),
        daily_carbs_target_g=Decimal(245),
        daily_water_target_ml=2000,
    )

    text = format_today(user, [], water_ml=650)

    assert "0 / 2100 ккал" in text
    assert "Осталось: 2100 ккал" in text
    assert "🍳 Завтрак: 0 ккал" in text
    assert "💧 Вода: 650 / 2000 мл" in text


def test_crossed_levels_reports_only_upward_crossings() -> None:
    assert crossed_calorie_levels(
        previous_total=Decimal(1500),
        current_total=Decimal(2200),
        target=Decimal(2100),
        warning_ratio=Decimal("0.8"),
    ) == ["warning", "goal", "exceeded"]
    assert (
        crossed_calorie_levels(
            previous_total=Decimal(2200),
            current_total=Decimal(2300),
            target=Decimal(2100),
            warning_ratio=Decimal("0.8"),
        )
        == []
    )


@pytest.mark.asyncio
async def test_alert_claim_is_deduplicated_and_suppresses_lower_levels() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=1, first_name="User")
            session.add(user)
            await session.commit()
            await session.refresh(user)

            alert = await claim_calorie_alert(
                session,
                user_id=user.id,
                local_date=date(2026, 9, 12),
                previous_total=Decimal(1500),
                current_total=Decimal(2200),
                target=Decimal(2100),
                warning_ratio=Decimal("0.8"),
            )
            duplicate = await claim_calorie_alert(
                session,
                user_id=user.id,
                local_date=date(2026, 9, 12),
                previous_total=Decimal(1500),
                current_total=Decimal(2200),
                target=Decimal(2100),
                warning_ratio=Decimal("0.8"),
            )
            logs = list(await session.scalars(select(NotificationLog).order_by(NotificationLog.id)))

        assert alert is not None
        assert alert.level == "exceeded"
        assert duplicate is None
        assert [log.status for log in logs] == ["suppressed", "suppressed", "pending"]
        assert user.first_name == "User"
    finally:
        await engine.dispose()



def test_today_screen_splits_numbered_snacks() -> None:
    user = User(telegram_id=2, first_name="User")
    food = Food(
        name="Банан",
        name_normalized="банан",
        calories_per_100g=Decimal(100),
        protein_per_100g=Decimal(1),
        fat_per_100g=Decimal(0),
        carbs_per_100g=Decimal(20),
        is_public=True,
    )
    entries = [
        FoodEntry(
            meal_type="snack",
            snack_number=1,
            calories=Decimal(100),
            protein=Decimal(1),
            fat=Decimal(0),
            carbs=Decimal(20),
            weight_grams=Decimal(100),
            is_full_serving=False,
            food=food,
        ),
        FoodEntry(
            meal_type="snack",
            snack_number=2,
            calories=Decimal(150),
            protein=Decimal(2),
            fat=Decimal(1),
            carbs=Decimal(30),
            weight_grams=Decimal(150),
            is_full_serving=False,
            food=food,
        ),
    ]

    text = format_today(user, entries)

    assert "🍎 Перекус 1: 100 ккал" in text
    assert "🍎 Перекус 2: 150 ккал" in text
    assert "🍎 Перекус: 250 ккал" not in text



def test_macro_source_details_show_food_contribution_share_and_meals() -> None:
    chicken = Food(
        id=11,
        name="Куриная грудка",
        name_normalized="куриная грудка",
        calories_per_100g=Decimal(165),
        protein_per_100g=Decimal(31),
        fat_per_100g=Decimal("3.6"),
        carbs_per_100g=Decimal(0),
        is_public=True,
    )
    eggs = Food(
        id=12,
        name="Яйца",
        name_normalized="яйца",
        calories_per_100g=Decimal(150),
        protein_per_100g=Decimal(13),
        fat_per_100g=Decimal(11),
        carbs_per_100g=Decimal(1),
        is_public=True,
    )
    entries = [
        FoodEntry(
            food_id=chicken.id,
            food=chicken,
            meal_type="lunch",
            weight_grams=Decimal(100),
            is_full_serving=False,
            calories=Decimal(165),
            protein=Decimal(31),
            fat=Decimal("3.6"),
            carbs=Decimal(0),
        ),
        FoodEntry(
            food_id=chicken.id,
            food=chicken,
            meal_type="dinner",
            weight_grams=Decimal(50),
            is_full_serving=False,
            calories=Decimal("82.5"),
            protein=Decimal("15.5"),
            fat=Decimal("1.8"),
            carbs=Decimal(0),
        ),
        FoodEntry(
            food_id=eggs.id,
            food=eggs,
            meal_type="breakfast",
            weight_grams=Decimal(100),
            is_full_serving=False,
            calories=Decimal(150),
            protein=Decimal(13),
            fat=Decimal(11),
            carbs=Decimal(1),
        ),
    ]

    sources = macro_sources(entries, macro="protein")
    text = format_macro_sources(
        entries,
        macro="protein",
        target=Decimal(120),
        day_label="03.10.2026",
    )

    assert [source.food_name for source in sources] == [
        "Куриная грудка",
        "Яйца",
    ]
    assert sources[0].amount == Decimal("46.5")
    assert sources[0].meal_labels == ("🍲 Обед", "🍽 Ужин")
    assert "🥩 Белки — источники · 03.10.2026" in text
    assert "Всего: 59.5 / 120 г" in text
    assert "Куриная грудка — 46.5 г (78%) · 🍲 Обед, 🍽 Ужин" in text
    assert "Яйца — 13 г (22%) · 🍳 Завтрак" in text


def test_macro_source_details_handle_empty_day() -> None:
    text = format_macro_sources(
        [],
        macro="fat",
        target=Decimal(70),
        day_label="03.10.2026",
    )

    assert "🥑 Жиры — источники" in text
    assert "Всего: 0 / 70 г" in text
    assert "источников пока нет" in text


def test_report_macro_detail_keyboard_targets_exact_report_day() -> None:
    keyboard = report_macro_details(date(2026, 10, 3))
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert callbacks == [
        "today:macro:protein:2026-10-03",
        "today:macro:fat:2026-10-03",
        "today:macro:carbs:2026-10-03",
    ]
