from app.handlers.food import FOOD_MENU_ACTIONS
from app.handlers.water import WATER_MENU_ACTIONS
from app.handlers.weight import WEIGHT_MENU_ACTIONS
from app.keyboards.food import food_menu
from app.keyboards.water import water_menu
from app.keyboards.weight import weight_menu


def keyboard_texts(markup) -> set[str]:
    return {button.text for row in markup.keyboard for button in row}


def test_direct_entry_sections_keep_all_actions_visible() -> None:
    assert FOOD_MENU_ACTIONS <= keyboard_texts(food_menu())
    assert WATER_MENU_ACTIONS <= keyboard_texts(water_menu())
    assert WEIGHT_MENU_ACTIONS <= keyboard_texts(weight_menu())


def test_direct_entry_navigation_actions_are_not_missing() -> None:
    assert {
        "🍽 Блюда",
        "⭐ Избранные",
        "🕘 Недавние",
        "➕ Создать продукт",
        "➕ Создать блюдо",
        "↩️ Главное меню",
    } <= FOOD_MENU_ACTIONS
    assert {
        "+200 мл",
        "+300 мл",
        "+500 мл",
        "Записи воды за сегодня",
        "↩️ Главное меню",
    } <= WATER_MENU_ACTIONS
    assert {
        "История веса",
        "👤 Профиль",
        "↩️ Главное меню",
    } <= WEIGHT_MENU_ACTIONS
