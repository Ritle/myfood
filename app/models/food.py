from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Food(Base):
    """A public or user-owned catalog item with per-100g or full-serving nutrients."""

    __tablename__ = "foods"
    __table_args__ = (UniqueConstraint("source", "source_ref", name="uq_foods_source_source_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    name_normalized: Mapped[str] = mapped_column(String(200), index=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    brand_normalized: Mapped[str | None] = mapped_column(String(120), nullable=True)
    calories_per_100g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    protein_per_100g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    fat_per_100g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    carbs_per_100g: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    catalog_section: Mapped[str] = mapped_column(
        String(16), default="food", server_default="food", index=True
    )
    nutrition_basis: Mapped[str] = mapped_column(
        String(16), default="per_100g", server_default="per_100g", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
