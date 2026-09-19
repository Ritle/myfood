from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_menu() -> ReplyKeyboardMarkup:
    """Create the persistent top-level navigation keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍽 Питание"), KeyboardButton(text="💧 Вода")],
            [KeyboardButton(text="📊 Сегодня"), KeyboardButton(text="📅 История")],
            [KeyboardButton(text="⚖️ Вес"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🌙 Завершить день")],
        ],
        resize_keyboard=True,
    )
