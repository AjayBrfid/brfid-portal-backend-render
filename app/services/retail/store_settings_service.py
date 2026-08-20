import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.retail import Store, StoreApproval
from app.repositories.retail_repository import RetailRepository


class StoreSettingsService:
    """Retail's admin-edit-requires-approval workflow: an Admin's change is queued as a
    StoreApproval and applied only once approved; a Manager's own change applies immediately
    with no approval row created at all."""

    def __init__(self, session: Session):
        self.session = session
        self.repo = RetailRepository(session)

    def get_store(self, store_id: uuid.UUID) -> Store | None:
        return self.repo.get_by_id(store_id)

    def update_organization(self, store_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str, name: str, gstin: str, address: str) -> dict | None:
        store = self.repo.get_by_id(store_id)
        if not store:
            raise NotFoundException("Store not found")
        new_value = {"name": name, "gstin": gstin, "address": address}
        if actor_role == "store-admin":
            approval = self.repo.add_approval(
                StoreApproval(
                    store_id=store_id, field="organization",
                    old_value={"name": store.name, "gstin": store.gstin, "address": store.address},
                    new_value=new_value, status="waiting", requested_by=actor_user_id,
                )
            )
            self.session.commit()
            from app.services.audit_service import AuditService

            AuditService(self.session).log(actor_user_id, "store", "Store Settings Change Requested", f"Organization details change requested (approval {approval.id}).", "store_approval", approval.id)
            return {"status": "waiting_approval", "approval_id": approval.id}
        store.name = name
        store.gstin = gstin
        store.address = address
        self.session.commit()
        from app.services.audit_service import AuditService

        AuditService(self.session).log(actor_user_id, "store", "Store Settings Updated", f"Organization details updated for store {store.code}.", "store", store_id)
        return None

    def update_low_stock_threshold(self, store_id: uuid.UUID, actor_user_id: uuid.UUID, actor_role: str, threshold: int) -> dict | None:
        store = self.repo.get_by_id(store_id)
        if not store:
            raise NotFoundException("Store not found")
        if actor_role == "store-admin":
            approval = self.repo.add_approval(
                StoreApproval(
                    store_id=store_id, field="low_stock_threshold",
                    old_value={"threshold": store.low_stock_threshold}, new_value={"threshold": threshold},
                    status="waiting", requested_by=actor_user_id,
                )
            )
            self.session.commit()
            from app.services.audit_service import AuditService

            AuditService(self.session).log(actor_user_id, "store", "Store Settings Change Requested", f"Low stock threshold change requested (approval {approval.id}).", "store_approval", approval.id)
            return {"status": "waiting_approval", "approval_id": approval.id}
        store.low_stock_threshold = threshold
        self.session.commit()
        from app.services.audit_service import AuditService

        AuditService(self.session).log(actor_user_id, "store", "Store Settings Updated", f"Low stock threshold updated to {threshold} for store {store.code}.", "store", store_id)
        return None

    def get_approval(self, approval_id: uuid.UUID) -> StoreApproval:
        approval = self.repo.get_approval(approval_id)
        if not approval:
            raise NotFoundException("Approval not found")
        return approval

    def approve(self, approval_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
        from datetime import datetime, timezone

        approval = self.get_approval(approval_id)
        store = self.repo.get_by_id(approval.store_id)
        if approval.field == "organization":
            store.name = approval.new_value["name"]
            store.gstin = approval.new_value["gstin"]
            store.address = approval.new_value["address"]
        elif approval.field == "low_stock_threshold":
            store.low_stock_threshold = approval.new_value["threshold"]
        approval.status = "approved"
        approval.approved_by = actor_user_id
        approval.approved_at = datetime.now(timezone.utc)
        self.session.commit()
