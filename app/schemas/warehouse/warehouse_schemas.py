import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class RegisterWarehouseRequest(BaseModel):
    business_type: str
    company_name: str
    pan: str
    gstin: str
    cin: str | None = None
    state: str
    city: str
    address: str
    pincode: str
    warehouse_name: str
    admin_name: str
    country_code: str = "+91"
    phone: str
    email: EmailStr
    temporary_password: str


class RegisterWarehouseResponse(BaseModel):
    warehouse_id: uuid.UUID
    status: str


class WarehouseSettingsUpdate(BaseModel):
    working_days: str | None = None
    low_stock_warning_units: int | None = None
    critical_stock_warning_units: int | None = None


class OnboardVendorRequest(BaseModel):
    name: str
    code: str | None = None
    gstin: str
    city: str
    rating: float | None = None
    lead_time_days: int | None = None


class VendorStatusUpdate(BaseModel):
    status: str


class StoreStatusUpdate(BaseModel):
    status: str


class RejectRequest(BaseModel):
    reason: str


class SplitFulfilRequest(BaseModel):
    invited_vendor_ids: list[uuid.UUID]


class RaiseRfqRequest(BaseModel):
    invited_vendor_ids: list[uuid.UUID]


class DispatchRequest(BaseModel):
    transporter: str
    vehicle_number: str
    tracking_number: str | None = None
    packages: int
    remarks: str | None = None


class UpdateTransferStatusRequest(BaseModel):
    status: str


class AdjustInventoryRequest(BaseModel):
    on_hand_delta: int | None = None
    available_delta: int | None = None
