from collections import defaultdict
from decimal import Decimal

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.keyboards.diary import (
    FINISH_DIARY_ADDING_TEXT,
    delete_confirmation,
    diary_batch_confirmation,
    diary_entry_actions,
    diary_food_page,
    diary_food_results,
    diary_meal_templates,
    diary_menu,
    diary_portion_keyboard,
    diary_recent_food_results,
    diary_source_actions,
    meal_template_delete_confirmation,
)
from app.models import Food, FoodEntry, User
from app.repositories.notifications import mark_notification_sent
from app.repositories.users import get_or_create_user
from app.services.calorie_alerts import CalorieAlert, claim_calorie_alert
from app.services.days import get_or_create_active_diary_day
from app.services.diary import (
    MEAL_LABELS,
    add_diary_entries,
    add_diary_entry,
    calculate_portion,
    get_entries_for_day,
    load_owned_entry,
    remove_diary_entry,
    resize_diary_entry,
    suggest_meal_type,
    summarize_entries,
)
from app.services.foods import (
    favorite_foods,
    latest_food_portion_entry,
    load_food,
    normalize_food_text,
    recent_food_portions,
    search_foods,
    search_foods_page,
)
from app.services.meal_templates import (
    MAX_MEAL_TEMPLATE_ITEMS,
    delete_owned_meal_template,
    list_user_meal_templates,
    load_owned_meal_template,
)
from app.states.diary import DiaryAdd, DiaryEdit
from app.utils.food_batches import (
    MAX_BATCH_ITEMS,
    ParsedFoodBatch,
    ParsedFoodItem,
    parse_food_batch_input,
)
from app.utils.formatting import format_decimal
from app.utils.numbers import parse_decimal
from app.utils.portions import parse_portion_input

router = Router()
MEAL_BUTTONS = {label: meal_type for meal_type, label in MEAL_LABELS.items()}
DIARY_NAVIGATION_TEXTS = {
    "📋 Дневник за сегодня",
    "📚 Каталог продуктов",
    "↩️ Главное меню",
    "🌙 Завершить день",
    FINISH_DIARY_ADDING_TEXT,
}


def is_diary_search_text(text: str | None) -> bool:
    """Keep commands and keyboard navigation out of the product search handler."""
    return bool(
        text
        and not text.startswith("/")
        and text not in MEAL_BUTTONS
        and text not in DIARY_NAVIGATION_TEXTS
    )


@router.message(Command("food"))
@router.message(F.text == "🍽 Питание")
async def open_diary(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Open the diary with a meal suggested from the user's local time."""
    await state.clear()
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
    meal_type = suggest_meal_type(user.timezone)
    await state.set_state(DiaryAdd.query)
    await state.update_data(meal_type=meal_type)
    await message.answer(
        f"Предлагаю записать в «{MEAL_LABELS[meal_type]}». Введите продукт или бренд; "
        "при необходимости смените прием пищи кнопкой ниже.",
        reply_markup=diary_menu(adding=True),
    )
    await message.answer(
        "Можно также выбрать продукт из готового списка:",
        reply_markup=diary_source_actions(meal_type),
    )


@router.message(F.text.in_(MEAL_BUTTONS))
async def choose_meal(message: Message, state: FSMContext) -> None:
    """Select a meal and prompt for a product search."""
    meal_type = MEAL_BUTTONS[message.text or ""]
    await state.set_state(DiaryAdd.query)
    await state.update_data(meal_type=meal_type)
    await message.answer(
        f"Выбрано «{MEAL_LABELS[meal_type]}». Введите продукт или бренд; "
        "при необходимости смените прием пищи кнопкой ниже.",
        reply_markup=diary_menu(adding=True),
    )
    await message.answer(
        "Можно также выбрать продукт из готового списка:",
        reply_markup=diary_source_actions(meal_type),
    )


@router.message(F.text == FINISH_DIARY_ADDING_TEXT)
async def finish_diary_addition(message: Message, state: FSMContext) -> None:
    """Finish the current meal-entry session without changing the logical day."""
    data = await state.get_data()
    meal_type = data.get("meal_type")
    await state.clear()
    label = MEAL_LABELS.get(meal_type)
    text = (
        f"✅ Добавление в «{label}» завершено."
        if label is not None
        else "✅ Добавление питания завершено."
    )
    await message.answer(text, reply_markup=diary_menu())


@router.message(DiaryAdd.query, F.text.func(is_diary_search_text))
async def search_product_for_diary(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Search products for the selected meal."""
    try:
        batch = parse_food_batch_input(message.text)
    except ValueError as error:
        await message.answer(str(error))
        return
    if batch is not None:
        data = await state.get_data()
        await prepare_food_batch(
            message,
            state,
            session_factory,
            batch=batch,
            default_meal_type=data.get("meal_type"),
        )
        return
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


async def prepare_food_batch(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker,
    *,
    batch: ParsedFoodBatch,
    default_meal_type: str | None,
) -> None:
    """Resolve products and display their weights and totals for confirmation."""
    if message.from_user is None:
        return
    meal_type = batch.meal_type or default_meal_type
    if meal_type not in MEAL_LABELS:
        await message.answer("Сначала выберите прием пищи.")
        return

    resolved: list[tuple[ParsedFoodItem, Food]] = []
    missing: list[str] = []
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        for item in batch.items:
            matches = await search_foods(
                session, user_id=user.id, query=item.query, limit=20
            )
            if not matches:
                missing.append(item.query)
                continue
            normalized_query = normalize_food_text(item.query)
            exact = [food for food in matches if food.name_normalized == normalized_query]
            if not exact:
                exact = [
                    food for food in matches if food.brand_normalized == normalized_query
                ]
            prefix = [
                food for food in matches if food.name_normalized.startswith(normalized_query)
            ]
            resolved.append((item, (exact or prefix or matches)[0]))
    if missing:
        await message.answer(
            f"Не нашел в каталоге: {', '.join(missing)}. "
            "Исправьте названия и отправьте список еще раз."
        )
        return

    preview_items = [
        (item.query, food, item.weight_grams, item.assumed_weight)
        for item, food in resolved
    ]
    await prepare_batch_confirmation(
        message,
        state,
        meal_type=meal_type,
        preview_items=preview_items,
        title=f"Проверьте список для «{MEAL_LABELS[meal_type]}»:",
    )


async def prepare_batch_confirmation(
    message: Message,
    state: FSMContext,
    *,
    meal_type: str,
    preview_items: list[tuple[str, Food, Decimal, bool]],
    title: str,
) -> None:
    """Calculate a reusable multi-item preview and await user confirmation."""
    state_items = []
    lines = [title]
    totals = {"calories": Decimal(0), "protein": Decimal(0), "fat": Decimal(0), "carbs": Decimal(0)}
    has_assumed_weights = False
    for label, food, weight, assumed_weight in preview_items:
        portion = calculate_portion(food, weight)
        totals["calories"] += portion.calories
        totals["protein"] += portion.protein
        totals["fat"] += portion.fat
        totals["carbs"] += portion.carbs
        assumed_note = " (вес принят за 100 г)" if assumed_weight else ""
        has_assumed_weights = (
            has_assumed_weights
            or (assumed_weight and food.nutrition_basis != "portion")
        )
        product_label = f"{label} → {food.name}" if label != food.name else food.name
        if food.nutrition_basis == "portion":
            lines.append(
                f"• {product_label} — 1 порция · "
                f"{format_decimal(portion.calories)} ккал"
            )
        else:
            lines.append(
                f"• {product_label} — {format_decimal(weight)} г"
                f"{assumed_note} · {format_decimal(portion.calories)} ккал"
            )
        state_items.append(
            {
                "food_id": food.id,
                "weight_grams": str(weight),
                "assumed_weight": assumed_weight,
            }
        )
    if has_assumed_weights:
        lines.append("Для продуктов без указанного веса использовал 100 г.")
    lines.append(
        f"\nИтого: {format_decimal(totals['calories'])} ккал · "
        f"Б {format_decimal(totals['protein'])} · Ж {format_decimal(totals['fat'])} · "
        f"У {format_decimal(totals['carbs'])}"
    )
    await state.set_state(DiaryAdd.batch_confirm)
    await state.update_data(meal_type=meal_type, batch_items=state_items)
    await message.answer("\n".join(lines), reply_markup=diary_batch_confirmation())


@router.callback_query(F.data == "diary:batch:cancel")
async def cancel_food_batch(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancel a pending multi-food confirmation and return to product input."""
    if await state.get_state() != DiaryAdd.batch_confirm.state:
        await callback.answer("Этот список уже закрыт.", show_alert=True)
        return
    data = await state.get_data()
    meal_type = data.get("meal_type")
    if meal_type not in MEAL_LABELS:
        await callback.answer("Выберите приём пищи заново.", show_alert=True)
        return
    await state.set_state(DiaryAdd.query)
    await state.update_data(batch_items=None, meal_type=meal_type)
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            pass
        await callback.message.answer(
            "Список отменён. Введите продукты заново.",
            reply_markup=diary_menu(adding=True),
        )
    await callback.answer("Отменено")


@router.callback_query(F.data == "diary:batch:confirm")
async def confirm_food_batch(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    """Atomically add every visible product in a confirmed message batch."""
    if await state.get_state() != DiaryAdd.batch_confirm.state:
        await callback.answer("Этот список уже закрыт.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Не удалось открыть дневник. Попробуйте снова.", show_alert=True)
        return

    data = await state.get_data()
    meal_type = data.get("meal_type")
    raw_items = data.get("batch_items")
    if (
        meal_type not in MEAL_LABELS
        or not isinstance(raw_items, list)
        or not 1 <= len(raw_items) <= MAX_BATCH_ITEMS
    ):
        await callback.answer("Список устарел. Введите продукты заново.", show_alert=True)
        return

    stale = False
    entries: list[FoodEntry] = []
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        items: list[tuple[Food, Decimal]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                stale = True
                break
            food_id = raw_item.get("food_id")
            weight = parse_decimal(str(raw_item.get("weight_grams", "")))
            if (
                not isinstance(food_id, int)
                or not 1 <= food_id
                or weight is None
                or not Decimal("0.01") <= weight <= Decimal(10000)
            ):
                stale = True
                break
            food = await load_food(session, user_id=user.id, food_id=food_id)
            if food is None:
                stale = True
                break
            items.append((food, weight))
        if not stale:
            previous_entries = await today_entries(session, user)
            previous_total = summarize_entries(previous_entries).calories
            entries = await add_diary_entries(
                session,
                user_id=user.id,
                items=items,
                meal_type=meal_type,
            )
            current_entries = await today_entries(session, user)
            alert = await claim_alert_for_change(
                session,
                user=user,
                previous_total=previous_total,
                current_total=summarize_entries(current_entries).calories,
                settings=settings,
            )

    if stale:
        await state.set_state(DiaryAdd.query)
        await state.update_data(batch_items=None, meal_type=meal_type)
        await callback.message.answer(
            "Один из продуктов стал недоступен. Проверьте названия и отправьте список заново.",
            reply_markup=diary_menu(adding=True),
        )
        await callback.answer("Список устарел", show_alert=True)
        return

    await continue_diary_addition(state, meal_type)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError:
        pass
    await callback.message.answer(
        f"Добавлено продуктов: {len(entries)}.\n\n{format_summary(current_entries)}\n\n"
        f"Добавьте следующий продукт в «{MEAL_LABELS[meal_type]}» "
        "или нажмите «✅ Завершить добавление».",
        reply_markup=diary_menu(adding=True),
    )
    await callback.answer("Добавлено")
    await deliver_calorie_alert(callback.message, alert, settings, session_factory)


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
    if source not in {"recent", "favorites", "templates"} or meal_type not in MEAL_LABELS:
        await callback.answer("Некорректный список", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        recent_items = (
            await recent_food_portions(session, user_id=user.id)
            if source == "recent"
            else []
        )
        foods = (
            []
            if source == "recent"
            or source == "templates"
            else await favorite_foods(session, user_id=user.id)
        )
        templates = (
            await list_user_meal_templates(session, user_id=user.id)
            if source == "templates"
            else []
        )
    await state.set_state(DiaryAdd.query)
    await state.update_data(meal_type=meal_type)
    if callback.message is not None:
        if source == "recent" and recent_items:
            await callback.message.answer(
                "Нажмите «изменить», чтобы задать вес заново, или ↻, "
                "чтобы повторить прошлую порцию:",
                reply_markup=diary_recent_food_results(recent_items[:10], meal_type),
            )
        elif source == "templates" and templates:
            await callback.message.answer(
                "Выберите шаблон, чтобы проверить и добавить привычное блюдо:",
                reply_markup=diary_meal_templates(templates, meal_type=meal_type),
            )
        elif foods:
            await callback.message.answer(
                "Выберите продукт:",
                reply_markup=diary_food_results(foods[:10], meal_type),
            )
        else:
            label = {
                "recent": "Недавних продуктов",
                "favorites": "Избранных продуктов",
                "templates": "Шаблонов блюд",
            }[source]
            detail = (
                "Добавьте блюдо в дневник и сохраните его из раздела «История»."
                if source == "templates"
                else "Введите название для поиска."
            )
            await callback.message.answer(f"{label} пока нет. {detail}")
    await callback.answer()


@router.callback_query(F.data.startswith("diary:template:use:"))
async def use_meal_template(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
) -> None:
    """Preview an owned template in the currently selected diary meal."""
    if not isinstance(callback.message, Message):
        await callback.answer("Не удалось открыть дневник. Попробуйте снова.", show_alert=True)
        return
    try:
        _, _, _, meal_type, raw_template_id = (callback.data or "").split(":", 4)
        template_id = int(raw_template_id)
    except ValueError:
        await callback.answer("Некорректный шаблон", show_alert=True)
        return
    if meal_type not in MEAL_LABELS or template_id <= 0:
        await callback.answer("Некорректный шаблон", show_alert=True)
        return

    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        template = await load_owned_meal_template(
            session, user_id=user.id, template_id=template_id
        )
        if template is None or not 1 <= len(template.items) <= MAX_MEAL_TEMPLATE_ITEMS:
            await callback.answer("Шаблон недоступен или устарел", show_alert=True)
            return
        preview_items = []
        for template_item in template.items:
            food = await load_food(
                session, user_id=user.id, food_id=template_item.food_id
            )
            if food is None:
                await callback.answer(
                    "Один из продуктов больше недоступен. Обновите шаблон.",
                    show_alert=True,
                )
                return
            preview_items.append(
                (food.name, food, Decimal(template_item.weight_grams), False)
            )

    await prepare_batch_confirmation(
        callback.message,
        state,
        meal_type=meal_type,
        preview_items=preview_items,
        title=(
            f"Шаблон «{template.name}» для «{MEAL_LABELS[meal_type]}». "
            "Проверьте состав и актуальные КБЖУ:"
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("diary:template:delete:"))
async def request_meal_template_deletion(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Ask before deleting one of the user's saved templates."""
    try:
        template_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректный шаблон", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        template = await load_owned_meal_template(
            session, user_id=user.id, template_id=template_id
        )
    if template is None:
        await callback.answer("Шаблон недоступен", show_alert=True)
        return
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"Удалить шаблон «{template.name}»?",
            reply_markup=meal_template_delete_confirmation(template.id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("diary:template:delete_yes:"))
async def confirm_meal_template_deletion(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Delete an owned meal template after explicit confirmation."""
    try:
        template_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректный шаблон", show_alert=True)
        return
    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        deleted = await delete_owned_meal_template(
            session, user_id=user.id, template_id=template_id
        )
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "Шаблон удален." if deleted else "Шаблон уже недоступен."
        )
    await callback.answer("Удалено" if deleted else "Недоступно")


@router.callback_query(F.data == "diary:template:delete_no")
async def cancel_meal_template_deletion(callback: CallbackQuery) -> None:
    """Dismiss the meal template delete prompt."""
    await callback.answer("Оставил шаблон")


@router.callback_query(F.data.startswith("diary:repeat:"))
async def repeat_recent_food_portion(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    """Repeat an owned recent diary entry with the same food and portion weight."""
    if not isinstance(callback.message, Message):
        await callback.answer("Не удалось открыть дневник. Попробуйте снова.", show_alert=True)
        return
    try:
        _, _, meal_type, raw_entry_id = (callback.data or "").split(":", 3)
        entry_id = int(raw_entry_id)
    except ValueError:
        await callback.answer("Некорректный выбор", show_alert=True)
        return
    if meal_type not in MEAL_LABELS:
        await callback.answer("Некорректный прием пищи", show_alert=True)
        return

    async with session_factory() as session:
        user = await ensure_user(session, callback.from_user)
        previous_entry = await load_owned_entry(
            session, user_id=user.id, entry_id=entry_id
        )
        if previous_entry is None or previous_entry.food.is_archived:
            await callback.answer(
                "Последняя порция больше недоступна. Откройте список недавних снова.",
                show_alert=True,
            )
            return
        latest_entry = await latest_food_portion_entry(
            session, user_id=user.id, food_id=previous_entry.food_id
        )
        if latest_entry is None or latest_entry.id != previous_entry.id:
            await callback.answer(
                "Список недавних устарел. Откройте его снова.", show_alert=True
            )
            return
        previous_entries = await today_entries(session, user)
        previous_total = summarize_entries(previous_entries).calories
        entry = await add_diary_entry(
            session,
            user_id=user.id,
            food=previous_entry.food,
            meal_type=meal_type,
            weight_grams=previous_entry.weight_grams,
        )
        entries = await today_entries(session, user)
        alert = await claim_alert_for_change(
            session,
            user=user,
            previous_total=previous_total,
            current_total=summarize_entries(entries).calories,
            settings=settings,
        )
        recent_items = await recent_food_portions(session, user_id=user.id)

    await continue_diary_addition(state, meal_type)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=diary_recent_food_results(recent_items, meal_type)
        )
    except TelegramAPIError:
        pass
    await callback.message.answer(
        (
            f"Повторно добавлено: {previous_entry.food.name}, 1 порция\n"
            if entry.is_full_serving
            else f"Повторно добавлено: {previous_entry.food.name}, "
            f"{format_decimal(entry.weight_grams)} г\n"
        )
        f"{format_decimal(entry.calories)} ккал · "
        f"Б {format_decimal(entry.protein)} · Ж {format_decimal(entry.fat)} · "
        f"У {format_decimal(entry.carbs)}\n\n{format_summary(entries)}\n\n"
        f"Добавьте следующий продукт в «{MEAL_LABELS[meal_type]}» "
        "или нажмите «✅ Завершить добавление».",
        reply_markup=diary_menu(adding=True),
    )
    await callback.answer("Добавлено")
    await deliver_calorie_alert(callback.message, alert, settings, session_factory)


@router.callback_query(F.data == "diary:noop")
async def ignore_diary_page_counter(callback: CallbackQuery) -> None:
    """Acknowledge the inert page counter button."""
    await callback.answer()


@router.callback_query(F.data.startswith("diary:add:"))
async def select_diary_food(
    callback: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    """Add a whole dish immediately or ask for a product portion weight."""
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
        if food is not None and meal_type in MEAL_LABELS and food.nutrition_basis == "portion":
            previous_entries = await today_entries(session, user)
            previous_total = summarize_entries(previous_entries).calories
            entry = await add_diary_entry(
                session,
                user_id=user.id,
                food=food,
                meal_type=meal_type,
                weight_grams=Decimal(1),
            )
            entries = await today_entries(session, user)
            alert = await claim_alert_for_change(
                session,
                user=user,
                previous_total=previous_total,
                current_total=summarize_entries(entries).calories,
                settings=settings,
            )
        else:
            entry = None
            entries = []
            alert = None
    if food is None or meal_type not in MEAL_LABELS:
        await callback.answer("Продукт недоступен", show_alert=True)
        return
    if entry is not None:
        await continue_diary_addition(state, meal_type)
        if callback.message is not None:
            await callback.message.answer(
                f"Добавлено блюдо целиком: {food.name}\n"
                f"{format_decimal(entry.calories)} ккал · "
                f"Б {format_decimal(entry.protein)} · Ж {format_decimal(entry.fat)} · "
                f"У {format_decimal(entry.carbs)}\n\n{format_summary(entries)}\n\n"
                f"Добавьте следующую позицию в «{MEAL_LABELS[meal_type]}» "
                "или нажмите «✅ Завершить добавление».",
                reply_markup=diary_menu(adding=True),
            )
            await deliver_calorie_alert(
                callback.message, alert, settings, session_factory
            )
        await callback.answer("Блюдо добавлено")
        return
    await state.set_state(DiaryAdd.weight)
    await state.update_data(food_id=food_id, meal_type=meal_type)
    if callback.message is not None:
        await callback.message.answer(
            f"Выберите порцию для «{food.name}» или введите точный вес в граммах.\n"
            "Меры приблизительные: вес зависит от продукта.",
            reply_markup=diary_portion_keyboard(),
        )
    await callback.answer()


@router.message(DiaryAdd.weight)
async def enter_portion_weight(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker,
    settings: Settings,
) -> None:
    """Calculate and save a selected product portion."""
    weight = parse_portion_input(message.text)
    if weight is None or not Decimal("0.01") <= weight <= Decimal(10000):
        await message.answer(
            "Выберите меру на клавиатуре или введите вес от 0,01 до 10000 г."
        )
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    async with session_factory() as session:
        user = await ensure_user(session, message.from_user)
        food = await load_food(session, user_id=user.id, food_id=data["food_id"])
        if food is None:
            meal_type = data.get("meal_type")
            if meal_type in MEAL_LABELS:
                await continue_diary_addition(state, meal_type)
            else:
                await state.clear()
            await message.answer(
                "Продукт больше недоступен. Выберите другой.",
                reply_markup=diary_menu(adding=meal_type in MEAL_LABELS),
            )
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
    meal_type = data["meal_type"]
    await continue_diary_addition(state, meal_type)
    await message.answer(
        (
            f"Добавлено: {food.name}, 1 порция\n"
            if entry.is_full_serving
            else f"Добавлено: {food.name}, {format_decimal(entry.weight_grams)} г\n"
        )
        f"{format_decimal(entry.calories)} ккал · "
        f"Б {format_decimal(entry.protein)} · Ж {format_decimal(entry.fat)} · "
        f"У {format_decimal(entry.carbs)}\n\n{format_summary(entries)}\n\n"
        f"Добавьте следующий продукт в «{MEAL_LABELS[meal_type]}» "
        "или нажмите «✅ Завершить добавление».",
        reply_markup=diary_menu(adding=True),
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
    if entry.is_full_serving:
        await callback.answer(
            "Готовое блюдо учитывается целиком; вес для него не изменяется.",
            show_alert=True,
        )
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


async def continue_diary_addition(state: FSMContext, meal_type: str) -> None:
    """Return to product input while preserving the selected meal."""
    await state.set_state(DiaryAdd.query)
    await state.set_data({"meal_type": meal_type})


async def ensure_user(session: AsyncSession, telegram_user: TelegramUser) -> User:
    """Resolve the internal user for a Telegram actor."""
    return await get_or_create_user(
        session,
        telegram_id=telegram_user.id,
        username=telegram_user.username,
        first_name=telegram_user.first_name,
    )


async def today_entries(session: AsyncSession, user: User) -> list[FoodEntry]:
    """Load entries for the user's currently active logical day."""
    day = await get_or_create_active_diary_day(session, user=user)
    return await get_entries_for_day(
        session,
        user_id=user.id,
        day=day.logical_date,
        timezone_name=user.timezone,
    )


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
            amount = (
                "1 порция"
                if entry.is_full_serving
                else f"{format_decimal(entry.weight_grams)} г"
            )
            lines.append(
                f"• {entry.food.name} — {amount}, "
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
    day = await get_or_create_active_diary_day(session, user=user)
    return await claim_calorie_alert(
        session,
        user_id=user.id,
        local_date=day.logical_date,
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
