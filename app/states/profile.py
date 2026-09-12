from aiogram.fsm.state import State, StatesGroup


class ProfileSetup(StatesGroup):
    gender = State()
    birth_date = State()
    height = State()
    current_weight = State()
    target_weight = State()
    activity = State()
    goal = State()
    calorie_choice = State()
    manual_calories = State()
    protein = State()
    fat = State()
    carbs = State()
    water = State()

