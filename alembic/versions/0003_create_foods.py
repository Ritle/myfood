"""Create the food catalog.

Revision ID: 0003_create_foods
Revises: 0002_add_user_profile
Create Date: 2026-09-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_create_foods"
down_revision: str | None = "0002_add_user_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "foods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_normalized", sa.String(length=200), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=True),
        sa.Column("brand_normalized", sa.String(length=120), nullable=True),
        sa.Column("calories_per_100g", sa.Numeric(8, 2), nullable=False),
        sa.Column("protein_per_100g", sa.Numeric(8, 2), nullable=False),
        sa.Column("fat_per_100g", sa.Numeric(8, 2), nullable=False),
        sa.Column("carbs_per_100g", sa.Numeric(8, 2), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("source_ref", sa.String(length=64), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_foods_created_by_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_foods")),
        sa.UniqueConstraint("source", "source_ref", name="uq_foods_source_source_ref"),
    )
    op.create_index(op.f("ix_foods_created_by_user_id"), "foods", ["created_by_user_id"])
    op.create_index(op.f("ix_foods_name_normalized"), "foods", ["name_normalized"])


def downgrade() -> None:
    op.drop_index(op.f("ix_foods_name_normalized"), table_name="foods")
    op.drop_index(op.f("ix_foods_created_by_user_id"), table_name="foods")
    op.drop_table("foods")
