from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.food import Food


class FoodEntry(Base):
    """An immutable nutrient snapshot for one consumed product portion."""

    __tablename__ = "food_entries"
    __table_args__ = (
        CheckConstraint("weight_grams > 0", name="positive_weight"),
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name="valid_meal_type",
        ),
        Index("ix_food_entries_user_eaten", "user_id", "eaten_at"),
        Index("ix_food_entries_user_meal_eaten", "user_id", "meal_type", "eaten_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id", ondelete="RESTRICT"))
    meal_type: Mapped[str] = mapped_column(String(16))
    weight_grams: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    calories: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    protein: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    fat: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    carbs: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    eaten_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    food: Mapped[Food] = relationship(lazy="joined")
