from datetime import datetime

from pydantic import BaseModel

from app.schemas.player import VALID_POSITIONS


class PlayerPreferenceBase(BaseModel):
    position_prefs: list[str] | None = None
    ice_time_constraints: str | None = None
    style_notes: str | None = None


class PlayerPreferenceUpdate(PlayerPreferenceBase):
    pass


class PlayerPreferenceRead(PlayerPreferenceBase):
    model_config = {"from_attributes": True}

    id: int
    player_id: int
    updated_at: datetime
