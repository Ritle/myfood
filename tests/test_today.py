from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, NotificationLog, User
from app.services.calorie_alerts import claim_calorie_alert, crossed_calorie_levels
from app.services.today import format_today, progress_bar


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
