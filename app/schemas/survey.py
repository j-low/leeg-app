from datetime import datetime

from pydantic import BaseModel

from app.models.survey import SurveyScope


class SurveyResponseCreate(BaseModel):
    survey_id: str
    player_id: int
    question: str
    answer: str | None = None
    scope: SurveyScope


class SurveyResponseRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    survey_id: str
    player_id: int
    question: str
    answer: str | None
    scope: SurveyScope
    created_at: datetime


class SurveyBlastRequest(BaseModel):
    """Captain-initiated survey blast to a list of players."""
    team_id: int
    question: str
    scope: SurveyScope
    player_ids: list[int] | None = None  # None = all active players on team
