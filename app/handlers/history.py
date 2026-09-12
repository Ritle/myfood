from datetime import date
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.handlers.diary import deliver_calorie_alert
from app.keyboards.history import (
    history_keyboard,
    repeat_entry_confirmation,
    repeat_meal_confirmation,
)
from app.keyboards.main_menu import main_menu
from app.models import FoodEntry, User
from app.repositories.users import get_or_create_user
from app.services.calorie_alerts import CalorieAlert, claim_calorie_alert
from app.services.diary import (
    MEAL_LABELS,
    get_entries_for_day,
    load_owned_entry,
    local_today,
    summarize_entries,
)
from app.services.history import repeat_food_entry, repeat_meal
from app.services.today import format_today
from app.services.water import get_water_for_day, total_water
from app.states.history import HistorySelect
from app.utils.formatting import format_decimal

router = Router()
PAGE_SIZE = 8


@router.message(Command("history"))
@router.message(F.text == "📅 История")
async def show_history(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Open history at the user's current local date."""
    if message.from_user is None:
        return
    await state.clear()
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        day = local_today(user.timezone)
        text, keyboard = await build_history_page(session, user=user, day=day, page=0)
    await message.answer(text, reply_markup=keyboard)
    await message.answer("Главное меню", reply_markup=main_menu())


@router.callback_query(F.data.startswith("history:day:"))
async def change_history_day(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Move history to an adjacent date."""
    day = parse_date((callback.data or "").rsplit(":", 1)[-1])
    if day is None or callback.message is None:
        await callback.answer("Некорректная дата", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        if day > local_today(user.timezone):
            await callback.answer("Будущий день пока недоступен", show_alert=True)
            return
        text, keyboard = await build_history_page(session, user=user, day=day, page=0)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "history:select_date")
async def begin_history_date_selection(
    callback: CallbackQuery, state: FSMContext
) -> None:
    """Ask for a specific history date."""
    await state.set_state(HistorySelect.date)
    if callback.message is not None:
        await callback.message.answer(
            "Введите дату в формате ДД.ММ.ГГГГ:", reply_markup=ReplyKeyboardRemove()
        )
    await callback.answer()


@router.message(HistorySelect.date)
async def select_history_date(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Validate a manually entered date and render its history."""
    day = parse_user_date(message.text)
    if day is None:
        await message.answer("Введите корректную дату в формате ДД.ММ.ГГГГ.")
        return
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        if day > local_today(user.timezone):
            await message.answer("Будущая дата пока недоступна.")
            return
        text, keyboard = await build_history_page(session, user=user, day=day, page=0)
    await state.clear()
    await message.answer(text, reply_markup=keyboard)
    await message.answer("Главное меню", reply_markup=main_menu())


@router.callback_query(F.data.startswith("history:page:"))
async def change_history_page(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Move through a long list of entries for one date."""
    try:
        _, _, raw_day, raw_page = (callback.data or "").split(":", 3)
        day = date.fromisoformat(raw_day)
        page = int(raw_page)
    except ValueError:
        await callback.answer("Некорректная страница", show_alert=True)
        return
    if page < 0 or callback.message is None:
        await callback.answer("Некорректная страница", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        if day > local_today(user.timezone):
            await callback.answer("Будущий день пока недоступен", show_alert=True)
            return
        text, keyboard = await build_history_page(
            session, user=user, day=day, page=page
        )
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("history:repeat_entry:"))
async def request_repeat_entry(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Ask for confirmation before repeating one owned entry."""
    entry_id = parse_positive_id(callback.data)
    if entry_id is None:
        await callback.answer("Некорректная запись", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        entry = await load_owned_entry(session, user_id=user.id, entry_id=entry_id)
    if entry is None:
        await callback.answer("Запись недоступна", show_alert=True)
        return
    if callback.message is not None:
        await callback.message.answer(
            f"Повторить сегодня «{entry.food.name}», "
            f"{format_decimal(entry.weight_grams)} г?",
            reply_markup=repeat_entry_confirmation(entry.id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("history:repeat_meal:"))
async def request_repeat_meal(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Ask for confirmation before repeating a meal."""
    parsed = parse_meal_callback(callback.data)
    if parsed is None:
        await callback.answer("Некорректный прием пищи", show_alert=True)
        return
    day, meal_type = parsed
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        entries = await get_entries_for_day(
            session, user_id=user.id, day=day, timezone_name=user.timezone
        )
    count = sum(entry.meal_type == meal_type for entry in entries)
    if count == 0:
        await callback.answer("Прием пищи больше недоступен", show_alert=True)
        return
    if callback.message is not None:
        await callback.message.answer(
            f"Повторить сегодня {MEAL_LABELS[meal_type].lower()} ({count} поз.)?",
            reply_markup=repeat_meal_confirmation(day, meal_type),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("history:confirm_entry:"))
async def confirm_repeat_entry(
    callback: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    """Repeat one entry and evaluate today's calorie threshold."""
    entry_id = parse_positive_id(callback.data)
    if entry_id is None:
        await callback.answer("Некорректная запись", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        previous = await current_day_entries(session, user)
        entry = await repeat_food_entry(session, user_id=user.id, entry_id=entry_id)
        current = await current_day_entries(session, user)
        alert = await claim_repeat_alert(
            session, user=user, previous=previous, current=current, settings=settings
        )
    if callback.message is not None:
        if entry is None:
            await callback.message.answer("Запись больше недоступна.")
        else:
            await callback.message.answer(
                f"Добавлено сегодня: {entry.food.name}, "
                f"{format_decimal(entry.weight_grams)} г."
            )
            await deliver_calorie_alert(
                callback.message, alert, settings, session_factory
            )
    await callback.answer()


@router.callback_query(F.data.startswith("history:confirm_meal:"))
async def confirm_repeat_meal(
    callback: CallbackQuery,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    """Repeat a whole meal and evaluate today's calorie threshold."""
    parsed = parse_meal_callback(callback.data)
    if parsed is None:
        await callback.answer("Некорректный прием пищи", show_alert=True)
        return
    day, meal_type = parsed
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        previous = await current_day_entries(session, user)
        copies = await repeat_meal(
            session,
            user_id=user.id,
            source_day=day,
            meal_type=meal_type,
            timezone_name=user.timezone,
        )
        current = await current_day_entries(session, user)
        alert = await claim_repeat_alert(
            session, user=user, previous=previous, current=current, settings=settings
        )
    if callback.message is not None:
        if not copies:
            await callback.message.answer("Прием пищи больше недоступен.")
        else:
            await callback.message.answer(
                f"{MEAL_LABELS[meal_type]} повторен: добавлено {len(copies)} поз."
            )
            await deliver_calorie_alert(
                callback.message, alert, settings, session_factory
            )
    await callback.answer()


@router.callback_query(F.data.in_({"history:cancel", "history:noop"}))
async def cancel_or_ignore_history_action(callback: CallbackQuery) -> None:
    """Acknowledge cancel and inert history buttons."""
    text = "Действие отменено" if callback.data == "history:cancel" else None
    await callback.answer(text)


async def build_history_page(
    session: AsyncSession, *, user: User, day: date, page: int
):
    """Load and render one paginated history date."""
    entries = await get_entries_for_day(
        session, user_id=user.id, day=day, timezone_name=user.timezone
    )
    water_entries = await get_water_for_day(
        session, user_id=user.id, day=day, timezone_name=user.timezone
    )
    total_pages = max(1, (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE)
    actual_page = min(max(0, page), total_pages - 1)
    start = actual_page * PAGE_SIZE
    visible = entries[start : start + PAGE_SIZE]
    text = format_history_day(
        user,
        day,
        entries,
        visible_entries=visible,
        water_ml=total_water(water_entries),
        page=actual_page,
        total_pages=total_pages,
    )
    keyboard = history_keyboard(
        day=day,
        today=local_today(user.timezone),
        visible_entries=visible,
        all_entries=entries,
        page=actual_page,
        total_pages=total_pages,
    )
    return text, keyboard


def format_history_day(
    user: User,
    day: date,
    entries: list[FoodEntry],
    *,
    visible_entries: list[FoodEntry],
    water_ml: int,
    page: int,
    total_pages: int,
) -> str:
    """Format nutrition totals and a bounded list of diary entries."""
    text = format_today(user, entries, water_ml=water_ml).replace(
        "📊 Сегодня", f"📅 {day:%d.%m.%Y}", 1
    )
    lines = [text, "", "Записи питания:"]
    if not visible_entries:
        lines.append("Нет записей.")
    else:
        for entry in visible_entries:
            lines.append(
                f"• {MEAL_LABELS[entry.meal_type]} · {entry.food.name} — "
                f"{format_decimal(entry.weight_grams)} г"
            )
    if total_pages > 1:
        lines.append(f"Страница {page + 1} из {total_pages}")
    return "\n".join(lines)


async def current_day_entries(session: AsyncSession, user: User) -> list[FoodEntry]:
    """Load the user's current local diary day."""
    return await get_entries_for_day(
        session,
        user_id=user.id,
        day=local_today(user.timezone),
        timezone_name=user.timezone,
    )


async def claim_repeat_alert(
    session: AsyncSession,
    *,
    user: User,
    previous: list[FoodEntry],
    current: list[FoodEntry],
    settings: Settings,
) -> CalorieAlert | None:
    """Claim any calorie threshold crossed by repeated history entries."""
    if user.daily_calorie_target is None:
        return None
    return await claim_calorie_alert(
        session,
        user_id=user.id,
        local_date=local_today(user.timezone),
        previous_total=summarize_entries(previous).calories,
        current_total=summarize_entries(current).calories,
        target=Decimal(user.daily_calorie_target),
        warning_ratio=settings.calorie_warning_ratio,
    )


async def ensure_user(session: AsyncSession, telegram_user: TelegramUser) -> User:
    """Resolve the internal user for a Telegram actor."""
    return await get_or_create_user(
        session,
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
    )


def parse_date(value: str) -> date | None:
    """Parse an ISO date from callback data."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_user_date(value: str | None) -> date | None:
    """Parse a user-facing DD.MM.YYYY date."""
    try:
        raw_day, raw_month, raw_year = (value or "").strip().split(".")
        if len(raw_day) != 2 or len(raw_month) != 2 or len(raw_year) != 4:
            return None
        return date(int(raw_year), int(raw_month), int(raw_day))
    except (TypeError, ValueError):
        return None


def parse_positive_id(data: str | None) -> int | None:
    """Extract a positive integer ID from callback data."""
    try:
        value = int((data or "").rsplit(":", 1)[-1])
    except ValueError:
        return None
    return value if value > 0 else None


def parse_meal_callback(data: str | None) -> tuple[date, str] | None:
    """Parse a source date and meal type from callback data."""
    try:
        raw_day, meal_type = (data or "").rsplit(":", 2)[-2:]
        day = date.fromisoformat(raw_day)
    except ValueError:
        return None
    if meal_type not in MEAL_LABELS:
        return None
    return day, meal_type
