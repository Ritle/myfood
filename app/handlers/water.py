from datetime import UTC
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.keyboards.water import (
    water_delete_confirmation,
    water_entry_actions,
    water_menu,
)
from app.models import User, WaterEntry
from app.repositories.users import get_or_create_user
from app.services.diary import local_today
from app.services.water import (
    add_water,
    change_water_amount,
    get_water_for_day,
    load_owned_water,
    parse_water_amount,
    remove_water,
    total_water,
)
from app.states.water import WaterAdd, WaterEdit

router = Router()
QUICK_AMOUNTS = {"+200 мл": 200, "+300 мл": 300, "+500 мл": 500}


@router.message(Command("water"))
@router.message(F.text == "💧 Вода")
async def open_water(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Open water tracking and show today's progress."""
    if message.from_user is None:
        return
    await state.clear()
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        entries = await today_water(session, user)
    await message.answer(format_water_status(user, entries), reply_markup=water_menu())


@router.message(F.text.in_(QUICK_AMOUNTS))
async def add_quick_water(message: Message, session_factory: async_sessionmaker) -> None:
    """Store one of the quick water amounts."""
    if message.from_user is None:
        return
    amount_ml = QUICK_AMOUNTS[message.text or ""]
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        await add_water(session, user_id=user.id, amount_ml=amount_ml)
        entries = await today_water(session, user)
    await message.answer(
        f"Добавлено: {amount_ml} мл.\n\n{format_water_status(user, entries)}",
        reply_markup=water_menu(),
    )


@router.message(F.text == "Другой объем")
async def begin_custom_water(message: Message, state: FSMContext) -> None:
    """Ask for a custom water amount."""
    await state.set_state(WaterAdd.amount)
    await message.answer(
        "Введите объем воды от 1 до 10000 мл:", reply_markup=ReplyKeyboardRemove()
    )


@router.message(WaterAdd.amount)
async def save_custom_water(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Validate and store a custom water amount."""
    amount_ml = parse_water_amount(message.text)
    if amount_ml is None:
        await message.answer("Введите целое число от 1 до 10000 мл.")
        return
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        await add_water(session, user_id=user.id, amount_ml=amount_ml)
        entries = await today_water(session, user)
    await state.clear()
    await message.answer(
        f"Добавлено: {amount_ml} мл.\n\n{format_water_status(user, entries)}",
        reply_markup=water_menu(),
    )


@router.message(F.text == "Записи воды за сегодня")
async def show_water_history(message: Message, session_factory: async_sessionmaker) -> None:
    """Show today's editable water entries."""
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        entries = await today_water(session, user)
    if not entries:
        await message.answer("Сегодня вода еще не записана.", reply_markup=water_menu())
        return
    await message.answer(
        format_water_history(user, entries), reply_markup=water_entry_actions(entries)
    )


@router.callback_query(F.data.startswith("water:edit:"))
async def begin_water_edit(
    callback: CallbackQuery, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Ask for a replacement amount after checking entry ownership."""
    entry_id = parse_callback_id(callback.data)
    if entry_id is None:
        await callback.answer("Некорректная запись", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        entries = await today_water(session, user)
        entry = next((item for item in entries if item.id == entry_id), None)
    if entry is None:
        await callback.answer("Запись недоступна", show_alert=True)
        return
    await state.set_state(WaterEdit.amount)
    await state.update_data(water_entry_id=entry_id)
    if callback.message is not None:
        await callback.message.answer(
            f"Введите новый объем вместо {entry.amount_ml} мл:",
            reply_markup=ReplyKeyboardRemove(),
        )
    await callback.answer()


@router.message(WaterEdit.amount)
async def save_water_edit(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Apply a new amount to an owned water entry."""
    amount_ml = parse_water_amount(message.text)
    if amount_ml is None:
        await message.answer("Введите целое число от 1 до 10000 мл.")
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        entry = await change_water_amount(
            session,
            user_id=user.id,
            entry_id=data["water_entry_id"],
            amount_ml=amount_ml,
        )
        entries = await today_water(session, user)
    await state.clear()
    if entry is None:
        await message.answer("Запись недоступна.", reply_markup=water_menu())
        return
    await message.answer(
        f"Запись обновлена: {amount_ml} мл.\n\n{format_water_status(user, entries)}",
        reply_markup=water_menu(),
    )


@router.callback_query(F.data.startswith("water:delete:"))
async def request_water_deletion(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Request confirmation before deleting a water entry."""
    entry_id = parse_callback_id(callback.data)
    if entry_id is None:
        await callback.answer("Некорректная запись", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        entry = await load_owned_water(session, user_id=user.id, entry_id=entry_id)
    if entry is None:
        await callback.answer("Запись недоступна", show_alert=True)
        return
    if callback.message is not None:
        await callback.message.answer(
            "Удалить эту запись воды?", reply_markup=water_delete_confirmation(entry_id)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("water:delete_yes:"))
async def confirm_water_deletion(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Delete a water entry after checking ownership."""
    entry_id = parse_callback_id(callback.data)
    if entry_id is None:
        await callback.answer("Некорректная запись", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        removed = await remove_water(session, user_id=user.id, entry_id=entry_id)
        entries = await today_water(session, user)
    if callback.message is not None:
        text = "Запись удалена." if removed else "Запись уже недоступна."
        await callback.message.answer(
            f"{text}\n\n{format_water_status(user, entries)}", reply_markup=water_menu()
        )
    await callback.answer()


@router.callback_query(F.data == "water:delete_no")
async def cancel_water_deletion(callback: CallbackQuery) -> None:
    """Dismiss water-entry deletion."""
    await callback.answer("Удаление отменено")


async def ensure_user(session: AsyncSession, telegram_user: TelegramUser) -> User:
    """Resolve the internal user for a Telegram actor."""
    return await get_or_create_user(
        session,
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
    )


async def today_water(session: AsyncSession, user: User) -> list[WaterEntry]:
    """Load the current user's water entries for their local today."""
    return await get_water_for_day(
        session,
        user_id=user.id,
        day=local_today(user.timezone, day_boundary_time=user.day_boundary_time),
        timezone_name=user.timezone,
        day_boundary_time=user.day_boundary_time,
    )


def format_water_status(user: User, entries: list[WaterEntry]) -> str:
    """Format today's water total and optional target."""
    consumed = total_water(entries)
    if user.daily_water_target_ml:
        remaining = max(0, user.daily_water_target_ml - consumed)
        return (
            f"💧 Вода сегодня: {consumed} / {user.daily_water_target_ml} мл\n"
            f"Осталось: {remaining} мл"
        )
    return f"💧 Вода сегодня: {consumed} мл\nЦель не задана"


def format_water_history(user: User, entries: list[WaterEntry]) -> str:
    """Format today's water entries in the user's timezone."""
    zone = ZoneInfo(user.timezone)
    lines = [format_water_status(user, entries), "", "Записи:"]
    for entry in entries:
        instant = entry.drunk_at
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        lines.append(f"• {instant.astimezone(zone):%H:%M} — {entry.amount_ml} мл")
    return "\n".join(lines)


def parse_callback_id(data: str | None) -> int | None:
    """Extract a positive integer ID from callback data."""
    try:
        value = int((data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return None
    return value if value > 0 else None
