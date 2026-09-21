"""Number snack groups inside one logical day.

Revision ID: 0016_add_snack_numbers
Revises: 0015_full_dish_portions
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_add_snack_numbers"
down_revision: str | None = "0015_full_dish_portions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("food_entries") as batch_op:
        batch_op.add_column(sa.Column("snack_number", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE food_entries SET snack_number = 1 "
        "WHERE meal_type = 'snack' AND snack_number IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("food_entries") as batch_op:
        batch_op.drop_column("snack_number")
