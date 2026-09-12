from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def choices(*labels: str) -> ReplyKeyboardMarkup:
    """Build a compact one-column keyboard for a profile choice."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label)] for label in labels],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def skip_choice() -> ReplyKeyboardMarkup:
    """Build a keyboard for an optional profile target."""
    return choices("Пропустить")


def profile_actions() -> ReplyKeyboardMarkup:
    """Build profile navigation with an edit action."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ Изменить параметры")],
            [KeyboardButton(text="🍽 Питание"), KeyboardButton(text="💧 Вода")],
            [KeyboardButton(text="📊 Сегодня"), KeyboardButton(text="📅 История")],
            [KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
    )
