"""Create food diary entries.

Revision ID: 0004_create_food_entries
Revises: 0003_create_foods
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_create_food_entries"
down_revision: str | None = "0003_create_foods"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "food_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("meal_type", sa.String(length=16), nullable=False),
        sa.Column("weight_grams", sa.Numeric(8, 2), nullable=False),
        sa.Column("calories", sa.Numeric(10, 2), nullable=False),
        sa.Column("protein", sa.Numeric(10, 2), nullable=False),
        sa.Column("fat", sa.Numeric(10, 2), nullable=False),
        sa.Column("carbs", sa.Numeric(10, 2), nullable=False),
        sa.Column("eaten_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("weight_grams > 0", name=op.f("ck_food_entries_positive_weight")),
        sa.CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name=op.f("ck_food_entries_valid_meal_type"),
        ),
        sa.ForeignKeyConstraint(
            ["food_id"],
            ["foods.id"],
            name=op.f("fk_food_entries_food_id_foods"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_food_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_entries")),
    )
    op.create_index("ix_food_entries_user_eaten", "food_entries", ["user_id", "eaten_at"])
    op.create_index(
        "ix_food_entries_user_meal_eaten",
        "food_entries",
        ["user_id", "meal_type", "eaten_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_food_entries_user_meal_eaten", table_name="food_entries")
    op.drop_index("ix_food_entries_user_eaten", table_name="food_entries")
    op.drop_table("food_entries")
