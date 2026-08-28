"""Add evidence platform, research map, and expert evaluation persistence.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-28
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("paper_documents", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column(
        "paper_documents", sa.Column("source_record_id", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "paper_documents", sa.Column("rights_basis", sa.String(length=120), nullable=True)
    )
    op.add_column("paper_documents", sa.Column("license", sa.String(length=120), nullable=True))
    op.add_column(
        "paper_documents", sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "paper_documents", sa.Column("response_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "paper_documents", sa.Column("acquisition_run_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "paper_documents",
        sa.Column(
            "parse_status",
            sa.String(length=80),
            nullable=False,
            server_default="succeeded",
        ),
    )

    op.add_column(
        "paper_analyses", sa.Column("analysis_run_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "paper_analyses",
        sa.Column(
            "analysis_mode",
            sa.String(length=40),
            nullable=False,
            server_default="deterministic",
        ),
    )
    op.add_column(
        "paper_analyses",
        sa.Column(
            "provider",
            sa.String(length=120),
            nullable=False,
            server_default="deterministic",
        ),
    )
    op.add_column("paper_analyses", sa.Column("model_name", sa.String(length=160), nullable=True))
    op.add_column(
        "paper_analyses", sa.Column("prompt_version", sa.String(length=80), nullable=True)
    )
    op.add_column(
        "paper_analyses",
        sa.Column("input_evidence_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "paper_analyses",
        sa.Column("provider_output_hash", sa.String(length=64), nullable=True),
    )
    op.add_column("paper_analyses", sa.Column("fallback_reason", sa.Text(), nullable=True))

    op.add_column("tool_calls", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column(
        "tool_calls",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "tool_calls",
        sa.Column("token_usage_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.add_column("tool_calls", sa.Column("response_status", sa.String(length=80), nullable=True))
    op.add_column(
        "tool_calls", sa.Column("validated_output_hash", sa.String(length=64), nullable=True)
    )

    op.create_table(
        "source_runtime_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column(
            "operational_status", sa.String(length=40), nullable=False, server_default="unknown"
        ),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rate_limit_limit", sa.Integer(), nullable=True),
        sa.Column("rate_limit_remaining", sa.Integer(), nullable=True),
        sa.Column("rate_limit_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("last_error_code", sa.String(length=120), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", name="uq_source_runtime_state_source"),
    )
    op.create_index(
        "ix_source_runtime_states_status", "source_runtime_states", ["operational_status"]
    )

    op.create_table(
        "authors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("orcid", sa.String(length=200), nullable=True),
        sa.Column("openalex_id", sa.String(length=300), nullable=True),
        sa.Column("semantic_scholar_id", sa.String(length=300), nullable=True),
        sa.Column("affiliations_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("topics_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("works_count", sa.Integer(), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=True),
        sa.Column("homepage", sa.Text(), nullable=True),
        sa.Column(
            "identity_status", sa.String(length=40), nullable=False, server_default="unresolved"
        ),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("orcid", name="uq_authors_orcid"),
        sa.UniqueConstraint("openalex_id", name="uq_authors_openalex_id"),
        sa.UniqueConstraint("semantic_scholar_id", name="uq_authors_semantic_scholar_id"),
    )
    op.create_index("ix_authors_normalized_name", "authors", ["normalized_name"])

    op.create_table(
        "paper_authors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "paper_id", sa.Integer(), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "author_id",
            sa.Integer(),
            sa.ForeignKey("authors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("credit_roles_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("paper_id", "position", name="uq_paper_author_position"),
        sa.UniqueConstraint("paper_id", "author_id", name="uq_paper_author_identity"),
    )
    op.create_index("ix_paper_authors_paper", "paper_authors", ["paper_id"])

    op.create_table(
        "author_source_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "author_id",
            sa.Integer(),
            sa.ForeignKey("authors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_author_id", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_hash", sa.String(length=64), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_author_id", name="uq_author_source_record_identity"),
    )
    op.create_index("ix_author_source_records_author", "author_source_records", ["author_id"])

    op.create_table(
        "dataset_cards",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("access_url", sa.Text(), nullable=True),
        sa.Column("license", sa.String(length=160), nullable=True),
        sa.Column("domain", sa.String(length=240), nullable=True),
        sa.Column(
            "identity_status", sa.String(length=40), nullable=False, server_default="mentioned_only"
        ),
        sa.Column("provenance_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dataset_cards_normalized_name", "dataset_cards", ["normalized_name"])

    op.create_table(
        "paper_dataset_mentions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "paper_id", sa.Integer(), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("paper_analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dataset_id",
            sa.Integer(),
            sa.ForeignKey("dataset_cards.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("raw_mention", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=True),
        sa.Column("task", sa.Text(), nullable=True),
        sa.Column("train_split", sa.Text(), nullable=True),
        sa.Column("validation_split", sa.Text(), nullable=True),
        sa.Column("test_split", sa.Text(), nullable=True),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_level", sa.String(length=80), nullable=False),
        sa.Column("field_citations_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "identity_status", sa.String(length=40), nullable=False, server_default="mentioned_only"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_paper_dataset_mentions_lookup",
        "paper_dataset_mentions",
        ["user_id", "paper_id", "analysis_id"],
    )

    op.create_table(
        "direction_cluster_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("research_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "algorithm_version",
            sa.String(length=80),
            nullable=False,
            server_default="direction-cluster-v1",
        ),
        sa.Column("parameters_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="succeeded"),
        sa.Column(
            "disclaimer",
            sa.Text(),
            nullable=False,
            server_default="Literature organization result; not an objective field taxonomy.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_direction_cluster_runs_user_project",
        "direction_cluster_runs",
        ["user_id", "project_id"],
    )

    op.create_table(
        "direction_clusters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("direction_cluster_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cluster_key", sa.String(length=80), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("terms_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_distribution_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "cluster_key", name="uq_direction_cluster_key"),
    )
    op.create_index("ix_direction_clusters_run", "direction_clusters", ["run_id"])

    op.create_table(
        "direction_cluster_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.Integer(),
            sa.ForeignKey("direction_cluster_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cluster_id",
            sa.Integer(),
            sa.ForeignKey("direction_clusters.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "paper_id", sa.Integer(), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("similarity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_unclustered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "paper_id", name="uq_direction_cluster_member"),
    )
    op.create_index("ix_direction_cluster_members_run", "direction_cluster_members", ["run_id"])

    op.create_table(
        "evaluation_studies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
        sa.Column("study_version", sa.String(length=80), nullable=False),
        sa.Column("frozen_input_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "expert_outcome_validation",
            sa.String(length=60),
            nullable=False,
            server_default="awaiting_real_experts",
        ),
        sa.Column("randomized_seed", sa.String(length=64), nullable=False),
        sa.Column("protocol_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_evaluation_studies_owner", "evaluation_studies", ["owner_user_id", "status"]
    )

    op.create_table(
        "evaluation_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "study_id",
            sa.Integer(),
            sa.ForeignKey("evaluation_studies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_key", sa.String(length=160), nullable=False),
        sa.Column(
            "paper_id", sa.Integer(), sa.ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("baseline_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("candidate_payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("study_id", "task_key", name="uq_evaluation_task_key"),
    )
    op.create_index("ix_evaluation_tasks_study", "evaluation_tasks", ["study_id"])

    op.create_table(
        "evaluation_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "study_id",
            sa.Integer(),
            sa.ForeignKey("evaluation_studies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.Integer(),
            sa.ForeignKey("evaluation_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "expert_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("blind_order_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="assigned"),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "task_id", "expert_user_id", name="uq_evaluation_assignment_expert_task"
        ),
    )
    op.create_index(
        "ix_evaluation_assignments_expert",
        "evaluation_assignments",
        ["expert_user_id", "status"],
    )

    op.create_table(
        "evaluation_ratings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "assignment_id",
            sa.Integer(),
            sa.ForeignKey("evaluation_assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "expert_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_correctness", sa.Float(), nullable=False),
        sa.Column("evidence_sufficiency", sa.Float(), nullable=False),
        sa.Column("citation_usefulness", sa.Float(), nullable=False),
        sa.Column("missing_field_correctness", sa.Float(), nullable=False),
        sa.Column("preference", sa.String(length=40), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assignment_id", name="uq_evaluation_rating_assignment"),
    )
    op.create_index("ix_evaluation_ratings_expert", "evaluation_ratings", ["expert_user_id"])

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "study_id",
            sa.Integer(),
            sa.ForeignKey("evaluation_studies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("real_expert_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("simulated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "validation_status",
            sa.String(length=60),
            nullable=False,
            server_default="awaiting_real_experts",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("study_id", name="uq_evaluation_results_study"),
    )


def downgrade() -> None:
    op.drop_table("evaluation_results")
    op.drop_index("ix_evaluation_ratings_expert", table_name="evaluation_ratings")
    op.drop_table("evaluation_ratings")
    op.drop_index("ix_evaluation_assignments_expert", table_name="evaluation_assignments")
    op.drop_table("evaluation_assignments")
    op.drop_index("ix_evaluation_tasks_study", table_name="evaluation_tasks")
    op.drop_table("evaluation_tasks")
    op.drop_index("ix_evaluation_studies_owner", table_name="evaluation_studies")
    op.drop_table("evaluation_studies")
    op.drop_index("ix_direction_cluster_members_run", table_name="direction_cluster_members")
    op.drop_table("direction_cluster_members")
    op.drop_index("ix_direction_clusters_run", table_name="direction_clusters")
    op.drop_table("direction_clusters")
    op.drop_index("ix_direction_cluster_runs_user_project", table_name="direction_cluster_runs")
    op.drop_table("direction_cluster_runs")
    op.drop_index("ix_paper_dataset_mentions_lookup", table_name="paper_dataset_mentions")
    op.drop_table("paper_dataset_mentions")
    op.drop_index("ix_dataset_cards_normalized_name", table_name="dataset_cards")
    op.drop_table("dataset_cards")
    op.drop_index("ix_author_source_records_author", table_name="author_source_records")
    op.drop_table("author_source_records")
    op.drop_index("ix_paper_authors_paper", table_name="paper_authors")
    op.drop_table("paper_authors")
    op.drop_index("ix_authors_normalized_name", table_name="authors")
    op.drop_table("authors")
    op.drop_index("ix_source_runtime_states_status", table_name="source_runtime_states")
    op.drop_table("source_runtime_states")

    op.drop_column("tool_calls", "validated_output_hash")
    op.drop_column("tool_calls", "response_status")
    op.drop_column("tool_calls", "token_usage_json")
    op.drop_column("tool_calls", "attempt_count")
    op.drop_column("tool_calls", "latency_ms")

    op.drop_column("paper_analyses", "fallback_reason")
    op.drop_column("paper_analyses", "provider_output_hash")
    op.drop_column("paper_analyses", "input_evidence_hash")
    op.drop_column("paper_analyses", "prompt_version")
    op.drop_column("paper_analyses", "model_name")
    op.drop_column("paper_analyses", "provider")
    op.drop_column("paper_analyses", "analysis_mode")
    op.drop_column("paper_analyses", "analysis_run_id")

    op.drop_column("paper_documents", "parse_status")
    op.drop_column("paper_documents", "acquisition_run_id")
    op.drop_column("paper_documents", "response_hash")
    op.drop_column("paper_documents", "retrieved_at")
    op.drop_column("paper_documents", "license")
    op.drop_column("paper_documents", "rights_basis")
    op.drop_column("paper_documents", "source_record_id")
    op.drop_column("paper_documents", "source_url")
