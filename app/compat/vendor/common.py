"""Shared helpers for the vms-react legacy-contract compat layer.

Every compat router builds plain camelCase dicts by hand rather than round-tripping through
CamelModel response models, because the old contract's field *names* (and sometimes its status
enums) rarely match the new unified backend's verbatim -- this is thin re-shaping of whatever the
real service/repository already returns, never a re-implementation of business logic.

List endpoints in the old contract accept filters (search/status/category) that don't map 1:1
onto a single SQL WHERE clause once you account for the old contract's coarser status enums (e.g.
old RFQ status "Open" corresponds to *several* real RfqStatus values). Rather than reproduce each
resource's filtering as bespoke SQL, every compat list endpoint fetches the vendor's full
(unfiltered) rows from the existing repository, reshapes them to the old field names/status
labels, then filters/paginates in Python. Data volumes per vendor in this system are small, so
this trade favors correctness (filters actually match the old contract's semantics) over raw
efficiency.
"""
from datetime import date, datetime, timezone

from fastapi.responses import RedirectResponse

from app.core.exceptions import NotFoundException


def envelope(data, meta: dict | None = None) -> dict:
    body = {"success": True, "data": data}
    if meta is not None:
        body["meta"] = meta
    return body


def iso(value):
    """vms-react parses every timestamp with `new Date(...)`, which accepts both a bare
    YYYY-MM-DD date and a full `...Z` instant -- so a plain `.isoformat()` (with `+00:00`
    normalized to `Z` for tz-aware datetimes) satisfies the old contract's examples either way."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value


def dec(value):
    return float(value) if value is not None else None


def camelize(obj):
    """Recursively converts dict keys from snake_case to camelCase -- used only where the real
    backend's field names already conceptually match the old contract 1:1 (e.g. the vendor
    dashboard), so a bare case conversion is the whole translation."""
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            parts = key.split("_")
            camel_key = parts[0] + "".join(p.title() for p in parts[1:])
            out[camel_key] = camelize(value)
        return out
    if isinstance(obj, list):
        return [camelize(v) for v in obj]
    return obj


def paginate_list(items: list[dict], page: int, limit: int) -> tuple[list[dict], int]:
    total = len(items)
    start = (page - 1) * limit
    return items[start : start + limit], total


def vendor_meta(page: int, limit: int, total_items: int, **extra) -> dict:
    total_pages = max(1, -(-total_items // limit)) if total_items else 1
    return {"page": page, "limit": limit, "totalItems": total_items, "totalPages": total_pages, **extra}


def redirect_to_file(stored_url: str | None) -> RedirectResponse:
    """Every PDF/attachment download in the old contract is `file stream or redirect to signed
    URL` per API_SPECIFICATION.md -- a redirect to the storage backend's (possibly presigned)
    URL satisfies vms-react's `downloadFile()` helper (a plain axios GET with responseType:
    'blob', which follows redirects transparently)."""
    if not stored_url:
        raise NotFoundException("No file has been uploaded for this record")
    from app.utils.storage import get_storage_client

    return RedirectResponse(get_storage_client().resolve_url(stored_url))


def enum_value(value):
    """Every status enum in this compat layer is passed through verbatim (native RfqStatus,
    PurchaseOrderStatus, QuotationStatus, ShipmentStatus, VendorReturnStatus, InvoiceStatus,
    PaymentStatus, FreightPaymentStatus, VendorStatus, ComplianceDocType, GoodsCategory,
    GoodsUnit, StockStatus, CatalogSubmissionStatus string values all match vms-react's *actual*
    current frontend code verbatim -- confirmed by reading src/pages/*.jsx directly, which is
    quite different from API_SPECIFICATION.md's older/stale documented enums). This just
    normalizes a Python enum member to its `.value` for JSON encoding."""
    return value.value if hasattr(value, "value") else value
