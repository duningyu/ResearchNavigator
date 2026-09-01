"""Small, explicit database dialect contract used by cloud deployment."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.engine import make_url


@dataclass(frozen=True, slots=True)
class DatabaseDialect:
    name: str
    driver: str
    supports_sqlite_fts: bool
    supports_postgres_text_search: bool


def database_dialect(database_url: str) -> DatabaseDialect:
    """Validate and describe supported URLs without connecting or logging secrets."""
    try:
        parsed = make_url(database_url)
    except Exception as exc:
        raise ValueError("Invalid database URL") from exc
    if parsed.get_backend_name() == "sqlite":
        return DatabaseDialect("sqlite", parsed.get_driver_name(), True, False)
    if parsed.get_backend_name() == "postgresql":
        return DatabaseDialect("postgresql", parsed.get_driver_name(), False, True)
    raise ValueError(f"Unsupported database dialect: {parsed.get_backend_name()!r}")


def redact_database_url(database_url: str) -> str:
    """Return a safe URL for receipts and logs."""
    try:
        parsed = make_url(database_url).set(password="***")
        return parsed.render_as_string(hide_password=True)
    except Exception:
        parts = urlsplit(database_url)
        if parts.username or parts.password:
            host = parts.hostname or ""
            if parts.port:
                host += f":{parts.port}"
            netloc = f"{parts.username or 'user'}:***@{host}"
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
        return "<invalid-database-url>"
