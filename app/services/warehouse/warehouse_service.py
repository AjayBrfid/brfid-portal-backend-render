"""Warehouse registration/settings and vendor+store roster linking."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.core.security import hash_password
from app.models.catalog import SkuSupplyingVendor
from app.models.user import User
from app.models.warehouse import Warehouse, WarehouseStatus, WarehouseStoreLink, WarehouseVendorLink
from app.repositories.user_repository import UserRepository
from app.repositories.warehouse_repository import WarehouseRepository
from app.utils.pagination import PaginationParams


class WarehouseService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = WarehouseRepository(session)
        self.users = UserRepository(session)

    def register_warehouse(
        self,
        business_type: str,
        company_name: str,
        pan: str,
        gstin: str,
        cin: str | None,
        state: str,
        city: str,
        address: str,
        pincode: str,
        warehouse_name: str,
        admin_name: str,
        phone: str,
        email: str,
        temporary_password: str,
    ) -> Warehouse:
        warehouse = self.repo.add(
            Warehouse(
                code=self.repo.next_code(),
                name=warehouse_name,
                business_type=business_type,
                company_name=company_name,
                pan=pan,
                gstin=gstin,
                cin=cin,
                state=state,
                city=city,
                address=address,
                pincode=pincode,
                contact_phone=phone,
                contact_email=email,
                status=WarehouseStatus.PENDING_APPROVAL,
            )
        )
        self.users.add(
            User(
                code=self.users.next_code("warehouse"),
                portal_type="warehouse",
                entity_id=warehouse.id,
                email=email,
                password_hash=hash_password(temporary_password),
                name=admin_name,
                role="wh-admin",
                phone=phone,
                status="active",
            )
        )
        self.session.commit()
        return warehouse

    def get_warehouse(self, warehouse_id: uuid.UUID) -> Warehouse:
        warehouse = self.repo.get_by_id(warehouse_id)
        if not warehouse:
            raise NotFoundException("Warehouse not found")
        return warehouse

    def update_settings(self, warehouse_id: uuid.UUID, **fields) -> Warehouse:
        warehouse = self.get_warehouse(warehouse_id)
        for key, value in fields.items():
            if value is not None:
                setattr(warehouse, key, value)
        self.session.commit()
        return warehouse

    # --- vendor roster ---

    def _vendor_roster_row(self, vendor, link: WarehouseVendorLink | None, sku_count: int) -> dict:
        return {
            "id": vendor.id,
            "code": vendor.code,
            "name": vendor.name,
            "gstin": vendor.gst,
            "city": vendor.city,
            "lead_time_days": vendor.lead_time_days,
            "rating": float(vendor.rating) if vendor.rating is not None else None,
            "sku_count": sku_count,
            "status": link.status.value if link else vendor.status.value,
            "linked_at": link.linked_at if link else None,
        }

    def list_vendor_roster(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None, status: str | None, linked: bool | None):
        from app.models.vendor import Vendor, VendorStatus  # Phase 4

        links = {link.vendor_id: link for link in self.repo.active_vendor_links(warehouse_id)}
        stmt = select(Vendor)
        if linked is True:
            stmt = stmt.where(Vendor.id.in_(links.keys()) if links else Vendor.id.in_([]))
        elif linked is False:
            stmt = stmt.where(Vendor.status == VendorStatus.ACTIVE)
            if links:
                stmt = stmt.where(Vendor.id.notin_(links.keys()))
        if search:
            stmt = stmt.where(Vendor.name.ilike(f"%{search}%"))
        from app.utils.pagination import paginate

        vendors, total = paginate(self.session, stmt, params)

        sku_counts: dict[uuid.UUID, int] = {}
        if vendors:
            rows = self.session.execute(
                select(SkuSupplyingVendor.vendor_id, func.count())
                .where(SkuSupplyingVendor.vendor_id.in_([v.id for v in vendors]))
                .group_by(SkuSupplyingVendor.vendor_id)
            ).all()
            sku_counts = dict(rows)

        items = [self._vendor_roster_row(v, links.get(v.id), sku_counts.get(v.id, 0)) for v in vendors]
        if status:
            items = [i for i in items if i["status"] == status]
        return items, total

    def get_vendor_detail(self, vendor_id: uuid.UUID):
        from app.models.vendor import Vendor  # Phase 4

        vendor = self.session.get(Vendor, vendor_id)
        if not vendor:
            raise NotFoundException("Vendor not found")
        return vendor

    def onboard_vendor(self, name: str, code: str | None, gstin: str, city: str, rating: float | None, lead_time_days: int | None = None):
        from app.models.vendor import Vendor, VendorStatus  # Phase 4
        from app.repositories.vendor_repository import VendorRepository  # Phase 4

        vendor = Vendor(
            code=code or VendorRepository(self.session).next_code(),
            name=name,
            gst=gstin,
            city=city,
            rating=rating,
            lead_time_days=lead_time_days,
            status=VendorStatus.PENDING_APPROVAL,
        )
        self.session.add(vendor)
        self.session.commit()
        return vendor

    def _get_or_create_vendor_link(self, warehouse_id: uuid.UUID, vendor_id: uuid.UUID) -> WarehouseVendorLink:
        link = self.repo.get_vendor_link(warehouse_id, vendor_id)
        if not link:
            link = WarehouseVendorLink(warehouse_id=warehouse_id, vendor_id=vendor_id, status="active")
            self.repo.add_vendor_link(link)
        return link

    def link_vendor(self, warehouse_id: uuid.UUID, vendor_id: uuid.UUID, user_id: uuid.UUID | None = None) -> WarehouseVendorLink:
        vendor = self.get_vendor_detail(vendor_id)
        link = self._get_or_create_vendor_link(warehouse_id, vendor_id)
        link.status = "active"
        link.linked_at = datetime.now(timezone.utc)
        link.unlinked_at = None
        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "warehouse", "Vendor Linked", f"Linked vendor {vendor.name}", "vendor", vendor_id)
        return link

    def unlink_vendor(self, warehouse_id: uuid.UUID, vendor_id: uuid.UUID) -> WarehouseVendorLink:
        link = self._get_or_create_vendor_link(warehouse_id, vendor_id)
        link.unlinked_at = datetime.now(timezone.utc)
        self.session.commit()
        return link

    def update_vendor_status(self, warehouse_id: uuid.UUID, vendor_id: uuid.UUID, status: str) -> WarehouseVendorLink:
        link = self._get_or_create_vendor_link(warehouse_id, vendor_id)
        link.status = status
        self.session.commit()
        return link

    # --- store roster ---

    def list_store_roster(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None, status: str | None, region: str | None, linked: bool | None):
        from app.models.retail import Store, StoreStatus
        from app.utils.pagination import paginate

        links = {link.store_id: link for link in self.repo.active_store_links(warehouse_id)}
        stmt = select(Store)
        if linked is True:
            stmt = stmt.where(Store.id.in_(links.keys()) if links else Store.id.in_([]))
        elif linked is False:
            stmt = stmt.where(Store.status == StoreStatus.ACTIVE)
            if links:
                stmt = stmt.where(Store.id.notin_(links.keys()))
        if search:
            stmt = stmt.where(Store.name.ilike(f"%{search}%"))
        if region:
            stmt = stmt.where(Store.region == region)
        stores, total = paginate(self.session, stmt, params)
        items = []
        for store in stores:
            link = links.get(store.id)
            items.append({"id": store.id, "code": store.code, "name": store.name, "city": store.city, "region": store.region, "status": link.status.value if link else store.status.value, "linked_at": link.linked_at if link else None})
        if status:
            items = [i for i in items if i["status"] == status]
        return items, total

    def get_store_detail(self, store_id: uuid.UUID):
        from app.models.retail import Store

        store = self.session.get(Store, store_id)
        if not store:
            raise NotFoundException("Store not found")
        return store

    def _get_or_create_store_link(self, warehouse_id: uuid.UUID, store_id: uuid.UUID) -> WarehouseStoreLink:
        link = self.repo.get_store_link(warehouse_id, store_id)
        if not link:
            link = WarehouseStoreLink(warehouse_id=warehouse_id, store_id=store_id, status="active")
            self.repo.add_store_link(link)
        return link

    def link_store(self, warehouse_id: uuid.UUID, store_id: uuid.UUID, user_id: uuid.UUID | None = None) -> WarehouseStoreLink:
        store = self.get_store_detail(store_id)
        link = self._get_or_create_store_link(warehouse_id, store_id)
        link.status = "active"
        link.linked_at = datetime.now(timezone.utc)
        link.unlinked_at = None
        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "warehouse", "Store Linked", f"Linked store {store.name}", "store", store_id)
        return link

    def unlink_store(self, warehouse_id: uuid.UUID, store_id: uuid.UUID) -> WarehouseStoreLink:
        link = self._get_or_create_store_link(warehouse_id, store_id)
        link.unlinked_at = datetime.now(timezone.utc)
        self.session.commit()
        return link

    def update_store_status(self, warehouse_id: uuid.UUID, store_id: uuid.UUID, status: str) -> WarehouseStoreLink:
        link = self._get_or_create_store_link(warehouse_id, store_id)
        link.status = status
        self.session.commit()
        return link
