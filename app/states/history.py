from aiogram.fsm.state import State, StatesGroup


class HistorySelect(StatesGroup):
    date = State()
