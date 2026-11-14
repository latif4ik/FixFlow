"""SLA cache columns on service_requests, maintenance plans + generated-request traceability

Revision ID: 0006_sla_maintenance
Revises: 0005_estimates_inventory
Create Date: 2026-11-15 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_sla_maintenance"
down_revision: str | None = "0005_estimates_inventory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "maintenance_plans",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "priority",
            sa.Enum(
                "LOW",
                "NORMAL",
                "HIGH",
                name="priority",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="NORMAL",
            nullable=False,
        ),
        sa.Column("first_date", sa.Date(), nullable=False),
        sa.Column(
            "recurrence",
            sa.Enum(
                "WEEKLY",
                "MONTHLY",
                name="recurrence",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_generated_for", sa.Date(), nullable=True),
        sa.Column("created_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint("char_length(title) BETWEEN 5 AND 100", name="title_length"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_maintenance_plans_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "asset_id"],
            ["assets.organization_id", "assets.id"],
            name="fk_maintenance_plans_asset",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["service_categories.organization_id", "service_categories.id"],
            name="fk_maintenance_plans_category",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_maintenance_plans_created_by",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_maintenance_plans")),
        sa.UniqueConstraint("organization_id", "id", name="uq_maintenance_plans_org_id"),
    )
    op.create_index(
        "ix_maintenance_plans_org_asset", "maintenance_plans", ["organization_id", "asset_id"]
    )
    op.create_index(
        "ix_maintenance_plans_org_enabled", "maintenance_plans", ["organization_id", "is_enabled"]
    )

    op.add_column("service_requests", sa.Column("plan_id", sa.Uuid(), nullable=True))
    op.add_column("service_requests", sa.Column("occurrence_date", sa.Date(), nullable=True))
    op.add_column("service_requests", sa.Column("sla_budget_minutes", sa.Integer(), nullable=True))
    op.add_column(
        "service_requests", sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "service_requests", sa.Column("sla_at_risk_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "service_requests",
        sa.Column("sla_paused", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "service_requests", sa.Column("sla_consumed_minutes", sa.Integer(), nullable=True)
    )
    op.add_column("service_requests", sa.Column("sla_outcome", sa.String(length=10), nullable=True))
    op.add_column(
        "service_requests", sa.Column("sla_stopped_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "service_requests",
        sa.Column("overdue_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_service_requests_plan",
        "service_requests",
        "maintenance_plans",
        ["organization_id", "plan_id"],
        ["organization_id", "id"],
    )
    op.create_unique_constraint(
        "uq_service_requests_plan_occurrence", "service_requests", ["plan_id", "occurrence_date"]
    )
    op.create_check_constraint(
        op.f("ck_service_requests_plan_occurrence_together"),
        "service_requests",
        "(plan_id IS NULL) = (occurrence_date IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_service_requests_sla_outcome_valid"),
        "service_requests",
        "sla_outcome IS NULL OR sla_outcome IN ('MET', 'BREACHED')",
    )
    op.create_index(
        "ix_service_requests_org_sla_due",
        "service_requests",
        ["organization_id", "sla_due_at"],
        postgresql_where=sa.text("sla_due_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_service_requests_org_sla_due", table_name="service_requests")
    op.drop_constraint(
        op.f("ck_service_requests_sla_outcome_valid"), "service_requests", type_="check"
    )
    op.drop_constraint(
        op.f("ck_service_requests_plan_occurrence_together"), "service_requests", type_="check"
    )
    op.drop_constraint("uq_service_requests_plan_occurrence", "service_requests", type_="unique")
    op.drop_constraint("fk_service_requests_plan", "service_requests", type_="foreignkey")
    for col in (
        "overdue_notified_at",
        "sla_stopped_at",
        "sla_outcome",
        "sla_consumed_minutes",
        "sla_paused",
        "sla_at_risk_at",
        "sla_due_at",
        "sla_budget_minutes",
        "occurrence_date",
        "plan_id",
    ):
        op.drop_column("service_requests", col)
    op.drop_index("ix_maintenance_plans_org_enabled", table_name="maintenance_plans")
    op.drop_index("ix_maintenance_plans_org_asset", table_name="maintenance_plans")
    op.drop_table("maintenance_plans")
