"""Bind a persisted abstract to the source that supplied it.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-28
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_sources",
        sa.Column(
            "provides_abstract",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("paper_sources", "provides_abstract")
