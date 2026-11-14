"""estimates, inventory + material usage, notifications

Revision ID: 0005_estimates_inventory
Revises: 0004_assignments
Create Date: 2026-11-15 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_estimates_inventory"
down_revision: str | None = "0004_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _mem_fk(col: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id", col], ["memberships.organization_id", "memberships.id"], name=name
    )


def _org_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name=op.f(f"fk_{table}_organization_id_organizations"),
    )


def _created_updated() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _clock_created() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("clock_timestamp()"),
        nullable=False,
    )


def upgrade() -> None:
    num = sa.Numeric(12, 3)
    op.create_table(
        "inventory_items",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("stock_quantity", num, nullable=False),
        sa.Column("reorder_threshold", num, nullable=False),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_created_updated(),
        sa.CheckConstraint("char_length(code) BETWEEN 1 AND 40", name="code_length"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
        sa.CheckConstraint("char_length(unit) BETWEEN 1 AND 20", name="unit_length"),
        sa.CheckConstraint("stock_quantity >= 0", name="stock_nonneg"),
        sa.CheckConstraint("reorder_threshold >= 0", name="threshold_nonneg"),
        sa.CheckConstraint("unit_price_minor >= 0", name="price_nonneg"),
        _org_fk("inventory_items"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inventory_items")),
        sa.UniqueConstraint("organization_id", "code", name="uq_inventory_items_org_code"),
        sa.UniqueConstraint("organization_id", "id", name="uq_inventory_items_org_id"),
    )
    op.create_index(
        "ix_inventory_items_org_active", "inventory_items", ["organization_id", "is_active"]
    )

    op.create_table(
        "estimates",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "AWAITING_APPROVAL",
                "APPROVED",
                "REJECTED",
                "SUPERSEDED",
                name="status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("labor_minutes", sa.Integer(), nullable=False),
        sa.Column("labor_rate_minor", sa.BigInteger(), nullable=False),
        sa.Column("labor_cost_minor", sa.BigInteger(), nullable=False),
        sa.Column("materials_total_minor", sa.BigInteger(), nullable=False),
        sa.Column("total_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="KGS", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by_membership_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_membership_id", sa.Uuid(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_by_membership_id", sa.Uuid(), nullable=True),
        sa.Column("withdraw_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_created_updated(),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint("labor_minutes >= 0", name="labor_minutes_nonneg"),
        sa.CheckConstraint("labor_rate_minor >= 0", name="labor_rate_nonneg"),
        sa.CheckConstraint("labor_cost_minor >= 0", name="labor_cost_nonneg"),
        sa.CheckConstraint("materials_total_minor >= 0", name="materials_total_nonneg"),
        sa.CheckConstraint("total_minor >= 0", name="total_nonneg"),
        sa.CheckConstraint("currency = 'KGS'", name="currency_kgs"),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_estimates_request",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supersedes_id"],
            ["estimates.organization_id", "estimates.id"],
            name="fk_estimates_supersedes",
        ),
        _mem_fk("created_by_membership_id", "fk_estimates_created_by"),
        _mem_fk("submitted_by_membership_id", "fk_estimates_submitted_by"),
        _mem_fk("decided_by_membership_id", "fk_estimates_decided_by"),
        _mem_fk("withdrawn_by_membership_id", "fk_estimates_withdrawn_by"),
        _org_fk("estimates"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_estimates")),
        sa.UniqueConstraint("organization_id", "id", name="uq_estimates_org_id"),
        sa.UniqueConstraint("request_id", "version", name="uq_estimates_request_version"),
    )
    op.create_index(
        "uq_estimates_one_draft_per_request",
        "estimates",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"),
    )
    op.create_index(
        "uq_estimates_one_pending_per_request",
        "estimates",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("status = 'AWAITING_APPROVAL'"),
    )
    op.create_index("ix_estimates_org_status", "estimates", ["organization_id", "status"])

    op.create_table(
        "estimate_lines",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("estimate_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("inventory_item_id", sa.Uuid(), nullable=True),
        sa.Column("quantity", num, nullable=False),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("line_total_minor", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("char_length(description) BETWEEN 1 AND 300", name="description_length"),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("unit_price_minor >= 0", name="unit_price_nonneg"),
        sa.CheckConstraint("line_total_minor >= 0", name="line_total_nonneg"),
        sa.ForeignKeyConstraint(
            ["organization_id", "estimate_id"],
            ["estimates.organization_id", "estimates.id"],
            name="fk_estimate_lines_estimate",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "inventory_item_id"],
            ["inventory_items.organization_id", "inventory_items.id"],
            name="fk_estimate_lines_item",
        ),
        _org_fk("estimate_lines"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_estimate_lines")),
        sa.UniqueConstraint("estimate_id", "position", name="uq_estimate_lines_estimate_position"),
    )
    op.create_index("ix_estimate_lines_estimate", "estimate_lines", ["estimate_id"])

    op.create_table(
        "material_usage",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("technician_membership_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", num, nullable=False),
        sa.Column("unit_cost_minor_snapshot", sa.BigInteger(), nullable=False),
        sa.Column("total_cost_minor", sa.BigInteger(), nullable=False),
        sa.Column("client_command_id", sa.Uuid(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        _clock_created(),
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("unit_cost_minor_snapshot >= 0", name="unit_cost_nonneg"),
        sa.CheckConstraint("total_cost_minor >= 0", name="total_cost_nonneg"),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_material_usage_request",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "item_id"],
            ["inventory_items.organization_id", "inventory_items.id"],
            name="fk_material_usage_item",
        ),
        _mem_fk("technician_membership_id", "fk_material_usage_technician"),
        _org_fk("material_usage"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_usage")),
        sa.UniqueConstraint("organization_id", "id", name="uq_material_usage_org_id"),
        sa.UniqueConstraint(
            "organization_id", "client_command_id", name="uq_material_usage_org_client_command"
        ),
    )
    op.create_index("ix_material_usage_request", "material_usage", ["request_id", "created_at"])

    op.create_table(
        "stock_movements",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "ADDITION",
                "CONSUMPTION",
                "ADJUSTMENT",
                name="kind",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("delta", num, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_membership_id", sa.Uuid(), nullable=False),
        sa.Column("material_usage_id", sa.Uuid(), nullable=True),
        sa.Column("stock_after", num, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        _clock_created(),
        sa.CheckConstraint("delta <> 0", name="delta_nonzero"),
        sa.CheckConstraint("stock_after >= 0", name="stock_after_nonneg"),
        sa.ForeignKeyConstraint(
            ["organization_id", "item_id"],
            ["inventory_items.organization_id", "inventory_items.id"],
            name="fk_stock_movements_item",
        ),
        _mem_fk("actor_membership_id", "fk_stock_movements_actor"),
        sa.ForeignKeyConstraint(
            ["organization_id", "material_usage_id"],
            ["material_usage.organization_id", "material_usage.id"],
            name="fk_stock_movements_usage",
        ),
        _org_fk("stock_movements"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
    )
    op.create_index("ix_stock_movements_item_created", "stock_movements", ["item_id", "created_at"])

    op.create_table(
        "notifications",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_membership_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=120), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        _clock_created(),
        _mem_fk("recipient_membership_id", "fk_notifications_recipient"),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_notifications_request",
        ),
        _org_fk("notifications"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint(
            "organization_id",
            "recipient_membership_id",
            "dedupe_key",
            name="uq_notifications_recipient_dedupe",
        ),
    )
    op.create_index(
        "ix_notifications_recipient_read_created",
        "notifications",
        ["recipient_membership_id", "read_at", sa.text("created_at DESC")],
    )

    # ---- DB-level immutability --------------------------------------------------------
    for table in ("stock_movements", "material_usage"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
        )
    op.execute(
        """
        CREATE FUNCTION estimates_guard_immutable() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF OLD.status <> 'DRAFT' THEN
                    RAISE EXCEPTION 'submitted estimates are never deleted'
                        USING ERRCODE = 'restrict_violation';
                END IF;
                RETURN OLD;
            END IF;
            IF OLD.status <> 'DRAFT' AND (
                NEW.labor_minutes IS DISTINCT FROM OLD.labor_minutes
                OR NEW.labor_rate_minor IS DISTINCT FROM OLD.labor_rate_minor
                OR NEW.labor_cost_minor IS DISTINCT FROM OLD.labor_cost_minor
                OR NEW.materials_total_minor IS DISTINCT FROM OLD.materials_total_minor
                OR NEW.total_minor IS DISTINCT FROM OLD.total_minor
                OR NEW.currency IS DISTINCT FROM OLD.currency
                OR NEW.notes IS DISTINCT FROM OLD.notes
                OR NEW.version IS DISTINCT FROM OLD.version
                OR NEW.supersedes_id IS DISTINCT FROM OLD.supersedes_id
                OR NEW.request_id IS DISTINCT FROM OLD.request_id
            ) THEN
                RAISE EXCEPTION 'estimate % is immutable after submission', OLD.id
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_estimates_immutable BEFORE UPDATE OR DELETE ON estimates "
        "FOR EACH ROW EXECUTE FUNCTION estimates_guard_immutable()"
    )
    op.execute(
        """
        CREATE FUNCTION estimate_lines_guard_immutable() RETURNS trigger AS $$
        DECLARE
            est_status text;
            est_id uuid;
        BEGIN
            est_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.estimate_id ELSE NEW.estimate_id END;
            SELECT status INTO est_status FROM estimates WHERE id = est_id;
            IF est_status IS NOT NULL AND est_status <> 'DRAFT' THEN
                RAISE EXCEPTION 'lines of a submitted estimate are immutable'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            IF TG_OP = 'UPDATE' AND NEW.estimate_id <> OLD.estimate_id THEN
                RAISE EXCEPTION 'estimate lines cannot move between estimates'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_estimate_lines_immutable BEFORE INSERT OR UPDATE OR DELETE "
        "ON estimate_lines FOR EACH ROW EXECUTE FUNCTION estimate_lines_guard_immutable()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_estimate_lines_immutable ON estimate_lines")
    op.execute("DROP TRIGGER IF EXISTS trg_estimates_immutable ON estimates")
    op.execute("DROP FUNCTION IF EXISTS estimate_lines_guard_immutable()")
    op.execute("DROP FUNCTION IF EXISTS estimates_guard_immutable()")
    op.execute("DROP TRIGGER IF EXISTS trg_material_usage_immutable ON material_usage")
    op.execute("DROP TRIGGER IF EXISTS trg_stock_movements_immutable ON stock_movements")
    op.drop_index("ix_notifications_recipient_read_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_stock_movements_item_created", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("ix_material_usage_request", table_name="material_usage")
    op.drop_table("material_usage")
    op.drop_index("ix_estimate_lines_estimate", table_name="estimate_lines")
    op.drop_table("estimate_lines")
    op.drop_index("ix_estimates_org_status", table_name="estimates")
    op.drop_index("uq_estimates_one_pending_per_request", table_name="estimates")
    op.drop_index("uq_estimates_one_draft_per_request", table_name="estimates")
    op.drop_table("estimates")
    op.drop_index("ix_inventory_items_org_active", table_name="inventory_items")
    op.drop_table("inventory_items")
