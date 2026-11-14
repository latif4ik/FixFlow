"""Requester feedback, SSE stream tickets, report indexes

Revision ID: 0007_feedback_stream_reports
Revises: 0006_sla_maintenance
Create Date: 2026-11-15 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_feedback_stream_reports"
down_revision: str | None = "0006_sla_maintenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feedback",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("requester_membership_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        sa.CheckConstraint(
            "comment IS NULL OR char_length(comment) <= 2000", name="comment_length"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_feedback_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "request_id"],
            ["service_requests.organization_id", "service_requests.id"],
            name="fk_feedback_request",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requester_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_feedback_requester",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
        sa.UniqueConstraint("request_id", name="uq_feedback_request_id"),
    )
    op.execute(
        "CREATE TRIGGER trg_feedback_immutable BEFORE UPDATE OR DELETE ON feedback "
        "FOR EACH ROW EXECUTE FUNCTION forbid_mutation()"
    )

    op.create_table(
        "stream_tickets",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_stream_tickets_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_stream_tickets_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name=op.f("fk_stream_tickets_session_id_sessions")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_stream_tickets_membership",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stream_tickets")),
        sa.UniqueConstraint("token_hash", name="uq_stream_tickets_token_hash"),
    )
    op.create_index("ix_stream_tickets_expires_at", "stream_tickets", ["expires_at"])

    # Report indexes (all queries are org-scoped and range-filtered).
    op.create_index(
        "ix_service_requests_org_completed",
        "service_requests",
        ["organization_id", "completed_at"],
        postgresql_where=sa.text("completed_at IS NOT NULL"),
    )
    op.create_index(
        "ix_estimates_org_decided",
        "estimates",
        ["organization_id", "decided_at"],
        postgresql_where=sa.text("status = 'APPROVED'"),
    )
    op.create_index(
        "ix_material_usage_org_created", "material_usage", ["organization_id", "created_at"]
    )
    op.create_index(
        "ix_assignments_org_start_end", "assignments", ["organization_id", "start_at", "end_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_assignments_org_start_end", table_name="assignments")
    op.drop_index("ix_material_usage_org_created", table_name="material_usage")
    op.drop_index("ix_estimates_org_decided", table_name="estimates")
    op.drop_index("ix_service_requests_org_completed", table_name="service_requests")
    op.drop_index("ix_stream_tickets_expires_at", table_name="stream_tickets")
    op.drop_table("stream_tickets")
    op.execute("DROP TRIGGER IF EXISTS trg_feedback_immutable ON feedback")
    op.drop_table("feedback")
