from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_paper_page_uses_user_facing_translation_labels_and_separates_summary() -> None:
    source = (ROOT / "apps" / "web" / "src" / "pages" / "PaperPage.tsx").read_text(encoding="utf-8")
    quick_interpretation = (
        ROOT / "apps" / "web" / "src" / "components" / "QuickInterpretationPanel.tsx"
    ).read_text(encoding="utf-8")

    assert "摘要译文" in source
    assert "查看原文" in source
    assert "查看中文" in source
    assert "中文译文暂未生成，以下为论文原始摘要。" in source
    assert "QuickInterpretationPanel" in source
    assert "快速解读" in quick_interpretation
    assert "translation_status" not in source
