from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings loaded from environment or .env."""

    bot_token: SecretStr | None = None
    database_url: str = "sqlite+aiosqlite:///./myfood.db"
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"
    calorie_warning_ratio: Decimal = Field(default=Decimal("0.80"), gt=0, lt=1)
    notification_poll_seconds: int = Field(default=60, ge=10, le=3600)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return cached process settings."""
    return Settings()
