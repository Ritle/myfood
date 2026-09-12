from collections import defaultdict
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.keyboards.diary import (
    delete_confirmation,
    diary_entry_actions,
    diary_food_page,
    diary_food_results,
    diary_menu,
    diary_source_actions,
)
from app.models import FoodEntry, User
from app.repositories.notifications import mark_notification_sent
from app.repositories.users import get_or_create_user
from app.services.calorie_alerts import CalorieAlert, claim_calorie_alert
from app.services.diary import (
    MEAL_LABELS,
    add_diary_entry,
    get_entries_for_day,
    load_owned_entry,
    local_today,
    remove_diary_entry,
    resize_diary_entry,
    summarize_entries,
)
from app.services.foods import (
    favorite_foods,
    load_food,
    recent_foods,
    search_foods_page,
)
from app.states.diary import DiaryAdd, DiaryEdit
from app.utils.formatting import format_decimal
from app.utils.numbers import parse_decimal

router = Router()
MEAL_BUTTONS = {label: meal_type for meal_type, label in MEAL_LABELS.items()}


@router.message(Command("food"))
@router.message(F.text == "🍽 Питание")
async def open_diary(message: Message, state: FSMContext) -> None:
    """Open the food diary and meal selection."""
    await state.clear()
    await message.answer("Выберите прием пищи:", reply_markup=diary_menu())


@router.message(F.text.in_(MEAL_BUTTONS))
async def choose_meal(message: Message, state: FSMContext) -> None:
    """Select a meal and prompt for a product search."""
    meal_type = MEAL_BUTTONS[message.text or ""]
    await state.set_state(DiaryAdd.query)
    await state.update_data(meal_type=meal_type)
    await message.answer(
        f"{MEAL_LABELS[meal_type]}: введите название продукта или бренд.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Можно также выбрать продукт из готового списка:",
        reply_markup=diary_source_actions(meal_type),
    )


@router.message(DiaryAdd.query)
async def search_product_for_diary(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Search products for the selected meal."""
    if message.from_user is None:
        return
    data = await state.get_data()
    meal_type = data["meal_type"]
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        try:
            page = await search_foods_page(
                session, user_id=user.id, query=message.text or "", page=0
            )
        except ValueError as error:
            await message.answer(str(error))
            return
    if not page.items:
        await message.answer("Продукт не найден. Введите другой запрос.")
        return
    await state.update_data(diary_query=message.text or "")
    await message.answer(
        "Выберите продукт:",
        reply_markup=diary_food_page(
            page.items,
            meal_type,
            page=page.page,
            total_pages=page.total_pages,
        ),
    )


@router.callback_query(F.data.startswith("diary:page:"))
async def paginate_diary_search(
    callback: CallbackQuery, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Move through product search pages without losing the selected meal."""
    try:
        requested_page = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректная страница", show_alert=True)
        return
    data = await state.get_data()
    query = data.get("diary_query")
    meal_type = data.get("meal_type")
    if callback.message is None or not isinstance(query, str) or meal_type not in MEAL_LABELS:
        await callback.answer("Поиск устарел. Выберите прием пищи снова.", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        page = await search_foods_page(
            session, user_id=user.id, query=query, page=requested_page
        )
    await callback.message.edit_reply_markup(
        reply_markup=diary_food_page(
            page.items,
            meal_type,
            page=page.page,
            total_pages=page.total_pages,
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("diary:source:"))
async def show_diary_food_source(
    callback: CallbackQuery, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Show recent or favorite products for the selected meal."""
    try:
        _, _, source, meal_type = (callback.data or "").split(":", 3)
    except ValueError:
        await callback.answer("Некорректный список", show_alert=True)
        return
    if source not in {"recent", "favorites"} or meal_type not in MEAL_LABELS:
        await callback.answer("Некорректный список", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        foods = (
            await recent_foods(session, user_id=user.id)
            if source == "recent"
            else await favorite_foods(session, user_id=user.id)
        )
    await state.set_state(DiaryAdd.query)
    await state.update_data(meal_type=meal_type)
    if callback.message is not None:
        if foods:
            await callback.message.answer(
                "Выберите продукт:",
                reply_markup=diary_food_results(foods[:10], meal_type),
            )
        else:
            label = "Недавних продуктов" if source == "recent" else "Избранных продуктов"
            await callback.message.answer(f"{label} пока нет. Введите название для поиска.")
    await callback.answer()


@router.callback_query(F.data == "diary:noop")
async def ignore_diary_page_counter(callback: CallbackQuery) -> None:
    """Acknowledge the inert page counter button."""
    await callback.answer()


@router.callback_query(F.data.startswith("diary:add:"))
async def select_diary_food(
    callback: CallbackQuery, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Select a visible product and ask for portion weight."""
    if callback.data is None:
        return
    try:
        _, _, meal_type, raw_food_id = callback.data.split(":", 3)
        food_id = int(raw_food_id)
    except (ValueError, TypeError):
        await callback.answer("Некорректный выбор", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        food = await load_food(session, user_id=user.id, food_id=food_id)
    if food is None or meal_type not in MEAL_LABELS:
        await callback.answer("Продукт недоступен", show_alert=True)
        return
    await state.set_state(DiaryAdd.weight)
    await state.update_data(food_id=food_id, meal_type=meal_type)
    if callback.message is not None:
        await callback.message.answer(f"Сколько граммов «{food.name}» вы съели?")
    await callback.answer()


@router.message(DiaryAdd.weight)
async def enter_portion_weight(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    """Calculate and save a selected product portion."""
    weight = parse_decimal(message.text)
    if weight is None or not Decimal("0.01") <= weight <= Decimal(10000):
        await message.answer("Введите вес порции от 0,01 до 10000 г.")
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        food = await load_food(session, user_id=user.id, food_id=data["food_id"])
        if food is None:
            await state.clear()
            await message.answer("Продукт больше недоступен.", reply_markup=diary_menu())
            return
        previous_entries = await today_entries(session, user)
        previous_total = summarize_entries(previous_entries).calories
        entry = await add_diary_entry(
            session,
            user_id=user.id,
            food=food,
            meal_type=data["meal_type"],
            weight_grams=weight,
        )
        entries = await today_entries(session, user)
        alert = await claim_alert_for_change(
            session,
            user=user,
            previous_total=previous_total,
            current_total=summarize_entries(entries).calories,
            settings=settings,
        )
    await state.clear()
    await message.answer(
        f"Добавлено: {food.name}, {format_decimal(entry.weight_grams)} г\n"
        f"{format_decimal(entry.calories)} ккал · "
        f"Б {format_decimal(entry.protein)} · Ж {format_decimal(entry.fat)} · "
        f"У {format_decimal(entry.carbs)}\n\n{format_summary(entries)}",
        reply_markup=diary_menu(),
    )
    await deliver_calorie_alert(message, alert, settings, session_factory)


@router.message(F.text == "📋 Дневник за сегодня")
async def show_today_diary(message: Message, session_factory: async_sessionmaker) -> None:
    """Show today's entries grouped by meal."""
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        entries = await today_entries(session, user)
    if not entries:
        await message.answer("Сегодня в дневнике пока нет записей.", reply_markup=diary_menu())
        return
    await message.answer(format_diary(entries), reply_markup=diary_entry_actions(entries))
    await message.answer("Выберите действие или прием пищи.", reply_markup=diary_menu())


@router.callback_query(F.data.startswith("diary:edit:"))
async def begin_entry_edit(
    callback: CallbackQuery, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Ask for a replacement weight of an owned entry."""
    entry_id = parse_callback_id(callback.data)
    if entry_id is None:
        await callback.answer("Некорректная запись", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        entry = await load_owned_entry(session, user_id=user.id, entry_id=entry_id)
    if entry is None:
        await callback.answer("Запись недоступна", show_alert=True)
        return
    await state.set_state(DiaryEdit.weight)
    await state.update_data(entry_id=entry_id)
    if callback.message is not None:
        await callback.message.answer(
            f"Новый вес для «{entry.food.name}» в граммах:",
            reply_markup=ReplyKeyboardRemove(),
        )
    await callback.answer()


@router.message(DiaryEdit.weight)
async def save_entry_edit(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    """Apply a new portion weight to an owned diary entry."""
    weight = parse_decimal(message.text)
    if weight is None or not Decimal("0.01") <= weight <= Decimal(10000):
        await message.answer("Введите вес порции от 0,01 до 10000 г.")
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        previous_entries = await today_entries(session, user)
        previous_total = summarize_entries(previous_entries).calories
        entry = await resize_diary_entry(
            session, user_id=user.id, entry_id=data["entry_id"], new_weight_grams=weight
        )
        if entry is not None:
            entries = await today_entries(session, user)
            alert = await claim_alert_for_change(
                session,
                user=user,
                previous_total=previous_total,
                current_total=summarize_entries(entries).calories,
                settings=settings,
            )
        else:
            alert = None
    await state.clear()
    if entry is None:
        await message.answer("Запись недоступна.", reply_markup=diary_menu())
        return
    await message.answer(
        f"Запись обновлена: {format_decimal(entry.weight_grams)} г, "
        f"{format_decimal(entry.calories)} ккал.",
        reply_markup=diary_menu(),
    )
    await deliver_calorie_alert(message, alert, settings, session_factory)


@router.callback_query(F.data.startswith("diary:delete:"))
async def request_entry_deletion(callback: CallbackQuery) -> None:
    """Request confirmation before deleting an entry."""
    entry_id = parse_callback_id(callback.data)
    if entry_id is None:
        await callback.answer("Некорректная запись", show_alert=True)
        return
    if callback.message is not None:
        await callback.message.answer(
            "Удалить эту запись из дневника?",
            reply_markup=delete_confirmation(entry_id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("diary:delete_yes:"))
async def confirm_entry_deletion(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Delete an entry after checking ownership."""
    entry_id = parse_callback_id(callback.data)
    if entry_id is None:
        await callback.answer("Некорректная запись", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        removed = await remove_diary_entry(session, user_id=user.id, entry_id=entry_id)
    if callback.message is not None:
        await callback.message.answer("Запись удалена." if removed else "Запись уже недоступна.")
    await callback.answer()


@router.callback_query(F.data == "diary:delete_no")
async def cancel_entry_deletion(callback: CallbackQuery) -> None:
    """Dismiss entry deletion."""
    await callback.answer("Удаление отменено")


async def ensure_user(session: AsyncSession, telegram_user: TelegramUser) -> User:
    """Resolve the internal user for a Telegram actor."""
    return await get_or_create_user(
        session,
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
    )


async def today_entries(session: AsyncSession, user: User) -> list[FoodEntry]:
    """Load the current user's entries for their local today."""
    day = local_today(user.timezone)
    return await get_entries_for_day(session, user_id=user.id, day=day, timezone_name=user.timezone)


def format_diary(entries: list[FoodEntry]) -> str:
    """Format entries grouped in the canonical meal order."""
    grouped: dict[str, list[FoodEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.meal_type].append(entry)
    lines = ["📋 Дневник за сегодня"]
    for meal_type in MEAL_LABELS:
        meal_entries = grouped[meal_type]
        if not meal_entries:
            continue
        lines.append(f"\n{MEAL_LABELS[meal_type]}")
        for entry in meal_entries:
            lines.append(
                f"• {entry.food.name} — {format_decimal(entry.weight_grams)} г, "
                f"{format_decimal(entry.calories)} ккал"
            )
        meal_total = summarize_entries(meal_entries)
        lines.append(f"Подытог: {format_decimal(meal_total.calories)} ккал")
    lines.append(f"\n{format_summary(entries)}")
    return "\n".join(lines)


def format_summary(entries: list[FoodEntry]) -> str:
    """Format calorie and macronutrient totals."""
    total = summarize_entries(entries)
    return (
        f"Итого: {format_decimal(total.calories)} ккал\n"
        f"Б: {format_decimal(total.protein)} г · Ж: {format_decimal(total.fat)} г · "
        f"У: {format_decimal(total.carbs)} г"
    )


def parse_callback_id(data: str | None) -> int | None:
    """Extract a positive integer ID from callback data."""
    try:
        value = int((data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return None
    return value if value > 0 else None


async def claim_alert_for_change(
    session: AsyncSession,
    *,
    user: User,
    previous_total: Decimal,
    current_total: Decimal,
    settings: Settings,
) -> CalorieAlert | None:
    """Claim a calorie alert when a diary mutation crosses a configured threshold."""
    if user.daily_calorie_target is None:
        return None
    return await claim_calorie_alert(
        session,
        user_id=user.id,
        local_date=local_today(user.timezone),
        previous_total=previous_total,
        current_total=current_total,
        target=Decimal(user.daily_calorie_target),
        warning_ratio=settings.calorie_warning_ratio,
    )


async def deliver_calorie_alert(
    message: Message,
    alert: CalorieAlert | None,
    settings: Settings,
    session_factory: async_sessionmaker,
) -> None:
    """Deliver a claimed alert and mark it sent only after Telegram accepts it."""
    if alert is None:
        return
    if alert.level == "warning":
        percent = int(settings.calorie_warning_ratio * 100)
        text = (
            f"⚠️ Вы использовали {percent}% дневной нормы калорий.\n"
            f"{format_decimal(alert.total)} / {format_decimal(alert.target)} ккал"
        )
    elif alert.level == "goal":
        text = (
            "🔥 Вы достигли дневной нормы калорий.\n"
            f"{format_decimal(alert.total)} / {format_decimal(alert.target)} ккал"
        )
    else:
        excess = alert.total - alert.target
        text = (
            f"⚠️ Дневная норма превышена на {format_decimal(excess)} ккал.\n"
            f"{format_decimal(alert.total)} / {format_decimal(alert.target)} ккал"
        )
    await message.answer(text)
    async with session_factory() as session:
        await mark_notification_sent(session, alert.log_id)
