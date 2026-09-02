from pathlib import Path

import pytest
from sqlalchemy import text

from research_navigator.db import Database
from research_navigator.models import ResearchProject, User


def test_database_enables_sqlite_integrity_and_persists_models(tmp_path: Path) -> None:
    db_path = tmp_path / "research.db"
    database = Database.from_url(f"sqlite+pysqlite:///{db_path}")
    database.init()

    with database.session() as session:
        user = User(email="student@example.com", password_hash="hash", display_name="Student")
        session.add(user)
        session.flush()
        session.add(ResearchProject(user_id=user.id, name="未来窗口异常预警"))
        session.commit()

    with database.engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
        assert str(journal_mode).lower() == "wal"
        assert connection.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM research_projects")).scalar_one() == 1


def test_local_sqlite_connect_args_keep_timeout_and_thread_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeEngine:
        dialect = type("Dialect", (), {"name": "sqlite"})()

    def fake_create_engine(url: str, **kwargs: object) -> FakeEngine:
        captured.update(kwargs)
        return FakeEngine()

    monkeypatch.setattr(
        "research_navigator.db.event.listens_for",
        lambda *_args, **_kwargs: lambda function: function,
    )
    monkeypatch.setattr("research_navigator.db.create_engine", fake_create_engine)
    Database.from_url("sqlite+pysqlite:///local.db")

    assert captured["connect_args"] == {"check_same_thread": False, "timeout": 30}


def test_turso_libsql_connect_args_only_use_supported_auth_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeEngine:
        dialect = type("Dialect", (), {"name": "turso"})()

    def fake_create_engine(url: str, **kwargs: object) -> FakeEngine:
        captured.update(kwargs)
        return FakeEngine()

    monkeypatch.setenv("TURSO_AUTH_TOKEN", "synthetic-test-token")
    monkeypatch.setattr("research_navigator.db.create_engine", fake_create_engine)
    Database.from_url("sqlite+libsql://example.turso.io?secure=true")

    assert captured["connect_args"] == {"auth_token": "synthetic-test-token"}
    assert "timeout" not in captured["connect_args"]
    assert "check_same_thread" not in captured["connect_args"]


def test_installed_libsql_dialect_loads_without_connecting() -> None:
    pytest.importorskip("sqlalchemy_libsql")
    from sqlalchemy import create_engine

    engine = create_engine("sqlite+libsql://example.turso.io?secure=true")

    assert engine.dialect.driver == "libsql"
    engine.dispose()
