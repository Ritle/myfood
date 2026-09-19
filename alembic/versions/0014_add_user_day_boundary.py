"""Add a configurable logical day boundary to users.

Revision ID: 0014_add_user_day_boundary
Revises: 0013_add_food_catalog_section
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_add_user_day_boundary"
down_revision: str | None = "0013_add_food_catalog_section"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "day_boundary_time",
                sa.Time(),
                server_default="00:00:00",
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("day_boundary_time")
