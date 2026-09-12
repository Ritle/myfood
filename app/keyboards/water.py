from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.models import WaterEntry


def water_menu() -> ReplyKeyboardMarkup:
    """Build quick water actions and navigation."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="+200 мл"),
                KeyboardButton(text="+300 мл"),
                KeyboardButton(text="+500 мл"),
            ],
            [KeyboardButton(text="Другой объем"), KeyboardButton(text="Записи воды за сегодня")],
            [KeyboardButton(text="↩️ Главное меню")],
        ],
        resize_keyboard=True,
    )


def water_entry_actions(entries: list[WaterEntry]) -> InlineKeyboardMarkup:
    """Build edit and delete actions for today's water entries."""
    rows = []
    for entry in entries:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ {entry.amount_ml} мл", callback_data=f"water:edit:{entry.id}"
                ),
                InlineKeyboardButton(text="🗑", callback_data=f"water:delete:{entry.id}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def water_delete_confirmation(entry_id: int) -> InlineKeyboardMarkup:
    """Build an explicit water-entry deletion confirmation."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Удалить", callback_data=f"water:delete_yes:{entry_id}"
                ),
                InlineKeyboardButton(text="Отмена", callback_data="water:delete_no"),
            ]
        ]
    )
