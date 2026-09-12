import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.config import get_settings
from app.database import create_database
from app.handlers.diary import router as diary_router
from app.handlers.food import router as food_router
from app.handlers.profile import router as profile_router
from app.handlers.start import router as start_router


async def main() -> None:
    """Start polling and close application resources on shutdown."""
    settings = get_settings()
    if settings.bot_token is None:
        raise RuntimeError("BOT_TOKEN is required to start the Telegram bot")
    logging.basicConfig(level=settings.log_level.upper())
    bot = Bot(token=settings.bot_token.get_secret_value())
    engine, session_factory = create_database(settings.database_url)
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(profile_router)
    dispatcher.include_router(diary_router)
    dispatcher.include_router(food_router)
    dispatcher["session_factory"] = session_factory
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
