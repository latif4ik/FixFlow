import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin
from app.models.enums import StockMovementKind
from app.models.identity import enum_col


def _mem_fk(col: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organization_id", col], ["memberships.organization_id", "memberships.id"], name=name
    )


class InventoryItem(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_inventory_items_org_code"),
        UniqueConstraint("organization_id", "id", name="uq_inventory_items_org_id"),
        CheckConstraint("char_length(code) BETWEEN 1 AND 40", name="code_length"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        CheckConstraint("char_length(unit) BETWEEN 1 AND 20", name="unit_length"),
        CheckConstraint("stock_quantity >= 0", name="stock_nonneg"),
        CheckConstraint("reorder_threshold >= 0", name="threshold_nonneg"),
        CheckConstraint("unit_price_minor >= 0", name="price_nonneg"),
        Index("ix_inventory_items_org_active", "organization_id", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(20))
    stock_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    reorder_threshold: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_price_minor: Mapped[int] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class MaterialUsage(UUIDPkMixin, Base):
    """Append-only record of materials a technician used (INV-03/05)."""

    __tablename__ = "material_usage"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_material_usage_org_id"),
        UniqueConstraint(
            "organization_id", "client_command_id", name="uq_material_usage_org_client_command"
        ),
        ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_material_usage_request",
        ),
        ForeignKeyConstraint(
            ["organization_id", "item_id"],
            ["inventory_items.organization_id", "inventory_items.id"],
            name="fk_material_usage_item",
        ),
        _mem_fk("technician_membership_id", "fk_material_usage_technician"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_cost_minor_snapshot >= 0", name="unit_cost_nonneg"),
        CheckConstraint("total_cost_minor >= 0", name="total_cost_nonneg"),
        Index("ix_material_usage_request", "request_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    request_id: Mapped[uuid.UUID] = mapped_column()
    item_id: Mapped[uuid.UUID] = mapped_column()
    technician_membership_id: Mapped[uuid.UUID] = mapped_column()
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_cost_minor_snapshot: Mapped[int] = mapped_column(BigInteger)
    total_cost_minor: Mapped[int] = mapped_column(BigInteger)
    client_command_id: Mapped[uuid.UUID] = mapped_column()
    payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class StockMovement(UUIDPkMixin, Base):
    """Append-only stock ledger."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "item_id"],
            ["inventory_items.organization_id", "inventory_items.id"],
            name="fk_stock_movements_item",
        ),
        _mem_fk("actor_membership_id", "fk_stock_movements_actor"),
        ForeignKeyConstraint(
            ["organization_id", "material_usage_id"],
            ["material_usage.organization_id", "material_usage.id"],
            name="fk_stock_movements_usage",
        ),
        CheckConstraint("delta <> 0", name="delta_nonzero"),
        CheckConstraint("stock_after >= 0", name="stock_after_nonneg"),
        Index("ix_stock_movements_item_created", "item_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    item_id: Mapped[uuid.UUID] = mapped_column()
    kind: Mapped[StockMovementKind] = mapped_column(enum_col(StockMovementKind, "kind"))
    delta: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    reason: Mapped[str] = mapped_column(Text)
    actor_membership_id: Mapped[uuid.UUID] = mapped_column()
    material_usage_id: Mapped[uuid.UUID | None] = mapped_column()
    stock_after: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
