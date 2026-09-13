from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.keyboards.food import (
    food_card_actions,
    food_edit_cancel,
    food_edit_fields,
    food_menu,
    food_results,
    no_brand,
)
from app.keyboards.main_menu import main_menu
from app.models import Food
from app.repositories.users import get_or_create_user
from app.services.foods import (
    add_user_food,
    favorite_foods,
    food_is_favorite,
    load_food,
    recent_foods,
    search_foods_page,
    toggle_food_favorite,
    update_user_food,
    validate_food_name,
)
from app.states.food import FoodCreation, FoodEdit, FoodSearch
from app.utils.formatting import format_decimal
from app.utils.numbers import parse_decimal

router = Router()

EDITABLE_FOOD_FIELDS = {"name", "brand", "calories", "protein", "fat", "carbs"}
NUTRIENT_EDIT_FIELDS = {
    "calories": (Decimal(1000), "калории на 100 г", "calories_per_100g"),
    "protein": (Decimal(100), "белки на 100 г", "protein_per_100g"),
    "fat": (Decimal(100), "жиры на 100 г", "fat_per_100g"),
    "carbs": (Decimal(100), "углеводы на 100 г", "carbs_per_100g"),
}


def food_card_text(food) -> str:
    """Format a product card with its per-100-gram nutrition."""
    brand = f"\nБренд: {food.brand}" if food.brand else ""
    source_name = {
        "USDA_FDC": "USDA FoodData Central Foundation Foods",
        "USDA_FNDDS": "USDA FoodData Central Survey Foods",
    }.get(food.source or "", "USDA FoodData Central")
    source = f"\nИсточник: {source_name}, FDC {food.source_ref}" if food.source_ref else ""
    return (
        f"{food.name}{brand}\n\nНа 100 г:\n"
        f"{format_decimal(food.calories_per_100g)} ккал\n"
        f"Б: {format_decimal(food.protein_per_100g)} г\n"
        f"Ж: {format_decimal(food.fat_per_100g)} г\n"
        f"У: {format_decimal(food.carbs_per_100g)} г{source}"
    )


async def answer_food_card(
    message: Message, *, food: Food, user_id: int, favorite: bool
) -> None:
    """Send a product card and expose editing only to its private owner."""
    editable = food.created_by_user_id == user_id and not food.is_public
    await message.answer(
        food_card_text(food),
        reply_markup=food_card_actions(food.id, favorite=favorite, editable=editable),
    )


@router.message(Command("catalog"))
@router.message(F.text == "📚 Каталог продуктов")
async def open_food_menu(message: Message, state: FSMContext) -> None:
    """Open the product catalog menu."""
    await state.clear()
    await message.answer("Каталог продуктов:", reply_markup=food_menu())


@router.message(F.text == "↩️ Главное меню")
async def return_to_main_menu(message: Message, state: FSMContext) -> None:
    """Return to top-level navigation."""
    await state.clear()
    await message.answer("Главное меню", reply_markup=main_menu())


@router.message(F.text == "📚 Найти продукт")
async def begin_food_search(message: Message, state: FSMContext) -> None:
    """Prompt for a catalog query."""
    await state.set_state(FoodSearch.query)
    await message.answer("Введите название продукта или бренд:", reply_markup=ReplyKeyboardRemove())


@router.message(FoodSearch.query)
async def search_food_catalog(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Search visible products and render selectable results."""
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        try:
            page = await search_foods_page(
                session, user_id=user.id, query=message.text or "", page=0
            )
        except ValueError as error:
            await message.answer(str(error))
            return
    if not page.items:
        await state.clear()
        await message.answer(
            "Ничего не найдено. Попробуйте другой запрос или создайте продукт.",
            reply_markup=food_menu(),
        )
        return
    await state.set_state(FoodSearch.results)
    await state.update_data(food_query=message.text or "")
    await message.answer(
        "Найденные продукты:",
        reply_markup=food_results(
            page.items, page=page.page, total_pages=page.total_pages
        ),
    )
    await message.answer(
        "Выберите продукт или продолжите работу с каталогом.", reply_markup=food_menu()
    )


@router.callback_query(F.data.startswith("food:page:"))
async def paginate_food_search(
    callback: CallbackQuery, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Move through catalog search result pages."""
    try:
        requested_page = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректная страница", show_alert=True)
        return
    data = await state.get_data()
    query = data.get("food_query")
    if callback.message is None or not isinstance(query, str):
        await callback.answer("Поиск устарел. Запустите его снова.", show_alert=True)
        return
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        page = await search_foods_page(
            session, user_id=user.id, query=query, page=requested_page
        )
    await callback.message.edit_reply_markup(
        reply_markup=food_results(
            page.items, page=page.page, total_pages=page.total_pages
        )
    )
    await callback.answer()


@router.callback_query(F.data == "food:noop")
async def ignore_food_page_counter(callback: CallbackQuery) -> None:
    """Acknowledge the inert page counter button."""
    await callback.answer()


@router.message(F.text.in_({"⭐ Избранные", "🕘 Недавние"}))
async def show_saved_foods(message: Message, session_factory: async_sessionmaker) -> None:
    """Show favorite or recently used products in the catalog."""
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        if message.text == "⭐ Избранные":
            foods = await favorite_foods(session, user_id=user.id)
            title = "Избранные продукты:"
        else:
            foods = await recent_foods(session, user_id=user.id)
            title = "Недавние продукты:"
    if not foods:
        empty = "В избранном пока ничего нет." if message.text == "⭐ Избранные" else "Недавних продуктов пока нет."
        await message.answer(empty, reply_markup=food_menu())
        return
    await message.answer(title, reply_markup=food_results(foods[:10]))


@router.callback_query(F.data.startswith("food:view:"))
async def show_food_card(callback: CallbackQuery, session_factory: async_sessionmaker) -> None:
    """Show a product card after checking visibility for the requesting user."""
    if callback.from_user is None or callback.data is None:
        return
    try:
        food_id = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await callback.answer("Некорректный продукт", show_alert=True)
        return
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        food = await load_food(session, user_id=user.id, food_id=food_id)
        favorite = (
            await food_is_favorite(session, user_id=user.id, food_id=food_id)
            if food is not None
            else False
        )
    if food is None:
        await callback.answer("Продукт недоступен", show_alert=True)
        return
    if callback.message is not None:
        await answer_food_card(
            callback.message,
            food=food,
            user_id=callback.from_user.id,
            favorite=favorite,
        )
    await callback.answer()


@router.callback_query(F.data.startswith("food:favorite:"))
async def toggle_favorite(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Toggle a product bookmark after checking visibility."""
    try:
        food_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректный продукт", show_alert=True)
        return
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        favorite = await toggle_food_favorite(
            session, user_id=user.id, food_id=food_id
        )
        food = (
            await load_food(session, user_id=user.id, food_id=food_id)
            if favorite is not None
            else None
        )
    if favorite is None:
        await callback.answer("Продукт недоступен", show_alert=True)
        return
    if callback.message is not None:
        await callback.message.edit_reply_markup(
            reply_markup=food_card_actions(
                food_id,
                favorite=favorite,
                editable=(
                    food is not None
                    and food.created_by_user_id == user.id
                    and not food.is_public
                ),
            )
        )
    await callback.answer(
        "Добавлено в избранное" if favorite else "Удалено из избранного"
    )


@router.callback_query(F.data.startswith("food:edit:"))
async def begin_food_edit(
    callback: CallbackQuery, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Open field selection for a private product owned by the user."""
    try:
        food_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректный продукт", show_alert=True)
        return
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        food = await load_food(session, user_id=user.id, food_id=food_id)
    if food is None or food.created_by_user_id != user.id or food.is_public:
        await callback.answer("Можно изменять только свои продукты", show_alert=True)
        return
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            "Выберите, что изменить:", reply_markup=food_edit_fields(food.id)
        )
    await callback.answer()


@router.callback_query(F.data.startswith("food:editfield:"))
async def begin_food_field_edit(
    callback: CallbackQuery, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Ask for a replacement value for one owned product field."""
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or parts[3] not in EDITABLE_FOOD_FIELDS:
        await callback.answer("Некорректное поле продукта", show_alert=True)
        return
    try:
        food_id = int(parts[2])
    except ValueError:
        await callback.answer("Некорректный продукт", show_alert=True)
        return
    field = parts[3]
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        food = await load_food(session, user_id=user.id, food_id=food_id)
    if food is None or food.created_by_user_id != user.id or food.is_public:
        await callback.answer("Можно изменять только свои продукты", show_alert=True)
        return

    labels = {
        "name": "название",
        "brand": "бренд",
        **{key: value[1] for key, value in NUTRIENT_EDIT_FIELDS.items()},
    }
    current = {
        "name": food.name,
        "brand": food.brand or "не указан",
        **{
            key: format_decimal(getattr(food, attribute))
            for key, (_, _, attribute) in NUTRIENT_EDIT_FIELDS.items()
        },
    }[field]
    if field == "brand":
        instruction = "Введите новый бренд или «Без бренда», чтобы очистить поле."
    elif field in NUTRIENT_EDIT_FIELDS:
        maximum = NUTRIENT_EDIT_FIELDS[field][0]
        instruction = f"Введите число от 0 до {format_decimal(maximum)}."
    else:
        instruction = "Введите новое название."

    await state.set_state(FoodEdit.value)
    await state.update_data(food_id=food.id, field=field)
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"Текущее значение ({labels[field]}): {current}.\n{instruction}\n"
            "Для отмены нажмите кнопку ниже.",
            reply_markup=food_edit_cancel(food.id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("food:editcancel:"))
async def cancel_food_field_edit(
    callback: CallbackQuery, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Cancel a pending field edit and return to the product card."""
    try:
        food_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректный продукт", show_alert=True)
        return
    await state.clear()
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        food = await load_food(session, user_id=user.id, food_id=food_id)
        favorite = (
            await food_is_favorite(session, user_id=user.id, food_id=food_id)
            if food is not None
            else False
        )
    if food is None or food.created_by_user_id != user.id or food.is_public:
        await callback.answer("Продукт недоступен", show_alert=True)
        return
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Изменение отменено.", reply_markup=food_menu())
        await answer_food_card(
            callback.message, food=food, user_id=user.id, favorite=favorite
        )
    await callback.answer()


@router.message(FoodEdit.value)
async def save_food_field_edit(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Validate and save one changed field on the user's private product."""
    data = await state.get_data()
    field = data.get("field")
    food_id = data.get("food_id")
    if field not in EDITABLE_FOOD_FIELDS or not isinstance(food_id, int):
        await state.clear()
        await message.answer("Сеанс редактирования завершился. Откройте продукт ещё раз.")
        return

    raw = (message.text or "").strip()
    try:
        if field == "name":
            value: str | Decimal | None = validate_food_name(raw)
        elif field == "brand":
            value = (
                None
                if raw.casefold() in {"без бренда", "/clear"}
                else validate_food_name(raw, field="Бренд", maximum_length=120)
            )
        else:
            maximum = NUTRIENT_EDIT_FIELDS[field][0]
            parsed = parse_decimal(raw)
            if parsed is None or not Decimal(0) <= parsed <= maximum:
                await message.answer(
                    f"Введите число от 0 до {format_decimal(maximum)}.",
                    reply_markup=food_edit_cancel(food_id),
                )
                return
            value = parsed
    except ValueError as error:
        await message.answer(str(error), reply_markup=food_edit_cancel(food_id))
        return

    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        food = await update_user_food(
            session,
            user_id=user.id,
            food_id=food_id,
            field=field,
            value=value,
        )
        favorite = (
            await food_is_favorite(session, user_id=user.id, food_id=food_id)
            if food is not None
            else False
        )
    await state.clear()
    if food is None:
        await message.answer("Продукт недоступен или принадлежит другому пользователю.")
        return
    await message.answer("Изменения сохранены.", reply_markup=food_menu())
    await answer_food_card(message, food=food, user_id=user.id, favorite=favorite)


@router.message(F.text == "➕ Создать продукт")
async def begin_food_creation(message: Message, state: FSMContext) -> None:
    """Start collecting a private product."""
    await state.set_state(FoodCreation.name)
    await message.answer("Введите название продукта:", reply_markup=ReplyKeyboardRemove())


@router.message(FoodCreation.name)
async def enter_food_name(message: Message, state: FSMContext) -> None:
    try:
        name = validate_food_name(message.text or "")
    except ValueError as error:
        await message.answer(str(error))
        return
    await state.update_data(name=name)
    await state.set_state(FoodCreation.brand)
    await message.answer("Введите бренд или выберите «Без бренда»:", reply_markup=no_brand())


@router.message(FoodCreation.brand)
async def enter_food_brand(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == "Без бренда":
        brand = None
    else:
        try:
            brand = validate_food_name(raw, field="Бренд", maximum_length=120)
        except ValueError as error:
            await message.answer(str(error))
            return
    await state.update_data(brand=brand)
    await state.set_state(FoodCreation.calories)
    await message.answer("Введите калории на 100 г (0–1000):", reply_markup=ReplyKeyboardRemove())


async def collect_nutrient(
    message: Message,
    state: FSMContext,
    *,
    field: str,
    maximum: Decimal,
    next_state: object,
    prompt: str,
) -> None:
    value = parse_decimal(message.text)
    if value is None or not Decimal(0) <= value <= maximum:
        await message.answer(f"Введите число от 0 до {maximum}.")
        return
    await state.update_data(**{field: value})
    await state.set_state(next_state)
    await message.answer(prompt)


@router.message(FoodCreation.calories)
async def enter_food_calories(message: Message, state: FSMContext) -> None:
    await collect_nutrient(
        message,
        state,
        field="calories",
        maximum=Decimal(1000),
        next_state=FoodCreation.protein,
        prompt="Введите белки на 100 г (0–100):",
    )


@router.message(FoodCreation.protein)
async def enter_food_protein(message: Message, state: FSMContext) -> None:
    await collect_nutrient(
        message,
        state,
        field="protein",
        maximum=Decimal(100),
        next_state=FoodCreation.fat,
        prompt="Введите жиры на 100 г (0–100):",
    )


@router.message(FoodCreation.fat)
async def enter_food_fat(message: Message, state: FSMContext) -> None:
    await collect_nutrient(
        message,
        state,
        field="fat",
        maximum=Decimal(100),
        next_state=FoodCreation.carbs,
        prompt="Введите углеводы на 100 г (0–100):",
    )


@router.message(FoodCreation.carbs)
async def enter_food_carbs(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    carbs = parse_decimal(message.text)
    if carbs is None or not Decimal(0) <= carbs <= Decimal(100):
        await message.answer("Введите число от 0 до 100.")
        return
    if message.from_user is None:
        return
    data = await state.get_data()
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        product = await add_user_food(
            session,
            user_id=user.id,
            name=data["name"],
            brand=data["brand"],
            calories=data["calories"],
            protein=data["protein"],
            fat=data["fat"],
            carbs=carbs,
        )
    await state.clear()
    await message.answer(
        f"Продукт «{product.name}» сохранен в вашем каталоге.",
        reply_markup=food_menu(),
    )
