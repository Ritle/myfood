from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.food import Food


class MealTemplate(Base):
    """A named, reusable meal recipe owned by one user."""

    __tablename__ = "meal_templates"
    __table_args__ = (
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name="valid_meal_type",
        ),
        UniqueConstraint("user_id", "name_normalized", name="uq_meal_templates_user_name"),
        Index("ix_meal_templates_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(50))
    name_normalized: Mapped[str] = mapped_column(String(150))
    meal_type: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list[MealTemplateItem]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="MealTemplateItem.position",
        lazy="selectin",
    )


class MealTemplateItem(Base):
    """A product and portion included in a reusable meal template."""

    __tablename__ = "meal_template_items"
    __table_args__ = (
        CheckConstraint("weight_grams > 0", name="positive_weight"),
        CheckConstraint("position >= 0", name="nonnegative_position"),
        UniqueConstraint("template_id", "position", name="uq_meal_template_items_position"),
        Index("ix_meal_template_items_food", "food_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("meal_templates.id", ondelete="CASCADE")
    )
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id", ondelete="RESTRICT"))
    weight_grams: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    is_full_serving: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    position: Mapped[int] = mapped_column(Integer)

    template: Mapped[MealTemplate] = relationship(back_populates="items")
    food: Mapped[Food] = relationship(lazy="joined")
