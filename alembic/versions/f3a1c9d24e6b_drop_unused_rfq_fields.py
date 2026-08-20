"""drop unused rfqs.delivery_location, specifications, terms, estimated_budget columns

Revision ID: f3a1c9d24e6b
Revises: a7855d58c75b
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f3a1c9d24e6b'
down_revision: Union[str, None] = 'a7855d58c75b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # RFQ module UI no longer collects or displays these fields (never populated by any
    # creation path — see DATABASE_UNUSED_FIELDS_ANALYSIS.md); removed at the user's request.
    op.drop_column('rfqs', 'delivery_location')
    op.drop_column('rfqs', 'specifications')
    op.drop_column('rfqs', 'terms')
    op.drop_column('rfqs', 'estimated_budget')


def downgrade() -> None:
    op.add_column('rfqs', sa.Column('estimated_budget', sa.NUMERIC(precision=14, scale=2), autoincrement=False, nullable=True))
    op.add_column('rfqs', sa.Column('terms', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('rfqs', sa.Column('specifications', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('rfqs', sa.Column('delivery_location', sa.VARCHAR(length=500), autoincrement=False, nullable=True))
