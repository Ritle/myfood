"""Create weight history entries.

Revision ID: 0007_create_weight_entries
Revises: 0006_create_water_entries
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_create_weight_entries"
down_revision: str | None = "0006_create_water_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weight_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(6, 2), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "weight_kg >= 30 AND weight_kg <= 350",
            name=op.f("ck_weight_entries_valid_weight"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_weight_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weight_entries")),
    )
    op.create_index(
        "ix_weight_entries_user_measured",
        "weight_entries",
        ["user_id", "measured_at"],
    )
    op.execute(
        sa.text(
            "INSERT INTO weight_entries (user_id, weight_kg, measured_at) "
            "SELECT id, current_weight_kg, CURRENT_TIMESTAMP FROM users "
            "WHERE current_weight_kg IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_weight_entries_user_measured", table_name="weight_entries")
    op.drop_table("weight_entries")
