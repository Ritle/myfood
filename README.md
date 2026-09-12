# MyFood Telegram-бот

Асинхронный Telegram-бот для дневника питания, калорий, КБЖУ и воды. Реализованы базовый каркас приложения, регистрация через `/start`, профиль с пошаговой анкетой и расчетом рекомендуемой нормы калорий.

## Требования

- Python 3.12+
- Telegram-бот, созданный через [@BotFather](https://t.me/BotFather)

## Локальный запуск

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Укажите токен бота в `.env`, затем примените миграции и запустите polling:

```powershell
alembic upgrade head
python -m app.main
```

Проверки:

```powershell
pytest
ruff check .
```

Параметры окружения описаны в `.env.example`. SQLite-файл по умолчанию создается как `myfood.db` в рабочем каталоге. Не коммитьте `.env` или токен бота.

## Документация

- [План и спецификация реализации](docs/IMPLEMENTATION.md)
