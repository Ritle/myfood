from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_database(database_url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Build the async database engine and its session factory."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    if database_url.startswith("sqlite"):
        event.listen(engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Enable SQLite foreign-key enforcement on every new connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
