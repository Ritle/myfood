import asyncio
import json
import logging

import pytest
from apscheduler.schedulers.base import STATE_PAUSED, STATE_STOPPED

from app.config import Settings
from app.handlers.help import HELP_TEXT
from app.handlers.start import start_welcome_text
from app.logging_config import JsonFormatter
from app.main import (
    BOT_COMMANDS,
    BOT_DESCRIPTION,
    BOT_SHORT_DESCRIPTION,
    build_dispatcher,
    build_scheduler,
    configure_bot,
)


class FakeBot:
    def __init__(self) -> None:
        self.commands = None
        self.description = None
        self.short_description = None

    async def set_my_commands(self, commands) -> None:
        self.commands = commands

    async def set_my_description(self, *, description: str) -> bool:
        self.description = description
        return True

    async def set_my_short_description(self, *, short_description: str) -> bool:
        self.short_description = short_description
        return True


def test_json_formatter_emits_searchable_context() -> None:
    record = logging.LogRecord(
        name="myfood.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="failed",
        args=(),
        exc_info=None,
    )
    record.update_id = 42
    record.user_id = 77

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "ERROR"
    assert payload["message"] == "failed"
    assert payload["update_id"] == 42
    assert payload["user_id"] == 77


@pytest.mark.asyncio
async def test_bot_commands_and_scheduler_lifecycle() -> None:
    bot = FakeBot()
    settings = Settings(notification_poll_seconds=60)
    dispatcher = build_dispatcher(object(), settings)
    scheduler = build_scheduler(bot, object(), settings)

    await configure_bot(bot)
    assert bot.commands == BOT_COMMANDS
    assert bot.description == BOT_DESCRIPTION
    assert bot.short_description == BOT_SHORT_DESCRIPTION
    assert len(BOT_DESCRIPTION) <= 512
    assert len(BOT_SHORT_DESCRIPTION) <= 120
    assert "/today" in HELP_TEXT
    assert "Мои шаблоны" in HELP_TEXT
    assert dispatcher["settings"] is settings
    assert scheduler.state == STATE_STOPPED

    scheduler.start(paused=True)
    assert scheduler.state == STATE_PAUSED
    scheduler.shutdown(wait=False)
    await asyncio.sleep(0)
    assert scheduler.state == STATE_STOPPED


def test_start_welcome_explains_features_and_next_action() -> None:
    new_user = start_welcome_text("Анна", profile_completed=False)
    returning_user = start_welcome_text("Анна", profile_completed=True)

    assert "Привет, Анна!" in new_user
    assert "шаблоны" in new_user
    assert "настроим профиль" in new_user
    assert "Профиль настроен" in returning_user
    assert "меню ниже" in returning_user
