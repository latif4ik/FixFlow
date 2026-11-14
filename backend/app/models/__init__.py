"""Import every model module so Alembic autogenerate sees all tables."""

from app.models.assets import Asset, Property, PropertyAccess
from app.models.audit import AuditEvent
from app.models.enums import AssetStatus, MembershipRole
from app.models.identity import Membership, Organization, SecurityEvent, Session, User
from app.models.org import (
    BusinessHour,
    CategoryRequiredSkill,
    Holiday,
    ServiceCategory,
    Skill,
    TechnicianAvailability,
    TechnicianProfile,
    TechnicianSkill,
    TechnicianTimeOff,
)

__all__ = [
    "Asset",
    "AssetStatus",
    "AuditEvent",
    "BusinessHour",
    "CategoryRequiredSkill",
    "Holiday",
    "Membership",
    "MembershipRole",
    "Organization",
    "Property",
    "PropertyAccess",
    "SecurityEvent",
    "ServiceCategory",
    "Session",
    "Skill",
    "TechnicianAvailability",
    "TechnicianProfile",
    "TechnicianSkill",
    "TechnicianTimeOff",
    "User",
]
