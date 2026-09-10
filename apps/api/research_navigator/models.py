"""SQLAlchemy persistence models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_admin: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    projects: Mapped[list[ResearchProject]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ResearchProject(TimestampMixin, Base):
    __tablename__ = "research_projects"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_project_user_name"),
        Index("ix_research_projects_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    broad_direction: Mapped[str | None] = mapped_column(String(240), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    user: Mapped[User] = relationship(back_populates="projects")


class SessionToken(TimestampMixin, Base):
    __tablename__ = "session_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResearchProfile(TimestampMixin, Base):
    __tablename__ = "research_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    major: Mapped[str | None] = mapped_column(String(160), nullable=True)
    broad_direction: Mapped[str | None] = mapped_column(String(240), nullable=True)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    excluded_terms_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    preferences_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    compute_constraints: Mapped[str | None] = mapped_column(Text, nullable=True)


class Paper(TimestampMixin, Base):
    __tablename__ = "papers"
    __table_args__ = (
        Index("ix_papers_normalized_title_year", "normalized_title", "publication_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    translated_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_year: Mapped[int | None] = mapped_column(nullable=True, index=True)
    publication_date_text: Mapped[str | None] = mapped_column(String(20), nullable=True)
    authors_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    venue: Mapped[str | None] = mapped_column(Text, nullable=True)
    venue_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(300), unique=True, nullable=True, index=True)
    arxiv_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    external_ids_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    source_urls_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    publisher_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_access_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    citation_count: Mapped[int | None] = mapped_column(nullable=True)
    reference_count: Mapped[int | None] = mapped_column(nullable=True)
    fields_of_study_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    concepts_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)


class PaperSource(TimestampMixin, Base):
    __tablename__ = "paper_sources"
    __table_args__ = (
        UniqueConstraint("paper_id", "source", "source_id", name="uq_paper_source_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_fixture: Mapped[bool] = mapped_column(default=False, nullable=False)
    provides_abstract: Mapped[bool] = mapped_column(default=False, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class SearchSession(TimestampMixin, Base):
    __tablename__ = "search_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    filters_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    source_status_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    result_count: Mapped[int] = mapped_column(default=0, nullable=False)
    search_mode: Mapped[str] = mapped_column(String(40), default="precise", nullable=False)
    ranking_rule_version: Mapped[str] = mapped_column(
        String(80), default="legacy-v0", nullable=False
    )
    diversity_seed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    composition_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class Favorite(TimestampMixin, Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "paper_id", name="uq_favorite_user_paper"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )


class Note(TimestampMixin, Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str] = mapped_column(String(40), default="user_note", nullable=False)


class Tag(TimestampMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tag_user_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)


class PaperTag(TimestampMixin, Base):
    __tablename__ = "paper_tags"
    __table_args__ = (UniqueConstraint("user_id", "paper_id", "tag_id", name="uq_paper_tag_user"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), nullable=False, index=True
    )


class PaperReadingStatus(TimestampMixin, Base):
    __tablename__ = "reading_status"
    __table_args__ = (UniqueConstraint("user_id", "paper_id", name="uq_reading_status_user_paper"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="unread", nullable=False)
    progress: Mapped[int] = mapped_column(default=0, nullable=False)


class PaperDocument(TimestampMixin, Base):
    __tablename__ = "paper_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "paper_id", "sha256", name="uq_document_user_paper_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(80), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(200), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    page_count: Mapped[int] = mapped_column(nullable=False)
    rights_confirmed: Mapped[bool] = mapped_column(default=False, nullable=False)
    ingestion_version: Mapped[str] = mapped_column(String(80), default="pdf-v1", nullable=False)
    material_binding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rights_basis: Mapped[str | None] = mapped_column(String(120), nullable=True)
    license: Mapped[str | None] = mapped_column(String(120), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acquisition_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(80), default="succeeded", nullable=False)


class PaperChunk(TimestampMixin, Base):
    __tablename__ = "paper_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        Index("ix_paper_chunks_access", "paper_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("paper_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    section: Mapped[str] = mapped_column(String(120), nullable=False)
    page_start: Mapped[int] = mapped_column(nullable=False)
    page_end: Mapped[int] = mapped_column(nullable=False)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    vector_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(80), nullable=False)
    ingestion_version: Mapped[str] = mapped_column(String(80), default="pdf-v1", nullable=False)


class PaperAnalysisRecord(TimestampMixin, Base):
    __tablename__ = "paper_analyses"
    __table_args__ = (Index("ix_paper_analyses_lookup", "user_id", "paper_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evidence_level: Mapped[str] = mapped_column(String(80), nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(80), nullable=False)
    analysis_json: Mapped[str] = mapped_column(Text, nullable=False)
    direction_similarity_json: Mapped[str] = mapped_column(Text, nullable=False)
    reproduction_assessment_json: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_mode: Mapped[str] = mapped_column(
        String(40), default="deterministic", nullable=False
    )
    provider: Mapped[str] = mapped_column(String(120), default="deterministic", nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_evidence_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class Recommendation(TimestampMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        Index("ix_recommendations_user_project_score", "user_id", "project_id", "score"),
        UniqueConstraint(
            "user_id",
            "project_id",
            "paper_id",
            "category",
            name="uq_recommendation_user_project_paper_category",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    score: Mapped[float] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    recommendation_version: Mapped[str] = mapped_column(
        String(80), default="recommendation-v1", nullable=False
    )


class GapCandidate(TimestampMixin, Base):
    __tablename__ = "gap_candidates"
    __table_args__ = (Index("ix_gap_candidates_user_project", "user_id", "project_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gap_type: Mapped[str] = mapped_column(String(120), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(60), default="generated", nullable=False, index=True)
    evidence_matrix_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    supporting_evidence_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    adjacent_work_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    counter_evidence_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    challenge_queries_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    data_sources_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    coverage_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    risk_factors_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    minimal_validation_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    suggested_research_question: Mapped[str] = mapped_column(Text, nullable=False)
    not_novelty_proof: Mapped[bool] = mapped_column(default=True, nullable=False)
    challenge_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    human_confirmation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    paper_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("paper_sets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    direction_snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class GapEvidence(TimestampMixin, Base):
    __tablename__ = "gap_evidence"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    gap_id: Mapped[int] = mapped_column(
        ForeignKey("gap_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[int | None] = mapped_column(
        ForeignKey("papers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evidence_role: Mapped[str] = mapped_column(String(40), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    source_query: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResearchPlan(TimestampMixin, Base):
    __tablename__ = "research_plans"
    __table_args__ = (Index("ix_research_plans_user_project", "user_id", "project_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gap_id: Mapped[int | None] = mapped_column(
        ForeignKey("gap_candidates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)


class PlanItem(TimestampMixin, Base):
    __tablename__ = "plan_items"
    __table_args__ = (Index("ix_plan_items_plan_sequence", "plan_id", "sequence"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("research_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentRun(TimestampMixin, Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    workflow_type: Mapped[str] = mapped_column(String(80), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    output_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PromptVersion(TimestampMixin, Base):
    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    template_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class ToolCall(TimestampMixin, Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.run_id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    input_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    output_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    attempt_count: Mapped[int] = mapped_column(default=1, nullable=False)
    token_usage_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    response_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    validated_output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SourceRequest(TimestampMixin, Base):
    __tablename__ = "source_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.run_id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    request_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    response_metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    source_records_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceRuntimeState(TimestampMixin, Base):
    __tablename__ = "source_runtime_states"
    __table_args__ = (
        UniqueConstraint("source", name="uq_source_runtime_state_source"),
        Index("ix_source_runtime_states_status", "operational_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    operational_status: Mapped[str] = mapped_column(
        String(40), default="unknown", nullable=False
    )
    cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_allowed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consecutive_failures: Mapped[int] = mapped_column(default=0, nullable=False)
    rate_limit_limit: Mapped[int | None] = mapped_column(nullable=True)
    rate_limit_remaining: Mapped[int | None] = mapped_column(nullable=True)
    rate_limit_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_http_status: Mapped[int | None] = mapped_column(nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class Author(TimestampMixin, Base):
    __tablename__ = "authors"
    __table_args__ = (Index("ix_authors_normalized_name", "normalized_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    orcid: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    openalex_id: Mapped[str | None] = mapped_column(String(300), unique=True, nullable=True)
    semantic_scholar_id: Mapped[str | None] = mapped_column(
        String(300), unique=True, nullable=True
    )
    affiliations_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    topics_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    works_count: Mapped[int | None] = mapped_column(nullable=True)
    citation_count: Mapped[int | None] = mapped_column(nullable=True)
    homepage: Mapped[str | None] = mapped_column(Text, nullable=True)
    identity_status: Mapped[str] = mapped_column(
        String(40), default="unresolved", nullable=False
    )
    provenance_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)


class PaperAuthorLink(TimestampMixin, Base):
    __tablename__ = "paper_authors"
    __table_args__ = (
        UniqueConstraint("paper_id", "position", name="uq_paper_author_position"),
        UniqueConstraint("paper_id", "author_id", name="uq_paper_author_identity"),
        Index("ix_paper_authors_paper", "paper_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("authors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(nullable=False)
    credit_roles_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)


class AuthorSourceRecord(TimestampMixin, Base):
    __tablename__ = "author_source_records"
    __table_args__ = (
        UniqueConstraint(
            "source", "source_author_id", name="uq_author_source_record_identity"
        ),
        Index("ix_author_source_records_author", "author_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(
        ForeignKey("authors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_author_id: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class DatasetCard(TimestampMixin, Base):
    __tablename__ = "dataset_cards"
    __table_args__ = (Index("ix_dataset_cards_normalized_name", "normalized_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    access_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    license: Mapped[str | None] = mapped_column(String(160), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(240), nullable=True)
    identity_status: Mapped[str] = mapped_column(
        String(40), default="mentioned_only", nullable=False
    )
    provenance_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)


class PaperDatasetMention(TimestampMixin, Base):
    __tablename__ = "paper_dataset_mentions"
    __table_args__ = (
        Index("ix_paper_dataset_mentions_lookup", "user_id", "paper_id", "analysis_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("paper_analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset_cards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    raw_mention: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    task: Mapped[str | None] = mapped_column(Text, nullable=True)
    train_split: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_split: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_split: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(80), nullable=False)
    field_citations_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    identity_status: Mapped[str] = mapped_column(
        String(40), default="mentioned_only", nullable=False
    )


class DirectionClusterRun(TimestampMixin, Base):
    __tablename__ = "direction_cluster_runs"
    __table_args__ = (
        Index("ix_direction_cluster_runs_user_project", "user_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    algorithm_version: Mapped[str] = mapped_column(
        String(80), default="direction-cluster-v1", nullable=False
    )
    parameters_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="succeeded", nullable=False)
    disclaimer: Mapped[str] = mapped_column(
        Text,
        default="Literature organization result; not an objective field taxonomy.",
        nullable=False,
    )


class DirectionCluster(TimestampMixin, Base):
    __tablename__ = "direction_clusters"
    __table_args__ = (
        UniqueConstraint("run_id", "cluster_key", name="uq_direction_cluster_key"),
        Index("ix_direction_clusters_run", "run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("direction_cluster_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cluster_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    terms_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    evidence_distribution_json: Mapped[str] = mapped_column(
        Text, default="{}", nullable=False
    )


class DirectionClusterMember(TimestampMixin, Base):
    __tablename__ = "direction_cluster_members"
    __table_args__ = (
        UniqueConstraint("run_id", "paper_id", name="uq_direction_cluster_member"),
        Index("ix_direction_cluster_members_run", "run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("direction_cluster_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("direction_clusters.id", ondelete="CASCADE"), nullable=True, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    similarity: Mapped[float] = mapped_column(default=0.0, nullable=False)
    is_unclustered: Mapped[bool] = mapped_column(default=False, nullable=False)


class EvaluationStudy(TimestampMixin, Base):
    __tablename__ = "evaluation_studies"
    __table_args__ = (
        Index("ix_evaluation_studies_owner", "owner_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    study_version: Mapped[str] = mapped_column(String(80), nullable=False)
    frozen_input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expert_outcome_validation: Mapped[str] = mapped_column(
        String(60), default="awaiting_real_experts", nullable=False
    )
    randomized_seed: Mapped[str] = mapped_column(String(64), nullable=False)
    protocol_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class EvaluationTask(TimestampMixin, Base):
    __tablename__ = "evaluation_tasks"
    __table_args__ = (
        UniqueConstraint("study_id", "task_key", name="uq_evaluation_task_key"),
        Index("ix_evaluation_tasks_study", "study_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_studies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_key: Mapped[str] = mapped_column(String(160), nullable=False)
    paper_id: Mapped[int | None] = mapped_column(
        ForeignKey("papers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    baseline_payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    candidate_payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)


class EvaluationAssignment(TimestampMixin, Base):
    __tablename__ = "evaluation_assignments"
    __table_args__ = (
        UniqueConstraint(
            "task_id", "expert_user_id", name="uq_evaluation_assignment_expert_task"
        ),
        Index("ix_evaluation_assignments_expert", "expert_user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_studies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expert_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    blind_order_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="assigned", nullable=False)
    is_simulated: Mapped[bool] = mapped_column(default=False, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EvaluationRating(TimestampMixin, Base):
    __tablename__ = "evaluation_ratings"
    __table_args__ = (
        UniqueConstraint("assignment_id", name="uq_evaluation_rating_assignment"),
        Index("ix_evaluation_ratings_expert", "expert_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expert_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_correctness: Mapped[float] = mapped_column(nullable=False)
    evidence_sufficiency: Mapped[float] = mapped_column(nullable=False)
    citation_usefulness: Mapped[float] = mapped_column(nullable=False)
    missing_field_correctness: Mapped[float] = mapped_column(nullable=False)
    preference: Mapped[str] = mapped_column(String(40), nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class EvaluationResult(TimestampMixin, Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("study_id", name="uq_evaluation_results_study"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    study_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_studies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metrics_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    real_expert_count: Mapped[int] = mapped_column(default=0, nullable=False)
    simulated_count: Mapped[int] = mapped_column(default=0, nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(60), default="awaiting_real_experts", nullable=False
    )


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=3, nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobEvent(TimestampMixin, Base):
    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job_created", "job_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class UserSettings(TimestampMixin, Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    default_result_count: Mapped[int] = mapped_column(default=50, nullable=False)
    default_page_size: Mapped[int] = mapped_column(default=10, nullable=False)
    preferred_sources_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    default_open_access_only: Mapped[bool] = mapped_column(default=False, nullable=False)
    display_language: Mapped[str] = mapped_column(String(20), default="zh-CN", nullable=False)
    analysis_execution_preference: Mapped[str] = mapped_column(
        String(40), default="synchronous", nullable=False
    )


class PaperSet(TimestampMixin, Base):
    __tablename__ = "paper_sets"
    __table_args__ = (Index("ix_paper_sets_user_project", "user_id", "project_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("research_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(40), default="explicit", nullable=False)
    direction_snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class PaperSetItem(TimestampMixin, Base):
    __tablename__ = "paper_set_items"
    __table_args__ = (
        UniqueConstraint("paper_set_id", "paper_id", name="uq_paper_set_item"),
        UniqueConstraint("paper_set_id", "position", name="uq_paper_set_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    paper_set_id: Mapped[int] = mapped_column(
        ForeignKey("paper_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id: Mapped[int] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(nullable=False)


class ComparisonRun(TimestampMixin, Base):
    __tablename__ = "comparison_runs"
    __table_args__ = (Index("ix_comparison_runs_user_project", "user_id", "project_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_set_id: Mapped[int] = mapped_column(
        ForeignKey("paper_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction_snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    matrix_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    analysis_version: Mapped[str] = mapped_column(String(80), default="analysis-v1", nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class GapExplanation(TimestampMixin, Base):
    __tablename__ = "gap_explanations"
    __table_args__ = (Index("ix_gap_explanations_gap_version", "gap_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    gap_id: Mapped[int] = mapped_column(
        ForeignKey("gap_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    provider: Mapped[str] = mapped_column(String(80), default="deterministic", nullable=False)
    explanation_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    validated: Mapped[bool] = mapped_column(default=True, nullable=False)


class IdempotencyRecord(TimestampMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "operation", "idempotency_key", name="uq_idempotency_user_operation_key"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(120), nullable=False)
    scenario_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    response_snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
