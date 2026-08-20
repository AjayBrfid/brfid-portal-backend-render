import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.fulfillment import Inventory
from app.repositories.fulfillment_repository import InventoryRepository
from app.repositories.warehouse_repository import WarehouseRepository
from app.utils.pagination import PaginationParams

DEFAULT_LOW_STOCK_WARNING_UNITS = 20


def _stock_status(available: int, low: int | None, critical: int | None) -> str:
    if available <= 0:
        return "Out of Stock"
    if critical is not None and available <= critical:
        return "Out of Stock"
    effective_low = low if low is not None else DEFAULT_LOW_STOCK_WARNING_UNITS
    if available <= effective_low:
        return "Low Stock"
    return "In-Stock"


class InventoryService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = InventoryRepository(session)
        self.warehouses = WarehouseRepository(session)

    def list_inventory(self, warehouse_id: uuid.UUID, params: PaginationParams, search: str | None, category: str | None, status: str | None):
        warehouse = self.warehouses.get_by_id(warehouse_id)
        all_rows = self.repo.joined_for_warehouse(warehouse_id, search, category)
        variant_ids = [variant.id for _, variant, _ in all_rows]
        reserved_map = self.repo.reserved_by_variant(warehouse_id, variant_ids)

        all_items = []
        for inv, variant, sku in all_rows:
            reserved = reserved_map.get(variant.id, 0)
            row_status = _stock_status(
                inv.available, warehouse.low_stock_warning_units if warehouse else None, warehouse.critical_stock_warning_units if warehouse else None
            )
            all_items.append(
                {"sku": variant.variant_code, "name": sku.name, "category": sku.category, "on_hand": inv.on_hand,
                 "available": inv.available, "reserved": reserved, "returns_qty": inv.returns_qty, "status": row_status}
            )
        if status:
            all_items = [i for i in all_items if i["status"] == status]
        total = len(all_items)
        items = all_items[params.offset : params.offset + params.limit]
        return items, total

    def _get_inventory_row(self, warehouse_id: uuid.UUID, variant_code: str):
        row = self.repo.joined_for_variant_code(warehouse_id, variant_code)
        if not row:
            raise NotFoundException("Inventory row not found")
        return row

    def get_inventory_detail(self, warehouse_id: uuid.UUID, variant_code: str) -> dict:
        inv, variant, sku = self._get_inventory_row(warehouse_id, variant_code)
        reserved = self.repo.reserved_by_variant(warehouse_id, [variant.id]).get(variant.id, 0)
        warehouse = self.warehouses.get_by_id(warehouse_id)
        return {
            "sku": variant.variant_code, "name": sku.name, "category": sku.category, "on_hand": inv.on_hand,
            "available": inv.available, "reserved": reserved, "returns_qty": inv.returns_qty,
            "status": _stock_status(inv.available, warehouse.low_stock_warning_units if warehouse else None, warehouse.critical_stock_warning_units if warehouse else None),
        }

    def get_style_stock(self, warehouse_id: uuid.UUID, style_code: str) -> dict:
        from app.repositories.catalog_repository import CatalogRepository

        catalog = CatalogRepository(self.session)
        sku = catalog.get_sku_by_style_code(style_code)
        if not sku:
            raise NotFoundException("SKU not found")
        variant_ids = [v.id for v in catalog.variants_for_sku(sku.id)]
        rows = self.repo.for_variant_ids(warehouse_id, variant_ids)
        reserved_map = self.repo.reserved_by_variant(warehouse_id, variant_ids)
        return {
            "style_code": style_code,
            "on_hand": sum(r.on_hand for r in rows),
            "available": sum(r.available for r in rows),
            "reserved": sum(reserved_map.values()),
            "returns_qty": sum(r.returns_qty for r in rows),
            "variant_count": len(variant_ids),
        }

    def adjust_inventory(self, warehouse_id: uuid.UUID, variant_code: str, on_hand_delta: int | None, available_delta: int | None) -> Inventory:
        inv, _, _ = self._get_inventory_row(warehouse_id, variant_code)
        if on_hand_delta:
            inv.on_hand += on_hand_delta
        if available_delta:
            inv.available += available_delta
        inv.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        return inv

    def list_reserved(self, warehouse_id: uuid.UUID, params: PaginationParams):
        rows, total = self.repo.joined_reservations(warehouse_id, params)
        items = [
            {"pr_id": pr.ref_code, "store": store.name, "prod": variant.variant_code, "sku": variant.variant_code,
             "reserved_qty": res.reserved_qty, "total_qty": res.total_qty, "vendor_qty": res.vendor_qty, "reserved_at": res.reserved_at}
            for res, pr, store, variant in rows
        ]
        return items, total

    def get_or_create_inventory(self, warehouse_id: uuid.UUID, sku_variant_id: uuid.UUID) -> Inventory:
        inv = self.repo.get(warehouse_id, sku_variant_id)
        if not inv:
            inv = self.repo.add(Inventory(warehouse_id=warehouse_id, sku_variant_id=sku_variant_id, on_hand=0, available=0, returns_qty=0))
        return inv

    def reserve_stock(self, warehouse_id: uuid.UUID, sku_variant_id: uuid.UUID, qty: int) -> None:
        """Decrements available stock. Raises if insufficient — callers must check
        availability themselves first if they need a graceful partial-fulfilment path."""
        inv = self.get_or_create_inventory(warehouse_id, sku_variant_id)
        if inv.available < qty:
            raise ConflictException("Insufficient stock available")
        inv.available -= qty
        inv.updated_at = datetime.now(timezone.utc)

    def increase_on_hand(self, warehouse_id: uuid.UUID, sku_variant_id: uuid.UUID, qty: int) -> None:
        """Accepted ASN units go here — on_hand only, NOT available, since accepted stock
        stays earmarked against the originating PR."""
        inv = self.get_or_create_inventory(warehouse_id, sku_variant_id)
        inv.on_hand += qty
        inv.updated_at = datetime.now(timezone.utc)

    def decrease_on_hand(self, warehouse_id: uuid.UUID, sku_variant_id: uuid.UUID, qty: int) -> None:
        """A unit stops being physically present the moment it's put on a Transfer Order."""
        inv = self.get_or_create_inventory(warehouse_id, sku_variant_id)
        inv.on_hand -= qty
        inv.updated_at = datetime.now(timezone.utc)

