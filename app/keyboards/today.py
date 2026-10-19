from datetime import date

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.models import FoodEntry
from app.services.diary import meal_label
from app.services.food_guidance import FoodRecommendation
from app.utils.formatting import format_decimal


def today_entry_move_actions(entries: list[FoodEntry]) -> InlineKeyboardMarkup:
    """Offer direct meal reassignment for entries shown in the Today summary."""
    rows: list[list[InlineKeyboardButton]] = []
    for entry in entries:
        if entry.id is None:
            continue
        amount = (
            "1 порция"
            if entry.is_full_serving
            else f"{format_decimal(entry.weight_grams)} г"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"🔄 {meal_label(entry.meal_type, entry.snack_number)} · "
                        f"{entry.food.name[:22]} · {amount}"
                    ),
                    callback_data=f"today:move:{entry.id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def today_entry_meal_choices(
    entry_id: int,
    *,
    current_meal_type: str,
) -> InlineKeyboardMarkup:
    """Choose a destination meal while keeping the Today summary in place."""
    rows: list[list[InlineKeyboardButton]] = []
    for meal_type in ("breakfast", "lunch", "dinner", "snack"):
        label = meal_label(meal_type)
        if meal_type == current_meal_type:
            label = f"✓ {label}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"today:move_to:{entry_id}:{meal_type}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data="today:move_cancel",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def today_menu() -> ReplyKeyboardMarkup:
    """Keep Today actions available while preserving an explicit way back."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍽 Что можно съесть?")],
            [KeyboardButton(text="🔥 Ккал подробнее")],
            [
                KeyboardButton(text="🥩 Белки подробнее"),
                KeyboardButton(text="🥑 Жиры подробнее"),
            ],
            [KeyboardButton(text="🍞 Углеводы подробнее")],
            [KeyboardButton(text="📌 Анализ приёма пищи")],
            [KeyboardButton(text="↩️ Главное меню")],
        ],
        resize_keyboard=True,
    )


def today_food_recommendations(
    recommendations: list[FoodRecommendation],
) -> InlineKeyboardMarkup:
    """Open catalog cards for food suggestions."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"{item.food.name} · {item.amount_label}",
                callback_data=f"food:view:{item.food.id}",
            )
        ]
        for item in recommendations
        if item.food.id is not None
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)



def report_macro_details(day: date) -> InlineKeyboardMarkup:
    """Open calorie and macro source details for one report day."""
    token = day.isoformat()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔥 Ккал",
                    callback_data=f"today:macro:calories:{token}",
                ),
                InlineKeyboardButton(
                    text="🥩 Белки",
                    callback_data=f"today:macro:protein:{token}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🥑 Жиры",
                    callback_data=f"today:macro:fat:{token}",
                ),
                InlineKeyboardButton(
                    text="🍞 Углеводы",
                    callback_data=f"today:macro:carbs:{token}",
                ),
            ],
        ]
    )
