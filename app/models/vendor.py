"""Vendor entity and its supply/catalog submissions. Reconciled from both source projects:
Vendor's stricter constraints (gst/pan unique, NOT NULL contact fields) and the whole
VendorGood/CatalogSubmission shape follow brfid-portal-backend's more evolved vendor-facing
design; Vendor.lead_time_days is Backend-WH-Retail's own field, used by RFQ eligible-vendor
logic, kept since brfid-portal-backend never modeled it.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _values(enum_cls):
    return [member.value for member in enum_cls]


class VendorStatus(str, enum.Enum):
    PENDING_APPROVAL = "Pending Approval"
    ACTIVE = "Active"
    REJECTED = "Rejected"
    SUSPENDED = "Suspended"
    BLOCKED = "Blocked"


class ComplianceDocType(str, enum.Enum):
    GST_CERT = "gstCert"
    PAN = "pan"
    BUSINESS_LICENSE = "businessLicense"
    MSME = "msme"
    ISO = "iso"


class GoodsCategory(str, enum.Enum):
    FABRIC = "Fabric"
    TRIMS = "Trims"
    PACKAGING = "Packaging"
    OTHER = "Other"


class GoodsUnit(str, enum.Enum):
    METERS = "Meters"
    PCS = "Pcs"
    KG = "Kg"
    ROLLS = "Rolls"


class StockStatus(str, enum.Enum):
    IN_STOCK = "In Stock"
    LOW_STOCK = "Low Stock"
    OUT_OF_STOCK = "Out of Stock"


class CatalogSubmissionStatus(str, enum.Enum):
    SUBMITTED = "Submitted"
    SKU_ASSIGNED = "SKU Assigned"


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_person: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    designation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    office_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, default="India", server_default="India")
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    gst: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    pan: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    cin: Mapped[str | None] = mapped_column(String(21), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_holder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[VendorStatus] = mapped_column(
        Enum(VendorStatus, name="vendor_status", values_callable=_values),
        nullable=False, default=VendorStatus.PENDING_APPROVAL, server_default=VendorStatus.PENDING_APPROVAL.value,
    )
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registered_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    compliance_documents: Mapped[list["VendorComplianceDocument"]] = relationship(back_populates="vendor", cascade="all, delete-orphan")
    goods: Mapped[list["VendorGood"]] = relationship(back_populates="vendor", cascade="all, delete-orphan")

    @property
    def approved(self) -> bool:
        return self.status == VendorStatus.ACTIVE


class VendorComplianceDocument(Base):
    __tablename__ = "vendor_compliance_documents"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    doc_type: Mapped[ComplianceDocType] = mapped_column(Enum(ComplianceDocType, name="compliance_doc_type", values_callable=_values), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    vendor: Mapped["Vendor"] = relationship(back_populates="compliance_documents")


class VendorGood(Base):
    """A vendor's own raw-material/component supply catalog — genuinely absent in
    Backend-WH-Retail, adopted from brfid-portal-backend so `VendorCatalogSubmission.goods_id`
    becomes a real FK instead of a dangling reference."""

    __tablename__ = "vendor_goods"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[GoodsCategory] = mapped_column(Enum(GoodsCategory, name="goods_category", values_callable=_values), nullable=False)
    unit: Mapped[GoodsUnit] = mapped_column(Enum(GoodsUnit, name="goods_unit", values_callable=_values), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    gst_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    stock_status: Mapped[StockStatus] = mapped_column(Enum(StockStatus, name="goods_stock_status", values_callable=_values), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    vendor: Mapped["Vendor"] = relationship(back_populates="goods")


class VendorCatalogSubmission(Base):
    __tablename__ = "vendor_catalog_submissions"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    goods_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendor_goods.id"), nullable=True)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_type: Mapped[str] = mapped_column(String(100), nullable=False)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    fabric: Mapped[str] = mapped_column(String(100), nullable=False)
    colour: Mapped[str] = mapped_column(String(50), nullable=False)
    size: Mapped[str] = mapped_column(String(10), nullable=False)
    gsm: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Real FK (unlike brfid-portal-backend's unconstrained UUID) — sku_variants already lives
    # in this same codebase, so there's no reason to leave this unconstrained.
    sku_variant_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("sku_variants.id"), nullable=True)
    status: Mapped[CatalogSubmissionStatus] = mapped_column(
        Enum(CatalogSubmissionStatus, name="catalog_submission_status", values_callable=_values),
        nullable=False, default=CatalogSubmissionStatus.SUBMITTED, server_default=CatalogSubmissionStatus.SUBMITTED.value,
    )
    submitted_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class VendorCatalogDocument(Base):
    __tablename__ = "vendor_catalog_documents"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("vendor_catalog_submissions.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
