from pathlib import Path

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
