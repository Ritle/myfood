# Источники данных каталога

## USDA FoodData Central

Каталог объединяет два официальных набора [USDA FoodData Central](https://fdc.nal.usda.gov/download-datasets/): Foundation Foods (выпуск April 2026) и FNDDS 2021–2023 (публикация October 2024). Записи Foundation Foods идентифицируются как `source = USDA_FDC`, а записи готовых продуктов и блюд FNDDS — как `source = USDA_FNDDS`. В `source_ref` хранится оригинальный `fdcId`; эти поля сохраняют происхождение и не дают одинаковым идентификаторам из разных наборов конфликтовать.

В каталог включено 159 позиций: 25 продуктов Foundation Foods и 134 позиции FNDDS — фрукты, овощи, приготовленные крупы и макароны, салаты, супы, блюда из птицы и мяса, а также популярные блюда. Русские названия являются переводом или краткой адаптацией описания USDA и указывают способ приготовления и важные ингредиенты, когда это нужно для различения вариантов.

Все значения указаны на 100 г. Для Foundation Foods используется Atwater-specific Energy (nutrient 2048), если показатель присутствует; иначе берется Energy (nutrient 1008). Для FNDDS используется Energy (nutrient 1008). Белки, жиры и углеводы соответствуют nutrient 1003, 1004 и 1005. Позиции FNDDS описывают усредненные варианты продуктов и рецептов: фактические значения блюда могут различаться из-за марки, состава и способа приготовления.

Исходный перечень FNDDS хранится в [scripts/build_fndds_catalog.py](../scripts/build_fndds_catalog.py), а проверенные значения каталога — в [app/data/fndds_foods.py](../app/data/fndds_foods.py). Продукты Foundation Foods находятся в [app/data/base_foods.py](../app/data/base_foods.py). Воспроизвести модуль FNDDS можно из официального JSON-экспорта FNDDS 2021–2023; для этого поместите распакованный `surveyDownload.json` в `.tools/usda/fndds/unpacked/` и выполните `python scripts/build_fndds_catalog.py`.

Оба набора загружаются командой:

```powershell
python -m app.commands.seed_foods
```

Команда выполняет upsert по паре `source/source_ref`: повторный запуск обновляет значения и не создает дубли. Для продукта конкретного бренда пользователь может создать личную карточку по информации с упаковки.
