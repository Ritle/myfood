from aiogram.fsm.state import State, StatesGroup


class DiaryAdd(StatesGroup):
    query = State()
    weight = State()
    batch_confirm = State()


class DiaryEdit(StatesGroup):
    weight = State()
