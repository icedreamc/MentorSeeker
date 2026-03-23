from pydantic import BaseModel, Field


class LocalSecretsRead(BaseModel):
    llm_base_url: str
    llm_model: str
    provider_email: str
    has_llm_api_key: bool
    has_browser_cookie: bool


class LocalSecretsUpdateRequest(BaseModel):
    llm_base_url: str | None = None
    llm_model: str | None = None
    provider_email: str | None = None
    llm_api_key: str | None = Field(default=None, description="When provided and non-empty, update key")
    browser_cookie: str | None = Field(default=None, description="When provided and non-empty, update cookie")
    clear_llm_api_key: bool = False
    clear_browser_cookie: bool = False


class LocalSecretsUpdateResponse(BaseModel):
    updated: bool
    has_llm_api_key: bool
    has_browser_cookie: bool


class ProfileRead(BaseModel):
    profile_text: str = ""
    library_summary_text: str = ""
    has_profile: bool = False
    has_library_summary: bool = False


class ProfileUpdateRequest(BaseModel):
    profile_text: str | None = None
    library_summary_text: str | None = None
    clear_profile: bool = False
    clear_library_summary: bool = False


class ProfileUpdateResponse(BaseModel):
    updated: bool
    profile_text: str = ""
    library_summary_text: str = ""
    has_profile: bool = False
    has_library_summary: bool = False
