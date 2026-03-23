from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ContactDraftGenerateRequest(BaseModel):
    user_id: int = 1
    mentor_id: int = Field(ge=1)
    language: Literal["auto", "zh", "en"] = "auto"
    extra_instruction: str = ""


class ContactDraftGenerateRead(BaseModel):
    mentor_id: int
    subject: str
    body: str
    used_llm: bool
    key_fit_points: list[str] = Field(default_factory=list)


class ContactDraftCommitRequest(BaseModel):
    user_id: int = 1
    mentor_id: int = Field(ge=1)
    event_date: date
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=12000)


class ContactDraftCommitRead(BaseModel):
    id: int
    user_id: int
    mentor_id: int
    event_type: str
    event_date: date
    content: str
    created_at: datetime
    updated_at: datetime
