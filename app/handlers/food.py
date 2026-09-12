from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.keyboards.food import food_menu, food_results, no_brand
from app.keyboards.main_menu import main_menu
from app.repositories.users import get_or_create_user
from app.services.foods import add_user_food, load_food, search_foods, validate_food_name
from app.states.food import FoodCreation, FoodSearch
from app.utils.formatting import format_decimal
from app.utils.numbers import parse_decimal

router = Router()


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
            foods = await search_foods(session, user_id=user.id, query=message.text or "")
        except ValueError as error:
            await message.answer(str(error))
            return
    await state.clear()
    if not foods:
        await message.answer(
            "Ничего не найдено. Попробуйте другой запрос или создайте продукт.",
            reply_markup=food_menu(),
        )
        return
    await message.answer("Найденные продукты:", reply_markup=food_results(foods))
    await message.answer(
        "Выберите продукт или продолжите работу с каталогом.", reply_markup=food_menu()
    )


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
    if food is None:
        await callback.answer("Продукт недоступен", show_alert=True)
        return
    brand = f"\nБренд: {food.brand}" if food.brand else ""
    source = f"\nИсточник: USDA FoodData Central, FDC {food.source_ref}" if food.source_ref else ""
    if callback.message is not None:
        await callback.message.answer(
            f"{food.name}{brand}\n\nНа 100 г:\n"
            f"{format_decimal(food.calories_per_100g)} ккал\n"
            f"Б: {format_decimal(food.protein_per_100g)} г\n"
            f"Ж: {format_decimal(food.fat_per_100g)} г\n"
            f"У: {format_decimal(food.carbs_per_100g)} г{source}"
        )
    await callback.answer()


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
