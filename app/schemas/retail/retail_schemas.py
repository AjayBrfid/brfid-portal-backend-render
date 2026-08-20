import uuid
from datetime import date

from pydantic import BaseModel, EmailStr


class RegisterStoreRequest(BaseModel):
    business_type: str
    store_name: str
    store_type: str = "Standard"
    pan: str
    gstin: str
    cin: str | None = None
    years_in_operation: int | None = None
    admin_name: str
    country_code: str = "+91"
    phone: str
    email: EmailStr
    address: str
    city: str
    state: str
    pincode: str
    temporary_password: str


class RegisterStoreResponse(BaseModel):
    store_id: uuid.UUID
    status: str


class UpdateOrganizationRequest(BaseModel):
    name: str
    gstin: str
    address: str


class UpdateThresholdRequest(BaseModel):
    threshold: int


class ApprovalOut(BaseModel):
    id: uuid.UUID
    status: str


class VisibilityUpdate(BaseModel):
    sku: str
    visible: bool


class UpdateVisibilityRequest(BaseModel):
    updates: list[VisibilityUpdate]


class RecordCountRequest(BaseModel):
    received: int
    condition: str


class RaiseIssueRequest(BaseModel):
    issue_type: str
    issue_qty: int
    issue_note: str
    return_type: str


class ApplyDiscountRequest(BaseModel):
    sku: str
    pct: float


class CreatePurchaseRequestBody(BaseModel):
    sku: str
    warehouse: str
    qty: int
    expected_date: date | None = None


class BulkItem(BaseModel):
    sku: str
    qty: int


class BulkCreateRequest(BaseModel):
    warehouse: str
    expected_date: date | None = None
    items: list[BulkItem]
