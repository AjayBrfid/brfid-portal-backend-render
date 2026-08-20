"""add vendor_return_attachments table (rejection-evidence photos, now genuinely used)

Revision ID: c9b7e2a41f3d
Revises: f3a1c9d24e6b
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9b7e2a41f3d'
down_revision: Union[str, None] = 'f3a1c9d24e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Re-adds the table dropped as unused in a7855d58c75b — the warehouse's ASN-rejection
    # "damage photo" upload is now wired to actually persist attachments against the
    # VendorReturn it creates, instead of being a client-side-only placeholder.
    op.create_table(
        'vendor_return_attachments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('vendor_return_id', sa.UUID(), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['vendor_return_id'], ['vendor_returns.id'], name=op.f('vendor_return_attachments_vendor_return_id_fkey'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('vendor_return_attachments_pkey')),
    )


def downgrade() -> None:
    op.drop_table('vendor_return_attachments')
