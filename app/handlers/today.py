from datetime import UTC, date, datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.keyboards.day import close_day_confirmation
from app.keyboards.main_menu import main_menu
from app.keyboards.today import (
    report_macro_details,
    today_food_recommendations,
    today_menu,
)
from app.repositories.users import get_or_create_user
from app.services.days import close_diary_day, get_or_create_active_diary_day
from app.services.diary import get_entries_for_day
from app.services.food_guidance import (
    format_food_recommendations,
    recommend_foods_for_today,
    remaining_targets,
)
from app.services.today import format_macro_sources, format_today, macro_target
from app.services.water import get_water_for_day, total_water

router = Router()

MACRO_DETAIL_TEXTS = {
    "🔥 Ккал подробнее": "calories",
    "🥩 Белки подробнее": "protein",
    "🥑 Жиры подробнее": "fat",
    "🍞 Углеводы подробнее": "carbs",
}


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
    await message.answer(text, reply_markup=today_menu())


@router.message(F.text.in_(set(MACRO_DETAIL_TEXTS)))
async def show_today_macro_sources(
    message: Message,
    session_factory: async_sessionmaker,
) -> None:
    """Show where today's selected macro came from."""
    if message.from_user is None:
        return
    macro = MACRO_DETAIL_TEXTS[message.text or ""]
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        day = await get_or_create_active_diary_day(session, user=user)
        entries = await get_entries_for_day(
            session,
            user_id=user.id,
            day=day.logical_date,
            timezone_name=user.timezone,
        )
        text = format_macro_sources(
            entries,
            macro=macro,
            target=macro_target(user, macro),
            day_label=day.logical_date.strftime("%d.%m.%Y"),
        )
    await message.answer(text, reply_markup=today_menu())


@router.callback_query(F.data.startswith("today:macro:"))
async def show_report_macro_sources(
    callback: CallbackQuery,
    session_factory: async_sessionmaker,
) -> None:
    """Show macro sources for the exact day encoded in a report button."""
    parsed = parse_macro_detail_callback(callback.data)
    if parsed is None:
        await callback.answer("Некорректная детализация", show_alert=True)
        return
    macro, report_day = parsed
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        entries = await get_entries_for_day(
            session,
            user_id=user.id,
            day=report_day,
            timezone_name=user.timezone,
        )
        text = format_macro_sources(
            entries,
            macro=macro,
            target=None,
            day_label=report_day.strftime("%d.%m.%Y"),
        )
    if callback.message is not None:
        await callback.message.answer(
            text,
            reply_markup=report_macro_details(report_day),
        )
    await callback.answer()


@router.message(F.text == "🍽 Что можно съесть?")
async def suggest_food_for_today(
    message: Message, session_factory: async_sessionmaker
) -> None:
    """Suggest catalog foods that best match the user's current remaining KBJU."""
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
            session,
            user_id=user.id,
            day=day.logical_date,
            timezone_name=user.timezone,
        )
        if not remaining_targets(user, entries):
            await message.answer(
                "Чтобы подбирать еду под остаток КБЖУ, сначала задайте цели в профиле.",
                reply_markup=today_menu(),
            )
            return
        current = datetime.now(UTC)
        recommendations = await recommend_foods_for_today(
            session,
            user=user,
            entries=entries,
            now=current,
        )
        text = format_food_recommendations(
            user,
            entries,
            recommendations,
            now=current,
        )
    await message.answer(
        text,
        reply_markup=(
            today_food_recommendations(recommendations)
            if recommendations
            else None
        ),
    )


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



def parse_macro_detail_callback(
    data: str | None,
) -> tuple[str, date] | None:
    """Decode a macro key and report date from an inline callback."""
    parts = (data or "").split(":")
    if len(parts) != 4 or parts[:2] != ["today", "macro"]:
        return None
    macro = parts[2]
    if macro not in {"calories", "protein", "fat", "carbs"}:
        return None
    try:
        report_day = date.fromisoformat(parts[3])
    except ValueError:
        return None
    return macro, report_day
