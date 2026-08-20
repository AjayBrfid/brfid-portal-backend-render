import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, InvalidStateTransitionException, NotFoundException
from app.core.security import hash_password
from app.models.user import User
from app.models.vendor import Vendor, VendorStatus
from app.repositories.user_repository import UserRepository
from app.repositories.vendor_repository import VendorRepository
from app.services.audit_service import AuditService
from app.utils.pagination import PaginationParams


class AdminVendorService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = VendorRepository(session)
        self.users = UserRepository(session)

    def _to_out(self, vendor: Vendor) -> dict:
        return {
            "id": vendor.code, "name": vendor.name, "category": vendor.category, "city": vendor.city,
            "status": vendor.status.value, "rating": float(vendor.rating) if vendor.rating else None,
            "lead_time_days": vendor.lead_time_days, "registered_on": vendor.registered_on, "approved_on": vendor.approved_on,
        }

    def list_vendors(self, params: PaginationParams, search: str | None, status: str | None, sort: str | None = None, order: str | None = None):
        rows, total = self.repo.list_all(params, search, status, sort, order)
        return [self._to_out(v) for v in rows], total

    def stats(self) -> dict:
        return self.repo.count_by_status()

    def _get_or_404(self, code: str) -> Vendor:
        vendor = self.repo.get_by_code(code)
        if not vendor:
            raise NotFoundException(f"Vendor '{code}' not found")
        return vendor

    def get_vendor(self, code: str) -> dict:
        return self._to_out(self._get_or_404(code))

    def approve(self, code: str, admin: User) -> dict:
        vendor = self._get_or_404(code)
        if vendor.status != VendorStatus.PENDING_APPROVAL:
            raise InvalidStateTransitionException(f"Cannot approve a vendor with status '{vendor.status.value}'")
        vendor.status = VendorStatus.ACTIVE
        vendor.approved_on = datetime.now(timezone.utc)
        vendor.approved_by = admin.id
        AuditService(self.session).log(admin.id, "super_admin", "VENDOR_APPROVED", f"Vendor {vendor.name} ({vendor.code}) approved.", "vendor", vendor.id)
        self.session.commit()
        return {"id": vendor.code, "status": vendor.status.value}

    def reject(self, code: str, admin: User, reason: str) -> dict:
        vendor = self._get_or_404(code)
        if vendor.status != VendorStatus.PENDING_APPROVAL:
            raise InvalidStateTransitionException(f"Cannot reject a vendor with status '{vendor.status.value}'")
        vendor.status = VendorStatus.REJECTED
        AuditService(self.session).log(admin.id, "super_admin", "VENDOR_REJECTED", f"Vendor {vendor.name} ({vendor.code}) rejected: {reason}", "vendor", vendor.id)
        self.session.commit()
        return {"id": vendor.code, "status": vendor.status.value}

    def block(self, code: str, admin: User) -> dict:
        vendor = self._get_or_404(code)
        if vendor.status not in (VendorStatus.ACTIVE, VendorStatus.SUSPENDED):
            raise InvalidStateTransitionException(f"Cannot block a vendor with status '{vendor.status.value}'")
        vendor.status = VendorStatus.BLOCKED
        AuditService(self.session).log(admin.id, "super_admin", "VENDOR_BLOCKED", f"Vendor {vendor.name} ({vendor.code}) blocked.", "vendor", vendor.id)
        self.session.commit()
        return {"id": vendor.code, "status": vendor.status.value}

    def unblock(self, code: str, admin: User) -> dict:
        vendor = self._get_or_404(code)
        if vendor.status != VendorStatus.BLOCKED:
            raise InvalidStateTransitionException(f"Cannot unblock a vendor with status '{vendor.status.value}'")
        vendor.status = VendorStatus.ACTIVE
        AuditService(self.session).log(admin.id, "super_admin", "VENDOR_UNBLOCKED", f"Vendor {vendor.name} ({vendor.code}) unblocked.", "vendor", vendor.id)
        self.session.commit()
        return {"id": vendor.code, "status": vendor.status.value}

    def set_vendor_password(self, code: str, new_password: str) -> None:
        vendor = self._get_or_404(code)
        user = self.users.get_by_portal_email("vendor", vendor.contact_email)
        if not user:
            raise NotFoundException("No login account found for this vendor")
        user.password_hash = hash_password(new_password)
        self.session.commit()

    def list_vendor_stock(self, params: PaginationParams, search: str | None = None):
        from app.services.vendor.goods_service import GoodsService

        # Cross-vendor stock view — not scoped to one vendor_id, unlike GoodsService's normal use.
        from app.models.vendor import VendorGood
        from app.utils.pagination import paginate
        from sqlalchemy import select

        stmt = select(VendorGood)
        if search:
            stmt = stmt.where(VendorGood.name.ilike(f"%{search}%"))
        rows, total = paginate(self.session, stmt, params)
        items = [{"id": g.id, "vendor_id": g.vendor_id, "name": g.name, "category": g.category.value, "quantity": float(g.quantity), "stock_status": g.stock_status.value} for g in rows]
        return items, total

    def list_vendor_catalog(self, params: PaginationParams, search: str | None = None, status: str | None = None):
        from app.services.vendor.catalog_service import CatalogService

        rows, total = CatalogService(self.session).list_all(params, search, status)
        return [
            {"id": r.id, "code": r.code, "vendor_id": r.vendor_id, "name": r.name, "product_type": r.product_type, "status": r.status.value, "submitted_date": r.submitted_date}
            for r in rows
        ], total

    def get_vendor_catalog_submission(self, submission_id: uuid.UUID):
        row = self.repo.get_catalog_submission(submission_id)
        if not row:
            raise NotFoundException("Catalog submission not found")
        return row

    def _ensure_stock_rows_everywhere(self, variant_id: uuid.UUID) -> None:
        """A newly-approved (or newly-linked) SKU variant should show up as "0 on hand"/"0 in
        stock" in every warehouse's Inventory screen and every store's Stock screen
        immediately, not stay invisible until that location happens to receive a shipment."""
        from app.models.fulfillment import Inventory
        from app.models.retail import StoreInventory
        from app.repositories.retail_repository import RetailRepository
        from app.repositories.warehouse_repository import WarehouseRepository

        warehouse_ids = WarehouseRepository(self.session).list_active_ids()
        existing_wh = set(
            self.session.execute(select(Inventory.warehouse_id).where(Inventory.sku_variant_id == variant_id)).scalars().all()
        )
        for warehouse_id in warehouse_ids:
            if warehouse_id not in existing_wh:
                self.session.add(Inventory(warehouse_id=warehouse_id, sku_variant_id=variant_id, on_hand=0, available=0, returns_qty=0))

        store_ids = RetailRepository(self.session).list_active_ids()
        existing_store = set(
            self.session.execute(select(StoreInventory.store_id).where(StoreInventory.sku_variant_id == variant_id)).scalars().all()
        )
        for store_id in store_ids:
            if store_id not in existing_store:
                self.session.add(StoreInventory(store_id=store_id, sku_variant_id=variant_id, quantity=0))

    def generate_sku(self, submission_id: uuid.UUID, admin: User, style_code: str | None, hsn: str | None, gst_rate, mrp) -> dict:
        from app.models.catalog import Sku, SkuStatus, SkuSupplyingVendor, SkuVariant
        from app.repositories.catalog_repository import CatalogRepository
        from app.utils.sku_codes import build_variant_code, next_style_code, sanitize_style_code

        submission = self.get_vendor_catalog_submission(submission_id)
        if submission.status.value != "Submitted":
            raise ConflictException("This submission has already been assigned a SKU")

        repo = CatalogRepository(self.session)
        if style_code:
            style_code = sanitize_style_code(style_code)
            if repo.get_sku_by_style_code(style_code):
                raise ConflictException(f"Style code '{style_code}' is already in use")
        else:
            style_code = next_style_code(self.session)

        match = repo.find_matching_variant(
            submission.product_type, submission.gender, submission.fabric, str(submission.gsm), submission.colour, submission.size,
        )
        if match:
            variant, sku = match
            if not self.session.get(SkuSupplyingVendor, (variant.id, submission.vendor_id)):
                self.session.add(SkuSupplyingVendor(sku_variant_id=variant.id, vendor_id=submission.vendor_id))
            submission.sku_variant_id = variant.id
            submission.status = "SKU Assigned"
            self._ensure_stock_rows_everywhere(variant.id)
            AuditService(self.session).log(
                admin.id, "super_admin", "SKU Added",
                f"Catalog submission matched existing SKU {sku.style_code} ({variant.variant_code}) — linked as an additional supplier instead of creating a duplicate SKU.",
                "sku", sku.id,
            )
            self.session.commit()
            return {"sku_id": sku.id, "sku_variant_id": variant.id, "style_code": sku.style_code, "variant_code": variant.variant_code, "matched_existing": True}

        sku = Sku(
            style_code=style_code, name=submission.name, category=submission.product_type, gender=submission.gender,
            fabric=submission.fabric, gsm=str(submission.gsm), hsn=hsn, gst_rate=gst_rate, mrp=mrp, status=SkuStatus.ACTIVE,
            published_by=admin.id,
        )
        self.session.add(sku)
        self.session.flush()
        variant = SkuVariant(sku_id=sku.id, variant_code=build_variant_code(style_code, submission.colour, submission.size), colour=submission.colour, size=submission.size)
        self.session.add(variant)
        self.session.flush()
        self.session.add(SkuSupplyingVendor(sku_variant_id=variant.id, vendor_id=submission.vendor_id))
        submission.sku_variant_id = variant.id
        submission.status = "SKU Assigned"
        self._ensure_stock_rows_everywhere(variant.id)
        AuditService(self.session).log(admin.id, "super_admin", "SKU Added", f"SKU {style_code} generated from vendor catalog submission.", "sku", sku.id)
        self.session.commit()
        return {"sku_id": sku.id, "sku_variant_id": variant.id, "style_code": style_code, "variant_code": variant.variant_code, "matched_existing": False}
