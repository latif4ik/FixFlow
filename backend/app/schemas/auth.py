import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import MembershipRole
from app.schemas.common import OrgBrief, UserBrief


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class MembershipOut(BaseModel):
    membership_id: uuid.UUID
    organization: OrgBrief
    role: MembershipRole


class LoginResponse(BaseModel):
    token: str
    expires_at: datetime
    user: UserBrief
    memberships: list[MembershipOut]


class MeResponse(BaseModel):
    user: UserBrief
    memberships: list[MembershipOut]


class CurrentMembershipResponse(BaseModel):
    membership_id: uuid.UUID
    role: MembershipRole
    organization: OrgBrief
    user: UserBrief
