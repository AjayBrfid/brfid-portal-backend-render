import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import InvalidStateTransitionException, NotFoundException
from app.models.user import User
from app.models.warehouse import Warehouse, WarehouseStatus
from app.repositories.warehouse_repository import WarehouseRepository
from app.services.audit_service import AuditService
from app.utils.pagination import PaginationParams


def _zone_to_out(zone, warehouse_code: str, warehouse_name: str) -> dict:
    return {
        "id": zone.id, "warehouse_code": warehouse_code, "warehouse_name": warehouse_name, "name": zone.name,
        "capacity": zone.capacity, "utilized_units": zone.utilized_units, "utilized_pct": zone.utilized_pct,
        "status": zone.status, "product_count": zone.product_count,
    }


def _movement_to_out(movement, warehouse_code: str, warehouse_name: str) -> dict:
    return {
        "id": movement.id, "warehouse_code": warehouse_code, "warehouse_name": warehouse_name,
        "type": movement.type.value, "product_name": movement.product_name, "unit": movement.unit,
        "quantity": float(movement.quantity), "from_location": movement.from_location, "to_location": movement.to_location,
        "reference_id": movement.reference_id, "performed_by": movement.performed_by, "remarks": movement.remarks,
        "occurred_at": movement.occurred_at,
    }


class AdminWarehouseService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = WarehouseRepository(session)

    def _to_out(self, warehouse: Warehouse) -> dict:
        manager = self.repo.manager_name(warehouse.id)
        zones = self.repo.zones_for_warehouse(warehouse.id)
        total_capacity = sum(z.capacity for z in zones)
        total_utilized = sum(z.utilized_units for z in zones)
        utilized_pct = round(100 * total_utilized / total_capacity) if total_capacity else 0
        return {
            "id": warehouse.code, "name": warehouse.name, "city": warehouse.city, "state": warehouse.state,
            "status": warehouse.status.value, "manager": manager, "zone_count": len(zones), "utilized_pct": utilized_pct,
            "registered_on": warehouse.registered_on, "approved_on": warehouse.approved_on,
        }

    def list_warehouses(self, params: PaginationParams, search: str | None, status: str | None):
        rows, total = self.repo.list_all(params, search, status)
        return [self._to_out(w) for w in rows], total

    def stats(self) -> dict:
        return self.repo.count_by_status()

    def _get_or_404(self, code: str) -> Warehouse:
        warehouse = self.repo.get_by_code(code)
        if not warehouse:
            raise NotFoundException(f"Warehouse '{code}' not found")
        return warehouse

    def get_warehouse(self, code: str) -> dict:
        return self._to_out(self._get_or_404(code))

    def approve(self, code: str, admin: User) -> dict:
        warehouse = self._get_or_404(code)
        if warehouse.status != WarehouseStatus.PENDING_APPROVAL:
            raise InvalidStateTransitionException(f"Cannot approve a warehouse with status '{warehouse.status.value}'")
        warehouse.status = WarehouseStatus.ACTIVE
        warehouse.approved_on = datetime.now(timezone.utc)
        warehouse.approved_by = admin.id
        AuditService(self.session).log(admin.id, "super_admin", "WAREHOUSE_APPROVED", f"Warehouse {warehouse.name} ({warehouse.code}) approved.", "warehouse", warehouse.id)
        self.session.commit()
        return {"id": warehouse.code, "status": warehouse.status.value}

    def reject(self, code: str, admin: User, reason: str) -> dict:
        warehouse = self._get_or_404(code)
        if warehouse.status != WarehouseStatus.PENDING_APPROVAL:
            raise InvalidStateTransitionException(f"Cannot reject a warehouse with status '{warehouse.status.value}'")
        warehouse.status = WarehouseStatus.REJECTED
        AuditService(self.session).log(admin.id, "super_admin", "WAREHOUSE_REJECTED", f"Warehouse {warehouse.name} ({warehouse.code}) rejected: {reason}", "warehouse", warehouse.id)
        self.session.commit()
        return {"id": warehouse.code, "status": warehouse.status.value}

    def block(self, code: str, admin: User) -> dict:
        warehouse = self._get_or_404(code)
        if warehouse.status not in (WarehouseStatus.ACTIVE, WarehouseStatus.SUSPENDED):
            raise InvalidStateTransitionException(f"Cannot block a warehouse with status '{warehouse.status.value}'")
        warehouse.status = WarehouseStatus.BLOCKED
        AuditService(self.session).log(admin.id, "super_admin", "WAREHOUSE_BLOCKED", f"Warehouse {warehouse.name} ({warehouse.code}) blocked.", "warehouse", warehouse.id)
        self.session.commit()
        return {"id": warehouse.code, "status": warehouse.status.value}

    def unblock(self, code: str, admin: User) -> dict:
        warehouse = self._get_or_404(code)
        if warehouse.status != WarehouseStatus.BLOCKED:
            raise InvalidStateTransitionException(f"Cannot unblock a warehouse with status '{warehouse.status.value}'")
        warehouse.status = WarehouseStatus.ACTIVE
        AuditService(self.session).log(admin.id, "super_admin", "WAREHOUSE_UNBLOCKED", f"Warehouse {warehouse.name} ({warehouse.code}) unblocked.", "warehouse", warehouse.id)
        self.session.commit()
        return {"id": warehouse.code, "status": warehouse.status.value}

    def list_zones(self, code: str) -> list[dict]:
        warehouse = self._get_or_404(code)
        zones = self.repo.zones_for_warehouse(warehouse.id)
        return [_zone_to_out(z, warehouse.code, warehouse.name) for z in zones]

    def get_zone(self, zone_id: uuid.UUID) -> dict:
        zone = self.repo.get_zone(zone_id)
        if not zone:
            raise NotFoundException("Zone not found")
        warehouse = self.repo.get_by_id(zone.warehouse_id)
        return _zone_to_out(zone, warehouse.code, warehouse.name)

    def list_movements(self, code: str, search: str | None, params: PaginationParams):
        warehouse = self._get_or_404(code)
        movements, total = self.repo.movements_for_warehouse(warehouse.id, search, params)
        return [_movement_to_out(m, warehouse.code, warehouse.name) for m in movements], total
