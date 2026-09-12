from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WaterEntry(Base):
    """One recorded serving of drinking water."""

    __tablename__ = "water_entries"
    __table_args__ = (
        CheckConstraint("amount_ml > 0 AND amount_ml <= 10000", name="valid_amount"),
        Index("ix_water_entries_user_drunk", "user_id", "drunk_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    amount_ml: Mapped[int] = mapped_column(Integer)
    drunk_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
