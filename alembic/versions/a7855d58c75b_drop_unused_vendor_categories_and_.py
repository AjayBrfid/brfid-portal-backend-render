"""drop unused vendor_categories and vendor_return_attachments tables, asn_items.uom and freight_payments.approved_on columns

Revision ID: a7855d58c75b
Revises: 0dcb263b355d
Create Date: 2026-08-17 11:54:36.053326

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a7855d58c75b'
down_revision: Union[str, None] = '0dcb263b355d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Removes tables/columns confirmed UNUSED end-to-end (no frontend, backend, or DB-level
    # reference anywhere) by DATABASE_UNUSED_FIELDS_ANALYSIS.md's full-codebase audit.
    op.drop_table('vendor_return_attachments')
    op.drop_table('vendor_categories')
    op.drop_column('asn_items', 'uom')
    op.drop_column('freight_payments', 'approved_on')
    # Note: autogenerate also detected an unrelated, pre-existing model/DB drift (a missing
    # unique constraint on sku_supplying_vendors) — intentionally left out of this migration
    # since it's out of scope for this UNUSED-column cleanup.


def downgrade() -> None:
    op.add_column('freight_payments', sa.Column('approved_on', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True))
    op.add_column('asn_items', sa.Column('uom', sa.VARCHAR(length=20), autoincrement=False, nullable=True))
    op.create_table('vendor_categories',
    sa.Column('vendor_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('category', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], name=op.f('vendor_categories_vendor_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('vendor_id', 'category', name=op.f('vendor_categories_pkey'))
    )
    op.create_table('vendor_return_attachments',
    sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('vendor_return_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('file_name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
    sa.Column('url', sa.VARCHAR(length=500), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['vendor_return_id'], ['vendor_returns.id'], name=op.f('vendor_return_attachments_vendor_return_id_fkey'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('vendor_return_attachments_pkey'))
    )
