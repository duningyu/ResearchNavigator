"""Add feedback-closure search, selection, comparison, settings, and idempotency schema.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column(
        "search_sessions",
        sa.Column("search_mode", sa.String(length=40), nullable=False, server_default="precise"),
    )
    op.add_column(
        "search_sessions",
        sa.Column(
            "ranking_rule_version",
            sa.String(length=80),
            nullable=False,
            server_default="legacy-v0",
        ),
    )
    op.add_column(
        "search_sessions", sa.Column("diversity_seed", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "search_sessions",
        sa.Column("composition_json", sa.Text(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("default_result_count", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("default_page_size", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("preferred_sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "default_open_access_only", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("display_language", sa.String(length=20), nullable=False, server_default="zh-CN"),
        sa.Column(
            "analysis_execution_preference",
            sa.String(length=40),
            nullable=False,
            server_default="synchronous",
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"], unique=True)

    op.create_table(
        "paper_sets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False, server_default="explicit"),
        sa.Column("direction_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_sets_user_id", "paper_sets", ["user_id"], unique=False)
    op.create_index("ix_paper_sets_project_id", "paper_sets", ["project_id"], unique=False)
    op.create_index(
        "ix_paper_sets_user_project", "paper_sets", ["user_id", "project_id"], unique=False
    )

    op.create_table(
        "paper_set_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("paper_set_id", sa.Integer(), nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_set_id"], ["paper_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_set_id", "paper_id", name="uq_paper_set_item"),
        sa.UniqueConstraint("paper_set_id", "position", name="uq_paper_set_position"),
    )
    op.create_index("ix_paper_set_items_paper_id", "paper_set_items", ["paper_id"], unique=False)
    op.create_index(
        "ix_paper_set_items_paper_set_id", "paper_set_items", ["paper_set_id"], unique=False
    )

    op.create_table(
        "comparison_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("paper_set_id", sa.Integer(), nullable=False),
        sa.Column("direction_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("matrix_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "analysis_version", sa.String(length=80), nullable=False, server_default="analysis-v1"
        ),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["paper_set_id"], ["paper_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_comparison_runs_user_id", "comparison_runs", ["user_id"], unique=False)
    op.create_index(
        "ix_comparison_runs_project_id", "comparison_runs", ["project_id"], unique=False
    )
    op.create_index(
        "ix_comparison_runs_paper_set_id", "comparison_runs", ["paper_set_id"], unique=False
    )
    op.create_index(
        "ix_comparison_runs_user_project",
        "comparison_runs",
        ["user_id", "project_id"],
        unique=False,
    )

    with op.batch_alter_table("gap_candidates") as batch_op:
        batch_op.add_column(sa.Column("paper_set_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("direction_snapshot_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch_op.create_foreign_key(
            "fk_gap_candidates_paper_set",
            "paper_sets",
            ["paper_set_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_gap_candidates_paper_set_id", ["paper_set_id"])

    op.create_table(
        "gap_explanations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("gap_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider", sa.String(length=80), nullable=False, server_default="deterministic"),
        sa.Column("explanation_json", sa.Text(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("validated", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["gap_id"], ["gap_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gap_explanations_gap_id", "gap_explanations", ["gap_id"], unique=False)
    op.create_index("ix_gap_explanations_user_id", "gap_explanations", ["user_id"], unique=False)
    op.create_index(
        "ix_gap_explanations_gap_version", "gap_explanations", ["gap_id", "version"], unique=False
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.String(length=120), nullable=False),
        sa.Column("scenario_version", sa.String(length=80), nullable=True),
        sa.Column("response_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "operation", "idempotency_key", name="uq_idempotency_user_operation_key"
        ),
    )
    op.create_index("ix_idempotency_records_user_id", "idempotency_records", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_user_id", table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index("ix_gap_explanations_gap_version", table_name="gap_explanations")
    op.drop_index("ix_gap_explanations_user_id", table_name="gap_explanations")
    op.drop_index("ix_gap_explanations_gap_id", table_name="gap_explanations")
    op.drop_table("gap_explanations")
    with op.batch_alter_table("gap_candidates") as batch_op:
        batch_op.drop_index("ix_gap_candidates_paper_set_id")
        batch_op.drop_constraint("fk_gap_candidates_paper_set", type_="foreignkey")
        batch_op.drop_column("direction_snapshot_json")
        batch_op.drop_column("paper_set_id")
    op.drop_index("ix_comparison_runs_user_project", table_name="comparison_runs")
    op.drop_index("ix_comparison_runs_paper_set_id", table_name="comparison_runs")
    op.drop_index("ix_comparison_runs_project_id", table_name="comparison_runs")
    op.drop_index("ix_comparison_runs_user_id", table_name="comparison_runs")
    op.drop_table("comparison_runs")
    op.drop_index("ix_paper_set_items_paper_set_id", table_name="paper_set_items")
    op.drop_index("ix_paper_set_items_paper_id", table_name="paper_set_items")
    op.drop_table("paper_set_items")
    op.drop_index("ix_paper_sets_user_project", table_name="paper_sets")
    op.drop_index("ix_paper_sets_project_id", table_name="paper_sets")
    op.drop_index("ix_paper_sets_user_id", table_name="paper_sets")
    op.drop_table("paper_sets")
    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_table("user_settings")
    op.drop_column("search_sessions", "composition_json")
    op.drop_column("search_sessions", "diversity_seed")
    op.drop_column("search_sessions", "ranking_rule_version")
    op.drop_column("search_sessions", "search_mode")
