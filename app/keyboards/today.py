from datetime import date

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.services.food_guidance import FoodRecommendation


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
