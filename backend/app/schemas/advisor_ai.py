from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AdvisorMentorRecommendationRead(BaseModel):
    mentor_id: int
    name: str
    school: str
    title: str
    research_direction: str
    match_score: float
    reason: str


class AdvisorMessageRead(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    recommendations: list[AdvisorMentorRecommendationRead] = Field(default_factory=list)
    created_at: datetime


class AdvisorSessionSummaryRead(BaseModel):
    id: int
    user_id: int
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class AdvisorSessionDetailRead(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[AdvisorMessageRead] = Field(default_factory=list)


class AdvisorSessionCreateRequest(BaseModel):
    user_id: int = 1
    title: str | None = None


class AdvisorMemoryRead(BaseModel):
    user_id: int
    memory_text: str
    updated_at: datetime


class AdvisorMemoryUpdateRequest(BaseModel):
    user_id: int = 1
    memory_text: str = ""


class AdvisorAskRequest(BaseModel):
    user_id: int = 1
    session_id: int | None = None
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=3, le=20)
    personalized_boost: bool = False


class AdvisorAskRead(BaseModel):
    session_id: int
    session_created: bool
    answer: str
    used_llm: bool
    memory_text: str
    used_personalization: bool = False
    retrieval_debug: dict[str, str] = Field(default_factory=dict)
    recommendations: list[AdvisorMentorRecommendationRead] = Field(default_factory=list)


class AdvisorVectorIndexStatusRead(BaseModel):
    vector_enabled: bool
    embedding_model: str
    total_mentors: int
    indexed_mentors: int
    outdated_mentors: int


class AdvisorVectorIndexRebuildRequest(BaseModel):
    force: bool = True
    batch_size: int = Field(default=32, ge=4, le=128)


class AdvisorVectorIndexRebuildRead(BaseModel):
    vector_enabled: bool
    embedding_model: str
    total_mentors: int
    updated_mentors: int
    skipped_mentors: int


class AdvisorLibrarySummaryGenerateRequest(BaseModel):
    user_id: int = 1
    scope: Literal["favorites"] = "favorites"


class AdvisorLibrarySummaryGenerateRead(BaseModel):
    summary_text: str
    used_llm: bool
    source_count: int
    updated: bool
