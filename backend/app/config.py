"""Application settings from environment variables (spec §5, §9.18, §9.27)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_STAFF_TOKEN_LENGTH = 16
DEFAULT_VERSION = "dev"

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["text", "json"]


def normalize_database_url(url: str) -> str:
    """Hosting platforms often hand out postgres:// URLs; use the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


class DatabaseSettings(BaseSettings):
    """Only what database tooling (Alembic, seed) needs — no STAFF_TOKEN required."""

    # Repo-root .env first, then backend/.env (later files win). Paths are relative to the cwd.
    # hide_input_in_errors: a rejected STAFF_TOKEN must never be echoed into startup logs.
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: str = "sqlite:///./benchtrack.db"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)


class Settings(DatabaseSettings):
    staff_token: SecretStr
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "text"
    # Built SPA to serve (the Docker image sets it). Unset in development: Vite serves it.
    frontend_dist: Path | None = None
    # Reported by /api/health so CD can verify the deployed commit (see `version`).
    app_version: str | None = None
    render_git_commit: str | None = None  # set automatically by Render
    # Header the edge proxy overwrites with the real client IP (Render: CF-Connecting-IP).
    # Unset: the rate limit keys on the TCP peer. Never X-Forwarded-For (client-forgeable).
    client_ip_header: str | None = None

    @field_validator("staff_token", mode="before")
    @classmethod
    def _check_staff_token(cls, value: object) -> object:
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(raw, str):
            raw = raw.strip()
            if len(raw) < MIN_STAFF_TOKEN_LENGTH:
                raise ValueError(
                    f"STAFF_TOKEN must be at least {MIN_STAFF_TOKEN_LENGTH} characters long."
                )
        return raw

    @property
    def version(self) -> str:
        """APP_VERSION, else RENDER_GIT_COMMIT, else "dev" (blank values are skipped)."""
        for candidate in (self.app_version, self.render_git_commit):
            if candidate and candidate.strip():
                return candidate.strip()
        return DEFAULT_VERSION

    @field_validator("client_ip_header", mode="before")
    @classmethod
    def _check_client_ip_header(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip() or None
        if isinstance(value, str) and value.lower() == "x-forwarded-for":
            raise ValueError("CLIENT_IP_HEADER must not be X-Forwarded-For: clients can forge it.")
        return value

    @field_validator("log_level", "log_format", mode="before")
    @classmethod
    def _normalize_case(cls, value: object, info) -> object:
        if isinstance(value, str):
            return value.upper() if info.field_name == "log_level" else value.lower()
        return value


@lru_cache
def get_settings() -> Settings:
    """Load settings once. Called at startup so a bad config fails fast."""
    return Settings()
