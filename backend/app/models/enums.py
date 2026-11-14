from enum import StrEnum


class MembershipRole(StrEnum):
    REQUESTER = "REQUESTER"
    DISPATCHER = "DISPATCHER"
    ADMIN = "ADMIN"
    TECHNICIAN = "TECHNICIAN"


class AssetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"
    RETIRED = "RETIRED"


class RequestStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    TRIAGED = "TRIAGED"
    SCHEDULED = "SCHEDULED"
    ACCEPTED = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"
    CANCELED = "CANCELED"


class Priority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class NoteVisibility(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"


class NoteKind(StrEnum):
    GENERAL = "GENERAL"
    TRIAGE = "TRIAGE"
    BLOCKER = "BLOCKER"
    RESOLUTION = "RESOLUTION"
    COMPLETION = "COMPLETION"
    CANCEL = "CANCEL"
    CLOSE = "CLOSE"
    REWORK = "REWORK"


class FilePurpose(StrEnum):
    INTAKE = "INTAKE"
    NOTE = "NOTE"
    COMPLETION = "COMPLETION"


class AssignmentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    DECLINED = "DECLINED"
    UNASSIGNED = "UNASSIGNED"
    RESCHEDULED = "RESCHEDULED"
    CANCELED = "CANCELED"


class EstimateStatus(StrEnum):
    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class StockMovementKind(StrEnum):
    ADDITION = "ADDITION"
    CONSUMPTION = "CONSUMPTION"
    ADJUSTMENT = "ADJUSTMENT"


class Recurrence(StrEnum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
