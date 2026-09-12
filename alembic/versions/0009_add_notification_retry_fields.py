"""Add bounded notification retry state.

Revision ID: 0009_add_notification_retry_fields
Revises: 0008_create_notification_settings
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_add_notification_retry_fields"
down_revision: str | None = "0008_create_notification_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_logs",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "notification_logs",
        sa.Column("last_error", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_logs", "last_error")
    op.drop_column("notification_logs", "attempt_count")
