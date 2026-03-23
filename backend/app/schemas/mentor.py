from datetime import datetime

from pydantic import BaseModel, Field


class MentorCreateRequest(BaseModel):
    school: str = Field(min_length=1, max_length=255)
    interested_field: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    title: str = ""
    research_direction: str = ""
    profile_urls: list[str] = Field(default_factory=list)


class MentorBatchEnrichRequest(BaseModel):
    mentor_ids: list[int] = Field(min_length=1, max_length=100)
    sleep_seconds: float = Field(default=0.2, ge=0.0, le=3.0)


class MentorBatchEnrichResult(BaseModel):
    requested_count: int
    enriched_count: int
    skipped_count: int
    updated_ids: list[int]
    output_file: str = ""


class MentorBatchDeleteRequest(BaseModel):
    mentor_ids: list[int] = Field(min_length=1, max_length=200)


class MentorBatchDeleteResult(BaseModel):
    requested_count: int
    deleted_count: int
    not_found_count: int
    deleted_ids: list[int] = Field(default_factory=list)
    not_found_ids: list[int] = Field(default_factory=list)
    deleted_favorites: int = 0
    deleted_notes: int = 0
    deleted_timeline: int = 0


class MentorSummaryRead(BaseModel):
    id: int
    school: str
    interested_field: str
    name: str
    title: str
    research_direction: str
    high_level_summary: str = ""
    ai_keywords: list[str] = Field(default_factory=list)
    is_favorite: bool = False
    is_auto_enriched: bool = False
    updated_at: datetime


class MentorDetailRead(BaseModel):
    id: int
    school: str
    interested_field: str
    name: str
    title: str
    research_direction: str
    profile_urls: list[str]
    structured_profile: dict
    publications: list[dict]
    papers_summary: str
    high_level_summary: str
    ai_keywords: list[str] = Field(default_factory=list)
    user_note: str = ""
    user_tags: list[str] = Field(default_factory=list)
    is_favorite: bool = False
    is_auto_enriched: bool = False
    updated_at: datetime


class MentorListRead(BaseModel):
    items: list[MentorSummaryRead]
    page: int
    page_size: int
    total: int


class FavoriteUpdateRequest(BaseModel):
    user_id: int = 1
    is_favorite: bool = True


class NoteUpdateRequest(BaseModel):
    user_id: int = 1
    note_text: str = ""
    tags: list[str] = Field(default_factory=list)


class NoteRead(BaseModel):
    mentor_id: int
    user_id: int
    note_text: str
    tags: list[str]
    updated_at: datetime
