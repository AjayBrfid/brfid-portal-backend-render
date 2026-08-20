import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.vendor import VendorGood
from app.repositories.vendor_repository import VendorRepository
from app.utils.pagination import PaginationParams


def compute_stock_status(quantity: Decimal) -> str:
    if quantity <= 0:
        return "Out of Stock"
    if quantity < 50:
        return "Low Stock"
    return "In Stock"


class GoodsService:
    """A vendor's own raw-material/component supply catalog."""

    def __init__(self, session: Session):
        self.session = session
        self.repo = VendorRepository(session)

    def _to_out(self, good: VendorGood) -> dict:
        return {
            "id": good.id, "code": good.code, "name": good.name, "category": good.category.value, "unit": good.unit.value,
            "quantity": float(good.quantity), "price": float(good.price), "gst_rate": float(good.gst_rate) if good.gst_rate else None,
            "stock_status": good.stock_status.value,
        }

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams):
        rows, total = self.repo.goods_for_vendor(vendor_id, params)
        return [self._to_out(g) for g in rows], total

    def create(self, vendor_id: uuid.UUID, name: str, category: str, unit: str, quantity: Decimal, price: Decimal, gst_rate: Decimal | None) -> dict:
        good = self.repo.add_good(
            VendorGood(
                code=self.repo.next_good_code(), vendor_id=vendor_id, name=name, category=category, unit=unit,
                quantity=quantity, price=price, gst_rate=gst_rate, stock_status=compute_stock_status(quantity),
            )
        )
        self.session.commit()
        return self._to_out(good)

    def update(self, vendor_id: uuid.UUID, good_id: uuid.UUID, **fields) -> dict:
        good = self.repo.get_good(good_id)
        if not good or good.vendor_id != vendor_id:
            raise NotFoundException("Good not found")
        for key, value in fields.items():
            if value is not None:
                setattr(good, key, value)
        if "quantity" in fields and fields["quantity"] is not None:
            good.stock_status = compute_stock_status(good.quantity)
        self.session.commit()
        return self._to_out(good)

    def delete(self, vendor_id: uuid.UUID, good_id: uuid.UUID) -> None:
        good = self.repo.get_good(good_id)
        if not good or good.vendor_id != vendor_id:
            raise NotFoundException("Good not found")
        self.session.delete(good)
        self.session.commit()
