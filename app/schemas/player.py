import re

from pydantic import BaseModel, field_validator

# E.164 phone format: +1XXXXXXXXXX
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")

VALID_POSITIONS = {"center", "wing", "defense", "goalie"}


class PlayerBase(BaseModel):
    name: str
    phone: str
    position_prefs: list[str] | None = None
    skill_notes: str | None = None
    sub_flag: bool = False

    @field_validator("phone")
    @classmethod
    def phone_e164(cls, v: str) -> str:
        if not _E164_RE.match(v):
            raise ValueError("Phone must be E.164 format (e.g. +16135550100)")
        return v

    @field_validator("position_prefs")
    @classmethod
    def valid_positions(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        invalid = set(v) - VALID_POSITIONS
        if invalid:
            raise ValueError(f"Invalid positions: {invalid}. Must be one of {VALID_POSITIONS}")
        return v


class PlayerCreate(PlayerBase):
    team_id: int | None = None
    captain_notes: str | None = None


class PlayerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    position_prefs: list[str] | None = None
    skill_notes: str | None = None
    sub_flag: bool | None = None
    captain_notes: str | None = None
    team_id: int | None = None


class PlayerRead(PlayerBase):
    model_config = {"from_attributes": True}

    id: int
    team_id: int | None
    # captain_notes intentionally omitted -- never expose in default read
    # Use PlayerReadCaptain below for captain-scoped responses


class PlayerReadCaptain(PlayerRead):
    """Extended read schema for captain/admin responses. Includes internal notes."""
    captain_notes: str | None = None
