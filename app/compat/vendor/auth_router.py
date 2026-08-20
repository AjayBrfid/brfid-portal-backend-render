"""vms-react's legacy auth contract, mounted at root (no /api/v1, no /vendor prefix — see
app/compat/vendor/router.py). Every endpoint is a thin adapter over the exact same
AuthService/VendorRegistrationService already used by app/api/v1/auth/router.py and
app/api/v1/vendor/registration_router.py -- no duplicated login/token/registration logic here.
"""
import json
import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import EmailStr

from app.compat.schemas import CamelModel
from app.compat.vendor.common import dec, envelope, iso
from app.core.exceptions import BadRequestException, ForbiddenException
from app.dependencies.auth import get_auth_service, get_current_user
from app.dependencies.database import get_db
from app.dependencies.vendor import get_current_vendor, get_vendor_registration_service
from app.models.user import User
from app.models.vendor import ComplianceDocType, GoodsCategory, GoodsUnit, Vendor
from app.repositories.vendor_repository import VendorRepository
from app.services.auth.auth_service import AuthService
from app.services.vendor.goods_service import GoodsService
from app.services.vendor.vendor_service import VendorRegistrationService

router = APIRouter(tags=["vendor-compat-auth"])

# vms-react's GoodsManager offers a wider category/unit picklist (CATEGORIES/UNITS in
# GoodsManager.jsx) than the real GoodsCategory/GoodsUnit enums support -- unmapped values fall
# back to the closest real value rather than rejecting the whole registration.
_GOODS_CATEGORY_MAP = {
    "Fabric": GoodsCategory.FABRIC, "Trims": GoodsCategory.TRIMS, "Packaging": GoodsCategory.PACKAGING,
    "Yarn": GoodsCategory.OTHER, "Dyes & Chemicals": GoodsCategory.OTHER, "Labels": GoodsCategory.OTHER,
    "Other": GoodsCategory.OTHER,
}
_GOODS_UNIT_MAP = {
    "Mtrs": GoodsUnit.METERS, "Pcs": GoodsUnit.PCS, "Kgs": GoodsUnit.KG, "Rolls": GoodsUnit.ROLLS,
    "Sets": GoodsUnit.PCS, "Cones": GoodsUnit.PCS,
}
_DOC_FIELD_TO_TYPE = {
    "gst_cert": ComplianceDocType.GST_CERT, "pan_card": ComplianceDocType.PAN,
    "business_license": ComplianceDocType.BUSINESS_LICENSE, "msme": ComplianceDocType.MSME, "iso": ComplianceDocType.ISO,
}


def _vendor_out(user: User, vendor: Vendor) -> dict:
    return {
        "id": vendor.code,
        "email": user.email,
        "company": {"name": vendor.name},
        "contact": {"person": vendor.contact_person, "designation": vendor.designation, "mobile": vendor.contact_phone},
        "status": vendor.status.value,
        "approved": vendor.approved,
    }


class LoginRequest(CamelModel):
    email: EmailStr
    password: str


class RefreshRequest(CamelModel):
    refresh_token: str


class ForgotPasswordRequest(CamelModel):
    email: EmailStr


class ResetPasswordRequest(CamelModel):
    token: str
    new_password: str


class ChangePasswordRequest(CamelModel):
    current_password: str
    new_password: str


@router.post("/auth/login")
def login(body: LoginRequest, auth: AuthService = Depends(get_auth_service), session=Depends(get_db)):
    access_token, refresh_token, user = auth.login("vendor", body.email, body.password)
    vendor = VendorRepository(session).get_by_id(user.entity_id)
    if not vendor:
        raise ForbiddenException("This account is not linked to a vendor")
    return envelope({
        "accessToken": access_token, "refreshToken": refresh_token, "expiresIn": 3600,
        "vendor": _vendor_out(user, vendor),
    })


@router.post("/auth/logout")
def logout():
    # The old contract never sent a refresh token on logout, so there's nothing here to revoke
    # server-side -- the frontend just drops its local session (see services/store.js Auth.logout()).
    return envelope({"message": "Logged out"})


@router.post("/auth/refresh")
def refresh(body: RefreshRequest, auth: AuthService = Depends(get_auth_service)):
    access_token = auth.refresh_access_token(body.refresh_token)
    return envelope({"accessToken": access_token, "expiresIn": 3600})


@router.post("/auth/forgot-password")
def forgot_password(body: ForgotPasswordRequest, auth: AuthService = Depends(get_auth_service)):
    auth.request_password_reset("vendor", body.email)
    return envelope({"message": "Reset instructions sent if the email is registered"})


@router.post("/auth/reset-password")
def reset_password(body: ResetPasswordRequest, auth: AuthService = Depends(get_auth_service)):
    auth.reset_password(body.token, body.new_password)
    return envelope({"message": "Password updated"})


@router.post("/auth/change-password")
def change_password(body: ChangePasswordRequest, user: User = Depends(get_current_user), auth: AuthService = Depends(get_auth_service)):
    auth.change_password(user, body.current_password, body.new_password)
    return envelope({"message": "Password changed"})


def _dec(value, default="0"):
    try:
        return Decimal(str(value)) if value is not None else Decimal(default)
    except InvalidOperation:
        return Decimal(default)


@router.post("/vendor/registration", status_code=201)
async def register(
    payload: str = Form(...),
    gst_cert: UploadFile | None = File(None),
    pan_card: UploadFile | None = File(None),
    business_license: UploadFile | None = File(None),
    msme: UploadFile | None = File(None),
    # Named `iso_cert` (not `iso`) so it doesn't shadow the `iso()` date-formatting helper
    # imported into this module's scope -- `alias="iso"` keeps the actual multipart field name
    # (which vms-react sends as `iso`) unchanged.
    iso_cert: UploadFile | None = File(None, alias="iso"),
    service: VendorRegistrationService = Depends(get_vendor_registration_service),
    session=Depends(get_db),
):
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise BadRequestException("`payload` must be valid JSON") from exc

    company = data.get("company") or {}
    contact = data.get("contact") or {}
    address = data.get("address") or {}
    bank = data.get("bank") or {}
    goods = data.get("goods") or []

    gst = company.get("gst")
    pan = company.get("pan")
    if not gst or not pan:
        # The real Vendor row requires GST/PAN (unique, NOT NULL) even though vms-react's
        # RegisterPage.jsx no longer marks them as required fields -- a genuine contract gap.
        raise BadRequestException("GST and PAN are required to complete registration")

    vendor = service.register(
        name=company.get("name"), contact_person=contact.get("person"), contact_email=contact.get("email"),
        contact_phone=contact.get("mobile"), state=address.get("state"), city=address.get("city"),
        address=address.get("address"), gst=gst, pan=pan, admin_email=data.get("email"),
        temporary_password=data.get("password"), category=None,
    )

    extra_fields = {
        "website": company.get("website"),
        "office_phone": contact.get("office"),
        "country": address.get("country"),
        "postal_code": address.get("postal"),
        "bank_name": bank.get("name"), "bank_holder": bank.get("holder"), "bank_account": bank.get("account"),
        "bank_ifsc": bank.get("ifsc"), "bank_branch": bank.get("branch"),
    }
    service.update_profile(vendor.id, **{k: v for k, v in extra_fields.items() if v})

    goods_service = GoodsService(session)
    for g in goods:
        category = _GOODS_CATEGORY_MAP.get(g.get("category"), GoodsCategory.OTHER)
        unit = _GOODS_UNIT_MAP.get(g.get("unit"), GoodsUnit.PCS)
        goods_service.create(vendor.id, g.get("name"), category, unit, _dec(g.get("quantity")), _dec(g.get("price")), None)

    for field_name, file in (("gst_cert", gst_cert), ("pan_card", pan_card), ("business_license", business_license), ("msme", msme), ("iso", iso_cert)):
        if file is not None:
            doc_type = _DOC_FIELD_TO_TYPE[field_name]
            service.upload_document(vendor.id, doc_type, file)

    return envelope({
        "id": vendor.code, "email": data.get("email"), "status": vendor.status.value,
        "approved": vendor.approved, "registeredOn": iso(vendor.registered_on),
    })


@router.post("/vendors/{vendor_id}/documents", status_code=201)
def upload_vendor_document(
    vendor_id: str, type: str = Form(...), file: UploadFile = File(...),
    vendor: Vendor = Depends(get_current_vendor), service: VendorRegistrationService = Depends(get_vendor_registration_service),
):
    # `vendor_id` in the URL is never trusted -- the caller's own vendor (from their token) is
    # always the one a compliance document gets attached to.
    file_name = file.filename
    doc = service.upload_document(vendor.id, type, file)
    return envelope({"id": doc.id, "type": doc.doc_type.value, "fileName": file_name, "uploadedAt": iso(doc.uploaded_at)})
