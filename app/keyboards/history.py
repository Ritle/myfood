from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import FoodEntry
from app.services.diary import meal_label


def history_keyboard(
    *,
    day: date,
    today: date,
    visible_entries: list[FoodEntry],
    all_entries: list[FoodEntry],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Build date, page, product, and meal actions for history."""
    previous_day = day - timedelta(days=1)
    next_day = day + timedelta(days=1)
    date_navigation = [
        InlineKeyboardButton(
            text="← День", callback_data=f"history:day:{previous_day.isoformat()}"
        ),
        InlineKeyboardButton(text=day.strftime("%d.%m.%Y"), callback_data="history:noop"),
    ]
    if next_day <= today:
        date_navigation.append(
            InlineKeyboardButton(
                text="День →", callback_data=f"history:day:{next_day.isoformat()}"
            )
        )
    rows = [date_navigation]
    rows.append(
        [
            InlineKeyboardButton(
                text="🗓 Выбрать дату", callback_data="history:select_date"
            )
        ]
    )
    if total_pages > 1:
        page_navigation = []
        if page > 0:
            page_navigation.append(
                InlineKeyboardButton(
                    text="← Записи",
                    callback_data=f"history:page:{day.isoformat()}:{page - 1}",
                )
            )
        page_navigation.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}", callback_data="history:noop"
            )
        )
        if page + 1 < total_pages:
            page_navigation.append(
                InlineKeyboardButton(
                    text="Записи →",
                    callback_data=f"history:page:{day.isoformat()}:{page + 1}",
                )
            )
        rows.append(page_navigation)
    for entry in visible_entries:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"↻ {entry.food.name[:32]}",
                    callback_data=f"history:repeat_entry:{entry.id}",
                )
            ]
        )
    present_groups: set[tuple[str, int | None]] = set()
    for entry in all_entries:
        snack_number = (
            entry.snack_number if entry.meal_type == "snack" else None
        )
        if entry.meal_type == "snack" and snack_number is None:
            snack_number = 1
        present_groups.add((entry.meal_type, snack_number))

    ordered_groups: list[tuple[str, int | None]] = []
    for meal_type in ("breakfast", "lunch", "dinner"):
        if (meal_type, None) in present_groups:
            ordered_groups.append((meal_type, None))
    ordered_groups.extend(
        sorted(
            (group for group in present_groups if group[0] == "snack"),
            key=lambda group: group[1] or 1,
        )
    )

    for meal_type, snack_number in ordered_groups:
        label = meal_label(meal_type, snack_number)
        number = snack_number or 0
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"↻ Весь {label.lower()}",
                    callback_data=(
                        f"history:repeat_meal:{day.isoformat()}:"
                        f"{meal_type}:{number}"
                    ),
                ),
                InlineKeyboardButton(
                    text="💾 Шаблон",
                    callback_data=(
                        f"history:save_meal:{day.isoformat()}:"
                        f"{meal_type}:{number}"
                    ),
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def repeat_entry_confirmation(entry_id: int) -> InlineKeyboardMarkup:
    """Build confirmation for repeating one product entry."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Повторить",
                    callback_data=f"history:confirm_entry:{entry_id}",
                ),
                InlineKeyboardButton(text="Отмена", callback_data="history:cancel"),
            ]
        ]
    )


def repeat_meal_confirmation(
    day: date, meal_type: str, snack_number: int | None = None
) -> InlineKeyboardMarkup:
    """Build confirmation for repeating one meal or numbered snack group."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Повторить прием",
                    callback_data=(
                        f"history:confirm_meal:{day.isoformat()}:"
                        f"{meal_type}:{snack_number or 0}"
                    ),
                ),
                InlineKeyboardButton(text="Отмена", callback_data="history:cancel"),
            ]
        ]
    )
