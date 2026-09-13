from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.keyboards.food import food_result_label
from app.models import Food, FoodEntry, MealTemplate
from app.services.diary import MEAL_LABELS
from app.services.foods import RecentFoodPortion
from app.utils.formatting import format_decimal
from app.utils.portions import QUICK_PORTIONS


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


def diary_portion_keyboard() -> ReplyKeyboardMarkup:
    """Offer common approximate portions while keeping free-form gram input."""
    labels = [label for label, _ in QUICK_PORTIONS]
    rows = [
        [KeyboardButton(text=labels[index]), KeyboardButton(text=labels[index + 1])]
        for index in range(0, len(labels) - 1, 2)
    ]
    if len(labels) % 2:
        rows.append([KeyboardButton(text=labels[-1])])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Выберите порцию или введите граммы",
    )


def diary_batch_confirmation() -> InlineKeyboardMarkup:
    """Ask before saving all products parsed from one message."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Добавить всё",
                    callback_data="diary:batch:confirm",
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="diary:batch:cancel",
                ),
            ]
        ]
    )


def diary_food_results(foods: list[Food], meal_type: str) -> InlineKeyboardMarkup:
    """Build product choices for adding to a selected meal."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=food_result_label(food),
                    callback_data=f"diary:add:{meal_type}:{food.id}",
                )
            ]
            for food in foods
        ]
    )


def diary_recent_food_results(
    items: list[RecentFoodPortion], meal_type: str
) -> InlineKeyboardMarkup:
    """Offer weight editing and one-tap repeat for each recently used product."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{item.food.name[:32]} · изменить",
                    callback_data=f"diary:add:{meal_type}:{item.food.id}",
                ),
                InlineKeyboardButton(
                    text=f"↻ {format_decimal(item.weight_grams)} г",
                    callback_data=f"diary:repeat:{meal_type}:{item.entry_id}",
                ),
            ]
            for item in items
        ]
    )


def diary_source_actions(meal_type: str) -> InlineKeyboardMarkup:
    """Offer recent, favorite, and reusable meal sources alongside text search."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🕘 Недавние",
                    callback_data=f"diary:source:recent:{meal_type}",
                ),
                InlineKeyboardButton(
                    text="⭐ Избранные",
                    callback_data=f"diary:source:favorites:{meal_type}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🍱 Мои шаблоны",
                    callback_data=f"diary:source:templates:{meal_type}",
                )
            ],
        ]
    )


def diary_meal_templates(
    templates: list[MealTemplate], *, meal_type: str
) -> InlineKeyboardMarkup:
    """Build apply and delete controls for the user's saved meal templates."""
    rows = []
    for template in templates:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🍽 {template.name[:28]} · {len(template.items)} поз.",
                    callback_data=f"diary:template:use:{meal_type}:{template.id}",
                ),
                InlineKeyboardButton(
                    text="🗑",
                    callback_data=f"diary:template:delete:{template.id}",
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def meal_template_delete_confirmation(template_id: int) -> InlineKeyboardMarkup:
    """Require confirmation before deleting a saved meal template."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Удалить шаблон",
                    callback_data=f"diary:template:delete_yes:{template_id}",
                ),
                InlineKeyboardButton(
                    text="Отмена", callback_data="diary:template:delete_no"
                ),
            ]
        ]
    )


def diary_food_page(
    foods: list[Food], meal_type: str, *, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """Build selectable diary results with page navigation."""
    rows = [
        [
            InlineKeyboardButton(
                text=food_result_label(food), callback_data=f"diary:add:{meal_type}:{food.id}"
            )
        ]
        for food in foods
    ]
    if total_pages > 1:
        navigation = []
        if page > 0:
            navigation.append(
                InlineKeyboardButton(text="←", callback_data=f"diary:page:{page - 1}")
            )
        navigation.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="diary:noop")
        )
        if page + 1 < total_pages:
            navigation.append(
                InlineKeyboardButton(text="→", callback_data=f"diary:page:{page + 1}")
            )
        rows.append(navigation)
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
