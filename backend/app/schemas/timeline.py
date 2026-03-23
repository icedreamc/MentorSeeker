from datetime import date, datetime

from pydantic import BaseModel, Field


class TimelineCreateRequest(BaseModel):
    user_id: int = 1
    mentor_id: int
    event_type: str = Field(min_length=1, max_length=32)
    event_date: date
    content: str = ""


class TimelineUpdateRequest(BaseModel):
    event_type: str | None = Field(default=None, min_length=1, max_length=32)
    event_date: date | None = None
    content: str | None = None


class TimelineRead(BaseModel):
    id: int
    user_id: int
    mentor_id: int
    mentor_name: str
    event_type: str
    event_date: date
    content: str
    created_at: datetime
    updated_at: datetime


class TimelineListRead(BaseModel):
    items: list[TimelineRead]
    page: int
    page_size: int
    total: int


class TimelineDailyPointRead(BaseModel):
    event_date: date
    count: int
    type_counts: dict[str, int] = Field(default_factory=dict)


class TimelineDailyOverviewRead(BaseModel):
    items: list[TimelineDailyPointRead]
