import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_all_migrations_apply_to_empty_database(tmp_path: Path) -> None:
    database_path = tmp_path / "migration-test.db"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = f"sqlite+aiosqlite:///{database_path.as_posix()}"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert revision == ("0011_create_meal_templates",)
    assert {
        "users",
        "foods",
        "food_entries",
        "water_entries",
        "weight_entries",
        "notification_settings",
        "notification_logs",
        "favorite_foods",
        "meal_templates",
        "meal_template_items",
    } <= tables
