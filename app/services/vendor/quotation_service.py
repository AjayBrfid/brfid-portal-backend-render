import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.procurement import Quotation, RfqStatus
from app.repositories.procurement_repository import QuotationRepository, RfqRepository
from app.utils.pagination import PaginationParams


class QuotationService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = QuotationRepository(session)
        self.rfqs = RfqRepository(session)

    def submit_quotation(
        self,
        vendor_id: uuid.UUID,
        rfq_id: uuid.UUID,
        unit_price: Decimal,
        tax_percent: Decimal,
        discount_percent: Decimal,
        delivery_days: int,
        warranty: str | None,
        payment_terms: str | None,
        remarks: str | None,
        validity_days: int,
        freight_payer: str,
        freight_details_json: dict | None,
        user_id: uuid.UUID | None = None,
    ) -> Quotation:
        rfq = self.rfqs.get_by_id(rfq_id)
        if not rfq or not self.rfqs.is_vendor_invited(rfq_id, vendor_id):
            raise NotFoundException("RFQ not found")
        # Server computes the total — never trust a client-supplied grand total.
        base = unit_price * rfq.quantity
        discounted = base * (1 - discount_percent / 100)
        total_amount = discounted * (1 + tax_percent / 100)
        quotation = self.repo.add(
            Quotation(
                code=self.repo.next_code(), rfq_id=rfq_id, vendor_id=vendor_id, unit_price=unit_price, tax_percent=tax_percent,
                discount_percent=discount_percent, total_amount=round(total_amount, 2), delivery_days=delivery_days,
                warranty=warranty, payment_terms=payment_terms, remarks=remarks, validity_days=validity_days,
                freight_payer=freight_payer, freight_details_json=freight_details_json,
            )
        )
        # "Partially Responded" only means what it says — fewer distinct vendors have quoted
        # than were invited. Once every invited vendor has responded, it's Ready for Comparison,
        # not still "partial" (the previous logic set Partially Responded unconditionally after
        # any single submission, regardless of how many vendors were actually still outstanding).
        invited_count = len(self.rfqs.invited_vendor_ids(rfq_id))
        responded_count = len({q.vendor_id for q in self.repo.list_for_rfq(rfq_id)})
        rfq.status = RfqStatus.READY_FOR_COMPARISON if responded_count >= invited_count else RfqStatus.PARTIALLY_RESPONDED
        self.session.commit()
        if user_id:
            from app.services.audit_service import AuditService

            AuditService(self.session).log(user_id, "vendor", "Quotation Submitted", f"Quotation {quotation.code} submitted for RFQ {rfq.ref_code}.", "quotation", quotation.id)
        return quotation

    def list_for_vendor(self, vendor_id: uuid.UUID, params: PaginationParams):
        return self.repo.list_for_vendor(vendor_id, params)

    def get_for_vendor(self, vendor_id: uuid.UUID, quotation_id: uuid.UUID) -> Quotation:
        quotation = self.repo.get_for_vendor(vendor_id, quotation_id)
        if not quotation:
            raise NotFoundException("Quotation not found")
        return quotation
