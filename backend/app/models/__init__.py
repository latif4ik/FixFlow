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
from app.models.requests import EvidenceFile, RequestEvent, ServiceRequest, WorkNote

__all__ = [
    "Asset",
    "AssetStatus",
    "AuditEvent",
    "BusinessHour",
    "CategoryRequiredSkill",
    "EvidenceFile",
    "Holiday",
    "Membership",
    "MembershipRole",
    "Organization",
    "Property",
    "PropertyAccess",
    "RequestEvent",
    "SecurityEvent",
    "ServiceCategory",
    "ServiceRequest",
    "Session",
    "Skill",
    "TechnicianAvailability",
    "TechnicianProfile",
    "TechnicianSkill",
    "TechnicianTimeOff",
    "User",
    "WorkNote",
]
