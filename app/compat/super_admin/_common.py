"""Shared helpers for the Super Admin compat layer: status-vocabulary translation between the
old (vms-sa-react) contract and this codebase's real enums, and simple date-bucketing for the
registration-trend endpoint. Kept in one place so every compat router applies the same
approximations consistently.
"""
import uuid
from calendar import month_abbr
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fulfillment import TransferOrderStatus
from app.models.procurement import PurchaseOrder, PurchaseOrderStatus, Rfq, RfqStatus
from app.models.retail import Store
from app.models.shipping import ShipmentStatus
from app.models.vendor import Vendor
from app.models.warehouse import Warehouse


def resolve_id(session: Session, model, code_column, code: str | None) -> uuid.UUID | None:
    """Resolves a display code (e.g. "VEN-001") to the row's real UUID primary key, or None if
    no code was given / no row matches. Callers use the sentinel `uuid.uuid4()` (never a real
    match) when a code was given but not found, so the resulting filter excludes everything
    rather than silently matching every row."""
    if not code:
        return None
    row = session.execute(select(model).where(code_column == code)).scalar_one_or_none()
    return row.id if row else uuid.uuid4()


def resolve_vendor_id(session: Session, code: str | None):
    return resolve_id(session, Vendor, Vendor.code, code)


def resolve_warehouse_id(session: Session, code: str | None):
    return resolve_id(session, Warehouse, Warehouse.code, code)


def resolve_store_id(session: Session, code: str | None):
    return resolve_id(session, Store, Store.code, code)


def resolve_po_id(session: Session, ref_code: str | None):
    return resolve_id(session, PurchaseOrder, PurchaseOrder.ref_code, ref_code)


def resolve_rfq_id(session: Session, ref_code: str | None):
    return resolve_id(session, Rfq, Rfq.ref_code, ref_code)

# --- RFQ status: the real state machine (Draft -> ... -> Purchase Order Generated -> Closed)
# is far more granular than the old contract's five buckets. This is a best-effort translation,
# not a byte-for-byte equivalent — noted as a genuine vocabulary gap in the implementation report.
_RFQ_STATUS_MAP = {
    RfqStatus.DRAFT: "Open",
    RfqStatus.SENT: "Open",
    RfqStatus.AWAITING_QUOTATIONS: "Open",
    RfqStatus.PARTIALLY_RESPONDED: "Open",
    RfqStatus.READY_FOR_COMPARISON: "Closing Soon",
    RfqStatus.VENDOR_SELECTED: "Awarded",
    RfqStatus.PURCHASE_ORDER_GENERATED: "Awarded",
    RfqStatus.CLOSED: "Closed",
}


def rfq_status_out(status: RfqStatus) -> str:
    return _RFQ_STATUS_MAP.get(status, status.value)


def po_status_out(status: PurchaseOrderStatus, received_qty: int, quantity: int) -> str:
    """Old contract has both "Partially Delivered" and "Completed" where the real enum only has
    a single "Delivered" terminal status — split it using received_qty vs. ordered quantity."""
    if status == PurchaseOrderStatus.DELIVERED:
        return "Completed" if received_qty >= quantity else "Partially Delivered"
    return status.value


# --- Outbound deliveries (TransferOrder): old contract wants Packed|Dispatched|In Transit|
# Delivered; the real TransferOrderStatus has no "In Transit" state distinct from "Dispatched" —
# it never appears in compat output. Also has no `delayed` concept at all (always False).
_TRANSFER_STATUS_MAP = {
    TransferOrderStatus.PENDING: "Packed",
    TransferOrderStatus.DISPATCHED: "Dispatched",
    TransferOrderStatus.DELIVERED: "Delivered",
    TransferOrderStatus.COMPLETED: "Delivered",
}


def transfer_status_out(status: TransferOrderStatus) -> str:
    return _TRANSFER_STATUS_MAP.get(status, status.value)


def transfer_statuses_for(old_status: str) -> list[TransferOrderStatus]:
    """Reverse of transfer_status_out — every real TransferOrderStatus that maps to the given
    old-contract status string, used to filter *before* pagination (never after, which would
    make `meta.total` wrong)."""
    return [real for real, old in _TRANSFER_STATUS_MAP.items() if old == old_status]


def shipment_status_out(status: ShipmentStatus) -> tuple[str, bool]:
    """Real ShipmentStatus models "Delayed" as its own status value; the old contract instead
    wants a normal status plus a separate `delayed` boolean. Delayed shipments are reported as
    still "In Transit" with delayed=True."""
    if status == ShipmentStatus.DELAYED:
        return "In Transit", True
    return status.value, False


_WEEKDAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def registration_buckets(dates: list[date], period: str) -> list[dict]:
    """Buckets a list of registration dates into the old contract's `{label, count}` shape.
    `week` -> one bucket per day for the last 7 days (labeled by weekday abbreviation).
    `month` -> one bucket per week for the last ~4 weeks (labeled "Week 1".."Week N", oldest
    first). `year` (default fallback too) -> one bucket per month for the last 12 months.
    Mirrors this codebase's existing date-bucketing convention (see
    app/api/v1/vendor/dashboard_router.py's fixed-window style) rather than introducing a new one.
    """
    today = date.today()
    if period == "week":
        buckets = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            count = sum(1 for d in dates if d == day)
            buckets.append({"label": _WEEKDAY_ABBR[day.weekday()], "count": count})
        return buckets
    if period == "year":
        buckets = []
        for i in range(11, -1, -1):
            # Walk back i months from today, landing on the 1st to avoid day-of-month overflow.
            year = today.year + (today.month - 1 - i) // 12
            month = (today.month - 1 - i) % 12 + 1
            count = sum(1 for d in dates if d.year == year and d.month == month)
            buckets.append({"label": month_abbr[month], "count": count})
        return buckets
    # "month" (default): 4 weekly buckets covering the last 28 days.
    buckets = []
    for i in range(3, -1, -1):
        start = today - timedelta(days=7 * (i + 1) - 1)
        end = today - timedelta(days=7 * i)
        count = sum(1 for d in dates if start <= d <= end)
        buckets.append({"label": f"Week {4 - i}", "count": count})
    return buckets


def window_start(period: str) -> datetime:
    days = {"week": 7, "month": 28, "year": 365}.get(period, 28)
    return datetime.now() - timedelta(days=days)
