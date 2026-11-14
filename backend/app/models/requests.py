import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin
from app.models.enums import FilePurpose, NoteKind, NoteVisibility, Priority, RequestStatus
from app.models.identity import enum_col


def _mem_fk(col: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", col],
        ["memberships.organization_id", "memberships.id"],
        name=name,
    )


class ServiceRequest(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "service_requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "number", name="uq_service_requests_org_number"),
        UniqueConstraint("organization_id", "id", name="uq_service_requests_org_id"),
        _mem_fk("requester_membership_id", "fk_service_requests_requester"),
        _mem_fk("created_by_membership_id", "fk_service_requests_created_by"),
        ForeignKeyConstraint(
            ["organization_id", "property_id"],
            ["properties.organization_id", "properties.id"],
            name="fk_service_requests_property",
        ),
        ForeignKeyConstraint(
            ["organization_id", "property_id", "asset_id"],
            ["assets.organization_id", "assets.property_id", "assets.id"],
            name="fk_service_requests_asset",
        ),
        ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["service_categories.organization_id", "service_categories.id"],
            name="fk_service_requests_category",
        ),
        ForeignKeyConstraint(
            ["organization_id", "duplicate_of_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_service_requests_duplicate_of",
        ),
        ForeignKeyConstraint(
            ["organization_id", "plan_id"],
            ["maintenance_plans.organization_id", "maintenance_plans.id"],
            name="fk_service_requests_plan",
        ),
        UniqueConstraint("plan_id", "occurrence_date", name="uq_service_requests_plan_occurrence"),
        CheckConstraint(
            "(plan_id IS NULL) = (occurrence_date IS NULL)", name="plan_occurrence_together"
        ),
        CheckConstraint(
            "sla_outcome IS NULL OR sla_outcome IN ('MET', 'BREACHED')", name="sla_outcome_valid"
        ),
        Index(
            "ix_service_requests_org_sla_due",
            "organization_id",
            "sla_due_at",
            postgresql_where=text("sla_due_at IS NOT NULL"),
        ),
        CheckConstraint("duplicate_of_id <> id", name="not_self_duplicate"),
        CheckConstraint(
            "preferred_window_start IS NULL OR preferred_window_end IS NULL "
            "OR preferred_window_end > preferred_window_start",
            name="preferred_window_order",
        ),
        Index("ix_service_requests_org_status", "organization_id", "status"),
        Index("ix_service_requests_org_created", "organization_id", text("created_at DESC")),
        Index("ix_service_requests_org_requester", "organization_id", "requester_membership_id"),
        Index("ix_service_requests_org_property", "organization_id", "property_id"),
        Index("ix_service_requests_org_priority", "organization_id", "priority"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    number: Mapped[int] = mapped_column(Integer)
    requester_membership_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by_membership_id: Mapped[uuid.UUID | None] = mapped_column()
    property_id: Mapped[uuid.UUID] = mapped_column()
    asset_id: Mapped[uuid.UUID | None] = mapped_column()
    category_id: Mapped[uuid.UUID] = mapped_column()
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[Priority] = mapped_column(
        enum_col(Priority, "priority"),
        default=Priority.NORMAL,
        server_default=Priority.NORMAL.value,
    )
    status: Mapped[RequestStatus] = mapped_column(
        enum_col(RequestStatus, "status"),
        default=RequestStatus.SUBMITTED,
        server_default=RequestStatus.SUBMITTED.value,
    )
    preferred_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preferred_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Preventive maintenance traceability (PM-02/03): unique (plan, occurrence).
    plan_id: Mapped[uuid.UUID | None] = mapped_column()
    occurrence_date: Mapped[date | None] = mapped_column(Date)
    # SLA cache (Phase 3b), maintained by app.sla.service.recompute_sla from request_events.
    sla_budget_minutes: Mapped[int | None] = mapped_column(Integer)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_at_risk_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sla_consumed_minutes: Mapped[int | None] = mapped_column(Integer)  # frozen at stop
    sla_outcome: Mapped[str | None] = mapped_column(String(10))  # MET | BREACHED
    sla_stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overdue_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RequestEvent(UUIDPkMixin, Base):
    """Append-only per-request timeline; also the future SLA event source."""

    __tablename__ = "request_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_request_events_request",
        ),
        _mem_fk("actor_membership_id", "fk_request_events_actor"),
        Index("ix_request_events_request_created", "request_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    request_id: Mapped[uuid.UUID] = mapped_column()
    type: Mapped[str] = mapped_column(String(60))
    actor_membership_id: Mapped[uuid.UUID | None] = mapped_column()
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class WorkNote(UUIDPkMixin, Base):
    """Immutable note (UPDATE/DELETE rejected by a DB trigger)."""

    __tablename__ = "work_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_work_notes_request",
        ),
        _mem_fk("author_membership_id", "fk_work_notes_author"),
        UniqueConstraint("organization_id", "id", name="uq_work_notes_org_id"),
        UniqueConstraint(
            "organization_id", "client_command_id", name="uq_work_notes_org_client_command"
        ),
        Index("ix_work_notes_request_created", "request_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    request_id: Mapped[uuid.UUID] = mapped_column()
    author_membership_id: Mapped[uuid.UUID] = mapped_column()
    visibility: Mapped[NoteVisibility] = mapped_column(enum_col(NoteVisibility, "visibility"))
    kind: Mapped[NoteKind] = mapped_column(enum_col(NoteKind, "kind"))
    body: Mapped[str] = mapped_column(Text)
    client_command_id: Mapped[uuid.UUID | None] = mapped_column()
    payload_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class EvidenceFile(UUIDPkMixin, Base):
    __tablename__ = "evidence_files"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_evidence_files_request",
        ),
        _mem_fk("uploaded_by_membership_id", "fk_evidence_files_uploader"),
        ForeignKeyConstraint(
            ["organization_id", "note_id"],
            ["work_notes.organization_id", "work_notes.id"],
            name="fk_evidence_files_note",
        ),
        UniqueConstraint(
            "organization_id",
            "client_command_id",
            "client_index",
            name="uq_evidence_files_org_client_command",
        ),
        Index("ix_evidence_files_request", "request_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    request_id: Mapped[uuid.UUID] = mapped_column()
    uploaded_by_membership_id: Mapped[uuid.UUID] = mapped_column()
    note_id: Mapped[uuid.UUID | None] = mapped_column()
    purpose: Mapped[FilePurpose] = mapped_column(enum_col(FilePurpose, "purpose"))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    client_command_id: Mapped[uuid.UUID | None] = mapped_column()
    client_index: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
