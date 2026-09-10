"""Preserve material identity separately from byte integrity (local validation only)."""
import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL means unconfirmed; never manufacture provenance for historic rows.
    op.add_column("paper_documents", sa.Column("material_binding_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("paper_documents", "material_binding_json")
