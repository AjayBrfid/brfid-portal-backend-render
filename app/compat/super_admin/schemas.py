"""Response/request Pydantic models for the Super Admin compat layer (vms-sa-react's original,
pre-unification API contract — see vms-sa-react/BACKEND_API_SPEC.md). All built on CamelModel so
JSON keys are camelCase while the Python side stays snake_case, matching this codebase's normal
style everywhere else.
"""
import uuid
from datetime import date, datetime

from pydantic import Field

from app.compat.schemas import CamelModel


# --- shared request bodies ---


class RejectBody(CamelModel):
    reason: str


class SetPasswordBody(CamelModel):
    new_password: str


class ChangePasswordBody(CamelModel):
    current_password: str
    new_password: str


class GenerateSkuBody(CamelModel):
    sku: str | None = None


class GenerateSkuOut(CamelModel):
    sku: str
    assigned_submission_ids: list[str]
    assigned_count: int


# --- vendors ---


class ComplianceItem(CamelModel):
    uploaded: bool
    url: str | None = None


class VendorOut(CamelModel):
    id: str
    name: str
    category: str | None = None
    contact_person: str
    email: str
    phone: str
    city: str
    state: str
    gst: str
    registered_on: date
    status: str
    rating: float | None = None
    # BACKEND_API_SPEC.md spells this "totalPOs" (capital PO) — the generic to_camel alias
    # generator would otherwise produce "totalPos", so it's pinned explicitly here.
    total_pos: int = Field(alias="totalPOs")
    total_quotations: int
    # Not tracked anywhere in the unified backend yet (no vendor scorecard/performance-review
    # feature exists) — always null until such a feature is built.
    performance_score: int | None = None
    on_time_delivery_pct: int | None = None
    quality_score: int | None = None
    compliance: dict[str, ComplianceItem]


class VendorStockOut(CamelModel):
    id: uuid.UUID
    vendor_id: str
    vendor_name: str
    # VendorGood (a vendor's own raw-material catalog) has no link to a specific finished
    # product or warehouse — those two fields are genuinely untracked for this table.
    product_id: str | None = None
    product_name: str
    unit: str
    quantity: float
    warehouse_id: str | None = None
    warehouse_name: str | None = None
    last_updated: date
    status: str


class CatalogDocOut(CamelModel):
    name: str
    uploaded_date: date
    url: str


class VendorCatalogOut(CamelModel):
    id: uuid.UUID
    code: str | None = None
    vendor_id: str
    vendor_name: str
    name: str
    product_type: str
    gender: str
    fabric: str
    colour: str
    size: str
    gsm: int
    description: str | None = None
    sku: str | None = None
    submitted_date: date
    documents: list[CatalogDocOut]
    status: str


# --- warehouses ---


class WarehouseOut(CamelModel):
    id: str
    name: str
    # This codebase tracks a single warehouse code (used as `id` everywhere), not a separate
    # short display code — duplicated here rather than left blank.
    code: str
    city: str
    state: str
    manager: str | None = None
    email: str | None = None
    contact: str
    business_type: str | None = None
    company_name: str | None = None
    pan: str | None = None
    gstin: str | None = None
    cin: str | None = None
    tax_jurisdiction: str | None = None
    address: str
    pincode: str | None = None
    license_no: str | None = None
    capacity_sqft: int | None = None
    utilized_pct: int
    zone_count: int
    status: str
    registered_on: date
    established_year: int | None = None


class ZoneOut(CamelModel):
    id: uuid.UUID
    warehouse_id: str
    warehouse_name: str
    name: str
    capacity: int
    utilized_pct: int
    product_count: int
    status: str


class MovementOut(CamelModel):
    id: uuid.UUID
    type: str
    product_name: str
    unit: str
    quantity: float
    warehouse_id: str
    warehouse_name: str
    from_location: str | None = None
    to_location: str | None = None
    date: date
    reference_id: str | None = None
    performed_by: str | None = None


# --- stores ---


class StoreOut(CamelModel):
    id: str
    name: str
    code: str
    city: str
    state: str
    region: str | None = None
    manager: str | None = None
    email: str | None = None
    contact: str
    store_type: str
    business_type: str | None = None
    pan: str | None = None
    gstin: str | None = None
    cin: str | None = None
    years_in_operation: int | None = None
    address: str
    pincode: str | None = None
    status: str
    opened_on: date
    documents: dict[str, ComplianceItem]


class StoreInventoryOut(CamelModel):
    store_id: str
    store_name: str
    product_id: str
    product_name: str
    unit: str
    quantity: int
    reorder_level: int | None = None


class WarehouseInventoryOut(CamelModel):
    sku: str
    name: str
    category: str | None = None
    on_hand: int
    available: int
    reserved: int
    returns_qty: int
    status: str


# --- deliveries ---


class InboundDeliveryOut(CamelModel):
    id: uuid.UUID
    po_id: str
    vendor_name: str
    warehouse_name: str
    dispatch_date: date
    expected_delivery: date | None = None
    status: str
    delayed: bool
    tracking_no: str | None = None


class OutboundDeliveryOut(CamelModel):
    id: str
    request_id: str | None = None
    store_name: str
    warehouse_name: str
    dispatch_date: date | None = None
    # TransferOrder has no expected-delivery-date column at all — this compat layer has no
    # source for it.
    expected_delivery: date | None = None
    status: str
    delayed: bool
    tracking_no: str | None = None


# --- quotations / stock requests / rfqs / purchase orders / products ---


class QuotationOut(CamelModel):
    id: uuid.UUID
    rfq_id: str
    rfq_title: str
    vendor_id: str
    vendor_name: str
    amount: float
    total_amount: float
    submitted_date: date
    delivery_days: int
    status: str
    warehouse_id: str
    warehouse_name: str


class StockRequestOut(CamelModel):
    id: str
    store_id: str
    store_name: str
    product_name: str
    unit: str
    quantity: int
    request_date: date
    required_by: date
    priority: str
    status: str
    warehouse_name: str


class ProductOut(CamelModel):
    id: uuid.UUID
    sku: str
    name: str
    category: str | None = None
    unit: str
    reorder_level: int | None = None
    unit_price: float | None = None


class RfqOut(CamelModel):
    id: str
    title: str
    category: str | None = None
    issue_date: date | None = None
    closing_date: date | None = None
    quantity: int
    unit: str
    status: str
    vendors_invited: int
    quotations_received: int
    warehouse_id: str
    warehouse_name: str


class PurchaseOrderOut(CamelModel):
    id: str
    vendor_id: str
    vendor_name: str
    warehouse_id: str
    warehouse_name: str
    quotation_id: uuid.UUID
    items_summary: str
    grand_total: float
    order_date: date
    delivery_date: date
    status: str


# --- notifications / activities ---


class NotificationOut(CamelModel):
    id: uuid.UUID
    type: str
    title: str
    text: str | None = None
    created_at: datetime
    unread: bool


class ActivityOut(CamelModel):
    id: uuid.UUID
    icon: str
    text: str
    created_at: datetime


# --- dashboard / analytics ---


class DashboardSummaryOut(CamelModel):
    total_vendors: int
    total_warehouses: int
    total_stores: int
    pending_vendors: int
    pending_warehouses: int
    pending_stores: int


class RegistrationBucket(CamelModel):
    label: str
    count: int


class RegistrationTrendOut(CamelModel):
    entity: str
    period: str
    buckets: list[RegistrationBucket]
