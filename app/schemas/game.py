from datetime import date, datetime, time

from pydantic import BaseModel


class GameBase(BaseModel):
    game_date: date
    game_time: time | None = None
    location: str | None = None
    season_id: int | None = None
    team_id: int | None = None
    standalone: bool = False
    notes: str | None = None


class GameCreate(GameBase):
    pass


class GameUpdate(BaseModel):
    game_date: date | None = None
    game_time: time | None = None
    location: str | None = None
    notes: str | None = None
    standalone: bool | None = None


class GameRead(GameBase):
    model_config = {"from_attributes": True}

    id: int
    created_at: datetime
