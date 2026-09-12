from aiogram.fsm.state import State, StatesGroup


class NotificationSettingsEdit(StatesGroup):
    value = State()
