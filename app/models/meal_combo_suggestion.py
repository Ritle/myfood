from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MealComboSuggestion(Base):
    """One durable automatic template suggestion for a recurring meal combo."""

    __tablename__ = "meal_combo_suggestions"
    __table_args__ = (
        CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')",
            name="valid_meal_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'saved', 'dismissed')",
            name="valid_status",
        ),
        UniqueConstraint(
            "user_id",
            "signature",
            name="uq_meal_combo_suggestions_user_signature",
        ),
        Index(
            "ix_meal_combo_suggestions_user_created",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    signature: Mapped[str] = mapped_column(String(220))
    meal_type: Mapped[str] = mapped_column(String(16))
    source_day: Mapped[date] = mapped_column(Date)
    snack_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
