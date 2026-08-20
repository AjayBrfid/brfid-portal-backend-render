from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import hash_password
from app.models.retail import Store, StoreStatus
from app.models.user import User
from app.repositories.retail_repository import RetailRepository
from app.repositories.user_repository import UserRepository
from app.utils.storage import UploadedFileOut, get_storage_client

ALLOWED_DOC_TYPES = {"gst_certificate", "pan_card", "business_registration_proof", "cancelled_cheque"}


class StoreService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = RetailRepository(session)
        self.users = UserRepository(session)

    def register_store(
        self,
        business_type: str,
        store_name: str,
        pan: str,
        gstin: str,
        cin: str | None,
        years_in_operation: int | None,
        admin_name: str,
        phone: str,
        email: str,
        address: str,
        city: str,
        state: str,
        pincode: str,
        temporary_password: str,
        store_type: str = "Standard",
    ) -> Store:
        store = self.repo.add(
            Store(
                code=self.repo.next_code(),
                name=store_name,
                store_type=store_type,
                business_type=business_type,
                pan=pan,
                cin=cin,
                years_in_operation=years_in_operation,
                address=address,
                city=city,
                state=state,
                pincode=pincode,
                gstin=gstin,
                contact_phone=phone,
                status=StoreStatus.PENDING_APPROVAL,
            )
        )
        self.users.add(
            User(
                code=self.users.next_code("store"),
                portal_type="store",
                entity_id=store.id,
                email=email,
                password_hash=hash_password(temporary_password),
                name=admin_name,
                role="store-admin",
                phone=phone,
                status="active",
            )
        )
        self.session.commit()
        return store

    def upload_store_document(self, store_id, doc_type: str, file: UploadFile) -> UploadedFileOut:
        if doc_type not in ALLOWED_DOC_TYPES:
            raise ConflictException(f"Unknown document type '{doc_type}'")
        store = self.repo.get_by_id(store_id)
        if not store:
            raise NotFoundException("Store not found")
        # Only accept uploads during the registration window itself — once a store is approved
        # (or rejected), no real session exists yet at this point in the flow either way, so
        # this status check is the one thing standing between "anyone with a store_id" and
        # overwriting an already-active store's documents.
        if store.status != StoreStatus.PENDING_APPROVAL:
            raise ConflictException("Store is not pending approval")

        uploaded = get_storage_client().save(file, folder="store-registrations")
        docs = dict(store.documents or {})
        docs[doc_type] = uploaded.url
        store.documents = docs
        self.session.commit()
        return uploaded

    def list_linked_warehouses(self, store_id) -> list[dict]:
        from app.repositories.warehouse_repository import WarehouseRepository

        warehouses = WarehouseRepository(self.session).linked_warehouses_for_store(store_id)
        return [{"id": w.id, "name": w.name} for w in warehouses]
