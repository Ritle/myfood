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
        notification_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(notification_settings)"
            ).fetchall()
        }
        food_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(foods)").fetchall()
        }
        diary_day_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(diary_days)").fetchall()
        }
        food_entry_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(food_entries)").fetchall()
        }
        template_item_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(meal_template_items)"
            ).fetchall()
        }

    assert revision == ("0017_nutrition_monitoring",)
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
        "diary_days",
    } <= tables
    assert {
        "movement_reminders_enabled",
        "movement_interval_minutes",
        "nutrition_monitoring_enabled",
        "nutrition_summary_time",
    } <= notification_columns
    assert {"catalog_section", "nutrition_basis"} <= food_columns
    assert {"is_full_serving", "snack_number"} <= food_entry_columns
    assert "is_full_serving" in template_item_columns
    assert {"user_id", "logical_date", "started_at", "ended_at"} <= diary_day_columns
