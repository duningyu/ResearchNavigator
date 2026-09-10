"""Nullable action purpose/output; leave user-authored historic plans unchanged."""
import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plan_items", sa.Column("purpose", sa.Text(), nullable=True))
    op.add_column("plan_items", sa.Column("expected_output", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("plan_items", "expected_output")
    op.drop_column("plan_items", "purpose")
