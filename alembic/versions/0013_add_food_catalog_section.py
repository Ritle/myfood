"""Add a dedicated catalog section for dishes.

Revision ID: 0013_add_food_catalog_section
Revises: 0012_add_movement_reminders
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_add_food_catalog_section"
down_revision: str | None = "0012_add_movement_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("foods") as batch_op:
        batch_op.add_column(
            sa.Column("catalog_section", sa.String(length=16), server_default="food", nullable=False)
        )
        batch_op.create_index("ix_foods_catalog_section", ["catalog_section"])


def downgrade() -> None:
    with op.batch_alter_table("foods") as batch_op:
        batch_op.drop_index("ix_foods_catalog_section")
        batch_op.drop_column("catalog_section")
