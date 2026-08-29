from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    blog_base_url: str = "https://j2gblog.tistory.com"
    blog_account_label: str = "money.ybrief"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    notion_api_key: str = ""
    notion_sns_database_id: str = ""
    threads_user_id: str = ""
    threads_access_token: str = ""
    timezone: str = Field("Asia/Seoul", alias="TZ")
    default_slots: Annotated[tuple[str, ...], NoDecode] = ("08:30", "18:30")
    sync_lookback_hours: int = 48
    request_timeout_seconds: float = 20.0
    prompt_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "prompts"
    )

    @field_validator("blog_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("default_slots", mode="before")
    @classmethod
    def parse_slots(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return tuple(value)  # type: ignore[arg-type]

    @field_validator("default_slots")
    @classmethod
    def validate_slots(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for slot in value:
            hour, minute = slot.split(":", maxsplit=1)
            if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
                raise ValueError(f"invalid publishing slot: {slot}")
        if not value:
            raise ValueError("at least one publishing slot is required")
        return tuple(sorted(set(value)))

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def missing_for(self, command: str) -> list[str]:
        required = {
            "sync": {
                "OPENAI_API_KEY": self.openai_api_key,
                "NOTION_API_KEY": self.notion_api_key,
                "NOTION_SNS_DATABASE_ID": self.notion_sns_database_id,
            },
            "publish": {
                "NOTION_API_KEY": self.notion_api_key,
                "NOTION_SNS_DATABASE_ID": self.notion_sns_database_id,
                "THREADS_USER_ID": self.threads_user_id,
                "THREADS_ACCESS_TOKEN": self.threads_access_token,
            },
            "sync-dry-run": {
                "NOTION_API_KEY": self.notion_api_key,
                "NOTION_SNS_DATABASE_ID": self.notion_sns_database_id,
            },
            "publish-dry-run": {
                "NOTION_API_KEY": self.notion_api_key,
                "NOTION_SNS_DATABASE_ID": self.notion_sns_database_id,
            },
        }
        return [name for name, value in required.get(command, {}).items() if not value]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
