from aiogram.fsm.state import State, StatesGroup


class WeightAdd(StatesGroup):
    value = State()


class WeightEdit(StatesGroup):
    value = State()
