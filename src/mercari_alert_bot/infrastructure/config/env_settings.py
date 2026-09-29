from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

KeywordRuleSourceKind = Literal["sqlite", "yaml"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", frozen=True
    )

    telegram_bot_token: SecretStr = Field(min_length=1)
    telegram_chat_id: SecretStr = Field(min_length=1)

    database_path: Path = Path("data/mercari_alert_bot.sqlite3")
    keyword_seed_path: Path = Path("config/keywords.yaml")
    keyword_rule_source: KeywordRuleSourceKind = "sqlite"

    web_host: str = "127.0.0.1"
    web_port: int = Field(default=8080, ge=1, le=65535)
    log_level: LogLevel = "INFO"

    polling_gap_seconds: int = Field(default=60, ge=1)
    search_page_size: int = Field(default=30, ge=1, le=120)
    is_item_detail_fetch_enabled: bool = True
    max_images_per_alert: int = Field(default=4, ge=1, le=10)
    consecutive_failure_alert_threshold: int = Field(default=3, ge=1)
    system_alert_cooldown_seconds: int = Field(default=1800, ge=0)
