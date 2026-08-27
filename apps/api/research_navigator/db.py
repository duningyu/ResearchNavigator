"""Database engine and session lifecycle."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from research_navigator.models import Base


@dataclass(slots=True)
class Database:
    engine: Engine
    session_factory: sessionmaker[Session]

    @classmethod
    def from_url(cls, url: str, *, echo: bool = False) -> Database:
        kwargs: dict[str, object] = {"future": True, "echo": echo}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
            if url.endswith(":memory:"):
                kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)

        if url.startswith("sqlite"):

            @event.listens_for(engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection: object, _: object) -> None:
                cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()

        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        return cls(engine=engine, session_factory=factory)

    def init(self) -> None:
        Base.metadata.create_all(self.engine)
        if self.engine.dialect.name == "sqlite":
            with self.engine.begin() as connection:
                connection.execute(text("PRAGMA foreign_keys=ON"))
                connection.execute(text("PRAGMA journal_mode=WAL"))
                connection.execute(
                    text(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS paper_chunks_fts "
                        "USING fts5(chunk_id UNINDEXED, document_id UNINDEXED, "
                        "paper_id UNINDEXED, user_id UNINDEXED, section, text, "
                        "tokenize='unicode61')"
                    )
                )

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()
