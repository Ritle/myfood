from aiogram.fsm.state import State, StatesGroup


class WaterAdd(StatesGroup):
    amount = State()


class WaterEdit(StatesGroup):
    amount = State()
