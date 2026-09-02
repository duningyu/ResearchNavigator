from __future__ import annotations

from pathlib import Path


def test_offline_composition_uses_provider_doubles(tmp_path: Path) -> None:
    from deployment.cloud.parity.offline_provider_doubles import (  # noqa: PLC0415
        OfflineR2Storage,
        build_offline_database,
        build_offline_storage,
    )

    database = build_offline_database(tmp_path / "provider")
    storage = build_offline_storage(tmp_path / "provider")

    assert database.engine.url.database is not None
    assert isinstance(storage, OfflineR2Storage)
