from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_admin_page_exposes_safe_historical_abstract_backfill() -> None:
    source = (ROOT / "apps" / "web" / "src" / "pages" / "AdminPage.tsx").read_text(
        encoding="utf-8"
    )
    assert "/admin/backfills/abstract-provenance" in source
    assert "/run" in source
    assert "/cancel" in source
    assert "dry_run" in source
    assert "历史摘要" in source
    assert "不会直接把旧摘要标记为可信" in source
    assert "verified_and_updated" in source
