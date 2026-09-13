"""Perform the one-time import of the supplied Health Diet catalog export."""

import asyncio
import os
from pathlib import Path

from app.config import get_settings
from app.data.health_diet import DATA_DIRECTORY, load_health_diet_foods
from app.database import create_database
from app.services.foods import seed_catalog_foods


async def main() -> None:
    """Load the local JSON export into the configured database once."""
    data_directory = Path(os.environ.get("HEALTH_DIET_DATA_DIRECTORY", DATA_DIRECTORY))
    foods = load_health_diet_foods(data_directory)
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
