import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


class VendorRegistrationRequest(BaseModel):
    name: str
    contact_person: str
    contact_email: EmailStr
    contact_phone: str
    state: str
    city: str
    address: str
    gst: str
    pan: str
    category: str | None = None
    admin_email: EmailStr
    temporary_password: str


class UpdateVendorProfileRequest(BaseModel):
    name: str | None = None
    contact_person: str | None = None
    contact_phone: str | None = None
    website: str | None = None
    description: str | None = None
    bank_name: str | None = None
    bank_holder: str | None = None
    bank_account: str | None = None
    bank_ifsc: str | None = None
    bank_branch: str | None = None


class RejectRequest(BaseModel):
    reason: str


class SetPasswordRequest(BaseModel):
    new_password: str


class GenerateSkuRequest(BaseModel):
    style_code: str | None = None
    hsn: str | None = None
    gst_rate: Decimal | None = None
    mrp: Decimal | None = None


class SubmitQuotationRequest(BaseModel):
    unit_price: Decimal
    tax_percent: Decimal = Decimal("0")
    discount_percent: Decimal = Decimal("0")
    delivery_days: int
    warranty: str | None = None
    payment_terms: str | None = None
    remarks: str | None = None
    validity_days: int = Field(ge=0)
    freight_payer: str = "vendor"
    freight_details_json: dict | None = None


class SelectVendorRequest(BaseModel):
    quotation_id: uuid.UUID


class PoRejectRequest(BaseModel):
    reason: str | None = None


class CreateAsnRequest(BaseModel):
    shipped_qty: int
    expected_delivery_date: date | None = None
    transport_charge: Decimal | None = None


class ResubmitAsnRequest(BaseModel):
    shipped_qty: int
    expected_delivery_date: date | None = None
    batch_no: str | None = None


class GoodsReceiptAttachment(BaseModel):
    file_name: str
    url: str


class GoodsReceiptRequest(BaseModel):
    accepted_qty: int
    rejected_qty: int = 0
    rejection_reason: str | None = None
    attachments: list[GoodsReceiptAttachment] = []


class ShipmentCreateRequest(BaseModel):
    asn_id: uuid.UUID
    dispatch_date: date
    expected_delivery: date | None = None
    transporter: str
    driver_name: str | None = None
    driver_contact: str | None = None
    vehicle_no: str | None = None
    tracking_no: str | None = None
    weight: Decimal | None = None
    packages: int | None = None
    notes: str | None = None


class ShipmentStatusUpdateRequest(BaseModel):
    status: str
    remarks: str | None = None


class VendorReturnReviewRequest(BaseModel):
    remarks: str | None = None
    refund_amount: Decimal | None = None


class VendorReturnPickupRequest(BaseModel):
    pickup_date: date
    transporter: str
    vehicle_no: str | None = None


class VendorReturnDispatchRequest(BaseModel):
    tracking_no: str | None = None


class InvoiceCreateRequest(BaseModel):
    po_id: uuid.UUID
    asn_id: uuid.UUID | None = None
    invoice_number: str
    invoice_date: date
    due_date: date | None = None
    base_amount: Decimal
    gst_amount: Decimal
    discount_amount: Decimal = Decimal("0")
    freight_amount: Decimal = Decimal("0")


class InvoiceStatusUpdateRequest(BaseModel):
    status: str


class GoodsCreateRequest(BaseModel):
    name: str
    category: str
    unit: str
    quantity: Decimal
    price: Decimal
    gst_rate: Decimal | None = None


class GoodsUpdateRequest(BaseModel):
    name: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    gst_rate: Decimal | None = None


class CatalogCreateRequest(BaseModel):
    goods_id: uuid.UUID | None = None
    name: str
    product_type: str
    gender: str
    fabric: str
    colour: str
    size: str
    gsm: int
    description: str | None = None


class CatalogUpdateRequest(BaseModel):
    name: str | None = None
    product_type: str | None = None
    gender: str | None = None
    fabric: str | None = None
    colour: str | None = None
    size: str | None = None
    gsm: int | None = None
    description: str | None = None
