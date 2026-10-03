from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.models import Food
from app.services.diary import MEAL_LABELS
from app.utils.formatting import format_decimal

_MAX_RESULT_NAME_LENGTH = 28


def food_result_label(food: Food) -> str:
    """Show a compact per-100-gram nutrition summary within Telegram's button limit."""
    name = food.name
    if len(name) > _MAX_RESULT_NAME_LENGTH:
        name = f"{name[:_MAX_RESULT_NAME_LENGTH - 1]}…"
    return (
        f"{name} · {format_decimal(food.calories_per_100g)} ккал\n"
        f"Б {format_decimal(food.protein_per_100g)} · "
        f"Ж {format_decimal(food.fat_per_100g)} · "
        f"У {format_decimal(food.carbs_per_100g)}"
    )


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
        [InlineKeyboardButton(text=food_result_label(food), callback_data=f"food:view:{food.id}")]
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
        [InlineKeyboardButton(text=food_result_label(food), callback_data=f"food:view:{food.id}")]
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



def created_food_diary_offer(
    food_id: int,
    *,
    suggested_meal_type: str,
) -> InlineKeyboardMarkup:
    """Offer one-tap diary adding to the time-prioritized meal."""
    if suggested_meal_type not in MEAL_LABELS:
        raise ValueError("unknown meal type")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"➕ Добавить в {MEAL_LABELS[suggested_meal_type]}",
                    callback_data=(
                        f"diary:add:{suggested_meal_type}:{food_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↔️ Изменить приём пищи",
                    callback_data=f"food:created:meals:{food_id}",
                )
            ],
        ]
    )


def created_food_meal_choices(food_id: int) -> InlineKeyboardMarkup:
    """Let the user override the suggested meal before adding a new food."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=MEAL_LABELS["breakfast"],
                    callback_data=f"diary:add:breakfast:{food_id}",
                ),
                InlineKeyboardButton(
                    text=MEAL_LABELS["lunch"],
                    callback_data=f"diary:add:lunch:{food_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=MEAL_LABELS["dinner"],
                    callback_data=f"diary:add:dinner:{food_id}",
                ),
                InlineKeyboardButton(
                    text=MEAL_LABELS["snack"],
                    callback_data=f"diary:add:snack:{food_id}",
                ),
            ],
        ]
    )
