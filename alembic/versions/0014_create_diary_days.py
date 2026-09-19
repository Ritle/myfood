"""Create manually bounded logical diary days.

Revision ID: 0014_create_diary_days
Revises: 0013_add_food_catalog_section
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_create_diary_days"
down_revision: str | None = "0013_add_food_catalog_section"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diary_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("logical_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "logical_date", name="uq_diary_days_user_date"),
    )
    op.create_index(
        "ix_diary_days_user_started",
        "diary_days",
        ["user_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_diary_days_user_started", table_name="diary_days")
    op.drop_table("diary_days")
