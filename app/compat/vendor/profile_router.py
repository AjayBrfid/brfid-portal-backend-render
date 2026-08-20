"""Vendor profile compat -- GET/PATCH /vendors/:id. Confirmed against the actual current
src/pages/ProfilePage.jsx (not just API_SPECIFICATION.md, which documents an older shape): the
frontend reads `profile.vendorCode` (not `.id`), `profile.company.category` as a single string
(not a `categories` array), and `profile.complianceDocuments` as `[{docType, url}]` (not a
`compliance: {gstCert: bool, ...}` object). The `:id` path param itself is never trusted -- the
caller's own vendor (from get_current_vendor) is always the one read/updated.
"""
from fastapi import APIRouter, Depends

from app.compat.schemas import CamelModel
from app.compat.vendor.common import dec, envelope, iso
from app.dependencies.auth import get_current_user
from app.dependencies.vendor import get_current_vendor, get_vendor_registration_service
from app.models.user import User
from app.models.vendor import Vendor
from app.services.vendor.vendor_service import VendorRegistrationService

router = APIRouter(tags=["vendor-compat-profile"])


def _profile_out(user: User, vendor: Vendor) -> dict:
    return {
        "id": vendor.code,
        "vendorCode": vendor.code,
        "email": user.email,
        "status": vendor.status.value,
        "approved": vendor.approved,
        "rating": dec(vendor.rating),
        "registeredOn": iso(vendor.registered_on),
        "company": {
            "name": vendor.name, "category": vendor.category, "gst": vendor.gst, "pan": vendor.pan,
            "website": vendor.website, "description": vendor.description,
        },
        "contact": {
            "person": vendor.contact_person, "designation": vendor.designation,
            "mobile": vendor.contact_phone, "office": vendor.office_phone,
        },
        "address": {
            "country": vendor.country, "state": vendor.state, "city": vendor.city,
            "address": vendor.address, "postal": vendor.postal_code,
        },
        "bank": {
            "name": vendor.bank_name, "holder": vendor.bank_holder, "account": vendor.bank_account,
            "ifsc": vendor.bank_ifsc, "branch": vendor.bank_branch,
        },
        "complianceDocuments": [
            {"docType": d.doc_type.value, "url": d.url} for d in vendor.compliance_documents
        ],
    }


class CompanyPatch(CamelModel):
    name: str | None = None
    website: str | None = None
    description: str | None = None


class ContactPatch(CamelModel):
    person: str | None = None
    designation: str | None = None
    mobile: str | None = None
    office: str | None = None


class AddressPatch(CamelModel):
    country: str | None = None
    state: str | None = None
    city: str | None = None
    address: str | None = None
    postal: str | None = None


class BankPatch(CamelModel):
    name: str | None = None
    holder: str | None = None
    account: str | None = None
    ifsc: str | None = None
    branch: str | None = None


class VendorProfilePatchRequest(CamelModel):
    company: CompanyPatch | None = None
    contact: ContactPatch | None = None
    address: AddressPatch | None = None
    bank: BankPatch | None = None


@router.get("/vendors/{vendor_id}")
def get_vendor_profile(vendor_id: str, user: User = Depends(get_current_user), vendor: Vendor = Depends(get_current_vendor)):
    return envelope(_profile_out(user, vendor))


@router.patch("/vendors/{vendor_id}")
def update_vendor_profile(
    vendor_id: str, body: VendorProfilePatchRequest, user: User = Depends(get_current_user),
    vendor: Vendor = Depends(get_current_vendor), service: VendorRegistrationService = Depends(get_vendor_registration_service),
):
    fields = {}
    if body.company:
        fields.update({"name": body.company.name, "website": body.company.website, "description": body.company.description})
    if body.contact:
        fields.update({"contact_person": body.contact.person, "designation": body.contact.designation, "contact_phone": body.contact.mobile, "office_phone": body.contact.office})
    if body.address:
        fields.update({"country": body.address.country, "state": body.address.state, "city": body.address.city, "address": body.address.address, "postal_code": body.address.postal})
    if body.bank:
        fields.update({"bank_name": body.bank.name, "bank_holder": body.bank.holder, "bank_account": body.bank.account, "bank_ifsc": body.bank.ifsc, "bank_branch": body.bank.branch})
    updated = service.update_profile(vendor.id, **fields)
    return envelope(_profile_out(user, updated))
