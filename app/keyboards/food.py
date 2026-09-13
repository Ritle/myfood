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
            [KeyboardButton(text="🍽 Блюда")],
            [KeyboardButton(text="⭐ Избранные"), KeyboardButton(text="🕘 Недавние")],
            [KeyboardButton(text="➕ Создать продукт"), KeyboardButton(text="➕ Создать блюдо")],
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


def food_results(
    foods: list[Food], *, page: int | None = None, total_pages: int | None = None
) -> InlineKeyboardMarkup:
    """Build buttons that open product cards."""
    rows = [
        [InlineKeyboardButton(text=food.name, callback_data=f"food:view:{food.id}")]
        for food in foods
    ]
    if page is not None and total_pages is not None and total_pages > 1:
        navigation = []
        if page > 0:
            navigation.append(
                InlineKeyboardButton(text="←", callback_data=f"food:page:{page - 1}")
            )
        navigation.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="food:noop")
        )
        if page + 1 < total_pages:
            navigation.append(
                InlineKeyboardButton(text="→", callback_data=f"food:page:{page + 1}")
            )
        rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dish_results(foods: list[Food], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Build a paginated list from the dedicated dish catalog."""
    rows = [
        [InlineKeyboardButton(text=food.name, callback_data=f"food:view:{food.id}")]
        for food in foods
    ]
    if total_pages > 1:
        navigation = []
        if page > 0:
            navigation.append(
                InlineKeyboardButton(text="←", callback_data=f"food:dishes:page:{page - 1}")
            )
        navigation.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="food:noop")
        )
        if page + 1 < total_pages:
            navigation.append(
                InlineKeyboardButton(text="→", callback_data=f"food:dishes:page:{page + 1}")
            )
        rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def food_card_actions(
    food_id: int, *, favorite: bool, editable: bool = False
) -> InlineKeyboardMarkup:
    """Build bookmark controls and, for private products, an edit action."""
    label = "★ Убрать из избранного" if favorite else "☆ В избранное"
    rows = [[InlineKeyboardButton(text=label, callback_data=f"food:favorite:{food_id}")]]
    if editable:
        rows.append(
            [InlineKeyboardButton(text="✏️ Изменить продукт", callback_data=f"food:edit:{food_id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def food_edit_fields(food_id: int) -> InlineKeyboardMarkup:
    """Build field selectors for editing one product attribute at a time."""
    labels = [
        ("Название", "name"),
        ("Бренд", "brand"),
        ("Калории", "calories"),
        ("Белки", "protein"),
        ("Жиры", "fat"),
        ("Углеводы", "carbs"),
    ]
    rows = [
        [
            InlineKeyboardButton(
                text=label, callback_data=f"food:editfield:{food_id}:{field}"
            )
        ]
        for label, field in labels
    ]
    rows.append(
        [InlineKeyboardButton(text="Назад", callback_data=f"food:view:{food_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def food_edit_cancel(food_id: int) -> InlineKeyboardMarkup:
    """Build a cancellation button for a pending product field edit."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data=f"food:editcancel:{food_id}")]
        ]
    )
