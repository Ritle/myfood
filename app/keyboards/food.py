from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.models import Food


def food_menu() -> ReplyKeyboardMarkup:
    """Build catalog actions."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📚 Найти продукт")],
            [KeyboardButton(text="➕ Создать продукт")],
            [KeyboardButton(text="↩️ Главное меню")],
        ],
        resize_keyboard=True,
    )


def no_brand() -> ReplyKeyboardMarkup:
    """Offer an explicit empty brand."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Без бренда")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def food_results(foods: list[Food]) -> InlineKeyboardMarkup:
    """Build buttons that open product cards."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=food.name, callback_data=f"food:view:{food.id}")]
            for food in foods
        ]
    )
