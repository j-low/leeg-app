from datetime import datetime

from pydantic import BaseModel, field_validator


class LineupCreate(BaseModel):
    game_id: int
    team_id: int
    # proposed_lines: list of lines, each line is a list of player_ids
    # e.g. [[1,2,3], [4,5,6]] for two forward lines
    proposed_lines: list[list[int]]
    criteria: str | None = None
    explanation: str | None = None

    @field_validator("proposed_lines")
    @classmethod
    def lines_not_empty(cls, v: list[list[int]]) -> list[list[int]]:
        if not v:
            raise ValueError("proposed_lines cannot be empty")
        return v


class LineupRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    game_id: int
    team_id: int
    proposed_lines: list[list[int]]
    criteria: str | None
    explanation: str | None
    created_at: datetime
