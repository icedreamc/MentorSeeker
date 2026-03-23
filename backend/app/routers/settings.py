from __future__ import annotations

import os

from fastapi import APIRouter

from ..config import settings
from ..schemas.settings import (
    LocalSecretsRead,
    LocalSecretsUpdateRequest,
    LocalSecretsUpdateResponse,
    ProfileRead,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
)
from ..services.local_env_service import (
    LIBRARY_SUMMARY_TEXT_KEY,
    PROFILE_TEXT_KEY,
    apply_runtime_values,
    clean_single_line,
    encode_text_to_b64,
    read_env_map,
    read_profile_state,
    update_env_file,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/local-secrets", response_model=LocalSecretsRead)
def get_local_secrets() -> LocalSecretsRead:
    env_map = read_env_map()

    llm_base_url = env_map.get("LLM_BASE_URL", settings.llm_base_url)
    llm_model = env_map.get("LLM_MODEL", settings.llm_model)
    provider_email = env_map.get("PROVIDER_EMAIL", os.getenv("PROVIDER_EMAIL", ""))

    has_llm_api_key = bool(env_map.get("LLM_API_KEY", os.getenv("LLM_API_KEY", "")).strip())
    has_browser_cookie = bool(env_map.get("BROWSER_COOKIE", os.getenv("BROWSER_COOKIE", "")).strip())

    return LocalSecretsRead(
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        provider_email=provider_email,
        has_llm_api_key=has_llm_api_key,
        has_browser_cookie=has_browser_cookie,
    )


@router.patch("/local-secrets", response_model=LocalSecretsUpdateResponse)
def patch_local_secrets(payload: LocalSecretsUpdateRequest) -> LocalSecretsUpdateResponse:
    changes: dict[str, str | None] = {}

    if payload.llm_base_url is not None:
        changes["LLM_BASE_URL"] = clean_single_line(payload.llm_base_url)
    if payload.llm_model is not None:
        changes["LLM_MODEL"] = clean_single_line(payload.llm_model)
    if payload.provider_email is not None:
        changes["PROVIDER_EMAIL"] = clean_single_line(payload.provider_email)

    if payload.clear_llm_api_key:
        changes["LLM_API_KEY"] = None
    elif payload.llm_api_key is not None:
        cleaned_key = clean_single_line(payload.llm_api_key)
        if cleaned_key:
            changes["LLM_API_KEY"] = cleaned_key

    if payload.clear_browser_cookie:
        changes["BROWSER_COOKIE"] = None
    elif payload.browser_cookie is not None:
        cleaned_cookie = clean_single_line(payload.browser_cookie)
        if cleaned_cookie:
            changes["BROWSER_COOKIE"] = cleaned_cookie

    if changes:
        update_env_file(changes)
        apply_runtime_values(changes)

    refreshed = read_env_map()
    has_llm_api_key = bool(refreshed.get("LLM_API_KEY", os.getenv("LLM_API_KEY", "")).strip())
    has_browser_cookie = bool(refreshed.get("BROWSER_COOKIE", os.getenv("BROWSER_COOKIE", "")).strip())

    return LocalSecretsUpdateResponse(
        updated=bool(changes),
        has_llm_api_key=has_llm_api_key,
        has_browser_cookie=has_browser_cookie,
    )


@router.get("/profile", response_model=ProfileRead)
def get_profile() -> ProfileRead:
    return ProfileRead(**read_profile_state())


@router.patch("/profile", response_model=ProfileUpdateResponse)
def patch_profile(payload: ProfileUpdateRequest) -> ProfileUpdateResponse:
    changes: dict[str, str | None] = {}

    if payload.clear_profile:
        changes[PROFILE_TEXT_KEY] = None
    elif payload.profile_text is not None:
        cleaned_profile = payload.profile_text.strip()
        changes[PROFILE_TEXT_KEY] = encode_text_to_b64(cleaned_profile) if cleaned_profile else None

    if payload.clear_library_summary:
        changes[LIBRARY_SUMMARY_TEXT_KEY] = None
    elif payload.library_summary_text is not None:
        cleaned_summary = payload.library_summary_text.strip()
        changes[LIBRARY_SUMMARY_TEXT_KEY] = encode_text_to_b64(cleaned_summary) if cleaned_summary else None

    if changes:
        update_env_file(changes)
        apply_runtime_values(changes)

    state = read_profile_state()
    return ProfileUpdateResponse(updated=bool(changes), **state)
