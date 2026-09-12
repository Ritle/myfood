from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WeightEntry(Base):
    """One measurement in a user's weight history."""

    __tablename__ = "weight_entries"
    __table_args__ = (
        CheckConstraint("weight_kg >= 30 AND weight_kg <= 350", name="valid_weight"),
        Index("ix_weight_entries_user_measured", "user_id", "measured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
