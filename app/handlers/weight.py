from datetime import UTC
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.keyboards.main_menu import main_menu
from app.keyboards.weight import (
    nutrition_recalculation_confirmation,
    weight_delete_confirmation,
    weight_entry_actions,
    weight_menu,
)
from app.models import User, WeightEntry
from app.repositories.users import get_or_create_user
from app.services.nutrition_recalculation import (
    NutritionRecalculation,
    apply_nutrition_recalculation,
    build_nutrition_recalculation,
    mark_nutrition_recalculation_prompted,
    nutrition_recalculation_due,
)
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
WEIGHT_MENU_ACTIONS = {
    "Записать вес",
    "История веса",
    "👤 Профиль",
    "↩️ Главное меню",
}


@router.message(Command("weight"))
@router.message(F.text == "⚖️ Вес")
async def open_weight(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Open weight tracking and immediately wait for a new measurement."""
    if message.from_user is None:
        return
    await state.clear()
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        history = await get_weight_history(session, user_id=user.id)
    await state.set_state(WeightAdd.value)
    await message.answer(
        f"{format_weight_status(user, history)}\n\n"
        "Введите текущий вес от 30 до 350 кг:",
        reply_markup=weight_menu(),
    )


@router.message(F.text == "Записать вес")
async def begin_weight_add(message: Message, state: FSMContext) -> None:
    """Ask for a new weight measurement."""
    await state.set_state(WeightAdd.value)
    await message.answer(
        "Введите текущий вес от 30 до 350 кг:",
        reply_markup=weight_menu(),
    )


@router.message(F.text == "↩️ Главное меню")
async def return_from_weight_to_main(message: Message, state: FSMContext) -> None:
    """Leave weight input without interpreting navigation as a weight."""
    await state.clear()
    await message.answer("Главное меню", reply_markup=main_menu())


@router.message(WeightAdd.value, ~F.text.in_(WEIGHT_MENU_ACTIONS))
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
    recalculation: NutritionRecalculation | None = None
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        await add_weight(session, user=user, weight_kg=weight_kg)
        history = await get_weight_history(session, user_id=user.id)
        if nutrition_recalculation_due(user, weight_kg):
            recalculation = build_nutrition_recalculation(user, weight_kg)
            if recalculation is not None:
                await mark_nutrition_recalculation_prompted(
                    session,
                    user=user,
                    weight_kg=weight_kg,
                )
    await state.clear()
    await message.answer(
        f"Вес записан: {format_decimal(weight_kg)} кг.\n\n"
        f"{format_weight_status(user, history)}",
        reply_markup=weight_menu(),
    )
    if recalculation is not None:
        await message.answer(
            format_nutrition_recalculation_prompt(recalculation),
            reply_markup=nutrition_recalculation_confirmation(weight_kg),
        )


@router.callback_query(F.data.startswith("weight:nutrition_recalc_yes:"))
async def confirm_nutrition_recalculation(
    callback: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    """Apply new nutrition targets only for the still-current weight."""
    expected_weight = parse_weight_token(callback.data)
    if expected_weight is None:
        await callback.answer("Некорректное предложение", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        result = await apply_nutrition_recalculation(
            session,
            user=user,
            expected_weight_kg=expected_weight,
        )
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        if result is None:
            await callback.message.answer(
                "Вес или параметры профиля уже изменились. "
                "Старое предложение пересчёта не применено.",
                reply_markup=weight_menu(),
            )
        else:
            await callback.message.answer(
                format_nutrition_recalculation_applied(result),
                reply_markup=weight_menu(),
            )
    await callback.answer("Нормы обновлены" if result is not None else "Предложение устарело")


@router.callback_query(F.data.startswith("weight:nutrition_recalc_no:"))
async def decline_nutrition_recalculation(callback: CallbackQuery) -> None:
    """Keep current targets; the prompt anchor was recorded when it was shown."""
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "Текущие нормы оставлены без изменений. "
            "Повторно предложу пересчёт после следующего заметного изменения веса."
        )
    await callback.answer("Оставляю текущие нормы")


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



def format_nutrition_recalculation_prompt(
    result: NutritionRecalculation,
) -> str:
    """Show the user exactly what will change before confirmation."""
    old_calories = result.old_calories if result.old_calories is not None else "—"
    old_protein = (
        format_decimal(result.old_protein) if result.old_protein is not None else "—"
    )
    old_fat = format_decimal(result.old_fat) if result.old_fat is not None else "—"
    old_carbs = (
        format_decimal(result.old_carbs) if result.old_carbs is not None else "—"
    )
    return (
        "⚖️ Вес заметно изменился. Пересчитать дневную норму?\n\n"
        f"Вес для нового расчёта: {format_decimal(result.weight_kg)} кг\n\n"
        f"Сейчас: {old_calories} ккал · "
        f"Б {old_protein} · Ж {old_fat} · У {old_carbs}\n"
        f"После пересчёта: {result.calories} ккал · "
        f"Б {result.protein} · Ж {result.fat} · У {result.carbs}\n\n"
        "Изменения применятся только после подтверждения."
    )


def format_nutrition_recalculation_applied(
    result: NutritionRecalculation,
) -> str:
    """Confirm the newly saved calorie and macro targets."""
    return (
        "✅ Дневная норма пересчитана.\n"
        f"🔥 {result.calories} ккал\n"
        f"Б {result.protein} г · Ж {result.fat} г · У {result.carbs} г"
    )


def parse_weight_token(data: str | None) -> Decimal | None:
    """Decode an exact hundredth-kilogram value from a callback."""
    try:
        token = int((data or "").rsplit(":", 1)[-1])
    except ValueError:
        return None
    if not 3000 <= token <= 35000:
        return None
    return Decimal(token) / Decimal(100)
