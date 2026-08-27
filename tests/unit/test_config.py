from pathlib import Path

from research_navigator.config import Settings


def test_settings_from_environment_and_create_directories(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RN_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("RN_DATABASE_URL", "sqlite+pysqlite:///custom.db")
    monkeypatch.setenv("RN_ENABLE_FIXTURE_SOURCE", "false")
    monkeypatch.setenv("RN_ALLOWED_ORIGINS", "http://localhost:5173,http://10.0.0.5:5173")

    settings = Settings.from_env()
    settings.ensure_directories()

    assert settings.database_url == "sqlite+pysqlite:///custom.db"
    assert settings.enable_fixture_source is False
    assert settings.allowed_origins == (
        "http://localhost:5173",
        "http://10.0.0.5:5173",
    )
    assert settings.data_dir.exists()
    assert settings.upload_dir.exists()
    assert settings.vector_dir.exists()
    assert settings.backup_dir.exists()
