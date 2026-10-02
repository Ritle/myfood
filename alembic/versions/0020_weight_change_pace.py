"""Add target weekly weight-change pace.

Revision ID: 0020_weight_change_pace
Revises: 0019_meal_combo_suggestions
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_weight_change_pace"
down_revision: str | None = "0019_meal_combo_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "target_weight_change_kg_per_week",
                sa.Numeric(4, 2),
                nullable=True,
            )
        )

    op.execute(
        sa.text(
            "UPDATE users "
            "SET target_weight_change_kg_per_week = "
            "CASE goal "
            "WHEN 'lose' THEN -0.50 "
            "WHEN 'maintain' THEN 0.00 "
            "WHEN 'gain' THEN 0.25 "
            "ELSE NULL END"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("target_weight_change_kg_per_week")
