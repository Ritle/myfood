from datetime import UTC, date, datetime
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.keyboards.main_menu import main_menu
from app.keyboards.profile import choices, profile_actions, skip_choice
from app.repositories.users import get_or_create_user
from app.services.nutrition import (
    age_on,
    calculate_daily_calorie_target,
    calculate_daily_macronutrient_targets,
)
from app.services.profiles import get_profile, persist_profile
from app.states.profile import ProfileSetup
from app.utils.dates import parse_birth_date
from app.utils.numbers import parse_decimal, parse_integer

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
KEEP_CALCULATED = "Оставить расчет"

MACRO_STEPS = {
    "daily_protein_target_g": (ProfileSetup.protein, "белка", Decimal(0), Decimal(500)),
    "daily_fat_target_g": (ProfileSetup.fat, "жиров", Decimal(0), Decimal(500)),
    "daily_carbs_target_g": (ProfileSetup.carbs, "углеводов", Decimal(0), Decimal(1000)),
}


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
        "Текущий ввод отменен. Чтобы настроить профиль, отправьте /profile.",
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
    await message.answer(
        "Введите дату рождения, например 25.04.1990. "
        "Также подойдут 25/04/1990, 25-04-1990 или 1990-04-25."
    )


@router.message(ProfileSetup.birth_date)
async def enter_birth_date(message: Message, state: FSMContext) -> None:
    birth_date = parse_birth_date(message.text)
    today = datetime.now(UTC).date()
    if birth_date is None or birth_date >= today or not 18 <= age_on(birth_date, today) <= 100:
        await message.answer(
            "Введите действительную дату рождения взрослого пользователя (18–100 лет), "
            "например 25.04.1990. Поддерживаются ДД.ММ.ГГГГ, ДД/ММ/ГГГГ, "
            "ДД-ММ-ГГГГ и ГГГГ-ММ-ДД."
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
    if value is None or not Decimal(100) <= value <= Decimal(250):
        await message.answer("Введите рост числом от 100 до 250 см.")
        return
    await state.update_data(height_cm=value)
    await ask_weight(message, state)


@router.message(ProfileSetup.current_weight)
async def enter_current_weight(message: Message, state: FSMContext) -> None:
    value = parse_decimal(message.text)
    if value is None or not Decimal(30) <= value <= Decimal(350):
        await message.answer("Введите вес числом от 30 до 350 кг.")
        return
    await state.update_data(current_weight_kg=value)
    await state.set_state(ProfileSetup.target_weight)
    await message.answer("Укажите целевой вес в килограммах (30–350):")


@router.message(ProfileSetup.target_weight)
async def enter_target_weight(message: Message, state: FSMContext) -> None:
    value = parse_decimal(message.text)
    if value is None or not Decimal(30) <= value <= Decimal(350):
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
    protein, fat, carbs = calculate_daily_macronutrient_targets(target)
    await state.update_data(
        goal=value,
        suggested_calories=target,
        suggested_daily_protein_target_g=protein,
        suggested_daily_fat_target_g=fat,
        suggested_daily_carbs_target_g=carbs,
    )
    await state.set_state(ProfileSetup.nutrition_choice)
    await message.answer(
        f"Расчетные нормы на день:\n"
        f"Калории: {target} ккал\n"
        f"Белки: {protein} г\n"
        f"Жиры: {fat} г\n"
        f"Углеводы: {carbs} г\n\n"
        "Можно оставить расчет или скорректировать значения. "
        "Расчет КБЖУ использует распределение энергии 25% / 30% / 45% "
        "и служит ориентиром.",
        reply_markup=choices(KEEP_CALCULATED, "Скорректировать"),
    )


@router.message(ProfileSetup.nutrition_choice)
async def choose_nutrition_targets(message: Message, state: FSMContext) -> None:
    if message.text == KEEP_CALCULATED:
        data = await state.get_data()
        await state.update_data(
            daily_calorie_target=data["suggested_calories"],
            daily_protein_target_g=Decimal(data["suggested_daily_protein_target_g"]),
            daily_fat_target_g=Decimal(data["suggested_daily_fat_target_g"]),
            daily_carbs_target_g=Decimal(data["suggested_daily_carbs_target_g"]),
        )
        await ask_water(message, state)
    elif message.text == "Скорректировать":
        await ask_calories(message, state)
    else:
        await message.answer(f"Нажмите «{KEEP_CALCULATED}» или «Скорректировать».")


async def ask_calories(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(ProfileSetup.manual_calories)
    await message.answer(
        f"Расчетная норма: {data['suggested_calories']} ккал. "
        f"Введите новое значение или нажмите «{KEEP_CALCULATED}».",
        reply_markup=choices(KEEP_CALCULATED),
    )


@router.message(ProfileSetup.manual_calories)
async def enter_calories(message: Message, state: FSMContext) -> None:
    if (message.text or "").strip() == KEEP_CALCULATED:
        data = await state.get_data()
        value = data["suggested_calories"]
    else:
        value = parse_integer(message.text)
        if value is None or not 800 <= value <= 10000:
            await message.answer("Введите целое число от 800 до 10000 ккал или оставьте расчет.")
            return
    protein, fat, carbs = calculate_daily_macronutrient_targets(value)
    await state.update_data(
        daily_calorie_target=value,
        suggested_daily_protein_target_g=protein,
        suggested_daily_fat_target_g=fat,
        suggested_daily_carbs_target_g=carbs,
    )
    await ask_macro(message, state, "daily_protein_target_g")


async def ask_macro(message: Message, state: FSMContext, field: str) -> None:
    next_state, label, _, _ = MACRO_STEPS[field]
    data = await state.get_data()
    suggestion = data[f"suggested_{field}"]
    await state.set_state(next_state)
    await message.answer(
        f"Расчетная норма {label}: {suggestion} г в день. "
        f"Введите другое значение или нажмите «{KEEP_CALCULATED}».",
        reply_markup=choices(KEEP_CALCULATED),
    )


async def ask_water(message: Message, state: FSMContext) -> None:
    await state.set_state(ProfileSetup.water)
    await message.answer(
        "Цель воды в мл в день? Введите число или нажмите «Пропустить»:",
        reply_markup=skip_choice(),
    )


async def read_macro_target(
    message: Message,
    state: FSMContext,
    *,
    field: str,
    next_field: str | None,
) -> None:
    raw = (message.text or "").strip()
    _, label, minimum, maximum = MACRO_STEPS[field]
    if raw == KEEP_CALCULATED:
        data = await state.get_data()
        value = Decimal(data[f"suggested_{field}"])
    else:
        value = parse_decimal(raw)
        if value is None or not minimum <= value <= maximum:
            await message.answer(
                f"Введите норму {label} числом от {minimum} до {maximum} г "
                f"или нажмите «{KEEP_CALCULATED}»."
            )
            return
    await state.update_data(**{field: value})
    if next_field is None:
        await ask_water(message, state)
    else:
        await ask_macro(message, state, next_field)


@router.message(ProfileSetup.protein)
async def enter_protein(message: Message, state: FSMContext) -> None:
    await read_macro_target(
        message, state, field="daily_protein_target_g", next_field="daily_fat_target_g"
    )


@router.message(ProfileSetup.fat)
async def enter_fat(message: Message, state: FSMContext) -> None:
    await read_macro_target(
        message, state, field="daily_fat_target_g", next_field="daily_carbs_target_g"
    )


@router.message(ProfileSetup.carbs)
async def enter_carbs(message: Message, state: FSMContext) -> None:
    await read_macro_target(message, state, field="daily_carbs_target_g", next_field=None)


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
            await message.answer("Введите целое число от 250 до 10000 мл или нажмите «Пропустить».")
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
        "Расчетные нормы БЖУ сохранены; цель воды — только если вы ее указали.",
        reply_markup=main_menu(),
    )


def format_target(value: Decimal | int | None) -> str:
    """Format a target while preserving a valid zero value."""
    return str(value) if value is not None else "—"
