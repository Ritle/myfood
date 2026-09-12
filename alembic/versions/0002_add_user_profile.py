"""Add profile attributes and nutrition targets to users.

Revision ID: 0002_add_user_profile
Revises: 0001_create_users
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_add_user_profile"
down_revision: Union[str, None] = "0001_create_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'Europe/Moscow'"),
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("gender", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("height_cm", sa.Numeric(5, 2), nullable=True))
    op.add_column("users", sa.Column("current_weight_kg", sa.Numeric(6, 2), nullable=True))
    op.add_column("users", sa.Column("target_weight_kg", sa.Numeric(6, 2), nullable=True))
    op.add_column("users", sa.Column("activity_level", sa.String(length=24), nullable=True))
    op.add_column("users", sa.Column("goal", sa.String(length=24), nullable=True))
    op.add_column("users", sa.Column("daily_calorie_target", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("daily_protein_target_g", sa.Numeric(7, 2), nullable=True))
    op.add_column("users", sa.Column("daily_fat_target_g", sa.Numeric(7, 2), nullable=True))
    op.add_column("users", sa.Column("daily_carbs_target_g", sa.Numeric(7, 2), nullable=True))
    op.add_column("users", sa.Column("daily_water_target_ml", sa.Integer(), nullable=True))
    op.add_column(
        "users", sa.Column("profile_completed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "profile_completed_at")
    op.drop_column("users", "daily_water_target_ml")
    op.drop_column("users", "daily_carbs_target_g")
    op.drop_column("users", "daily_fat_target_g")
    op.drop_column("users", "daily_protein_target_g")
    op.drop_column("users", "daily_calorie_target")
    op.drop_column("users", "goal")
    op.drop_column("users", "activity_level")
    op.drop_column("users", "target_weight_kg")
    op.drop_column("users", "current_weight_kg")
    op.drop_column("users", "height_cm")
    op.drop_column("users", "birth_date")
    op.drop_column("users", "gender")
    op.drop_column("users", "timezone")
