"""Track weight anchors for nutrition target recalculation.

Revision ID: 0018_weight_nutrition_recalc
Revises: 0017_nutrition_monitoring
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_weight_nutrition_recalc"
down_revision: str | None = "0017_nutrition_monitoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("nutrition_target_weight_kg", sa.Numeric(6, 2), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "nutrition_recalc_prompt_weight_kg",
                sa.Numeric(6, 2),
                nullable=True,
            )
        )

    op.execute(
        sa.text(
            "UPDATE users "
            "SET nutrition_target_weight_kg = current_weight_kg, "
            "nutrition_recalc_prompt_weight_kg = current_weight_kg "
            "WHERE current_weight_kg IS NOT NULL"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("nutrition_recalc_prompt_weight_kg")
        batch_op.drop_column("nutrition_target_weight_kg")
