import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin


def _org_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("organizations.id"))


class BusinessHour(UUIDPkMixin, Base):
    __tablename__ = "business_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("close_time > open_time", name="close_after_open"),
        Index("ix_business_hours_org_weekday", "organization_id", "weekday"),
    )

    organization_id: Mapped[uuid.UUID] = _org_fk()
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Monday
    open_time: Mapped[time] = mapped_column(Time)
    close_time: Mapped[time] = mapped_column(Time)


class Holiday(UUIDPkMixin, Base):
    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("organization_id", "date", name="uq_holidays_org_date"),)

    organization_id: Mapped[uuid.UUID] = _org_fk()
    date: Mapped[date] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(200))


class Skill(UUIDPkMixin, Base):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_skills_org_id"),
        Index("uq_skills_org_lower_name", "organization_id", func.lower(text("name")), unique=True),
    )

    organization_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String(80))


class ServiceCategory(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "service_categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_service_categories_org_name"),
        UniqueConstraint("organization_id", "id", name="uq_service_categories_org_id"),
        CheckConstraint("default_duration_minutes >= 30", name="duration_min_30"),
    )

    organization_id: Mapped[uuid.UUID] = _org_fk()
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    default_duration_minutes: Mapped[int] = mapped_column(Integer)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class CategoryRequiredSkill(Base):
    __tablename__ = "category_required_skills"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["service_categories.organization_id", "service_categories.id"],
            name="fk_category_required_skills_category",
        ),
        ForeignKeyConstraint(
            ["organization_id", "skill_id"],
            ["skills.organization_id", "skills.id"],
            name="fk_category_required_skills_skill",
        ),
        Index("ix_category_required_skills_skill_id", "skill_id"),
    )

    organization_id: Mapped[uuid.UUID] = _org_fk()
    category_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)


class TechnicianProfile(Base):
    __tablename__ = "technician_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_technician_profiles_membership",
        ),
        Index("ix_technician_profiles_org", "organization_id"),
    )

    membership_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = _org_fk()
    bio: Mapped[str | None] = mapped_column(Text)


class TechnicianSkill(Base):
    __tablename__ = "technician_skills"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_technician_skills_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "skill_id"],
            ["skills.organization_id", "skills.id"],
            name="fk_technician_skills_skill",
        ),
        Index("ix_technician_skills_skill_id", "skill_id"),
    )

    organization_id: Mapped[uuid.UUID] = _org_fk()
    membership_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)


class TechnicianAvailability(UUIDPkMixin, Base):
    __tablename__ = "technician_availability"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_technician_availability_membership",
        ),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("end_time > start_time", name="end_after_start"),
        Index("ix_technician_availability_org_member", "organization_id", "membership_id"),
    )

    organization_id: Mapped[uuid.UUID] = _org_fk()
    membership_id: Mapped[uuid.UUID] = mapped_column()
    weekday: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class TechnicianTimeOff(UUIDPkMixin, Base):
    __tablename__ = "technician_time_off"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            name="fk_technician_time_off_membership",
        ),
        CheckConstraint("end_at > start_at", name="end_after_start"),
        Index("ix_technician_time_off_org_member", "organization_id", "membership_id", "start_at"),
    )

    organization_id: Mapped[uuid.UUID] = _org_fk()
    membership_id: Mapped[uuid.UUID] = mapped_column()
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(300))
