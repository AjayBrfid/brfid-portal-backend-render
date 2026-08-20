import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.shipping import Asn, AsnAttachment, AsnItem, GoodsReceipt, Invoice, Shipment, ShipmentTimelineEvent
from app.utils.codes import next_sequential_code
from app.utils.pagination import PaginationParams, paginate


class AsnRepository:
    def __init__(self, session: Session):
        self.session = session

    def next_ref_code(self) -> str:
        return next_sequential_code(self.session, Asn.ref_code, "ASN")

    def add(self, asn: Asn) -> Asn:
        self.session.add(asn)
        self.session.flush()
        return asn

    def get_by_id(self, asn_id: uuid.UUID) -> Asn | None:
        return self.session.get(Asn, asn_id)

    def list_for_po(self, po_id: uuid.UUID) -> list[Asn]:
        return list(self.session.scalars(select(Asn).where(Asn.po_id == po_id)).all())

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams):
        from app.models.procurement import PurchaseOrder

        stmt = (
            select(Asn)
            .join(PurchaseOrder, PurchaseOrder.id == Asn.po_id)
            .where(PurchaseOrder.vendor_id == vendor_id)
            .order_by(Asn.created_date.desc())
        )
        return paginate(self.session, stmt, params)

    def list_for_warehouse(self, warehouse_id: uuid.UUID, params: PaginationParams, po_id: uuid.UUID | None = None):
        from app.models.procurement import PurchaseOrder

        stmt = (
            select(Asn)
            .join(PurchaseOrder, PurchaseOrder.id == Asn.po_id)
            .where(PurchaseOrder.warehouse_id == warehouse_id)
        )
        if po_id:
            stmt = stmt.where(Asn.po_id == po_id)
        stmt = stmt.order_by(Asn.created_date.desc())
        return paginate(self.session, stmt, params)

    def add_item(self, item: AsnItem) -> AsnItem:
        self.session.add(item)
        self.session.flush()
        return item

    def items_for_asn(self, asn_id: uuid.UUID) -> list[AsnItem]:
        return list(self.session.scalars(select(AsnItem).where(AsnItem.asn_id == asn_id)).all())

    def add_attachment(self, attachment: AsnAttachment) -> AsnAttachment:
        self.session.add(attachment)
        self.session.flush()
        return attachment

    def get_goods_receipt(self, asn_id: uuid.UUID) -> GoodsReceipt | None:
        stmt = select(GoodsReceipt).where(GoodsReceipt.asn_id == asn_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def add_goods_receipt(self, receipt: GoodsReceipt) -> GoodsReceipt:
        self.session.add(receipt)
        self.session.flush()
        return receipt

    def list_goods_receipts(self, params: PaginationParams):
        stmt = select(GoodsReceipt).order_by(GoodsReceipt.inspected_at.desc().nullslast())
        return paginate(self.session, stmt, params)


class ShipmentRepository:
    def __init__(self, session: Session):
        self.session = session

    def next_code(self) -> str:
        return next_sequential_code(self.session, Shipment.code, "ID")

    def get_by_code(self, code: str) -> Shipment | None:
        return self.session.execute(select(Shipment).where(Shipment.code == code)).scalar_one_or_none()

    def add(self, shipment: Shipment) -> Shipment:
        self.session.add(shipment)
        self.session.flush()
        return shipment

    def get_by_id(self, shipment_id: uuid.UUID) -> Shipment | None:
        return self.session.get(Shipment, shipment_id)

    def get_for_asn(self, asn_id: uuid.UUID) -> Shipment | None:
        return self.session.execute(select(Shipment).where(Shipment.asn_id == asn_id)).scalar_one_or_none()

    def get_for_vendor(self, vendor_id: uuid.UUID, shipment_id: uuid.UUID) -> Shipment | None:
        from app.models.procurement import PurchaseOrder

        stmt = (
            select(Shipment)
            .join(Asn, Asn.id == Shipment.asn_id)
            .join(PurchaseOrder, PurchaseOrder.id == Asn.po_id)
            .where(Shipment.id == shipment_id, PurchaseOrder.vendor_id == vendor_id)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams):
        from app.models.procurement import PurchaseOrder

        stmt = (
            select(Shipment)
            .join(Asn, Asn.id == Shipment.asn_id)
            .join(PurchaseOrder, PurchaseOrder.id == Asn.po_id)
            .where(PurchaseOrder.vendor_id == vendor_id)
            .order_by(Shipment.dispatch_date.desc())
        )
        return paginate(self.session, stmt, params)

    def add_timeline_event(self, event: ShipmentTimelineEvent) -> ShipmentTimelineEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def timeline_for_shipment(self, shipment_id: uuid.UUID) -> list[ShipmentTimelineEvent]:
        stmt = select(ShipmentTimelineEvent).where(ShipmentTimelineEvent.shipment_id == shipment_id).order_by(ShipmentTimelineEvent.occurred_at)
        return list(self.session.scalars(stmt).all())


class InvoiceRepository:
    def __init__(self, session: Session):
        self.session = session

    def add(self, invoice: Invoice) -> Invoice:
        self.session.add(invoice)
        self.session.flush()
        return invoice

    def get_by_id(self, invoice_id: uuid.UUID) -> Invoice | None:
        return self.session.get(Invoice, invoice_id)

    def get_for_vendor(self, vendor_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice | None:
        stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.vendor_id == vendor_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams, status: str | None = None):
        stmt = select(Invoice).where(Invoice.vendor_id == vendor_id)
        if status:
            stmt = stmt.where(Invoice.status == status)
        stmt = stmt.order_by(Invoice.invoice_date.desc())
        return paginate(self.session, stmt, params)

    def list_for_warehouse(self, warehouse_id: uuid.UUID, params: PaginationParams, status: str | None = None, po_id: uuid.UUID | None = None):
        from app.models.procurement import PurchaseOrder

        stmt = (
            select(Invoice)
            .join(PurchaseOrder, PurchaseOrder.id == Invoice.po_id)
            .where(PurchaseOrder.warehouse_id == warehouse_id)
        )
        if status:
            stmt = stmt.where(Invoice.status == status)
        if po_id:
            stmt = stmt.where(Invoice.po_id == po_id)
        stmt = stmt.order_by(Invoice.invoice_date.desc())
        return paginate(self.session, stmt, params)
