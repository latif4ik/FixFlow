import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ShortName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


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
