from research_navigator.models import Paper, PaperDocument, ResearchProfile, ResearchProject
from research_navigator.recommendations.service import build_reading_recommendation


def _profile() -> ResearchProfile:
    return ResearchProfile(
        user_id=1,
        broad_direction="工业时序异常检测与未来窗口预警",
        major="数据科学",
        keywords_json='["future horizon", "anomaly detection"]',
        excluded_terms_json="[]",
        preferences_json="[]",
    )


def test_task_mismatch_cannot_be_priority_read() -> None:
    paper = Paper(
        id=7,
        title="Monodense Deep Neural Model for Determining Item Price Elasticity",
        normalized_title="monodense deep neural model for determining item price elasticity",
        abstract="We estimate price elasticity from retail demand and promotions.",
        arxiv_id="2603.29261v1",
    )
    recommendation = build_reading_recommendation(
        paper=paper, profile=_profile(), project=None, material=None
    )
    assert recommendation["verdict"] in {"method_reference", "not_priority"}
    assert recommendation["verdict"] != "priority_read"
    assert recommendation["task_match"] == "mismatched"
    assert recommendation["evidence_level"] == "abstract"
    assert recommendation["evidence_refs"][0]["paper_identity"] == "arxiv:2603.29261v1"


def test_unknown_task_and_profile_identity_are_explicit() -> None:
    paper = Paper(id=8, title="Only metadata", normalized_title="only metadata", abstract=None)
    recommendation = build_reading_recommendation(
        paper=paper,
        profile=None,
        project=ResearchProject(id=3, user_id=1, name="Project"),
        material=None,
    )
    assert recommendation["verdict"] == "insufficient_evidence"
    assert recommendation["task_match"] == "unknown"
    assert recommendation["evidence_level"] == "metadata"
    assert recommendation["research_profile_identity"]
    assert recommendation["missing_information"]


def test_full_text_recommendation_is_bound_to_current_material() -> None:
    paper = Paper(
        id=9,
        title="Industrial time series anomaly detection",
        normalized_title="industrial time series anomaly detection",
        abstract="Future warning for industrial time series anomalies.",
        arxiv_id="fixture-fulltext-v1",
    )
    material = PaperDocument(
        id=41,
        paper_id=paper.id,
        source_type="fixture",
        evidence_level="fulltext",
        original_filename="fixture.pdf",
        stored_path="fixture.pdf",
        mime_type="application/pdf",
        sha256="a" * 64,
        size_bytes=12,
        page_count=1,
    )
    recommendation = build_reading_recommendation(
        paper=paper, profile=_profile(), project=None, material=material
    )
    assert recommendation["verdict"] == "priority_read"
    assert recommendation["evidence_level"] == "full_text"
    assert recommendation["material_identity"] == f"document:41:{'a' * 64}"
    assert (
        recommendation["evidence_refs"][0]["material_identity"]
        == recommendation["material_identity"]
    )


def test_profile_identity_changes_when_research_direction_changes() -> None:
    paper = Paper(
        id=10,
        title="Industrial time series anomaly detection",
        normalized_title="industrial time series anomaly detection",
        abstract="Future warning for industrial time series anomalies.",
    )
    first_profile = _profile()
    second_profile = _profile()
    second_profile.broad_direction = "医学影像分割"
    first = build_reading_recommendation(
        paper=paper, profile=first_profile, project=None, material=None
    )
    second = build_reading_recommendation(
        paper=paper, profile=second_profile, project=None, material=None
    )
    assert first["research_profile_identity"] != second["research_profile_identity"]
