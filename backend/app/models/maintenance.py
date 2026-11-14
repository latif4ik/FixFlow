import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin
from app.models.enums import Priority, Recurrence
from app.models.identity import enum_col


class MaintenancePlan(UUIDPkMixin, TimestampMixin, Base):
    """Recurring preventive-maintenance plan for one asset (PM-01)."""

    __tablename__ = "maintenance_plans"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_maintenance_plans_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "asset_id"],
            ["assets.organization_id", "assets.id"],
            name="fk_maintenance_plans_asset",
        ),
        ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["service_categories.organization_id", "service_categories.id"],
            name="fk_maintenance_plans_category",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_maintenance_plans_created_by",
        ),
        CheckConstraint("char_length(title) BETWEEN 5 AND 100", name="title_length"),
        Index("ix_maintenance_plans_org_asset", "organization_id", "asset_id"),
        Index("ix_maintenance_plans_org_enabled", "organization_id", "is_enabled"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    asset_id: Mapped[uuid.UUID] = mapped_column()
    category_id: Mapped[uuid.UUID] = mapped_column()
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[Priority] = mapped_column(
        enum_col(Priority, "priority"),
        default=Priority.NORMAL,
        server_default=Priority.NORMAL.value,
    )
    first_date: Mapped[date] = mapped_column(Date)
    recurrence: Mapped[Recurrence] = mapped_column(enum_col(Recurrence, "recurrence"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_generated_for: Mapped[date | None] = mapped_column(Date)
    created_by_membership_id: Mapped[uuid.UUID] = mapped_column()
