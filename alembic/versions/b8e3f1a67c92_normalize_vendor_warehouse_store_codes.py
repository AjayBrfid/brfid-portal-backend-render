"""normalize vendor/warehouse/store codes to the hyphenated {PREFIX}-{NNN} format

Revision ID: b8e3f1a67c92
Revises: a3d8f61c9b42
Create Date: 2026-08-21 00:00:00.000000

Registration used two different generators for these codes ("VEN001" from the self-registration
path vs "VEN-001" from the warehouse-onboards-a-vendor path, and similarly for warehouses/stores)
before both were unified onto the hyphenated format in app/repositories/*_repository.py. This
renumbers any row still in the old bare-digit format onto the next free hyphenated number, so
every row ends up unique and consistent without touching the id/FK columns.
"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8e3f1a67c92'
down_revision: Union[str, None] = 'a3d8f61c9b42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = [("vendors", "VEN"), ("warehouses", "WH"), ("stores", "STR")]


def _renumber(conn, table: str, prefix: str) -> None:
    rows = conn.execute(sa.text(f"SELECT id, code FROM {table} ORDER BY created_at ASC")).fetchall()

    hyphen_re = re.compile(rf"^{prefix}-([0-9]+)$")
    bare_re = re.compile(rf"^{prefix}([0-9]+)$")

    used = {int(m.group(1)) for _id, code in rows if (m := hyphen_re.match(code or ""))}
    next_num = max(used, default=0) + 1

    for row_id, code in rows:
        if hyphen_re.match(code or ""):
            continue
        if not bare_re.match(code or ""):
            continue  # unrecognized format — leave untouched rather than guess
        new_code = f"{prefix}-{next_num:03d}"
        next_num += 1
        conn.execute(sa.text(f"UPDATE {table} SET code = :code WHERE id = :id"), {"code": new_code, "id": row_id})


def upgrade() -> None:
    conn = op.get_bind()
    for table, prefix in _TABLES:
        _renumber(conn, table, prefix)


def downgrade() -> None:
    # The pre-migration bare-digit codes aren't recoverable per-row (only the format is known,
    # not which rows originally lacked the hyphen) — this is a one-way data normalization.
    pass
