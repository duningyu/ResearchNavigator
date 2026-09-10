from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web" / "src"


def text(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


def test_paper_page_exposes_full_workflow_timeline_and_research_cards() -> None:
    source = text("pages/PaperPage.tsx")
    workflow_component = text("components/EvidenceWorkflowPanel.tsx")
    intelligence_component = text("components/PaperIntelligenceCards.tsx")
    assert "/evidence-workflows" in source
    assert "EvidenceWorkflowPanel" in source
    assert "证据工作流时间线" in workflow_component
    assert "现有材料" in workflow_component
    assert "/authors" in source
    assert "PaperIntelligenceCards" in source
    assert "作者卡" in intelligence_component
    assert "/datasets" in source
    assert "数据集卡" in intelligence_component
    assert "待补充材料" in source
    assert "证据级分析" in source
    assert "fallback_reason" in source


def test_direction_map_and_evaluation_pages_are_routed_and_navigable() -> None:
    app = text("app/App.tsx")
    shell = text("components/AppShell.tsx")
    direction = text("pages/DirectionMapPage.tsx")
    evaluations = text("pages/EvaluationsPage.tsx")
    assert 'path="direction-map"' in app
    assert 'path="evaluations"' in app
    assert "方向聚类" in shell
    assert "专家评测" in shell
    assert "/direction-clusters" in direction
    assert "not an objective field taxonomy" in direction
    assert "/evaluations/studies" in evaluations
    assert "模拟或开发者评分不能作为真实专家验证" in evaluations
