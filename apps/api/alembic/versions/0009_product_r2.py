"""Product R2 durable translation cache and plan kinds."""

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_plans",
        sa.Column(
            "plan_kind", sa.String(length=40), nullable=False, server_default="confirmed_gap"
        ),
    )
    op.create_table(
        "abstract_translation_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("source_abstract_sha256", sa.String(length=64), nullable=False),
        sa.Column("target_language", sa.String(length=40), nullable=False),
        sa.Column("pipeline_version", sa.String(length=80), nullable=False),
        sa.Column("translated_abstract", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("fallback_reason", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "paper_id", "source_abstract_sha256", "target_language", "pipeline_version",
            name="uq_abstract_translation_cache_key",
        ),
    )
    op.create_index(
        "ix_abstract_translation_cache_paper", "abstract_translation_cache", ["paper_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_abstract_translation_cache_paper", table_name="abstract_translation_cache")
    op.drop_table("abstract_translation_cache")
    op.drop_column("research_plans", "plan_kind")
