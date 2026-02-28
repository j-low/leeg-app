from datetime import date, datetime

from pydantic import BaseModel, model_validator

from app.models.season import SeasonStatus


class SeasonBase(BaseModel):
    name: str
    start_date: date | None = None
    end_date: date | None = None
    status: SeasonStatus = SeasonStatus.open

    @model_validator(mode="after")
    def end_after_start(self) -> "SeasonBase":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class SeasonCreate(SeasonBase):
    pass


class SeasonUpdate(BaseModel):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: SeasonStatus | None = None


class SeasonRead(SeasonBase):
    model_config = {"from_attributes": True}

    id: int
    created_at: datetime
