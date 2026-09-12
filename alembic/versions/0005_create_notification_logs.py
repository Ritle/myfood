"""Create notification deduplication log.

Revision ID: 0005_create_notification_logs
Revises: 0004_create_food_entries
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_create_notification_logs"
down_revision: str | None = "0004_create_food_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(length=48), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("deduplication_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_logs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_logs")),
        sa.UniqueConstraint(
            "deduplication_key", name=op.f("uq_notification_logs_deduplication_key")
        ),
    )
    op.create_index(
        "ix_notification_logs_user_scheduled",
        "notification_logs",
        ["user_id", "scheduled_for"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_logs_user_scheduled", table_name="notification_logs")
    op.drop_table("notification_logs")
