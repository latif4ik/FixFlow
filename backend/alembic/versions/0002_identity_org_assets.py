"""identity, organization, assets

Revision ID: 0002_identity_org_assets
Revises: 0001_baseline
Create Date: 2026-11-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_identity_org_assets"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="Asia/Bishkek", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "business_hours",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("open_time", sa.Time(), nullable=False),
        sa.Column("close_time", sa.Time(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "close_time > open_time", name=op.f("ck_business_hours_close_after_open")
        ),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name=op.f("ck_business_hours_weekday_range")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_business_hours_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_business_hours")),
    )
    op.create_index(
        "ix_business_hours_org_weekday",
        "business_hours",
        ["organization_id", "weekday"],
        unique=False,
    )
    op.create_table(
        "holidays",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_holidays_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holidays")),
        sa.UniqueConstraint("organization_id", "date", name="uq_holidays_org_date"),
    )
    op.create_table(
        "memberships",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "REQUESTER",
                "DISPATCHER",
                "ADMIN",
                "TECHNICIAN",
                name="role",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_memberships_organization_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memberships_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint("organization_id", "id", name="uq_memberships_org_id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
    )
    op.create_index(
        "ix_memberships_org_role_active",
        "memberships",
        ["organization_id", "role", "is_active"],
        unique=False,
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"], unique=False)
    op.create_table(
        "properties",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("contact_instructions", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_properties_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_properties")),
        sa.UniqueConstraint("organization_id", "id", name="uq_properties_org_id"),
    )
    op.create_index(
        "ix_properties_org_active", "properties", ["organization_id", "is_active"], unique=False
    )
    op.create_index(
        "ix_properties_org_name", "properties", ["organization_id", "name"], unique=False
    )
    op.create_table(
        "security_events",
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("email_hash", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_security_events_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_security_events")),
    )
    op.create_index(
        "ix_security_events_type_email_created",
        "security_events",
        ["event_type", "email_hash", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_security_events_type_ip_created",
        "security_events",
        ["event_type", "ip", "created_at"],
        unique=False,
    )
    op.create_index("ix_security_events_user_id", "security_events", ["user_id"], unique=False)
    op.create_table(
        "service_categories",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="true", nullable=False),
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
            "default_duration_minutes >= 30", name=op.f("ck_service_categories_duration_min_30")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_service_categories_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_categories")),
        sa.UniqueConstraint("organization_id", "id", name="uq_service_categories_org_id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_service_categories_org_name"),
    )
    op.create_table(
        "sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_table(
        "skills",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_skills_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
        sa.UniqueConstraint("organization_id", "id", name="uq_skills_org_id"),
    )
    op.create_index(
        "uq_skills_org_lower_name",
        "skills",
        ["organization_id", sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "assets",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("asset_type", sa.String(length=100), nullable=False),
        sa.Column("serial_number", sa.String(length=100), nullable=True),
        sa.Column("installed_on", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "OUT_OF_SERVICE",
                "RETIRED",
                name="asset_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["organization_id", "property_id"],
            ["properties.organization_id", "properties.id"],
            name="fk_assets_property",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_assets_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
        sa.UniqueConstraint("organization_id", "code", name="uq_assets_org_code"),
        sa.UniqueConstraint("organization_id", "id", name="uq_assets_org_id"),
    )
    op.create_index(
        "ix_assets_org_property", "assets", ["organization_id", "property_id"], unique=False
    )
    op.create_index("ix_assets_org_status", "assets", ["organization_id", "status"], unique=False)
    op.create_table(
        "audit_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_membership_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=60), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_audit_events_actor_memberships",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_audit_events_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_org_action", "audit_events", ["organization_id", "action"], unique=False
    )
    op.create_index(
        "ix_audit_events_org_created",
        "audit_events",
        ["organization_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_org_target",
        "audit_events",
        ["organization_id", "target_type", "target_id"],
        unique=False,
    )
    op.create_table(
        "category_required_skills",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["service_categories.organization_id", "service_categories.id"],
            name="fk_category_required_skills_category",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "skill_id"],
            ["skills.organization_id", "skills.id"],
            name="fk_category_required_skills_skill",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_category_required_skills_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint(
            "category_id", "skill_id", name=op.f("pk_category_required_skills")
        ),
    )
    op.create_index(
        "ix_category_required_skills_skill_id",
        "category_required_skills",
        ["skill_id"],
        unique=False,
    )
    op.create_table(
        "property_access",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("property_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by_membership_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "granted_by_membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_property_access_granted_by",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_property_access_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "property_id"],
            ["properties.organization_id", "properties.id"],
            name="fk_property_access_property",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_property_access_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("property_id", "membership_id", name=op.f("pk_property_access")),
    )
    op.create_index(
        "ix_property_access_membership_id", "property_access", ["membership_id"], unique=False
    )
    op.create_index("ix_property_access_org", "property_access", ["organization_id"], unique=False)
    op.create_table(
        "technician_availability",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "end_time > start_time", name=op.f("ck_technician_availability_end_after_start")
        ),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6", name=op.f("ck_technician_availability_weekday_range")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_technician_availability_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_technician_availability_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_technician_availability")),
    )
    op.create_index(
        "ix_technician_availability_org_member",
        "technician_availability",
        ["organization_id", "membership_id"],
        unique=False,
    )
    op.create_table(
        "technician_profiles",
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_technician_profiles_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_technician_profiles_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("membership_id", name=op.f("pk_technician_profiles")),
    )
    op.create_index(
        "ix_technician_profiles_org", "technician_profiles", ["organization_id"], unique=False
    )
    op.create_table(
        "technician_skills",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_technician_skills_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "skill_id"],
            ["skills.organization_id", "skills.id"],
            name="fk_technician_skills_skill",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_technician_skills_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("membership_id", "skill_id", name=op.f("pk_technician_skills")),
    )
    op.create_index(
        "ix_technician_skills_skill_id", "technician_skills", ["skill_id"], unique=False
    )
    op.create_table(
        "technician_time_off",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "end_at > start_at", name=op.f("ck_technician_time_off_end_after_start")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_technician_time_off_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_technician_time_off_organization_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_technician_time_off")),
    )
    op.create_index(
        "ix_technician_time_off_org_member",
        "technician_time_off",
        ["organization_id", "membership_id", "start_at"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION audit_events_immutable() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only (% rejected)', TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_immutable
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_immutable()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_immutable ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_immutable()")
    op.drop_index("ix_technician_time_off_org_member", table_name="technician_time_off")
    op.drop_table("technician_time_off")
    op.drop_index("ix_technician_skills_skill_id", table_name="technician_skills")
    op.drop_table("technician_skills")
    op.drop_index("ix_technician_profiles_org", table_name="technician_profiles")
    op.drop_table("technician_profiles")
    op.drop_index("ix_technician_availability_org_member", table_name="technician_availability")
    op.drop_table("technician_availability")
    op.drop_index("ix_property_access_org", table_name="property_access")
    op.drop_index("ix_property_access_membership_id", table_name="property_access")
    op.drop_table("property_access")
    op.drop_index("ix_category_required_skills_skill_id", table_name="category_required_skills")
    op.drop_table("category_required_skills")
    op.drop_index("ix_audit_events_org_target", table_name="audit_events")
    op.drop_index("ix_audit_events_org_created", table_name="audit_events")
    op.drop_index("ix_audit_events_org_action", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_assets_org_status", table_name="assets")
    op.drop_index("ix_assets_org_property", table_name="assets")
    op.drop_table("assets")
    op.drop_index("uq_skills_org_lower_name", table_name="skills")
    op.drop_table("skills")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("service_categories")
    op.drop_index("ix_security_events_user_id", table_name="security_events")
    op.drop_index("ix_security_events_type_ip_created", table_name="security_events")
    op.drop_index("ix_security_events_type_email_created", table_name="security_events")
    op.drop_table("security_events")
    op.drop_index("ix_properties_org_name", table_name="properties")
    op.drop_index("ix_properties_org_active", table_name="properties")
    op.drop_table("properties")
    op.drop_index("ix_memberships_user_id", table_name="memberships")
    op.drop_index("ix_memberships_org_role_active", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("holidays")
    op.drop_index("ix_business_hours_org_weekday", table_name="business_hours")
    op.drop_table("business_hours")
    op.drop_table("users")
    op.drop_table("organizations")
