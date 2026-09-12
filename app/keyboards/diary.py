from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.models import Food, FoodEntry
from app.services.diary import MEAL_LABELS


def diary_menu() -> ReplyKeyboardMarkup:
    """Build meal selection and diary navigation."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=MEAL_LABELS["breakfast"]),
                KeyboardButton(text=MEAL_LABELS["lunch"]),
            ],
            [
                KeyboardButton(text=MEAL_LABELS["dinner"]),
                KeyboardButton(text=MEAL_LABELS["snack"]),
            ],
            [KeyboardButton(text="📋 Дневник за сегодня")],
            [KeyboardButton(text="📚 Каталог продуктов")],
            [KeyboardButton(text="↩️ Главное меню")],
        ],
        resize_keyboard=True,
    )


def diary_food_results(foods: list[Food], meal_type: str) -> InlineKeyboardMarkup:
    """Build product choices for adding to a selected meal."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=food.name,
                    callback_data=f"diary:add:{meal_type}:{food.id}",
                )
            ]
            for food in foods
        ]
    )


def diary_entry_actions(entries: list[FoodEntry]) -> InlineKeyboardMarkup:
    """Build edit and delete actions for each diary entry."""
    rows: list[list[InlineKeyboardButton]] = []
    for entry in entries:
        short_name = entry.food.name[:24]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {short_name}", callback_data=f"diary:edit:{entry.id}"
                ),
                InlineKeyboardButton(text="🗑", callback_data=f"diary:delete:{entry.id}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirmation(entry_id: int) -> InlineKeyboardMarkup:
    """Build an explicit deletion confirmation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Удалить", callback_data=f"diary:delete_yes:{entry_id}"),
                InlineKeyboardButton(text="Отмена", callback_data="diary:delete_no"),
            ]
        ]
    )
