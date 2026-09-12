from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu() -> ReplyKeyboardMarkup:
    """Create the persistent top-level navigation keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍽 Питание"), KeyboardButton(text="💧 Вода")],
            [KeyboardButton(text="📊 Сегодня"), KeyboardButton(text="📅 История")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
    )

