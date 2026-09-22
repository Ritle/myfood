"""Add nutrition monitoring preferences.

Revision ID: 0017_nutrition_monitoring
Revises: 0016_add_snack_numbers
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_nutrition_monitoring"
down_revision: str | None = "0016_add_snack_numbers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notification_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "nutrition_monitoring_enabled",
                sa.Boolean(),
                server_default=sa.true(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "nutrition_summary_time",
                sa.Time(),
                server_default="16:00:00",
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("notification_settings") as batch_op:
        batch_op.drop_column("nutrition_summary_time")
        batch_op.drop_column("nutrition_monitoring_enabled")
