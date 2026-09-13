from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.keyboards.main_menu import main_menu
from app.keyboards.settings import notification_settings_keyboard
from app.models import NotificationSettings, User
from app.repositories.users import get_or_create_user
from app.services.notification_settings import (
    TIME_FIELDS,
    load_notification_settings,
    parse_clock,
    parse_time_range,
    parse_timezone,
    set_movement_interval,
    set_notification_time,
    set_time_range,
    set_user_timezone,
    set_water_interval,
    toggle_notification_setting,
)
from app.states.settings import NotificationSettingsEdit
from app.utils.numbers import parse_integer

router = Router()
EDIT_PROMPTS = {
    "breakfast": "Введите время напоминания о завтраке в формате ЧЧ:ММ:",
    "lunch": "Введите время напоминания об обеде в формате ЧЧ:ММ:",
    "dinner": "Введите время напоминания об ужине в формате ЧЧ:ММ:",
    "report": "Введите время утреннего отчёта в формате ЧЧ:ММ:",
    "water_interval": "Введите интервал напоминаний о воде от 30 до 720 минут:",
    "movement_interval": "Введите интервал напоминаний о разминке от 30 до 240 минут:",
    "water_window": "Введите активные часы воды, например 09:00-21:00:",
    "quiet": "Введите тихие часы, например 22:00-08:00:",
    "timezone": "Введите часовой пояс IANA, например Europe/Moscow:",
}


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def show_settings(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Show the user's notification settings."""
    if message.from_user is None:
        return
    await state.clear()
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        settings = await load_notification_settings(session, user_id=user.id)
    await message.answer(
        format_notification_settings(user, settings),
        reply_markup=notification_settings_keyboard(settings, user.timezone),
    )
    await message.answer("Главное меню остается доступно ниже.", reply_markup=main_menu())


@router.callback_query(F.data.startswith("settings:toggle:"))
async def toggle_setting(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Toggle a known notification group."""
    name = (callback.data or "").rsplit(":", 1)[-1]
    if name not in {"meals", "water", "report", "movement"}:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        settings = await load_notification_settings(session, user_id=user.id)
        settings = await toggle_notification_setting(session, settings=settings, name=name)
    if callback.message is not None:
        await callback.message.edit_text(
            format_notification_settings(user, settings),
            reply_markup=notification_settings_keyboard(settings, user.timezone),
        )
    await callback.answer("Настройка сохранена")


@router.callback_query(F.data.startswith("settings:edit:"))
async def begin_setting_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt for a schedule value selected from the settings keyboard."""
    name = (callback.data or "").rsplit(":", 1)[-1]
    prompt = EDIT_PROMPTS.get(name)
    if prompt is None:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return
    await state.set_state(NotificationSettingsEdit.value)
    await state.update_data(setting_name=name)
    if callback.message is not None:
        await callback.message.answer(prompt, reply_markup=ReplyKeyboardRemove())
    await callback.answer()


@router.message(NotificationSettingsEdit.value)
async def save_setting_edit(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Validate and persist one schedule value."""
    if message.from_user is None:
        return
    data = await state.get_data()
    name = data.get("setting_name")
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        settings = await load_notification_settings(session, user_id=user.id)
        if name in TIME_FIELDS:
            value = parse_clock(message.text)
            if value is None:
                await message.answer("Введите корректное время в формате ЧЧ:ММ, например 09:30.")
                return
            settings = await set_notification_time(
                session, settings=settings, name=name, value=value
            )
        elif name == "water_interval":
            minutes = parse_integer(message.text)
            if minutes is None or not 30 <= minutes <= 720:
                await message.answer("Введите целое число минут от 30 до 720.")
                return
            settings = await set_water_interval(
                session, settings=settings, minutes=minutes
            )
        elif name == "movement_interval":
            minutes = parse_integer(message.text)
            if minutes is None or not 30 <= minutes <= 240:
                await message.answer("Введите целое число минут от 30 до 240.")
                return
            settings = await set_movement_interval(
                session, settings=settings, minutes=minutes
            )
        elif name in {"water_window", "quiet"}:
            value_range = parse_time_range(message.text)
            if value_range is None:
                await message.answer("Введите диапазон в формате ЧЧ:ММ-ЧЧ:ММ.")
                return
            start, end = value_range
            if name == "water_window" and start > end:
                await message.answer("Активные часы воды не должны переходить через полночь.")
                return
            settings = await set_time_range(
                session,
                settings=settings,
                name=name,
                start=start,
                end=end,
            )
        elif name == "timezone":
            timezone_name = parse_timezone(message.text)
            if timezone_name is None:
                await message.answer(
                    "Введите существующий часовой пояс IANA, например Europe/Moscow."
                )
                return
            user = await set_user_timezone(
                session, user=user, timezone_name=timezone_name
            )
        else:
            await state.clear()
            await message.answer("Настройка больше недоступна.", reply_markup=main_menu())
            return
    await state.clear()
    await message.answer(
        f"Настройка сохранена.\n\n{format_notification_settings(user, settings)}",
        reply_markup=notification_settings_keyboard(settings, user.timezone),
    )
    await message.answer("Главное меню", reply_markup=main_menu())


async def ensure_user(session: AsyncSession, telegram_user: TelegramUser) -> User:
    """Resolve the internal user for a Telegram actor."""
    return await get_or_create_user(
        session,
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
    )


def format_notification_settings(user: User, settings: NotificationSettings) -> str:
    """Render notification preferences for review."""
    return (
        "⚙️ Настройки уведомлений\n\n"
        f"Часовой пояс: {user.timezone}\n"
        f"Еда: {enabled(settings.meal_reminders_enabled)}\n"
        f"  Завтрак {clock(settings.breakfast_time)}, обед {clock(settings.lunch_time)}, "
        f"ужин {clock(settings.dinner_time)}\n"
        f"Вода: {enabled(settings.water_reminders_enabled)}, каждые "
        f"{settings.water_interval_minutes} мин\n"
        f"  Активные часы {clock(settings.water_start_time)}–"
        f"{clock(settings.water_end_time)}\n"
        f"Разминка: {enabled(settings.movement_reminders_enabled)}, каждые "
        f"{settings.movement_interval_minutes} мин\n"
        f"Утренний отчёт: {enabled(settings.morning_report_enabled)}, "
        f"{clock(settings.morning_report_time)}\n"
        f"Тихие часы: {clock(settings.quiet_start_time)}–"
        f"{clock(settings.quiet_end_time)}"
    )


def enabled(value: bool) -> str:
    """Format a boolean setting."""
    return "включено" if value else "выключено"


def clock(value) -> str:
    """Format a database time value."""
    return value.strftime("%H:%M")
