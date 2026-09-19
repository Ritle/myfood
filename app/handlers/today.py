from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.keyboards.main_menu import main_menu
from app.repositories.users import get_or_create_user
from app.services.diary import get_entries_for_day, local_today
from app.services.today import format_today
from app.services.water import get_water_for_day, total_water

router = Router()


@router.message(Command("today"))
@router.message(F.text == "📊 Сегодня")
async def show_today(message: Message, session_factory: async_sessionmaker) -> None:
    """Show progress against today's nutrition targets."""
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        day = local_today(user.timezone, day_boundary_time=user.day_boundary_time)
        entries = await get_entries_for_day(
            session,
            user_id=user.id,
            day=day,
            timezone_name=user.timezone,
            day_boundary_time=user.day_boundary_time,
        )
        water_entries = await get_water_for_day(
            session,
            user_id=user.id,
            day=day,
            timezone_name=user.timezone,
            day_boundary_time=user.day_boundary_time,
        )
        text = format_today(user, entries, water_ml=total_water(water_entries))
    await message.answer(text, reply_markup=main_menu())
