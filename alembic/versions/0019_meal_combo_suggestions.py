"""Add recurring meal combo suggestions.

Revision ID: 0019_meal_combo_suggestions
Revises: 0018_weight_nutrition_recalc
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_meal_combo_suggestions"
down_revision: str | None = "0018_weight_nutrition_recalc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meal_combo_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("signature", sa.String(length=220), nullable=False),
        sa.Column("meal_type", sa.String(length=16), nullable=False),
        sa.Column("source_day", sa.Date(), nullable=False),
        sa.Column("snack_number", sa.Integer(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name="valid_meal_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'saved', 'dismissed')",
            name="valid_status",
        ),
        sa.UniqueConstraint(
            "user_id",
            "signature",
            name="uq_meal_combo_suggestions_user_signature",
        ),
    )
    op.create_index(
        "ix_meal_combo_suggestions_user_created",
        "meal_combo_suggestions",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_meal_combo_suggestions_user_created",
        table_name="meal_combo_suggestions",
    )
    op.drop_table("meal_combo_suggestions")
