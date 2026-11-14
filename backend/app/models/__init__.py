"""Import every model module so Alembic autogenerate sees all tables."""

from app.models.assets import Asset, Property, PropertyAccess
from app.models.assignments import Assignment, IdempotencyKey
from app.models.audit import AuditEvent
from app.models.enums import AssetStatus, MembershipRole
from app.models.estimates import Estimate, EstimateLine
from app.models.identity import Membership, Organization, SecurityEvent, Session, User
from app.models.inventory import InventoryItem, MaterialUsage, StockMovement
from app.models.notifications import Notification
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
    "Assignment",
    "AuditEvent",
    "BusinessHour",
    "CategoryRequiredSkill",
    "Estimate",
    "EstimateLine",
    "EvidenceFile",
    "Holiday",
    "IdempotencyKey",
    "InventoryItem",
    "MaterialUsage",
    "Membership",
    "MembershipRole",
    "Notification",
    "Organization",
    "Property",
    "PropertyAccess",
    "RequestEvent",
    "SecurityEvent",
    "ServiceCategory",
    "ServiceRequest",
    "Session",
    "Skill",
    "StockMovement",
    "TechnicianAvailability",
    "TechnicianProfile",
    "TechnicianSkill",
    "TechnicianTimeOff",
    "User",
    "WorkNote",
]
