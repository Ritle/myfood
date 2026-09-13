# Эксплуатация MyFood

## Конфигурация

Создайте `.env` из `.env.example` и задайте `BOT_TOKEN`. Остальные параметры имеют безопасные значения по умолчанию:

- `DATABASE_URL` — URL базы SQLAlchemy;
- `LOG_LEVEL` — уровень логов;
- `LOG_FORMAT` — `json` для машинной обработки или `text` для локального запуска;
- `CALORIE_WARNING_RATIO` — доля дневной нормы для раннего предупреждения;
- `NOTIFICATION_POLL_SECONDS` — период фоновой проверки уведомлений.

Токен хранится только в `.env` или секретах среды. Приложение не выводит настройки и токен в лог.

## Запуск через Docker Compose

```bash
cp .env.example .env
# задайте BOT_TOKEN в .env
docker compose up -d --build
docker compose logs -f bot
```

Контейнер перед каждым запуском применяет Alembic-миграции и идемпотентно загружает базовый каталог. SQLite хранится в именованном томе `myfood-data`. Healthcheck проверяет подключение к базе каждые 30 секунд.

### Одноразовый импорт Health Diet

После обновления кода выполните импорт один раз. Команда подключает исходную папку только к временному контейнеру; в образ бота она не попадает.

```bash
docker compose stop bot
docker compose run --rm --no-deps \
  -v "$PWD/health_diet_data:/import/health_diet_data:ro" \
  -e HEALTH_DIET_DATA_DIRECTORY=/import/health_diet_data \
  bot python -m app.commands.import_health_diet
docker compose start bot
```

В результате команда выведет количество созданных и обновлённых позиций. Повторный запуск безопасен, но не нужен для обычной работы бота.

Остановка с корректным завершением планировщика и polling:

```bash
docker compose down
```

## Обновление

Перед обновлением создайте резервную копию. Затем получите новую версию кода и пересоберите контейнер:

```bash
docker compose down
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --tail=100 bot
```

Миграции применяются автоматически. Откат к старому образу после миграции следует выполнять только вместе с совместимой копией базы.

## Резервное копирование SQLite

Для согласованной копии используйте встроенную команду SQLite внутри работающего контейнера либо остановите контейнер перед копированием тома. Простой перенос файла во время записи может дать поврежденную копию.

Вариант с остановкой:

```bash
docker compose stop bot
docker run --rm -v myfood_myfood-data:/source -v "$PWD/backups:/backup" alpine \
  cp /source/myfood.db /backup/myfood-$(date +%F-%H%M%S).db
docker compose start bot
```

Имя тома зависит от имени Compose-проекта; уточнить его можно командой `docker volume ls`.

Для восстановления остановите бот, сохраните текущую базу отдельно, замените `/data/myfood.db` проверенной копией и снова запустите контейнер. После запуска проверьте `docker compose ps` и логи.

## Диагностика

```bash
docker compose ps
docker compose logs --tail=200 bot
docker compose exec bot python -m app.commands.healthcheck
docker compose exec bot alembic current
```

Нормальное состояние миграций: `0010_create_favorite_foods (head)`. Логи в формате JSON содержат время, уровень, имя логгера и контекст ошибки. Для необработанной Telegram-ошибки записываются `update_id` и `user_id` без содержимого токена.

SQLite подходит для одного экземпляра бота. Для нескольких реплик или заметного роста нагрузки следует перевести `DATABASE_URL` на PostgreSQL и проверить миграции на нем до переключения.
