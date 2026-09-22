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
