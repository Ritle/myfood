from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.keyboards.main_menu import main_menu

router = Router()

HELP_TEXT = """MyFood помогает вести питание, воду и вес.

/today — сводка за сегодня
/food — добавить еду
/water — записать воду
/weight — записать вес
/history — история по дням
/catalog — каталог продуктов
/profile — профиль и цели
/settings — напоминания и часовой пояс
/cancel — отменить текущий ввод
/help — эта справка

Данные о калориях и целях носят справочный характер."""


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    """Show the command reference and restore the main keyboard."""
    await message.answer(HELP_TEXT, reply_markup=main_menu())
