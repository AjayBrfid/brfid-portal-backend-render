"""Builds the single canonical SKU string format used everywhere in the app:

    SKU-{STYLE_CODE}-{COLOR_CODE}-{SIZE_CODE}      e.g. SKU-001-BLK-M

STYLE_CODE, COLOR_CODE and SIZE_CODE are always sanitized to upper-case alphanumerics with no
spaces, so the assembled string can never carry free text through from a vendor's colour/size
input. The underlying Sku.colour/size/style_code *data* is untouched by this — this module only
governs the display/identifier string built from them (see Sku.style_code, SkuVariant.variant_code
in app/models/catalog.py).
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

SKU_PREFIX = "SKU"

# Standardized colour -> code mapping (case-insensitive). Any colour not listed here still gets
# a deterministic, space-free fallback code instead of leaking the free-text name into the SKU.
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


def color_code(colour: str | None) -> str:
    key = (colour or "").strip().lower()
    if key in COLOR_CODES:
        return COLOR_CODES[key]
    fallback = _alnum_upper(colour)[:3]
    return fallback or "GEN"


def size_code(size: str | None) -> str:
    return _alnum_upper(size) or "NA"


def sanitize_style_code(raw: str) -> str:
    """Normalizes an admin-supplied style code override: strips a redundant leading "SKU-" (in
    case someone pastes a full previous SKU by mistake) and any spaces/punctuation."""
    value = _alnum_upper(raw)
    if value.startswith(SKU_PREFIX):
        value = value[len(SKU_PREFIX):]
    return value.lstrip("-").strip("-") or _alnum_upper(raw)


def next_style_code(session: Session) -> str:
    """Next sequential numeric style code, zero-padded to 3 digits (001, 002, ...) — used whenever
    Super Admin doesn't supply their own override when generating a SKU."""
    from app.models.catalog import Sku

    existing = session.execute(select(Sku.style_code)).scalars().all()
    numeric = [int(code) for code in existing if code and code.isdigit()]
    next_num = (max(numeric) + 1) if numeric else 1
    return f"{next_num:03d}"


def build_variant_code(style_code: str, colour: str | None, size: str | None) -> str:
    return f"{SKU_PREFIX}-{style_code}-{color_code(colour)}-{size_code(size)}"
