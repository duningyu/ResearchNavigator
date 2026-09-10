"""Add shared arXiv lease and send spacing state."""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_runtime_states", sa.Column("lease_owner", sa.String(length=200)))
    op.add_column(
        "source_runtime_states", sa.Column("lease_expires_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "source_runtime_states", sa.Column("next_allowed_at", sa.DateTime(timezone=True))
    )


def downgrade() -> None:
    op.drop_column("source_runtime_states", "next_allowed_at")
    op.drop_column("source_runtime_states", "lease_expires_at")
    op.drop_column("source_runtime_states", "lease_owner")
