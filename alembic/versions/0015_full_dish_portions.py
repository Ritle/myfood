"""Support full-serving dishes.

Revision ID: 0015_full_dish_portions
Revises: 0014_create_diary_days
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_full_dish_portions"
down_revision: str | None = "0014_create_diary_days"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("foods") as batch_op:
        batch_op.add_column(
            sa.Column(
                "nutrition_basis",
                sa.String(length=16),
                server_default="per_100g",
                nullable=False,
            )
        )
        batch_op.create_index("ix_foods_nutrition_basis", ["nutrition_basis"])
    with op.batch_alter_table("food_entries") as batch_op:
        batch_op.add_column(
            sa.Column("is_full_serving", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
    with op.batch_alter_table("meal_template_items") as batch_op:
        batch_op.add_column(
            sa.Column("is_full_serving", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("meal_template_items") as batch_op:
        batch_op.drop_column("is_full_serving")
    with op.batch_alter_table("food_entries") as batch_op:
        batch_op.drop_column("is_full_serving")
    with op.batch_alter_table("foods") as batch_op:
        batch_op.drop_index("ix_foods_nutrition_basis")
        batch_op.drop_column("nutrition_basis")
