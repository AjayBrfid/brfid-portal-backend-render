"""add shipments.code (ID001-style display code, for inbound deliveries)

Revision ID: e2f5a9c17d3b
Revises: d1e4f6a08b2c
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e2f5a9c17d3b'
down_revision: Union[str, None] = 'd1e4f6a08b2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('shipments', sa.Column('code', sa.String(length=20), nullable=True))
    op.create_unique_constraint('uq_shipments_code', 'shipments', ['code'])
    # Backfill existing rows so pre-existing shipments also get a display code, oldest first.
    conn = op.get_bind()
    rows = conn.execute(sa.text('SELECT id FROM shipments ORDER BY dispatch_date, id')).fetchall()
    for i, row in enumerate(rows, start=1):
        conn.execute(sa.text('UPDATE shipments SET code = :code WHERE id = :id'), {'code': f'ID{i:03d}', 'id': row.id})


def downgrade() -> None:
    op.drop_constraint('uq_shipments_code', 'shipments', type_='unique')
    op.drop_column('shipments', 'code')
