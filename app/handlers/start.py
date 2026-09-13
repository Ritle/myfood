from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.handlers.profile import begin_profile
from app.keyboards.main_menu import main_menu
from app.repositories.profiles import get_user_by_telegram_id
from app.repositories.users import get_or_create_user

router = Router()
START_OVERVIEW = (
    "MyFood — дневник питания и помощник по привычкам. "
    "Добавляйте продукты быстрым вводом, следите за калориями и КБЖУ, "
    "учитывайте воду и вес, сохраняйте частые приемы пищи в шаблоны."
)


def start_welcome_text(first_name: str, *, profile_completed: bool) -> str:
    """Build the welcome message for a new or returning user."""
    greeting = f"Привет, {first_name}!"
    if profile_completed:
        return (
            f"{greeting}\n\n{START_OVERVIEW}\n\n"
            "Профиль настроен. Выберите действие в меню ниже."
        )
    return (
        f"{greeting}\n\n{START_OVERVIEW}\n\n"
        "Чтобы рассчитать личные цели, сначала настроим профиль."
    )


@router.message(CommandStart())
async def start_handler(
    message: Message, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Create/update the account and route new users into profile setup."""
    if message.from_user is None:
        return

    async with session_factory() as session:
        await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        user = await get_user_by_telegram_id(session, message.from_user.id)

    if user is None or user.profile_completed_at is None:
        await message.answer(
            start_welcome_text(message.from_user.first_name, profile_completed=False)
        )
        await begin_profile(message, state)
        return
    await message.answer(
        start_welcome_text(message.from_user.first_name, profile_completed=True),
        reply_markup=main_menu(),
    )
