from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Mentor, TimelineEvent
from .local_env_service import read_profile_state

CONTACT_SYSTEM_PROMPT = """
你是学术套磁信写作助手。请基于用户资料与导师信息生成高质量草稿。
要求：
- 真实具体，不夸张，不捏造成果。
- 清晰说明研究契合点与下一步请求。
- 语气礼貌克制，适配学术邮件风格。
输出 JSON：
{
  "subject": "...",
  "body": "...",
  "key_fit_points": ["...", "..."]
}
""".strip()


def _safe_json_loads(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return default


def _build_openai_client() -> OpenAI | None:
    api_key = (os.getenv("LLM_API_KEY", "") or settings.llm_api_key or "").strip()
    if not api_key:
        return None

    base_url = (settings.llm_base_url or "").strip() or None
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _chat_json(system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = _build_openai_client()
    if client is None:
        return {}

    model_name = settings.llm_model or "gpt-5-mini"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]

    raw = ""
    try:
        response = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=messages,
        )
        raw = response.choices[0].message.content or ""
    except Exception:  # noqa: BLE001
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
            )
            raw = response.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            return {}

    parsed = _safe_json_loads(raw, {})
    if isinstance(parsed, dict) and parsed:
        return parsed

    if raw.strip():
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            recovered = _safe_json_loads(match.group(0), {})
            if isinstance(recovered, dict):
                return recovered

    return {}


def _extract_keywords(mentor: Mentor) -> list[str]:
    structured = _safe_json_loads(mentor.structured_profile_json, {})
    if isinstance(structured, dict):
        raw = structured.get("ai_keywords", [])
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()][:8]
        if isinstance(raw, str):
            return [item.strip() for item in re.split(r"[,，;；]", raw) if item.strip()][:8]
    return []


def _mentor_payload(mentor: Mentor) -> dict[str, Any]:
    return {
        "mentor_id": mentor.id,
        "name": mentor.name,
        "school": mentor.school,
        "title": mentor.title,
        "interested_field": mentor.interested_field,
        "research_direction": mentor.research_direction,
        "high_level_summary": mentor.high_level_summary,
        "papers_summary": mentor.papers_summary,
        "keywords": _extract_keywords(mentor),
    }


def _profile_highlights(profile_text: str, limit: int = 3) -> list[str]:
    if not profile_text.strip():
        return []
    parts = re.split(r"[\n;；。]", profile_text)
    rows: list[str] = []
    for raw in parts:
        clean = raw.strip()
        if not clean:
            continue
        rows.append(clean[:90])
        if len(rows) >= limit:
            break
    return rows


def _fallback_contact_draft(*, mentor: Mentor, language: str, profile_text: str) -> tuple[str, str, list[str], bool]:
    highlights = _profile_highlights(profile_text, limit=3)

    if language == "en":
        subject = f"Prospective collaboration inquiry - {mentor.name}"
        opening = f"Dear Professor {mentor.name},"
        intro = "I am writing to express my interest in your research and to seek potential guidance."
        fit = f"I am particularly interested in your work on {mentor.research_direction or mentor.interested_field}."
        profile_line = f"My background includes: {'; '.join(highlights)}." if highlights else ""
        closing = "If possible, I would be grateful for a short discussion to explore potential fit."
    else:
        subject = f"套磁咨询：希望申请您的课题组（{mentor.name}）"
        opening = f"{mentor.name} 教授您好："
        intro = "冒昧来信，想表达我对您课题方向的浓厚兴趣，并咨询是否有进一步沟通的机会。"
        fit = f"我尤其关注您在“{mentor.research_direction or mentor.interested_field}”相关方向的研究。"
        profile_line = f"我的相关背景包括：{'；'.join(highlights)}。" if highlights else ""
        closing = "若您方便，我非常希望能进一步请教，并根据您的建议完善后续申请材料。"

    body = "\n\n".join([line for line in [opening, intro, fit, profile_line, closing] if line])
    key_points = [fit]
    return subject, body, key_points, False


def generate_contact_draft(
    db: Session,
    *,
    user_id: int,
    mentor_id: int,
    language: str = "auto",
    extra_instruction: str = "",
) -> dict[str, Any]:
    mentor = db.get(Mentor, mentor_id)
    if mentor is None:
        raise ValueError("Mentor not found")

    profile_state = read_profile_state()
    profile_text = str(profile_state.get("profile_text", ""))

    normalized_language = language if language in {"zh", "en"} else "zh"

    payload = {
        "language": normalized_language,
        "my_profile_text": profile_text,
        "mentor_profile": _mentor_payload(mentor),
        "extra_instruction": extra_instruction.strip(),
        "writing_rules": "具体、真实、礼貌、可执行；禁止编造经历或论文",
    }

    parsed = _chat_json(CONTACT_SYSTEM_PROMPT, payload)
    subject = str(parsed.get("subject", "")).strip() if isinstance(parsed, dict) else ""
    body = str(parsed.get("body", "")).strip() if isinstance(parsed, dict) else ""
    key_fit_points = parsed.get("key_fit_points", []) if isinstance(parsed, dict) else []

    if not subject or not body:
        subject, body, fallback_points, used_llm = _fallback_contact_draft(
            mentor=mentor,
            language=normalized_language,
            profile_text=profile_text,
        )
        return {
            "mentor_id": mentor_id,
            "subject": subject,
            "body": body,
            "used_llm": used_llm,
            "key_fit_points": fallback_points,
        }

    return {
        "mentor_id": mentor_id,
        "subject": subject,
        "body": body,
        "used_llm": True,
        "key_fit_points": [str(item).strip() for item in key_fit_points if str(item).strip()][:6],
    }


def commit_contact_draft(
    db: Session,
    *,
    user_id: int,
    mentor_id: int,
    event_date,
    subject: str,
    body: str,
) -> TimelineEvent:
    mentor = db.get(Mentor, mentor_id)
    if mentor is None:
        raise ValueError("Mentor not found")

    content = f"Subject: {subject.strip()}\n\n{body.strip()}"

    row = TimelineEvent(
        user_id=user_id,
        mentor_id=mentor_id,
        event_type="draft",
        event_date=event_date,
        content=content,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
