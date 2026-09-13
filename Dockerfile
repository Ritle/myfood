FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system myfood \
    && adduser --system --ingroup myfood myfood \
    && mkdir -p /data \
    && chown myfood:myfood /data

COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN python -m pip install --no-cache-dir .

USER myfood

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "app.commands.healthcheck"]

CMD ["sh", "/app/docker-entrypoint.sh"]
