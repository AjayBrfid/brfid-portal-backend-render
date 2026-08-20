import uuid

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.exceptions import EmailAlreadyExistsException, NotFoundException
from app.core.exceptions import ConflictException
from app.core.security import hash_password
from app.models.user import User
from app.models.vendor import ComplianceDocType, Vendor, VendorComplianceDocument, VendorStatus
from app.repositories.user_repository import UserRepository
from app.repositories.vendor_repository import VendorRepository
from app.utils.storage import get_storage_client


class VendorRegistrationService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = VendorRepository(session)
        self.users = UserRepository(session)

    def register(
        self,
        name: str,
        contact_person: str,
        contact_email: str,
        contact_phone: str,
        state: str,
        city: str,
        address: str,
        gst: str,
        pan: str,
        admin_email: str,
        temporary_password: str,
        category: str | None = None,
    ) -> Vendor:
        if self.repo.get_by_gst(gst):
            raise ConflictException("A vendor with this GST number is already registered")
        if self.repo.get_by_pan(pan):
            raise ConflictException("A vendor with this PAN is already registered")
        if self.users.get_by_portal_email("vendor", admin_email):
            raise EmailAlreadyExistsException()

        vendor = self.repo.add(
            Vendor(
                code=self.repo.next_code(), name=name, category=category, contact_person=contact_person,
                contact_email=contact_email, contact_phone=contact_phone, state=state, city=city, address=address,
                gst=gst, pan=pan, status=VendorStatus.PENDING_APPROVAL,
            )
        )
        self.users.add(
            User(
                code=self.users.next_code("vendor"), portal_type="vendor", entity_id=vendor.id, email=admin_email,
                password_hash=hash_password(temporary_password), name=contact_person, role="vendor-admin",
                phone=contact_phone, status="active",
            )
        )
        self.session.commit()

        from app.services.auth.notification_service import NotificationService
        from sqlalchemy import select

        admins = self.session.scalars(select(User).where(User.portal_type == "super_admin")).all()
        for admin in admins:
            NotificationService(self.session).notify_user(admin.id, "vendor", "New vendor registration", f"{vendor.name} has registered and is awaiting approval.", "vendor", vendor.id)
        return vendor

    def get_profile(self, vendor_id: uuid.UUID) -> Vendor:
        vendor = self.repo.get_by_id(vendor_id)
        if not vendor:
            raise NotFoundException("Vendor not found")
        return vendor

    def update_profile(self, vendor_id: uuid.UUID, **fields) -> Vendor:
        vendor = self.get_profile(vendor_id)
        for key, value in fields.items():
            if value is not None:
                setattr(vendor, key, value)
        self.session.commit()
        return vendor

    def upload_document(self, vendor_id: uuid.UUID, doc_type: str, file: UploadFile) -> VendorComplianceDocument:
        self.get_profile(vendor_id)
        uploaded = get_storage_client().save(file, folder="vendor-compliance")
        doc = VendorComplianceDocument(vendor_id=vendor_id, doc_type=doc_type, url=uploaded.url)
        self.session.add(doc)
        self.session.commit()
        return doc
