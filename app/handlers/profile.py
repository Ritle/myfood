from datetime import date
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.keyboards.main_menu import main_menu
from app.keyboards.profile import choices, profile_actions, skip_choice
from app.repositories.users import get_or_create_user
from app.services.nutrition import age_on, calculate_daily_calorie_target
from app.services.profiles import get_profile, persist_profile
from app.states.profile import ProfileSetup

router = Router()
GENDER_LABELS = {"Женщина": "female", "Мужчина": "male"}
ACTIVITY_LABELS = {
    "Минимальная": "minimal",
    "Легкая": "light",
    "Средняя": "moderate",
    "Высокая": "high",
    "Очень высокая": "very_high",
}
GOAL_LABELS = {"Похудение": "lose", "Поддержание веса": "maintain", "Набор веса": "gain"}


async def begin_profile(message: Message, state: FSMContext) -> None:
    """Start the profile questionnaire."""
    await state.clear()
    await state.set_state(ProfileSetup.gender)
    await message.answer(
        "Давайте настроим профиль. Укажите пол:", reply_markup=choices(*GENDER_LABELS)
    )


@router.message(Command("cancel"))
async def cancel_setup(message: Message, state: FSMContext) -> None:
    """Cancel the current questionnaire without persisting partial answers."""
    await state.clear()
    await message.answer(
        "Настройка отменена. Чтобы начать снова, отправьте /profile.",
        reply_markup=main_menu(),
    )


@router.message(Command("profile"))
@router.message(F.text == "👤 Профиль")
async def profile_command(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Show the saved profile or open setup when it is incomplete."""
    if message.from_user is None:
        return
    async with session_factory() as session:
        await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        user = await get_profile(session, message.from_user.id)
    if user is None or user.profile_completed_at is None:
        await begin_profile(message, state)
        return
    await message.answer(
        "Ваш профиль:\n"
        f"Пол: {'мужской' if user.gender == 'male' else 'женский'}\n"
        f"Рост: {user.height_cm} см\n"
        f"Текущий вес: {user.current_weight_kg} кг\n"
        f"Целевой вес: {user.target_weight_kg} кг\n"
        f"Цель: {user.daily_calorie_target} ккал/день\n"
        f"БЖУ: {format_target(user.daily_protein_target_g)} / "
        f"{format_target(user.daily_fat_target_g)} / "
        f"{format_target(user.daily_carbs_target_g)} г\n"
        f"Вода: {format_target(user.daily_water_target_ml)} мл/день",
        reply_markup=profile_actions(),
    )


@router.message(F.text == "✏️ Изменить параметры")
async def edit_profile(message: Message, state: FSMContext) -> None:
    """Restart the profile questionnaire; old values remain until it is completed."""
    await begin_profile(message, state)


@router.message(ProfileSetup.gender)
async def choose_gender(message: Message, state: FSMContext) -> None:
    value = GENDER_LABELS.get(message.text or "")
    if value is None:
        await message.answer("Выберите вариант кнопкой: женщина или мужчина.")
        return
    await state.update_data(gender=value)
    await state.set_state(ProfileSetup.birth_date)
    await message.answer("Введите дату рождения в формате ГГГГ-ММ-ДД:")


@router.message(ProfileSetup.birth_date)
async def enter_birth_date(message: Message, state: FSMContext) -> None:
    try:
        birth_date = date.fromisoformat((message.text or "").strip())
        age = age_on(birth_date, date.today())
        if birth_date >= date.today() or age < 18 or age > 100:
            raise ValueError
    except ValueError:
        await message.answer(
            "Введите дату рождения взрослого пользователя (18–100 лет) в формате ГГГГ-ММ-ДД."
        )
        return
    await state.update_data(birth_date=birth_date.isoformat())
    await state.set_state(ProfileSetup.height)
    await message.answer("Укажите рост в сантиметрах (100–250):", reply_markup=None)


async def ask_weight(message: Message, state: FSMContext) -> None:
    await state.set_state(ProfileSetup.current_weight)
    await message.answer("Укажите текущий вес в килограммах (30–350):")


@router.message(ProfileSetup.height)
async def enter_height(message: Message, state: FSMContext) -> None:
    value = parse_decimal(message.text)
    if value is None or not Decimal("100") <= value <= Decimal("250"):
        await message.answer("Введите рост числом от 100 до 250 см.")
        return
    await state.update_data(height_cm=value)
    await ask_weight(message, state)


@router.message(ProfileSetup.current_weight)
async def enter_current_weight(message: Message, state: FSMContext) -> None:
    value = parse_decimal(message.text)
    if value is None or not Decimal("30") <= value <= Decimal("350"):
        await message.answer("Введите вес числом от 30 до 350 кг.")
        return
    await state.update_data(current_weight_kg=value)
    await state.set_state(ProfileSetup.target_weight)
    await message.answer("Укажите целевой вес в килограммах (30–350):")


@router.message(ProfileSetup.target_weight)
async def enter_target_weight(message: Message, state: FSMContext) -> None:
    value = parse_decimal(message.text)
    if value is None or not Decimal("30") <= value <= Decimal("350"):
        await message.answer("Введите целевой вес числом от 30 до 350 кг.")
        return
    await state.update_data(target_weight_kg=value)
    await state.set_state(ProfileSetup.activity)
    await message.answer(
        "Выберите уровень физической активности:",
        reply_markup=choices(*ACTIVITY_LABELS),
    )


@router.message(ProfileSetup.activity)
async def choose_activity(message: Message, state: FSMContext) -> None:
    value = ACTIVITY_LABELS.get(message.text or "")
    if value is None:
        await message.answer("Выберите уровень активности кнопкой.")
        return
    await state.update_data(activity_level=value)
    await state.set_state(ProfileSetup.goal)
    await message.answer("Выберите цель:", reply_markup=choices(*GOAL_LABELS))


@router.message(ProfileSetup.goal)
async def choose_goal(message: Message, state: FSMContext) -> None:
    value = GOAL_LABELS.get(message.text or "")
    if value is None:
        await message.answer("Выберите цель кнопкой.")
        return
    data = await state.get_data()
    target = calculate_daily_calorie_target(
        gender=data["gender"],
        birth_date=date.fromisoformat(data["birth_date"]),
        height_cm=data["height_cm"],
        weight_kg=data["current_weight_kg"],
        activity_level=data["activity_level"],
        goal=value,
    )
    await state.update_data(goal=value, suggested_calories=target)
    await state.set_state(ProfileSetup.calorie_choice)
    await message.answer(
        f"Расчетная дневная норма: {target} ккал. Использовать ее?",
        reply_markup=choices("Использовать расчет", "Указать вручную"),
    )


@router.message(ProfileSetup.calorie_choice)
async def choose_calories(message: Message, state: FSMContext) -> None:
    if message.text == "Использовать расчет":
        data = await state.get_data()
        await state.update_data(daily_calorie_target=data["suggested_calories"])
        await ask_protein(message, state)
    elif message.text == "Указать вручную":
        await state.set_state(ProfileSetup.manual_calories)
        await message.answer("Введите дневную норму калорий (800–10000):", reply_markup=None)
    else:
        await message.answer("Нажмите «Использовать расчет» или «Указать вручную».")


@router.message(ProfileSetup.manual_calories)
async def enter_calories(message: Message, state: FSMContext) -> None:
    value = parse_integer(message.text)
    if value is None or not 800 <= value <= 10000:
        await message.answer("Введите целое число от 800 до 10000 ккал.")
        return
    await state.update_data(daily_calorie_target=value)
    await ask_protein(message, state)


async def ask_protein(message: Message, state: FSMContext) -> None:
    await state.set_state(ProfileSetup.protein)
    await message.answer(
        "Норма белка в граммах в день? Введите число или нажмите «Пропустить»:",
        reply_markup=skip_choice(),
    )


async def read_optional_target(
    message: Message,
    state: FSMContext,
    *,
    field: str,
    minimum: Decimal,
    maximum: Decimal,
    next_state: type,
    next_prompt: str,
) -> None:
    raw = (message.text or "").strip()
    if raw == "Пропустить":
        await state.update_data(**{field: None})
    else:
        value = parse_decimal(raw)
        if value is None or not minimum <= value <= maximum:
            await message.answer(
                f"Введите число от {minimum} до {maximum} или нажмите «Пропустить»."
            )
            return
        await state.update_data(**{field: value})
    await state.set_state(next_state)
    await message.answer(next_prompt, reply_markup=skip_choice())


@router.message(ProfileSetup.protein)
async def enter_protein(message: Message, state: FSMContext) -> None:
    await read_optional_target(
        message,
        state,
        field="daily_protein_target_g",
        minimum=Decimal("0"),
        maximum=Decimal("500"),
        next_state=ProfileSetup.fat,
        next_prompt="Норма жиров в граммах в день? Введите число или пропустите:",
    )


@router.message(ProfileSetup.fat)
async def enter_fat(message: Message, state: FSMContext) -> None:
    await read_optional_target(
        message,
        state,
        field="daily_fat_target_g",
        minimum=Decimal("0"),
        maximum=Decimal("500"),
        next_state=ProfileSetup.carbs,
        next_prompt="Норма углеводов в граммах в день? Введите число или пропустите:",
    )


@router.message(ProfileSetup.carbs)
async def enter_carbs(message: Message, state: FSMContext) -> None:
    await read_optional_target(
        message,
        state,
        field="daily_carbs_target_g",
        minimum=Decimal("0"),
        maximum=Decimal("1000"),
        next_state=ProfileSetup.water,
        next_prompt="Цель воды в мл в день? Введите число или пропустите:",
    )


@router.message(ProfileSetup.water)
async def enter_water(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    raw = (message.text or "").strip()
    if raw == "Пропустить":
        value = None
    else:
        value = parse_integer(raw)
        if value is None or not 250 <= value <= 10000:
            await message.answer(
                "Введите целое число от 250 до 10000 мл или нажмите «Пропустить»."
            )
            return
    await state.update_data(daily_water_target_ml=value)
    data = await state.get_data()
    if message.from_user is None:
        return
    profile = {
        key: data[key]
        for key in (
            "gender",
            "birth_date",
            "height_cm",
            "current_weight_kg",
            "target_weight_kg",
            "activity_level",
            "goal",
            "daily_calorie_target",
            "daily_protein_target_g",
            "daily_fat_target_g",
            "daily_carbs_target_g",
            "daily_water_target_ml",
        )
    }
    profile["birth_date"] = date.fromisoformat(profile["birth_date"])
    async with session_factory() as session:
        await persist_profile(session, telegram_id=message.from_user.id, profile=profile)
    await state.clear()
    await message.answer(
        f"Профиль сохранен. Ваша дневная норма — {profile['daily_calorie_target']} ккал.\n"
        "Нормы БЖУ и воды сохранены только если вы их указали.",
        reply_markup=main_menu(),
    )


def parse_decimal(raw: str | None) -> Decimal | None:
    """Parse a finite decimal number allowing comma as decimal separator."""
    try:
        value = Decimal((raw or "").strip().replace(",", "."))
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def parse_integer(raw: str | None) -> int | None:
    """Parse an integer value from user input."""
    try:
        return int((raw or "").strip())
    except ValueError:
        return None


def format_target(value: Decimal | int | None) -> str:
    """Format a target while preserving a valid zero value."""
    return str(value) if value is not None else "—"
