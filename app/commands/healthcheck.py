import asyncio

from sqlalchemy import text

from app.config import get_settings
from app.database import create_database


async def check_database() -> None:
    """Fail unless the configured database accepts a trivial query."""
    settings = get_settings()
    engine, _ = create_database(settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(check_database())


if __name__ == "__main__":
    main()
