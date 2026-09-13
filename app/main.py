import asyncio
import logging
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import Settings, get_settings
from app.database import create_database
from app.handlers.diary import router as diary_router
from app.handlers.errors import handle_unexpected_error
from app.handlers.food import router as food_router
from app.handlers.help import router as help_router
from app.handlers.history import router as history_router
from app.handlers.notifications import router as notifications_router
from app.handlers.profile import router as profile_router
from app.handlers.settings import router as settings_router
from app.handlers.start import router as start_router
from app.handlers.today import router as today_router
from app.handlers.water import router as water_router
from app.handlers.weight import router as weight_router
from app.logging_config import configure_logging
from app.services.notifications import run_notification_cycle

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="today", description="Сводка за сегодня"),
    BotCommand(command="food", description="Добавить еду"),
    BotCommand(command="water", description="Записать воду"),
    BotCommand(command="weight", description="Записать вес"),
    BotCommand(command="history", description="История по дням"),
    BotCommand(command="catalog", description="Каталог продуктов"),
    BotCommand(command="profile", description="Профиль и цели"),
    BotCommand(command="settings", description="Настройки и напоминания"),
    BotCommand(command="help", description="Справка"),
    BotCommand(command="cancel", description="Отменить текущий ввод"),
]
BOT_SHORT_DESCRIPTION = (
    "Дневник питания, КБЖУ, воды и веса. Быстрый ввод и шаблоны привычных блюд."
)
BOT_DESCRIPTION = (
    "MyFood помогает вести дневник питания, воды и веса. Записывайте продукты, "
    "следите за калориями и КБЖУ, сохраняйте привычные приемы пищи в шаблоны, "
    "отслеживайте прогресс и получайте напоминания. Цели и расчеты носят справочный характер."
)


def build_dispatcher(session_factory, settings: Settings) -> Dispatcher:
    """Create the dispatcher and register all update and error handlers."""
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(help_router)
    dispatcher.include_router(profile_router)
    dispatcher.include_router(settings_router)
    dispatcher.include_router(notifications_router)
    dispatcher.include_router(history_router)
    dispatcher.include_router(today_router)
    dispatcher.include_router(water_router)
    dispatcher.include_router(weight_router)
    dispatcher.include_router(diary_router)
    dispatcher.include_router(food_router)
    dispatcher.errors.register(handle_unexpected_error)
    dispatcher["session_factory"] = session_factory
    dispatcher["settings"] = settings
    return dispatcher


def build_scheduler(bot: Bot, session_factory, settings: Settings) -> AsyncIOScheduler:
    """Create the notification scheduler without starting it."""
    scheduler = AsyncIOScheduler(timezone=UTC)
    scheduler.add_job(
        run_notification_cycle,
        "interval",
        seconds=settings.notification_poll_seconds,
        kwargs={"bot": bot, "session_factory": session_factory},
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )
    return scheduler


async def configure_bot(bot: Bot) -> None:
    """Publish the command menu displayed by Telegram clients."""
    await bot.set_my_commands(BOT_COMMANDS)
    await bot.set_my_short_description(short_description=BOT_SHORT_DESCRIPTION)
    await bot.set_my_description(description=BOT_DESCRIPTION)


async def main() -> None:
    """Start polling and close application resources on shutdown."""
    settings = get_settings()
    if settings.bot_token is None:
        raise RuntimeError("BOT_TOKEN is required to start the Telegram bot")
    configure_logging(settings.log_level, settings.log_format)
    bot = Bot(token=settings.bot_token.get_secret_value())
    engine, session_factory = create_database(settings.database_url)
    dispatcher = build_dispatcher(session_factory, settings)
    scheduler = build_scheduler(bot, session_factory, settings)
    try:
        await configure_bot(bot)
        scheduler.start()
        logger.info("Bot polling started")
        await dispatcher.start_polling(bot)
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await bot.session.close()
        await engine.dispose()
        logger.info("Bot shutdown completed")


if __name__ == "__main__":
    asyncio.run(main())
