from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import NotificationSettings


def notification_settings_keyboard(
    settings: NotificationSettings, timezone_name: str
) -> InlineKeyboardMarkup:
    """Build controls for notification preferences."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Часовой пояс: {timezone_name}",
                    callback_data="settings:edit:timezone",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Еда: {status(settings.meal_reminders_enabled)}",
                    callback_data="settings:toggle:meals",
                )
            ],
            [
                time_button("🍳 Завтрак", "breakfast", settings.breakfast_time),
                time_button("🍲 Обед", "lunch", settings.lunch_time),
            ],
            [time_button("🍽 Ужин", "dinner", settings.dinner_time)],
            [
                InlineKeyboardButton(
                    text=f"Вода: {status(settings.water_reminders_enabled)}",
                    callback_data="settings:toggle:water",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Интервал воды: {settings.water_interval_minutes} мин",
                    callback_data="settings:edit:water_interval",
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        f"Вода с {clock(settings.water_start_time)} "
                        f"до {clock(settings.water_end_time)}"
                    ),
                    callback_data="settings:edit:water_window",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Разминка: {status(settings.movement_reminders_enabled)}",
                    callback_data="settings:toggle:movement",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Интервал разминки: {settings.movement_interval_minutes} мин",
                    callback_data="settings:edit:movement_interval",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"Утренний отчёт: {status(settings.morning_report_enabled)}",
                    callback_data="settings:toggle:report",
                ),
                time_button("Время", "report", settings.morning_report_time),
            ],
            [
                InlineKeyboardButton(
                    text=(
                        f"Тихие часы {clock(settings.quiet_start_time)}–"
                        f"{clock(settings.quiet_end_time)}"
                    ),
                    callback_data="settings:edit:quiet",
                )
            ],
        ]
    )


def time_button(label: str, name: str, value) -> InlineKeyboardButton:
    """Build one reminder-time button."""
    return InlineKeyboardButton(
        text=f"{label} {clock(value)}", callback_data=f"settings:edit:{name}"
    )


def clock(value) -> str:
    """Format a database time value."""
    return value.strftime("%H:%M")


def status(enabled: bool) -> str:
    """Format an enabled flag compactly."""
    return "вкл" if enabled else "выкл"
