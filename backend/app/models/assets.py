import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin
from app.models.enums import AssetStatus
from app.models.identity import enum_col


class Property(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "properties"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_properties_org_id"),
        Index("ix_properties_org_active", "organization_id", "is_active"),
        Index("ix_properties_org_name", "organization_id", "name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(Text)
    contact_instructions: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Asset(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "property_id"],
            ["properties.organization_id", "properties.id"],
            name="fk_assets_property",
        ),
        UniqueConstraint("organization_id", "code", name="uq_assets_org_code"),
        UniqueConstraint("organization_id", "id", name="uq_assets_org_id"),
        Index("ix_assets_org_property", "organization_id", "property_id"),
        Index("ix_assets_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    property_id: Mapped[uuid.UUID] = mapped_column()
    code: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(200))
    asset_type: Mapped[str] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(100))
    installed_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[AssetStatus] = mapped_column(
        enum_col(AssetStatus, "asset_status"),
        default=AssetStatus.ACTIVE,
        server_default=AssetStatus.ACTIVE.value,
    )
    notes: Mapped[str | None] = mapped_column(Text)


class PropertyAccess(Base):
    __tablename__ = "property_access"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "property_id"],
            ["properties.organization_id", "properties.id"],
            name="fk_property_access_property",
        ),
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_property_access_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "granted_by_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_property_access_granted_by",
        ),
        Index("ix_property_access_membership_id", "membership_id"),
        Index("ix_property_access_org", "organization_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    property_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    granted_by_membership_id: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
