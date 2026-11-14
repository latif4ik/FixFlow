"""assignments with DB-enforced no-overlap, idempotency keys

Revision ID: 0004_assignments
Revises: 0003_requests
Create Date: 2026-11-15 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_assignments"
down_revision: str | None = "0003_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _mem_fk(col: str, name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id", col], ["memberships.organization_id", "memberships.id"], name=name
    )


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("technician_membership_id", sa.Uuid(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "COMPLETED",
                "DECLINED",
                "UNASSIGNED",
                "RESCHEDULED",
                "CANCELED",
                name="status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("assigned_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("released_by_membership_id", sa.Uuid(), nullable=True),
        sa.Column("released_reason", sa.Text(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("end_at >= start_at + interval '30 minutes'", name="min_duration"),
        sa.CheckConstraint("active = (status = 'ACTIVE')", name="active_matches_status"),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_assignments_request",
        ),
        _mem_fk("technician_membership_id", "fk_assignments_technician"),
        _mem_fk("assigned_by_membership_id", "fk_assignments_assigned_by"),
        _mem_fk("released_by_membership_id", "fk_assignments_released_by"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_assignments_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignments")),
        sa.UniqueConstraint("organization_id", "id", name="uq_assignments_org_id"),
    )
    op.execute(
        "ALTER TABLE assignments ADD CONSTRAINT ex_assignments_technician_no_overlap "
        "EXCLUDE USING gist (technician_membership_id WITH =, "
        "tstzrange(start_at, end_at, '[)') WITH &&) WHERE (active)"
    )
    op.create_index(
        "uq_assignments_one_active_per_request",
        "assignments",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("active"),
    )
    op.create_index(
        "ix_assignments_org_tech_start",
        "assignments",
        ["organization_id", "technician_membership_id", "start_at"],
    )
    op.create_index("ix_assignments_org_request", "assignments", ["organization_id", "request_id"])
    # Assignment history is permanent: rows can be updated (release) but never deleted.
    op.execute(
        """
        CREATE FUNCTION forbid_assignment_delete() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'assignments are never deleted (history is preserved)'
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_assignments_no_delete BEFORE DELETE ON assignments "
        "FOR EACH ROW EXECUTE FUNCTION forbid_assignment_delete()"
    )

    op.create_table(
        "idempotency_keys",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("endpoint", sa.String(length=200), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("char_length(key) BETWEEN 1 AND 128", name="key_length"),
        _mem_fk("membership_id", "fk_idempotency_keys_membership"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_idempotency_keys_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint(
            "organization_id", "membership_id", "key", name="uq_idempotency_keys_org_member_key"
        ),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.execute("DROP TRIGGER IF EXISTS trg_assignments_no_delete ON assignments")
    op.execute("DROP FUNCTION IF EXISTS forbid_assignment_delete()")
    op.drop_index("ix_assignments_org_request", table_name="assignments")
    op.drop_index("ix_assignments_org_tech_start", table_name="assignments")
    op.drop_index("uq_assignments_one_active_per_request", table_name="assignments")
    op.drop_table("assignments")  # drops the EXCLUDE constraint with it
