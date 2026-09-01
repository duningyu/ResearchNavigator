from __future__ import annotations

import pytest

from research_navigator.config import Settings
from research_navigator.data_plane.database import database_dialect


def test_libsql_url_is_classified_as_sqlite_fts_backend() -> None:
    dialect = database_dialect("sqlite+libsql://research-navigator.turso.io")

    assert dialect.name == "turso"
    assert dialect.driver == "libsql"
    assert dialect.supports_sqlite_fts is True
    assert dialect.supports_postgres_text_search is False


def test_turso_mode_builds_remote_libsql_url_without_logging_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_BACKEND", "turso")
    monkeypatch.setenv("TURSO_DATABASE_URL", "https://research-navigator.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "secret-token")

    settings = Settings.from_env()

    assert settings.database_backend == "turso"
    assert settings.database_url == "sqlite+libsql://https://research-navigator.turso.io?secure=true"
    assert settings.turso_auth_token == "secret-token"


def test_turso_mode_requires_auth_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_BACKEND", "turso")
    monkeypatch.setenv("TURSO_DATABASE_URL", "https://research-navigator.turso.io")
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    with pytest.raises(ValueError, match="TURSO_AUTH_TOKEN"):
        Settings.from_env()

