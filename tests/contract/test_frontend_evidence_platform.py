from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web" / "src"


def test_frontend_exposes_evidence_workflow_progress_and_research_cards() -> None:
    workflow = WEB / "components" / "EvidenceWorkflowPanel.tsx"
    intelligence = WEB / "components" / "PaperIntelligenceCards.tsx"
    paper_page = (WEB / "pages" / "PaperPage.tsx").read_text(encoding="utf-8")
    domain = (WEB / "types" / "domain.ts").read_text(encoding="utf-8")

    assert workflow.is_file()
    assert intelligence.is_file()
    assert "/evidence-workflows" in paper_page
    assert "EvidenceWorkflowPanel" in paper_page
    assert "PaperIntelligenceCards" in paper_page
    assert "export type EvidenceWorkflow" in domain
    assert "export type AuthorCard" in domain
    assert "export type DatasetCard" in domain


def test_frontend_routes_direction_map_and_real_expert_evaluation_boundaries() -> None:
    app = (WEB / "app" / "App.tsx").read_text(encoding="utf-8")
    shell = (WEB / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    direction = WEB / "pages" / "DirectionMapPage.tsx"
    evaluations = WEB / "pages" / "EvaluationsPage.tsx"

    assert direction.is_file()
    assert evaluations.is_file()
    assert 'path="direction-map"' in app
    assert 'path="evaluations"' in app
    assert "方向聚类" in shell
    assert "专家评测" in shell
    assert "这是一种文献组织结果，不是学术领域的客观分类" in direction.read_text(
        encoding="utf-8"
    )
    assert "awaiting_real_experts" in evaluations.read_text(encoding="utf-8")
