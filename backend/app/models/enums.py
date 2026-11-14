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
