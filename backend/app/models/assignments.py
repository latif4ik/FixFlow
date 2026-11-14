import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin
from app.models.enums import AssignmentStatus
from app.models.identity import enum_col

EX_NO_OVERLAP = "ex_assignments_technician_no_overlap"
UQ_ONE_ACTIVE = "uq_assignments_one_active_per_request"


def _mem_fk(col: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", col],
        ["memberships.organization_id", "memberships.id"],
        name=name,
    )


class Assignment(UUIDPkMixin, TimestampMixin, Base):
    """One technician booking of a request. Rows are never deleted (history).

    ``active`` is true exactly while ``status = 'ACTIVE'``; the gist EXCLUDE constraint
    forbids two active rows of one technician from overlapping ([start, end) half-open),
    so concurrent assignment attempts are serialized by PostgreSQL itself.
    """

    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_assignments_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_assignments_request",
        ),
        _mem_fk("technician_membership_id", "fk_assignments_technician"),
        _mem_fk("assigned_by_membership_id", "fk_assignments_assigned_by"),
        _mem_fk("released_by_membership_id", "fk_assignments_released_by"),
        CheckConstraint("end_at >= start_at + interval '30 minutes'", name="min_duration"),
        CheckConstraint("active = (status = 'ACTIVE')", name="active_matches_status"),
        ExcludeConstraint(
            ("technician_membership_id", "="),
            (func.tstzrange(text("start_at"), text("end_at"), text("'[)'")), "&&"),
            using="gist",
            where=text("active"),
            name=EX_NO_OVERLAP,
        ),
        Index(UQ_ONE_ACTIVE, "request_id", unique=True, postgresql_where=text("active")),
        Index(
            "ix_assignments_org_tech_start",
            "organization_id",
            "technician_membership_id",
            "start_at",
        ),
        Index("ix_assignments_org_request", "organization_id", "request_id"),
        Index("ix_assignments_org_start_end", "organization_id", "start_at", "end_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    request_id: Mapped[uuid.UUID] = mapped_column()
    technician_membership_id: Mapped[uuid.UUID] = mapped_column()
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[AssignmentStatus] = mapped_column(enum_col(AssignmentStatus, "status"))
    active: Mapped[bool] = mapped_column(Boolean)
    assigned_by_membership_id: Mapped[uuid.UUID] = mapped_column()
    released_by_membership_id: Mapped[uuid.UUID | None] = mapped_column()
    released_reason: Mapped[str | None] = mapped_column(Text)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyKey(UUIDPkMixin, Base):
    """Generic replay store for retryable commands (API-03)."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "membership_id", "key", name="uq_idempotency_keys_org_member_key"
        ),
        _mem_fk("membership_id", "fk_idempotency_keys_membership"),
        CheckConstraint("char_length(key) BETWEEN 1 AND 128", name="key_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    membership_id: Mapped[uuid.UUID] = mapped_column()
    key: Mapped[str] = mapped_column(String(128))
    endpoint: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[Any] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
