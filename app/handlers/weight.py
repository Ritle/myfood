from datetime import UTC
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.keyboards.weight import (
    weight_delete_confirmation,
    weight_entry_actions,
    weight_menu,
)
from app.models import User, WeightEntry
from app.repositories.users import get_or_create_user
from app.services.weight import (
    add_weight,
    change_weight,
    get_weight_history,
    load_owned_weight,
    parse_weight,
    remove_weight,
    weight_progress_percent,
)
from app.states.weight import WeightAdd, WeightEdit
from app.utils.formatting import format_decimal

router = Router()
HISTORY_LIMIT = 20


@router.message(Command("weight"))
@router.message(F.text == "⚖️ Вес")
async def open_weight(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Open weight tracking and show progress toward the target."""
    if message.from_user is None:
        return
    await state.clear()
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        history = await get_weight_history(session, user_id=user.id)
    await message.answer(format_weight_status(user, history), reply_markup=weight_menu())


@router.message(F.text == "Записать вес")
async def begin_weight_add(message: Message, state: FSMContext) -> None:
    """Ask for a new weight measurement."""
    await state.set_state(WeightAdd.value)
    await message.answer("Введите текущий вес от 30 до 350 кг:", reply_markup=ReplyKeyboardRemove())


@router.message(WeightAdd.value)
async def save_weight_add(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Validate and store a new weight measurement."""
    weight_kg = parse_weight(message.text)
    if weight_kg is None:
        await message.answer("Введите вес числом от 30 до 350 кг, например 72,5.")
        return
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        await add_weight(session, user=user, weight_kg=weight_kg)
        history = await get_weight_history(session, user_id=user.id)
    await state.clear()
    await message.answer(
        f"Вес записан: {format_decimal(weight_kg)} кг.\n\n"
        f"{format_weight_status(user, history)}",
        reply_markup=weight_menu(),
    )


@router.message(F.text == "История веса")
async def show_weight_history(message: Message, session_factory: async_sessionmaker) -> None:
    """Show recent weight measurements with edit and delete actions."""
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        history = await get_weight_history(session, user_id=user.id)
    if not history:
        await message.answer("Измерений веса пока нет.", reply_markup=weight_menu())
        return
    visible = history[:HISTORY_LIMIT]
    await message.answer(
        format_weight_history(
            user, visible, total_count=len(history), status_history=history
        ),
        reply_markup=weight_entry_actions(visible),
    )


@router.callback_query(F.data.startswith("weight:edit:"))
async def begin_weight_edit(
    callback: CallbackQuery, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Ask for a replacement value after checking ownership."""
    entry_id = parse_callback_id(callback.data)
    if entry_id is None:
        await callback.answer("Некорректная запись", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        entry = await load_owned_weight(session, user_id=user.id, entry_id=entry_id)
    if entry is None:
        await callback.answer("Запись недоступна", show_alert=True)
        return
    await state.set_state(WeightEdit.value)
    await state.update_data(weight_entry_id=entry_id)
    if callback.message is not None:
        await callback.message.answer(
            f"Введите новый вес вместо {format_decimal(entry.weight_kg)} кг:",
            reply_markup=ReplyKeyboardRemove(),
        )
    await callback.answer()


@router.message(WeightEdit.value)
async def save_weight_edit(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Apply a new value to an owned measurement."""
    weight_kg = parse_weight(message.text)
    if weight_kg is None:
        await message.answer("Введите вес числом от 30 до 350 кг, например 72,5.")
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        entry = await change_weight(
            session,
            user=user,
            entry_id=data["weight_entry_id"],
            weight_kg=weight_kg,
        )
        history = await get_weight_history(session, user_id=user.id)
    await state.clear()
    if entry is None:
        await message.answer("Запись недоступна.", reply_markup=weight_menu())
        return
    await message.answer(
        f"Запись обновлена: {format_decimal(weight_kg)} кг.\n\n"
        f"{format_weight_status(user, history)}",
        reply_markup=weight_menu(),
    )


@router.callback_query(F.data.startswith("weight:delete:"))
async def request_weight_deletion(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Request confirmation after checking measurement ownership."""
    entry_id = parse_callback_id(callback.data)
    if entry_id is None:
        await callback.answer("Некорректная запись", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        entry = await load_owned_weight(session, user_id=user.id, entry_id=entry_id)
    if entry is None:
        await callback.answer("Запись недоступна", show_alert=True)
        return
    if callback.message is not None:
        await callback.message.answer(
            "Удалить это измерение веса?", reply_markup=weight_delete_confirmation(entry_id)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("weight:delete_yes:"))
async def confirm_weight_deletion(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Delete an owned measurement and show the recalculated current weight."""
    entry_id = parse_callback_id(callback.data)
    if entry_id is None:
        await callback.answer("Некорректная запись", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        removed = await remove_weight(session, user=user, entry_id=entry_id)
        history = await get_weight_history(session, user_id=user.id)
    if callback.message is not None:
        text = "Измерение удалено." if removed else "Запись уже недоступна."
        await callback.message.answer(
            f"{text}\n\n{format_weight_status(user, history)}", reply_markup=weight_menu()
        )
    await callback.answer()


@router.callback_query(F.data == "weight:delete_no")
async def cancel_weight_deletion(callback: CallbackQuery) -> None:
    """Dismiss measurement deletion."""
    await callback.answer("Удаление отменено")


async def ensure_user(session: AsyncSession, telegram_user: TelegramUser) -> User:
    """Resolve the internal user for a Telegram actor."""
    return await get_or_create_user(
        session,
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
    )


def format_weight_status(user: User, history: list[WeightEntry]) -> str:
    """Format current weight and progress from the oldest measurement."""
    current = history[0].weight_kg if history else user.current_weight_kg
    target = user.target_weight_kg
    lines = ["⚖️ Вес"]
    if current is None:
        lines.append("Текущий вес не указан.")
        return "\n".join(lines)
    lines.append(f"Текущий: {format_decimal(current)} кг")
    if target is None:
        lines.append("Целевой вес не указан.")
        return "\n".join(lines)
    lines.append(f"Целевой: {format_decimal(target)} кг")
    remaining = abs(current - target)
    if remaining == 0:
        lines.append("Цель достигнута 🎉")
    else:
        lines.append(f"До цели: {format_decimal(remaining)} кг")
    if history:
        start = history[-1].weight_kg
        progress = weight_progress_percent(start, current, target)
        lines.append(f"{progress_bar(progress)} {progress}%")
        change = current - start
        sign = "+" if change > 0 else ""
        lines.append(f"Изменение: {sign}{format_decimal(change)} кг")
    return "\n".join(lines)


def format_weight_history(
    user: User,
    entries: list[WeightEntry],
    *,
    total_count: int,
    status_history: list[WeightEntry] | None = None,
) -> str:
    """Format recent measurements in the user's timezone."""
    zone = ZoneInfo(user.timezone)
    lines = [
        format_weight_status(user, status_history or entries),
        "",
        "Последние измерения:",
    ]
    for entry in entries:
        instant = entry.measured_at
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        lines.append(
            f"• {instant.astimezone(zone):%d.%m.%Y %H:%M} — "
            f"{format_decimal(entry.weight_kg)} кг"
        )
    if total_count > len(entries):
        lines.append(f"Показаны последние {len(entries)} из {total_count} измерений.")
    return "\n".join(lines)


def progress_bar(percent: int, *, width: int = 10) -> str:
    """Render a compact bounded progress bar."""
    filled = min(width, max(0, percent * width // 100))
    return f"{'█' * filled}{'░' * (width - filled)}"


def parse_callback_id(data: str | None) -> int | None:
    """Extract a positive integer ID from callback data."""
    try:
        value = int((data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return None
    return value if value > 0 else None
