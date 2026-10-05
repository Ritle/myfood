from decimal import Decimal

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

ADD_MORE_FOOD_TEXT = "➕ Добавить ещё"
FINISH_DIARY_ADDING_TEXT = "✅ Завершить добавление"
FINISH_MEAL_TEXTS = {
    "breakfast": "✅ Завершить завтрак",
    "lunch": "✅ Завершить обед",
    "dinner": "✅ Завершить ужин",
}


def finish_diary_adding_text(meal_type: str | None) -> str:
    """Return a meal-specific finish label for main meals."""
    return FINISH_MEAL_TEXTS.get(meal_type or "", FINISH_DIARY_ADDING_TEXT)


def diary_menu(
    *, adding: bool = False, meal_type: str | None = None
) -> ReplyKeyboardMarkup:
    """Build meal selection and diary navigation.

    During an active meal-entry session, show an explicit finish action so
    the selected meal can stay active across multiple added products.
    """
    rows = [
        [
            KeyboardButton(text=MEAL_LABELS["breakfast"]),
            KeyboardButton(text=MEAL_LABELS["lunch"]),
        ],
        [
            KeyboardButton(text=MEAL_LABELS["dinner"]),
            KeyboardButton(text=MEAL_LABELS["snack"]),
        ],
    ]
    if adding:
        rows.append(
            [KeyboardButton(text=finish_diary_adding_text(meal_type))]
        )
    rows.extend(
        [
            [KeyboardButton(text="📋 Дневник за сегодня")],
            [KeyboardButton(text="📚 Каталог продуктов")],
            [KeyboardButton(text="↩️ Главное меню")],
        ]
    )
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def diary_after_add_menu(meal_type: str) -> ReplyKeyboardMarkup:
    """Keep the next action obvious immediately after saving food."""
    rows = [
        [
            KeyboardButton(text=ADD_MORE_FOOD_TEXT),
            KeyboardButton(text=finish_diary_adding_text(meal_type)),
        ],
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
    ]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        input_field_placeholder="Добавить ещё или завершить приём",
    )


def diary_portion_keyboard(
    meal_type: str | None = None,
    *,
    habitual_portion: Decimal | None = None,
) -> ReplyKeyboardMarkup:
    """Offer a habitual portion first, then common approximate portions."""
    labels = [label for label, _ in QUICK_PORTIONS]
    if habitual_portion is not None:
        exact_label = f"{format_decimal(habitual_portion)} г"
        labels = [label for label in labels if label != exact_label]

    rows: list[list[KeyboardButton]] = []
    if habitual_portion is not None:
        rows.append(
            [
                KeyboardButton(
                    text=f"⭐ {format_decimal(habitual_portion)} г"
                )
            ]
        )
    rows.extend(
        [
            [
                KeyboardButton(text=labels[index]),
                KeyboardButton(text=labels[index + 1]),
            ]
            for index in range(0, len(labels) - 1, 2)
        ]
    )
    if len(labels) % 2:
        rows.append([KeyboardButton(text=labels[-1])])
    rows.append([KeyboardButton(text=finish_diary_adding_text(meal_type))])
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
                    text=(
                        f"{item.food.name[:32]} · добавить"
                        if item.food.nutrition_basis == "portion"
                        else f"{item.food.name[:32]} · изменить"
                    ),
                    callback_data=f"diary:add:{meal_type}:{item.food.id}",
                ),
                InlineKeyboardButton(
                    text=(
                        "↻ 1 порция"
                        if item.food.nutrition_basis == "portion"
                        else f"↻ {format_decimal(item.weight_grams)} г"
                    ),
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


def diary_post_add_actions(entry: FoodEntry) -> InlineKeyboardMarkup:
    """Build direct actions for the entry that was just saved."""
    buttons: list[InlineKeyboardButton] = []
    if not entry.is_full_serving:
        buttons.append(
            InlineKeyboardButton(
                text="⚖️ Изменить вес",
                callback_data=f"diary:quick_edit:{entry.id}",
            )
        )
    buttons.append(
        InlineKeyboardButton(
            text="🗑 Удалить",
            callback_data=f"diary:quick_delete:{entry.id}",
        )
    )
    buttons.append(
        InlineKeyboardButton(
            text="↻ Повторить",
            callback_data=(
                f"diary:repeat_entry:{entry.id}"
            ),
        )
    )
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def diary_entry_actions(entries: list[FoodEntry]) -> InlineKeyboardMarkup:
    """Build edit and delete actions for each diary entry."""
    rows: list[list[InlineKeyboardButton]] = []
    for entry in entries:
        short_name = entry.food.name[:24]
        if entry.is_full_serving:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🍽 {short_name}", callback_data="diary:noop"
                    ),
                    InlineKeyboardButton(
                        text="🗑", callback_data=f"diary:delete:{entry.id}"
                    ),
                ]
            )
        else:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✏️ {short_name}", callback_data=f"diary:edit:{entry.id}"
                    ),
                    InlineKeyboardButton(
                        text="🗑", callback_data=f"diary:delete:{entry.id}"
                    ),
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



def frequent_combo_confirmation(suggestion_id: int) -> InlineKeyboardMarkup:
    """Offer saving or permanently dismissing a detected recurring meal combo."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💾 Сохранить шаблон",
                    callback_data=f"diary:combo:save:{suggestion_id}",
                ),
                InlineKeyboardButton(
                    text="Не предлагать",
                    callback_data=f"diary:combo:dismiss:{suggestion_id}",
                ),
            ]
        ]
    )
