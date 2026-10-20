"""Engine options per backend (no connection is opened)."""

from sqlalchemy.pool import StaticPool

from app import db


def _capture(monkeypatch) -> dict:
    captured: dict = {}

    def fake_create_engine(url, **kwargs):
        captured.update(url=url, **kwargs)
        return object()

    monkeypatch.setattr(db, "create_engine", fake_create_engine)
    return captured


def test_postgres_engine_fails_fast_and_pings(monkeypatch):
    captured = _capture(monkeypatch)
    db.create_db_engine("postgresql+psycopg://u:p@127.0.0.1:5433/benchtrack")
    assert captured["connect_args"] == {"connect_timeout": db.CONNECT_TIMEOUT_SECONDS}
    assert captured["pool_pre_ping"] is True


def test_sqlite_engine_allows_cross_thread_use(monkeypatch):
    captured = _capture(monkeypatch)
    monkeypatch.setattr(db.event, "listens_for", lambda *_a: lambda fn: fn)
    db.create_db_engine("sqlite://", poolclass=StaticPool)
    assert captured["connect_args"] == {"check_same_thread": False}
    assert "pool_pre_ping" not in captured
