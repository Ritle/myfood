"""Add configurable movement reminders."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_add_movement_reminders"
down_revision: str | None = "0011_create_meal_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notification_settings") as batch_op:
        batch_op.add_column(
            sa.Column(
                "movement_reminders_enabled",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "movement_interval_minutes",
                sa.Integer(),
                server_default="60",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "valid_movement_interval",
            "movement_interval_minutes >= 30 AND movement_interval_minutes <= 240",
        )


def downgrade() -> None:
    with op.batch_alter_table("notification_settings") as batch_op:
        batch_op.drop_constraint("valid_movement_interval", type_="check")
        batch_op.drop_column("movement_interval_minutes")
        batch_op.drop_column("movement_reminders_enabled")
