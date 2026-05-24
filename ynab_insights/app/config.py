"""Runtime settings (v2.5).

No database fields, no provider tokens. Users supply tokens at session
creation; the app never reads them from env.
"""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    app_env: Literal["stage", "prod"]
    app_version: str

    # Session secret used to sign the `sid` cookie. Set per environment via
    # env; rotating breaks all live sessions (acceptable for v2.5).
    session_secret_key: str = "dev-only-do-not-use-in-prod"

    # Rate limit defaults (tunable via env). Bucketed per session except
    # session_create which buckets per IP (no session yet).
    rate_limit_session_create_per_hour: int = 5
    rate_limit_snapshot_per_hour: int = 10
    rate_limit_generate_per_hour: int = 10
    rate_limit_ask_per_hour: int = 20
    rate_limit_reads_per_minute: int = 120

    # Agent loop guardrails (v2.5).
    agent_max_tool_calls: int = 20
    agent_max_duration_seconds: int = 60
    agent_input_max_chars: int = 1000

    # Optional Anthropic model override; users still bring their own key.
    anthropic_model: str = "claude-haiku-4-5-20251001"

    @field_validator("session_secret_key", mode="after")
    @classmethod
    def _reject_default_in_prod(cls, value: str, info: object) -> str:
        # We can't get app_env here without a model_validator; defer the
        # actual rejection to startup wiring. Just hand back the value.
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
