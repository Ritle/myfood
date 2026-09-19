from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.keyboards.day import close_day_confirmation
from app.keyboards.main_menu import main_menu
from app.repositories.users import get_or_create_user
from app.services.days import close_diary_day, get_or_create_active_diary_day
from app.services.diary import get_entries_for_day
from app.services.today import format_today
from app.services.water import get_water_for_day, total_water

router = Router()


@router.message(Command("today"))
@router.message(F.text == "📊 Сегодня")
async def show_today(message: Message, session_factory: async_sessionmaker) -> None:
    """Show progress for the user's currently active logical day."""
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        day = await get_or_create_active_diary_day(session, user=user)
        entries = await get_entries_for_day(
            session, user_id=user.id, day=day.logical_date, timezone_name=user.timezone
        )
        water_entries = await get_water_for_day(
            session, user_id=user.id, day=day.logical_date, timezone_name=user.timezone
        )
        text = format_today(user, entries, water_ml=total_water(water_entries))
    await message.answer(text, reply_markup=main_menu())


@router.message(F.text == "🌙 Завершить день")
async def request_close_day(
    message: Message, session_factory: async_sessionmaker
) -> None:
    """Ask for confirmation before manually ending the active diary day."""
    if message.from_user is None:
        return
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        day = await get_or_create_active_diary_day(session, user=user)
        entries = await get_entries_for_day(
            session, user_id=user.id, day=day.logical_date, timezone_name=user.timezone
        )
        water_entries = await get_water_for_day(
            session, user_id=user.id, day=day.logical_date, timezone_name=user.timezone
        )
        summary = format_today(user, entries, water_ml=total_water(water_entries))
        summary = summary.replace("📊 Сегодня", f"📊 День {day.logical_date:%d.%m.%Y}", 1)
    await message.answer(
        summary
        + "\n\n🌙 Завершить этот день? После подтверждения все новые записи "
        "будут относиться к следующему дню.",
        reply_markup=close_day_confirmation(day.id, day.logical_date),
    )


@router.callback_query(F.data == "day:cancel")
async def cancel_close_day(callback: CallbackQuery) -> None:
    """Cancel manual day completion."""
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("День не завершён")


@router.callback_query(F.data.startswith("day:confirm:"))
async def confirm_close_day(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Close exactly the day that the user confirmed and open the next one."""
    try:
        day_id = int((callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректный день", show_alert=True)
        return
    if day_id <= 0:
        await callback.answer("Некорректный день", show_alert=True)
        return

    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        result = await close_diary_day(session, user=user, day_id=day_id)

    if result is None:
        await callback.answer("Этот день уже завершён", show_alert=True)
        return

    closed_day, next_day = result
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"🌙 День {closed_day.logical_date:%d.%m.%Y} завершён.\n"
            f"☀️ Новый день: {next_day.logical_date:%d.%m.%Y}.",
            reply_markup=main_menu(),
        )
    await callback.answer("День завершён")
