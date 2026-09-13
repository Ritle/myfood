"""Perform the one-time import of the supplied Health Diet catalog export."""

import asyncio

from app.config import get_settings
from app.data.health_diet import load_health_diet_foods
from app.database import create_database
from app.services.foods import seed_catalog_foods


async def main() -> None:
    """Load the local JSON export into the configured database once."""
    foods = load_health_diet_foods()
    settings = get_settings()
    engine, session_factory = create_database(settings.database_url)
    try:
        async with session_factory() as session:
            created, updated = await seed_catalog_foods(session, foods)
        print(f"Health Diet catalog imported: {created} created, {updated} updated")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
