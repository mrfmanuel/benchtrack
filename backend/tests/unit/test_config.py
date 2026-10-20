"""Settings from environment (spec §9.18, §9.27)."""

import pytest
from pydantic import ValidationError

from app.config import Settings

VALID_TOKEN = "fictional-test-token-0123456789"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("STAFF_TOKEN", "DATABASE_URL", "LOG_LEVEL", "LOG_FORMAT"):
        monkeypatch.delenv(name, raising=False)


def make(**env: str) -> Settings:
    """Build settings from the given values only (no .env file)."""
    return Settings(_env_file=None, **env)


def test_defaults():
    s = make(staff_token=VALID_TOKEN)
    assert s.staff_token.get_secret_value() == VALID_TOKEN
    assert s.database_url == "sqlite:///./benchtrack.db"
    assert s.log_level == "INFO"
    assert s.log_format == "text"


def test_reads_environment_variables(monkeypatch):
    monkeypatch.setenv("STAFF_TOKEN", VALID_TOKEN)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./other.db")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("LOG_FORMAT", "json")
    s = Settings(_env_file=None)
    assert s.database_url == "sqlite:///./other.db"
    assert s.log_level == "DEBUG"
    assert s.log_format == "json"


def test_missing_staff_token_fails():
    with pytest.raises(ValidationError, match="staff_token"):
        make()


@pytest.mark.parametrize("token", ["", "change-me", "x" * 15, " " * 20, "  short-token   "])
def test_short_or_blank_staff_token_fails(token):
    with pytest.raises(ValidationError, match="at least 16 characters"):
        make(staff_token=token)


def test_rejected_token_is_not_echoed_in_the_error():
    almost_secret = "fifteen-chars-x"
    with pytest.raises(ValidationError) as exc_info:
        make(staff_token=almost_secret)
    assert almost_secret not in str(exc_info.value)


def test_sixteen_char_token_is_accepted():
    assert make(staff_token="x" * 16).staff_token.get_secret_value() == "x" * 16


def test_staff_token_is_not_exposed_in_repr():
    s = make(staff_token=VALID_TOKEN)
    assert VALID_TOKEN not in repr(s)
    assert VALID_TOKEN not in str(s)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "postgres://bench:secret@db:5432/benchtrack",
            "postgresql+psycopg://bench:secret@db:5432/benchtrack",
        ),
        (
            "postgresql://bench:secret@db:5432/benchtrack",
            "postgresql+psycopg://bench:secret@db:5432/benchtrack",
        ),
        (
            "postgresql+psycopg://bench:secret@db:5432/benchtrack",
            "postgresql+psycopg://bench:secret@db:5432/benchtrack",
        ),
        ("sqlite:///./benchtrack.db", "sqlite:///./benchtrack.db"),
        ("sqlite://", "sqlite://"),
    ],
)
def test_database_url_normalization(url, expected):
    assert make(staff_token=VALID_TOKEN, database_url=url).database_url == expected


@pytest.mark.parametrize("level", ["TRACE", "verbose", ""])
def test_invalid_log_level_fails(level):
    with pytest.raises(ValidationError):
        make(staff_token=VALID_TOKEN, log_level=level)


@pytest.mark.parametrize("fmt", ["xml", "JSON-lines", ""])
def test_invalid_log_format_fails(fmt):
    with pytest.raises(ValidationError):
        make(staff_token=VALID_TOKEN, log_format=fmt)


def test_log_format_is_case_insensitive():
    assert make(staff_token=VALID_TOKEN, log_format="JSON").log_format == "json"
