import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPkMixin


class Feedback(UUIDPkMixin, Base):
    """Requester satisfaction rating (one per request, immutable via DB trigger)."""

    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_feedback_request_id"),
        ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_feedback_request",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requester_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_feedback_requester",
        ),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        CheckConstraint("comment IS NULL OR char_length(comment) <= 2000", name="comment_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    request_id: Mapped[uuid.UUID] = mapped_column()
    requester_membership_id: Mapped[uuid.UUID] = mapped_column()
    rating: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StreamTicket(UUIDPkMixin, Base):
    """Short-lived opaque credential for the SSE endpoint (EventSource cannot send headers)."""

    __tablename__ = "stream_tickets"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_stream_tickets_token_hash"),
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_stream_tickets_membership",
        ),
        Index("ix_stream_tickets_expires_at", "expires_at"),
    )

    token_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # The login session the ticket was minted from: revoking it ends open streams.
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    membership_id: Mapped[uuid.UUID] = mapped_column()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
