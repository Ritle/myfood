"""Create water intake entries.

Revision ID: 0006_create_water_entries
Revises: 0005_create_notification_logs
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_create_water_entries"
down_revision: str | None = "0005_create_notification_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "water_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount_ml", sa.Integer(), nullable=False),
        sa.Column("drunk_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount_ml > 0 AND amount_ml <= 10000",
            name=op.f("ck_water_entries_valid_amount"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_water_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_water_entries")),
    )
    op.create_index(
        "ix_water_entries_user_drunk", "water_entries", ["user_id", "drunk_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_water_entries_user_drunk", table_name="water_entries")
    op.drop_table("water_entries")
