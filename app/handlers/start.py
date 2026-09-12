from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.keyboards.main_menu import main_menu
from app.handlers.profile import begin_profile
from app.repositories.profiles import get_user_by_telegram_id
from app.repositories.users import get_or_create_user

router = Router()


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
            f"Привет, {message.from_user.first_name}! Давайте настроим ваш профиль."
        )
        await begin_profile(message, state)
        return
    await message.answer(
        f"Привет, {message.from_user.first_name}! Я помогу вести дневник питания и воды.\n"
        "Ваш профиль уже настроен.",
        reply_markup=main_menu(),
    )
