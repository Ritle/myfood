from datetime import date
from decimal import Decimal

import pytest

from app.handlers.profile import (
    KEEP_CALCULATED,
    choose_nutrition_targets,
    enter_calories,
    enter_protein,
)
from app.states.profile import ProfileSetup
from app.utils.dates import parse_birth_date


class FakeState:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.current_state = None

    async def get_data(self) -> dict:
        return dict(self.data)

    async def update_data(self, **values) -> None:
        self.data.update(values)

    async def set_state(self, state) -> None:
        self.current_state = state


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.answers = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append((text, kwargs))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("25.04.1990", date(1990, 4, 25)),
        ("25/04/1990", date(1990, 4, 25)),
        ("25-04-1990", date(1990, 4, 25)),
        ("1990-04-25", date(1990, 4, 25)),
        (" 5.4.1990 ", date(1990, 4, 5)),
    ],
)
def test_parse_birth_date_accepts_common_formats(raw: str, expected: date) -> None:
    assert parse_birth_date(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "31.02.1990", "04/25/1990", "1990/04/25"])
def test_parse_birth_date_rejects_invalid_or_ambiguous_formats(raw: str | None) -> None:
    assert parse_birth_date(raw) is None


@pytest.mark.asyncio
async def test_profile_can_keep_calculated_calories_and_macros() -> None:
    state = FakeState(
        {
            "suggested_calories": 2000,
            "suggested_daily_protein_target_g": 112,
            "suggested_daily_fat_target_g": 72,
            "suggested_daily_carbs_target_g": 226,
            "current_weight_kg": Decimal(80),
            "activity_level": "moderate",
            "goal": "maintain",
        }
    )
    message = FakeMessage(KEEP_CALCULATED)

    await choose_nutrition_targets(message, state)

    assert state.current_state == ProfileSetup.water
    assert state.data["daily_calorie_target"] == 2000
    assert state.data["daily_protein_target_g"] == Decimal(112)
    assert state.data["daily_fat_target_g"] == Decimal(72)
    assert state.data["daily_carbs_target_g"] == Decimal(226)


@pytest.mark.asyncio
async def test_profile_can_adjust_one_macro_and_keep_remaining_suggestions() -> None:
    state = FakeState(
        {
            "suggested_daily_protein_target_g": 125,
            "suggested_daily_fat_target_g": 67,
            "suggested_daily_carbs_target_g": 225,
        }
    )
    message = FakeMessage("140")

    await enter_protein(message, state)

    assert state.data["daily_protein_target_g"] == Decimal(140)
    assert state.current_state == ProfileSetup.fat
    assert "67 г" in message.answers[0][0]
    assert state.data["suggested_daily_fat_target_g"] == 67


@pytest.mark.asyncio
async def test_profile_can_keep_calories_then_adjust_macros() -> None:
    state = FakeState(
        {
            "suggested_calories": 2000,
            "suggested_daily_protein_target_g": 112,
            "suggested_daily_fat_target_g": 72,
            "suggested_daily_carbs_target_g": 226,
            "current_weight_kg": Decimal(80),
            "activity_level": "moderate",
            "goal": "maintain",
        }
    )
    message = FakeMessage(KEEP_CALCULATED)

    await enter_calories(message, state)

    assert state.data["daily_calorie_target"] == 2000
    assert state.current_state == ProfileSetup.protein
    assert "112 г" in message.answers[0][0]
