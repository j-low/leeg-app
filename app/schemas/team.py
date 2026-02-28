from datetime import datetime

from pydantic import BaseModel, field_validator


class TeamBase(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Team name cannot be empty")
        return v.strip()


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: str | None = None


class TeamRead(TeamBase):
    model_config = {"from_attributes": True}

    id: int
    captain_id: int
    created_at: datetime
    updated_at: datetime
