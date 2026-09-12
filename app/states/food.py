from aiogram.fsm.state import State, StatesGroup


class FoodSearch(StatesGroup):
    query = State()


class FoodCreation(StatesGroup):
    name = State()
    brand = State()
    calories = State()
    protein = State()
    fat = State()
    carbs = State()
