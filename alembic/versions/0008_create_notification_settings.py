"""Create per-user notification settings.

Revision ID: 0008_create_notification_settings
Revises: 0007_create_weight_entries
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_create_notification_settings"
down_revision: str | None = "0007_create_weight_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("meal_reminders_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("breakfast_time", sa.Time(), server_default="09:00:00", nullable=False),
        sa.Column("lunch_time", sa.Time(), server_default="14:00:00", nullable=False),
        sa.Column("dinner_time", sa.Time(), server_default="20:00:00", nullable=False),
        sa.Column("water_reminders_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("water_interval_minutes", sa.Integer(), server_default="120", nullable=False),
        sa.Column("water_start_time", sa.Time(), server_default="09:00:00", nullable=False),
        sa.Column("water_end_time", sa.Time(), server_default="21:00:00", nullable=False),
        sa.Column("morning_report_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("morning_report_time", sa.Time(), server_default="08:00:00", nullable=False),
        sa.Column("quiet_start_time", sa.Time(), server_default="22:00:00", nullable=False),
        sa.Column("quiet_end_time", sa.Time(), server_default="08:00:00", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "water_interval_minutes >= 30 AND water_interval_minutes <= 720",
            name=op.f("ck_notification_settings_valid_water_interval"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notification_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_settings")),
        sa.UniqueConstraint("user_id", name=op.f("uq_notification_settings_user_id")),
    )
    op.execute(
        sa.text(
            "INSERT INTO notification_settings (user_id) "
            "SELECT id FROM users"
        )
    )


def downgrade() -> None:
    op.drop_table("notification_settings")
