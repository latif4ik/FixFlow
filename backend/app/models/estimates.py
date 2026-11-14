import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin
from app.models.enums import EstimateStatus
from app.models.identity import enum_col


def _mem_fk(col: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", col], ["memberships.organization_id", "memberships.id"], name=name
    )


class Estimate(UUIDPkMixin, TimestampMixin, Base):
    """One version of a request's estimate. Content is immutable once not DRAFT (DB trigger)."""

    __tablename__ = "estimates"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_estimates_org_id"),
        UniqueConstraint("request_id", "version", name="uq_estimates_request_version"),
        ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_estimates_request",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supersedes_id"],
            ["estimates.organization_id", "estimates.id"],
            name="fk_estimates_supersedes",
        ),
        _mem_fk("created_by_membership_id", "fk_estimates_created_by"),
        _mem_fk("submitted_by_membership_id", "fk_estimates_submitted_by"),
        _mem_fk("decided_by_membership_id", "fk_estimates_decided_by"),
        _mem_fk("withdrawn_by_membership_id", "fk_estimates_withdrawn_by"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("labor_minutes >= 0", name="labor_minutes_nonneg"),
        CheckConstraint("labor_rate_minor >= 0", name="labor_rate_nonneg"),
        CheckConstraint("labor_cost_minor >= 0", name="labor_cost_nonneg"),
        CheckConstraint("materials_total_minor >= 0", name="materials_total_nonneg"),
        CheckConstraint("total_minor >= 0", name="total_nonneg"),
        CheckConstraint("currency = 'KGS'", name="currency_kgs"),
        Index(
            "uq_estimates_one_draft_per_request",
            "request_id",
            unique=True,
            postgresql_where=text("status = 'DRAFT'"),
        ),
        Index(
            "uq_estimates_one_pending_per_request",
            "request_id",
            unique=True,
            postgresql_where=text("status = 'AWAITING_APPROVAL'"),
        ),
        Index("ix_estimates_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    request_id: Mapped[uuid.UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[EstimateStatus] = mapped_column(enum_col(EstimateStatus, "status"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column()
    labor_minutes: Mapped[int] = mapped_column(Integer)
    labor_rate_minor: Mapped[int] = mapped_column(BigInteger)
    labor_cost_minor: Mapped[int] = mapped_column(BigInteger)
    materials_total_minor: Mapped[int] = mapped_column(BigInteger)
    total_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="KGS", server_default="KGS")
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_membership_id: Mapped[uuid.UUID] = mapped_column()
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by_membership_id: Mapped[uuid.UUID | None] = mapped_column()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_membership_id: Mapped[uuid.UUID | None] = mapped_column()
    decision_reason: Mapped[str | None] = mapped_column(Text)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_by_membership_id: Mapped[uuid.UUID | None] = mapped_column()
    withdraw_reason: Mapped[str | None] = mapped_column(Text)


class EstimateLine(UUIDPkMixin, Base):
    __tablename__ = "estimate_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "estimate_id"],
            ["estimates.organization_id", "estimates.id"],
            name="fk_estimate_lines_estimate",
        ),
        ForeignKeyConstraint(
            ["organization_id", "inventory_item_id"],
            ["inventory_items.organization_id", "inventory_items.id"],
            name="fk_estimate_lines_item",
        ),
        UniqueConstraint("estimate_id", "position", name="uq_estimate_lines_estimate_position"),
        CheckConstraint("char_length(description) BETWEEN 1 AND 300", name="description_length"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price_minor >= 0", name="unit_price_nonneg"),
        CheckConstraint("line_total_minor >= 0", name="line_total_nonneg"),
        Index("ix_estimate_lines_estimate", "estimate_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    estimate_id: Mapped[uuid.UUID] = mapped_column()
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(300))
    inventory_item_id: Mapped[uuid.UUID | None] = mapped_column()
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_price_minor: Mapped[int] = mapped_column(BigInteger)
    line_total_minor: Mapped[int] = mapped_column(BigInteger)
