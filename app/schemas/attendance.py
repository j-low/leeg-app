from datetime import datetime

from pydantic import BaseModel

from app.models.attendance import AttendanceStatus


class AttendanceUpsert(BaseModel):
    """Create or update attendance for a player/game pair."""
    game_id: int
    player_id: int
    status: AttendanceStatus


class AttendanceRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    game_id: int
    player_id: int
    status: AttendanceStatus
    updated_at: datetime


class AttendanceSummary(BaseModel):
    """Compact per-game summary used by the pipeline and dashboard."""
    game_id: int
    yes: int = 0
    no: int = 0
    maybe: int = 0
    total_players: int = 0
