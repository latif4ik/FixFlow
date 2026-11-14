"""requests lifecycle notes files

Revision ID: 0003_requests
Revises: 0002_identity_org_assets
Create Date: 2026-11-15 01:54:50.143952
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_requests"
down_revision: str | None = "0002_identity_org_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_assets_org_property_id", "assets", ["organization_id", "property_id", "id"]
    )
    op.add_column(
        "organizations", sa.Column("request_seq", sa.Integer(), server_default="0", nullable=False)
    )
    op.create_table(
        "service_requests",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("requester_membership_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_membership_id", sa.Uuid(), nullable=True),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
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
        sa.Column(
            "status",
            sa.Enum(
                "SUBMITTED",
                "TRIAGED",
                "SCHEDULED",
                "ACCEPTED",
                "IN_PROGRESS",
                "BLOCKED",
                "COMPLETED",
                "CLOSED",
                "REOPENED",
                "CANCELED",
                name="status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="SUBMITTED",
            nullable=False,
        ),
        sa.Column("preferred_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preferred_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duplicate_of_id", sa.Uuid(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "duplicate_of_id <> id", name=op.f("ck_service_requests_not_self_duplicate")
        ),
        sa.CheckConstraint(
            "preferred_window_start IS NULL OR preferred_window_end IS NULL "
            "OR preferred_window_end > preferred_window_start",
            name=op.f("ck_service_requests_preferred_window_order"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["service_categories.organization_id", "service_categories.id"],
            name="fk_service_requests_category",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_service_requests_created_by",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "duplicate_of_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_service_requests_duplicate_of",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "property_id", "asset_id"],
            ["assets.organization_id", "assets.property_id", "assets.id"],
            name="fk_service_requests_asset",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "property_id"],
            ["properties.organization_id", "properties.id"],
            name="fk_service_requests_property",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requester_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_service_requests_requester",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_service_requests_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_requests")),
        sa.UniqueConstraint("organization_id", "id", name="uq_service_requests_org_id"),
        sa.UniqueConstraint("organization_id", "number", name="uq_service_requests_org_number"),
    )
    op.create_index(
        "ix_service_requests_org_created",
        "service_requests",
        ["organization_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_service_requests_org_priority",
        "service_requests",
        ["organization_id", "priority"],
        unique=False,
    )
    op.create_index(
        "ix_service_requests_org_property",
        "service_requests",
        ["organization_id", "property_id"],
        unique=False,
    )
    op.create_index(
        "ix_service_requests_org_requester",
        "service_requests",
        ["organization_id", "requester_membership_id"],
        unique=False,
    )
    op.create_index(
        "ix_service_requests_org_status",
        "service_requests",
        ["organization_id", "status"],
        unique=False,
    )
    op.create_table(
        "request_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("actor_membership_id", sa.Uuid(), nullable=True),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_request_events_actor",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_request_events_request",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_request_events_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_events")),
    )
    op.create_index(
        "ix_request_events_request_created",
        "request_events",
        ["request_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "work_notes",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("author_membership_id", sa.Uuid(), nullable=False),
        sa.Column(
            "visibility",
            sa.Enum(
                "PUBLIC",
                "INTERNAL",
                name="visibility",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.Enum(
                "GENERAL",
                "TRIAGE",
                "BLOCKER",
                "RESOLUTION",
                "COMPLETION",
                "CANCEL",
                "CLOSE",
                "REWORK",
                name="kind",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("client_command_id", sa.Uuid(), nullable=True),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "author_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_work_notes_author",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_work_notes_request",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_work_notes_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_notes")),
        sa.UniqueConstraint(
            "organization_id", "client_command_id", name="uq_work_notes_org_client_command"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_work_notes_org_id"),
    )
    op.create_index(
        "ix_work_notes_request_created", "work_notes", ["request_id", "created_at"], unique=False
    )
    op.create_table(
        "evidence_files",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=True),
        sa.Column(
            "purpose",
            sa.Enum(
                "INTAKE",
                "NOTE",
                "COMPLETION",
                name="purpose",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("mime_type", sa.String(length=60), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("client_command_id", sa.Uuid(), nullable=True),
        sa.Column("client_index", sa.SmallInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "note_id"],
            ["work_notes.organization_id", "work_notes.id"],
            name="fk_evidence_files_note",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_evidence_files_request",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "uploaded_by_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_evidence_files_uploader",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_evidence_files_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_files")),
        sa.UniqueConstraint(
            "organization_id",
            "client_command_id",
            "client_index",
            name="uq_evidence_files_org_client_command",
        ),
    )
    op.create_index("ix_evidence_files_request", "evidence_files", ["request_id"], unique=False)
    op.execute(
        """
        CREATE FUNCTION forbid_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only (% rejected)', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("request_events", "work_notes"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
        )


def downgrade() -> None:
    for table in ("request_events", "work_notes"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS forbid_mutation()")
    op.drop_index("ix_evidence_files_request", table_name="evidence_files")
    op.drop_table("evidence_files")
    op.drop_index("ix_work_notes_request_created", table_name="work_notes")
    op.drop_table("work_notes")
    op.drop_index("ix_request_events_request_created", table_name="request_events")
    op.drop_table("request_events")
    for ix in ("status", "requester", "property", "priority", "created"):
        op.drop_index(f"ix_service_requests_org_{ix}", table_name="service_requests")
    op.drop_table("service_requests")
    op.drop_constraint("uq_assets_org_property_id", "assets", type_="unique")
    op.drop_column("organizations", "request_seq")
