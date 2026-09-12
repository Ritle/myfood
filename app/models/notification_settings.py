from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Time,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationSettings(Base):
    """Per-user schedule and notification preferences."""

    __tablename__ = "notification_settings"
    __table_args__ = (
        CheckConstraint(
            "water_interval_minutes >= 30 AND water_interval_minutes <= 720",
            name="valid_water_interval",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    meal_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    breakfast_time: Mapped[time] = mapped_column(Time, default=time(9), server_default="09:00:00")
    lunch_time: Mapped[time] = mapped_column(Time, default=time(14), server_default="14:00:00")
    dinner_time: Mapped[time] = mapped_column(Time, default=time(20), server_default="20:00:00")
    water_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    water_interval_minutes: Mapped[int] = mapped_column(
        Integer, default=120, server_default="120"
    )
    water_start_time: Mapped[time] = mapped_column(
        Time, default=time(9), server_default="09:00:00"
    )
    water_end_time: Mapped[time] = mapped_column(
        Time, default=time(21), server_default="21:00:00"
    )
    morning_report_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    morning_report_time: Mapped[time] = mapped_column(
        Time, default=time(8), server_default="08:00:00"
    )
    quiet_start_time: Mapped[time] = mapped_column(
        Time, default=time(22), server_default="22:00:00"
    )
    quiet_end_time: Mapped[time] = mapped_column(
        Time, default=time(8), server_default="08:00:00"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
