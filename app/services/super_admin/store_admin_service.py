from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import InvalidStateTransitionException, NotFoundException
from app.models.retail import Store, StoreStatus
from app.models.user import User
from app.repositories.retail_repository import RetailRepository
from app.services.audit_service import AuditService
from app.utils.pagination import PaginationParams


class AdminStoreService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = RetailRepository(session)

    def _to_out(self, store: Store) -> dict:
        return {
            "id": store.code, "name": store.name, "store_type": store.store_type.value, "city": store.city,
            "state": store.state, "status": store.status.value, "opened_on": store.opened_on, "approved_on": store.approved_on,
        }

    def list_stores(self, params: PaginationParams, search: str | None, status: str | None):
        rows, total = self.repo.list_all(params, search, status)
        return [self._to_out(s) for s in rows], total

    def stats(self) -> dict:
        return self.repo.count_by_status()

    def _get_or_404(self, code: str) -> Store:
        store = self.repo.get_by_code(code)
        if not store:
            raise NotFoundException(f"Store '{code}' not found")
        return store

    def get_store(self, code: str) -> dict:
        return self._to_out(self._get_or_404(code))

    def approve(self, code: str, admin: User) -> dict:
        store = self._get_or_404(code)
        if store.status != StoreStatus.PENDING_APPROVAL:
            raise InvalidStateTransitionException(f"Cannot approve a store with status '{store.status.value}'")
        store.status = StoreStatus.ACTIVE
        store.approved_on = datetime.now(timezone.utc)
        store.approved_by = admin.id
        AuditService(self.session).log(admin.id, "super_admin", "STORE_APPROVED", f"Store {store.name} ({store.code}) approved.", "store", store.id)
        self.session.commit()
        return {"id": store.code, "status": store.status.value}

    def reject(self, code: str, admin: User, reason: str) -> dict:
        store = self._get_or_404(code)
        if store.status != StoreStatus.PENDING_APPROVAL:
            raise InvalidStateTransitionException(f"Cannot reject a store with status '{store.status.value}'")
        store.status = StoreStatus.REJECTED
        AuditService(self.session).log(admin.id, "super_admin", "STORE_REJECTED", f"Store {store.name} ({store.code}) rejected: {reason}", "store", store.id)
        self.session.commit()
        return {"id": store.code, "status": store.status.value}

    def block(self, code: str, admin: User) -> dict:
        store = self._get_or_404(code)
        if store.status not in (StoreStatus.ACTIVE, StoreStatus.INACTIVE):
            raise InvalidStateTransitionException(f"Cannot block a store with status '{store.status.value}'")
        store.status = StoreStatus.BLOCKED
        AuditService(self.session).log(admin.id, "super_admin", "STORE_BLOCKED", f"Store {store.name} ({store.code}) blocked.", "store", store.id)
        self.session.commit()
        return {"id": store.code, "status": store.status.value}

    def unblock(self, code: str, admin: User) -> dict:
        store = self._get_or_404(code)
        if store.status != StoreStatus.BLOCKED:
            raise InvalidStateTransitionException(f"Cannot unblock a store with status '{store.status.value}'")
        store.status = StoreStatus.ACTIVE
        AuditService(self.session).log(admin.id, "super_admin", "STORE_UNBLOCKED", f"Store {store.name} ({store.code}) unblocked.", "store", store.id)
        self.session.commit()
        return {"id": store.code, "status": store.status.value}

    def list_store_inventory(self, code: str, params: PaginationParams):
        store = self._get_or_404(code)
        rows = self.repo.inventory_for_store(store.id)
        total = len(rows)
        page_rows = rows[params.offset : params.offset + params.limit]
        items = [
            {"sku": variant.variant_code, "name": sku.name, "category": sku.category, "stock": inv.quantity, "reorder_level": inv.reorder_level}
            for inv, variant, sku in page_rows
        ]
        return items, total
