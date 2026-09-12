from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import NotificationLog
from app.repositories.notifications import (
    get_owned_notification,
    mark_notification_suppressed,
    suppress_pending_meal_notifications,
    try_create_notification,
)
from app.repositories.users import get_or_create_user
from app.services.diary import MEAL_LABELS
from app.services.notifications import meal_skip_key
from app.states.diary import DiaryAdd

router = Router()


@router.callback_query(F.data.startswith("notify:add:"))
async def add_meal_from_reminder(
    callback: CallbackQuery, state: FSMContext, session_factory: async_sessionmaker
) -> None:
    """Open product search for the meal referenced by an owned reminder."""
    parsed = parse_reminder_callback(callback.data)
    if parsed is None:
        await callback.answer("Некорректное напоминание", show_alert=True)
        return
    log_id, meal_type = parsed
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        log = await valid_meal_log(session, user.id, log_id, meal_type)
    if log is None:
        await callback.answer("Напоминание недоступно", show_alert=True)
        return
    await state.set_state(DiaryAdd.query)
    await state.update_data(meal_type=meal_type)
    if callback.message is not None:
        await callback.message.answer(
            f"{MEAL_LABELS[meal_type]}: введите название продукта или бренд.",
            reply_markup=ReplyKeyboardRemove(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("notify:snooze:"))
async def snooze_meal_reminder(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Schedule one deduplicated retry in 30 minutes."""
    parsed = parse_reminder_callback(callback.data)
    if parsed is None:
        await callback.answer("Некорректное напоминание", show_alert=True)
        return
    log_id, meal_type = parsed
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        log = await valid_meal_log(session, user.id, log_id, meal_type)
        if log is None:
            await callback.answer("Напоминание недоступно", show_alert=True)
            return
        retry = await try_create_notification(
            session,
            user_id=user.id,
            notification_type=f"meal_snooze:{meal_type}",
            local_date=log.local_date,
            deduplication_key=f"meal_snooze:{user.id}:{log.id}",
            scheduled_for=datetime.now(UTC) + timedelta(minutes=30),
        )
    await callback.answer(
        "Напомню через 30 минут" if retry is not None else "Уже запланировано",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("notify:skip:"))
async def skip_meal_reminder(
    callback: CallbackQuery, session_factory: async_sessionmaker
) -> None:
    """Persist a skip marker and suppress retries for this meal and date."""
    parsed = parse_reminder_callback(callback.data)
    if parsed is None:
        await callback.answer("Некорректное напоминание", show_alert=True)
        return
    log_id, meal_type = parsed
    async with session_factory() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )
        log = await valid_meal_log(session, user.id, log_id, meal_type)
        if log is None:
            await callback.answer("Напоминание недоступно", show_alert=True)
            return
        marker = await try_create_notification(
            session,
            user_id=user.id,
            notification_type=f"meal_skip:{meal_type}",
            local_date=log.local_date,
            deduplication_key=meal_skip_key(user.id, log.local_date, meal_type),
        )
        if marker is not None:
            await mark_notification_suppressed(session, marker.id)
        await suppress_pending_meal_notifications(
            session, user_id=user.id, local_date=log.local_date, meal_type=meal_type
        )
    await callback.answer("Сегодня больше не напомню", show_alert=True)


async def valid_meal_log(
    session: AsyncSession, user_id: int, log_id: int, meal_type: str
) -> NotificationLog | None:
    """Validate reminder ownership, type, and meal identifier."""
    if meal_type not in MEAL_LABELS:
        return None
    log = await get_owned_notification(session, log_id=log_id, user_id=user_id)
    if log is None or not log.notification_type.startswith(("meal:", "meal_snooze:")):
        return None
    if not log.notification_type.endswith(f":{meal_type}"):
        return None
    return log


def parse_reminder_callback(data: str | None) -> tuple[int, str] | None:
    """Parse a reminder callback containing log ID and meal type."""
    try:
        _, _, raw_log_id, meal_type = (data or "").split(":", 3)
        log_id = int(raw_log_id)
    except ValueError:
        return None
    if log_id <= 0 or meal_type not in MEAL_LABELS:
        return None
    return log_id, meal_type
