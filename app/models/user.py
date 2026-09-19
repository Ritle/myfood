from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    """Telegram account and current nutrition profile."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(64), server_default=text("'Europe/Moscow'"))
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    current_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    target_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    activity_level: Mapped[str | None] = mapped_column(String(24), nullable=True)
    goal: Mapped[str | None] = mapped_column(String(24), nullable=True)
    daily_calorie_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_protein_target_g: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    daily_fat_target_g: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    daily_carbs_target_g: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    daily_water_target_ml: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
