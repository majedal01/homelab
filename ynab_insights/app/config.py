from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    app_env: Literal["stage", "prod"]
    app_version: str

    # Database. Either set DATABASE_URL directly, or set all four POSTGRES_*
    # components and the URL is assembled with proper password URL-encoding.
    database_url: str = ""
    postgres_host: str = ""
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_db: str = ""
    postgres_port: int = 5432

    ynab_token: str | None = None
    ynab_budget_id: str | None = None

    # Background sync interval. 0 disables the scheduler (useful for tests
    # and for running the app as a one-shot read-only service).
    sync_interval_minutes: int = 30

    # Anthropic agent (Phase 4). API key is required for /ask; without it the
    # endpoint returns 503 but the rest of the app still boots.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-haiku-4-5-20251001"
    ask_max_turns: int = 10

    @model_validator(mode="after")
    def _assemble_database_url(self) -> "Settings":
        if self.database_url:
            return self
        missing = [
            name
            for name, value in [
                ("POSTGRES_HOST", self.postgres_host),
                ("POSTGRES_USER", self.postgres_user),
                ("POSTGRES_PASSWORD", self.postgres_password),
                ("POSTGRES_DB", self.postgres_db),
            ]
            if not value
        ]
        if missing:
            raise ValueError(
                f"Set DATABASE_URL or all of POSTGRES_HOST, POSTGRES_USER, "
                f"POSTGRES_PASSWORD, POSTGRES_DB. Missing: {', '.join(missing)}"
            )
        encoded_password = quote(self.postgres_password, safe="")
        self.database_url = (
            f"postgresql+asyncpg://{self.postgres_user}:{encoded_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
        return self


@lru_cache
def get_settings() -> Settings:
    # pydantic-settings reads required fields from env vars at construction;
    # mypy can't model that and reports them as missing kwargs.
    return Settings()  # type: ignore[call-arg]
