from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def meal_reminder_actions(log_id: int, meal_type: str) -> InlineKeyboardMarkup:
    """Build actions for a meal reminder."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Добавить сейчас",
                    callback_data=f"notify:add:{log_id}:{meal_type}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Через 30 минут",
                    callback_data=f"notify:snooze:{log_id}:{meal_type}",
                ),
                InlineKeyboardButton(
                    text="Пропустить сегодня",
                    callback_data=f"notify:skip:{log_id}:{meal_type}",
                ),
            ],
        ]
    )
