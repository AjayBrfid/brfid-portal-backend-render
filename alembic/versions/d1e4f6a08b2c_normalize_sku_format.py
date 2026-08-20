"""normalize existing SKU style/variant codes to SKU-{STYLE}-{COLOR_CODE}-{SIZE_CODE}

Revision ID: d1e4f6a08b2c
Revises: c9b7e2a41f3d
Create Date: 2026-08-17 00:00:00.000000

"""
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1e4f6a08b2c'
down_revision: Union[str, None] = 'c9b7e2a41f3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors app/utils/sku_codes.COLOR_CODES — duplicated here so this migration stays runnable
# on its own even if that module changes later.
COLOR_CODES = {
    "black": "BLK",
    "blue": "BLU",
    "brown": "BRN",
    "green": "GRN",
    "yellow": "YLW",
    "red": "RED",
}


def _alnum_upper(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value or "").upper()


def _color_code(colour) -> str:
    key = (colour or "").strip().lower()
    if key in COLOR_CODES:
        return COLOR_CODES[key]
    return _alnum_upper(colour)[:3] or "GEN"


def _size_code(size) -> str:
    return _alnum_upper(size) or "NA"


def upgrade() -> None:
    conn = op.get_bind()

    skus = conn.execute(sa.text("SELECT id, style_code FROM skus ORDER BY published_at ASC")).fetchall()
    for i, (sku_id, _old_style_code) in enumerate(skus, start=1):
        new_style_code = f"{i:03d}"
        conn.execute(sa.text("UPDATE skus SET style_code = :code WHERE id = :id"), {"code": new_style_code, "id": sku_id})

        variants = conn.execute(
            sa.text("SELECT id, colour, size FROM sku_variants WHERE sku_id = :sku_id"), {"sku_id": sku_id}
        ).fetchall()
        for variant_id, colour, size in variants:
            new_variant_code = f"SKU-{new_style_code}-{_color_code(colour)}-{_size_code(size)}"
            conn.execute(
                sa.text("UPDATE sku_variants SET variant_code = :code WHERE id = :id"),
                {"code": new_variant_code, "id": variant_id},
            )


def downgrade() -> None:
    # The pre-migration codes (raw UUID-hash-based style codes, free-text colour/size embedded
    # directly in variant codes) aren't recoverable — this is a one-way data normalization.
    pass
