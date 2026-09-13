"""Create reusable meal templates."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_create_meal_templates"
down_revision: str | None = "0010_create_favorite_foods"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meal_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("name_normalized", sa.String(length=150), nullable=False),
        sa.Column("meal_type", sa.String(length=16), nullable=False),
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
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name=op.f("ck_meal_templates_valid_meal_type"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_meal_templates_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_templates")),
        sa.UniqueConstraint(
            "user_id", "name_normalized", name="uq_meal_templates_user_name"
        ),
    )
    op.create_index(
        "ix_meal_templates_user_created", "meal_templates", ["user_id", "created_at"]
    )
    op.create_table(
        "meal_template_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.Column("weight_grams", sa.Numeric(8, 2), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("weight_grams > 0", name=op.f("ck_meal_template_items_positive_weight")),
        sa.CheckConstraint("position >= 0", name=op.f("ck_meal_template_items_nonnegative_position")),
        sa.ForeignKeyConstraint(
            ["food_id"],
            ["foods.id"],
            name=op.f("fk_meal_template_items_food_id_foods"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["meal_templates.id"],
            name=op.f("fk_meal_template_items_template_id_meal_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_template_items")),
        sa.UniqueConstraint(
            "template_id", "position", name="uq_meal_template_items_position"
        ),
    )
    op.create_index("ix_meal_template_items_food", "meal_template_items", ["food_id"])


def downgrade() -> None:
    op.drop_index("ix_meal_template_items_food", table_name="meal_template_items")
    op.drop_table("meal_template_items")
    op.drop_index("ix_meal_templates_user_created", table_name="meal_templates")
    op.drop_table("meal_templates")
