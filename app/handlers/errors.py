import logging

from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

ERROR_MESSAGE = "Не удалось выполнить действие. Попробуйте ещё раз или отправьте /cancel."


async def handle_unexpected_error(event: ErrorEvent) -> bool:
    """Log an unexpected update failure and return a safe user-facing response."""
    user_id = None
    if event.update.message and event.update.message.from_user:
        user_id = event.update.message.from_user.id
    elif event.update.callback_query and event.update.callback_query.from_user:
        user_id = event.update.callback_query.from_user.id

    exception = event.exception
    logger.error(
        "Unhandled update error",
        exc_info=(type(exception), exception, exception.__traceback__),
        extra={"update_id": event.update.update_id, "user_id": user_id},
    )
    try:
        if event.update.callback_query:
            await event.update.callback_query.answer(ERROR_MESSAGE, show_alert=True)
        elif event.update.message:
            await event.update.message.answer(ERROR_MESSAGE)
    except Exception:
        logger.exception(
            "Failed to send error response",
            extra={"update_id": event.update.update_id, "user_id": user_id},
        )
    return True
