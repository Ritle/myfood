from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.models import WeightEntry


def weight_menu() -> ReplyKeyboardMarkup:
    """Build weight tracking actions and navigation."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Записать вес"), KeyboardButton(text="История веса")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="↩️ Главное меню")],
        ],
        resize_keyboard=True,
    )


def weight_entry_actions(entries: list[WeightEntry]) -> InlineKeyboardMarkup:
    """Build edit and delete actions for recent weight entries."""
    rows = []
    for entry in entries:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {entry.weight_kg} кг", callback_data=f"weight:edit:{entry.id}"
                ),
                InlineKeyboardButton(text="🗑", callback_data=f"weight:delete:{entry.id}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def weight_delete_confirmation(entry_id: int) -> InlineKeyboardMarkup:
    """Build an explicit weight-entry deletion confirmation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Удалить", callback_data=f"weight:delete_yes:{entry_id}"
                ),
                InlineKeyboardButton(text="Отмена", callback_data="weight:delete_no"),
            ]
        ]
    )
