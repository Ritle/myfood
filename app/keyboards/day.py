from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def close_day_confirmation(day_id: int, logical_date: date) -> InlineKeyboardMarkup:
    """Confirm manual completion of the current logical day."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🌙 Завершить {logical_date:%d.%m}",
                    callback_data=f"day:close:{day_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="day:close:cancel",
                )
            ],
        ]
    )
