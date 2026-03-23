from datetime import datetime

from pydantic import BaseModel, Field


class DiscoveryJobCreate(BaseModel):
    school: str = Field(min_length=1, max_length=255)
    interested_field: str = Field(min_length=1, max_length=255)
    max_steps: int = Field(default=10, ge=1, le=50)
    target_mentor_count: int = Field(default=40, ge=1, le=300)
    enrich_limit: int = Field(default=5, ge=1, le=100)
    run_immediately: bool = False


class DiscoveryJobRead(BaseModel):
    id: str
    school: str
    interested_field: str
    status: str
    max_steps: int
    target_mentor_count: int
    enrich_limit: int
    progress_message: str
    raw_output_file: str
    enriched_output_file: str
    error_message: str
    mentor_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
