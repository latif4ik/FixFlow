import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ShortName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]

# Quantities are serialized as strings with exactly 3 decimals ("2.500"), whatever their source.
Qty3Out = Annotated[Decimal, PlainSerializer(lambda d: f"{d:.3f}", return_type=str)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserBrief(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str


class OrgBrief(ORMModel):
    id: uuid.UUID
    name: str
    timezone: str


class Timestamps(ORMModel):
    created_at: datetime
    updated_at: datetime


class PersonBrief(BaseModel):
    membership_id: uuid.UUID
    name: str
