import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPkMixin


class Notification(UUIDPkMixin, Base):
    """In-app notification addressed to ONE membership (so also one org)."""

    __tablename__ = "notifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "recipient_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_notifications_recipient",
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_notifications_request",
        ),
        UniqueConstraint(
            "organization_id",
            "recipient_membership_id",
            "dedupe_key",
            name="uq_notifications_recipient_dedupe",
        ),
        Index(
            "ix_notifications_recipient_read_created",
            "recipient_membership_id",
            "read_at",
            text("created_at DESC"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    recipient_membership_id: Mapped[uuid.UUID] = mapped_column()
    type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    request_id: Mapped[uuid.UUID | None] = mapped_column()
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    dedupe_key: Mapped[str | None] = mapped_column(String(120))
