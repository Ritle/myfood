import asyncio

from app.config import get_settings
from app.database import create_database
from app.services.foods import seed_base_foods


async def main() -> None:
    """Load packaged catalog products into the configured database."""
    settings = get_settings()
    engine, session_factory = create_database(settings.database_url)
    try:
        async with session_factory() as session:
            created, updated = await seed_base_foods(session)
        print(f"Base catalog loaded: {created} created, {updated} updated")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
