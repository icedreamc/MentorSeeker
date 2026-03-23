import importlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import OpenAI
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Favorite, Mentor, MentorNote, TimelineEvent

KEYWORD_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "using",
    "based",
    "study",
    "research",
    "professor",
    "university",
    "department",
    "导师",
    "教授",
    "研究",
    "方向",
    "相关",
    "以及",
    "包括",
    "进行",
}


def _safe_json_loads(raw: str, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _normalize_profile_urls(payload: dict) -> list[str]:
    value = payload.get("profile_url", [])
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _extract_profile_urls(mentor: Mentor) -> list[str]:
    value = _safe_json_loads(mentor.profile_urls_json, [])
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def _normalize_keywords(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = re.split(r"[,，;；/\\\n]+", value)
    elif isinstance(value, list):
        parts = [str(item) for item in value]
    else:
        return []

    result: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        keyword = str(raw).strip().strip("#")
        if not keyword:
            continue
        if len(keyword) > 28:
            keyword = keyword[:28].strip()
        lowered = keyword.lower()
        if lowered in seen or lowered in KEYWORD_STOPWORDS:
            continue
        seen.add(lowered)
        result.append(keyword)
        if len(result) >= 10:
            break
    return result


def _collect_profile_keywords(structured_profile: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ["ai_keywords", "keywords", "key_topics", "research_keywords", "research_interests", "tags"]:
        if key in structured_profile:
            candidates.extend(_normalize_keywords(structured_profile.get(key)))

    # Some payloads store interests in nested dict/list values.
    for key, value in structured_profile.items():
        if not isinstance(key, str):
            continue
        if "keyword" in key.lower() or "interest" in key.lower() or "topic" in key.lower():
            candidates.extend(_normalize_keywords(value))

    return _normalize_keywords(candidates)


def _heuristic_keywords(*texts: str) -> list[str]:
    joined = "\n".join([text for text in texts if text]).strip()
    if not joined:
        return []

    found: list[str] = []
    seen: set[str] = set()

    zh_phrases = re.findall(r"[\u4e00-\u9fff]{2,8}", joined)
    for phrase in zh_phrases:
        lowered = phrase.lower()
        if lowered in seen or lowered in KEYWORD_STOPWORDS:
            continue
        seen.add(lowered)
        found.append(phrase)
        if len(found) >= 8:
            return found

    en_tokens = re.findall(r"[A-Za-z][A-Za-z0-9+\-]{2,24}", joined)
    for token in en_tokens:
        lowered = token.lower()
        if lowered in seen or lowered in KEYWORD_STOPWORDS:
            continue
        seen.add(lowered)
        found.append(token)
        if len(found) >= 8:
            return found

    return found


def _build_openai_client() -> OpenAI | None:
    api_key = (os.getenv("LLM_API_KEY", "") or settings.llm_api_key or "").strip()
    if not api_key:
        return None

    base_url = (settings.llm_base_url or "").strip() or None
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _generate_ai_keywords_via_llm(*texts: str) -> list[str]:
    content = "\n".join([text for text in texts if text and text.strip()]).strip()
    if not content:
        return []

    client = _build_openai_client()
    if client is None:
        return []

    model_name = settings.llm_model or "gpt-5-mini"
    messages = [
        {
            "role": "system",
            "content": (
                "You extract concise academic topic tags for a mentor profile. "
                "Return JSON only with schema: {\"keywords\": [\"...\"]}. "
                "Use 4-8 short tags, avoid generic words."
            ),
        },
        {"role": "user", "content": content[:6000]},
    ]

    raw = ""
    try:
        resp = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=messages,
        )
        raw = resp.choices[0].message.content or ""
    except Exception:  # noqa: BLE001
        try:
            resp = client.chat.completions.create(model=model_name, messages=messages)
            raw = resp.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            return []

    parsed = _safe_json_loads(raw, {})
    if not isinstance(parsed, dict) and raw.strip():
        matched = re.search(r"\{[\s\S]*\}", raw)
        if matched:
            parsed = _safe_json_loads(matched.group(0), {})

    if isinstance(parsed, dict):
        return _normalize_keywords(parsed.get("keywords", []))
    return []


def _extract_ai_keywords(payload: dict, structured_profile: dict[str, Any]) -> list[str]:
    candidates: list[str] = []

    candidates.extend(_normalize_keywords(payload.get("ai_keywords", [])))
    candidates.extend(_normalize_keywords(payload.get("keywords", [])))
    candidates.extend(_collect_profile_keywords(structured_profile))

    normalized = _normalize_keywords(candidates)
    if normalized:
        return normalized

    papers_summary = str(payload.get("papers_summary", ""))
    high_level_summary = str(payload.get("high_level_summary", ""))

    # Only trigger extra LLM keyword extraction for enriched mentors (has summaries).
    if papers_summary.strip() or high_level_summary.strip():
        llm_keywords = _generate_ai_keywords_via_llm(
            str(payload.get("title", "")),
            str(payload.get("research_direction", "")),
            papers_summary,
            high_level_summary,
        )
        if llm_keywords:
            return llm_keywords

    return _heuristic_keywords(
        str(payload.get("research_direction", "")),
        papers_summary,
        high_level_summary,
    )


def is_mentor_auto_enriched(mentor: Mentor) -> bool:
    publications = _safe_json_loads(mentor.publications_json, [])
    structured_profile = _safe_json_loads(mentor.structured_profile_json, {})

    has_publications = isinstance(publications, list) and len(publications) > 0
    has_structured_profile = isinstance(structured_profile, dict) and len(structured_profile) > 0
    has_summaries = bool((mentor.papers_summary or "").strip() or (mentor.high_level_summary or "").strip())

    return has_publications or has_structured_profile or has_summaries


def upsert_mentors(db: Session, mentors: list[dict], school: str, interested_field: str, job_id: str) -> int:
    saved = 0
    for payload in mentors:
        name = str(payload.get("name", "")).strip()
        if not name:
            continue

        mentor = (
            db.query(Mentor)
            .filter(Mentor.school == school, Mentor.interested_field == interested_field, Mentor.name == name)
            .first()
        )
        if mentor is None:
            mentor = Mentor(school=school, interested_field=interested_field, name=name)
            db.add(mentor)

        structured_profile = payload.get("structured_profile", {})
        if not isinstance(structured_profile, dict):
            structured_profile = {}

        ai_keywords = _extract_ai_keywords(payload, structured_profile)
        if ai_keywords:
            structured_profile["ai_keywords"] = ai_keywords

        mentor.job_id = job_id
        mentor.title = str(payload.get("title", ""))
        mentor.research_direction = str(payload.get("research_direction", ""))
        mentor.profile_urls_json = json.dumps(_normalize_profile_urls(payload), ensure_ascii=False)
        mentor.structured_profile_json = json.dumps(structured_profile, ensure_ascii=False)
        mentor.publications_json = json.dumps(payload.get("publications", []), ensure_ascii=False)
        mentor.papers_summary = str(payload.get("papers_summary", ""))
        mentor.high_level_summary = str(payload.get("high_level_summary", ""))
        mentor.raw_payload_json = json.dumps(payload, ensure_ascii=False)
        saved += 1

    db.commit()
    return saved


def list_mentors(
    db: Session,
    *,
    page: int,
    page_size: int,
    q: str | None,
    school: str | None,
    interested_field: str | None,
    favorite_only: bool,
    user_id: int,
) -> tuple[list[Mentor], int, set[int]]:
    query = db.query(Mentor)

    if school:
        query = query.filter(Mentor.school.ilike(f"%{school}%"))
    if interested_field:
        query = query.filter(Mentor.interested_field.ilike(f"%{interested_field}%"))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Mentor.name.ilike(like),
                Mentor.title.ilike(like),
                Mentor.research_direction.ilike(like),
                Mentor.high_level_summary.ilike(like),
                Mentor.papers_summary.ilike(like),
            )
        )

    if favorite_only:
        query = query.join(Favorite, Favorite.mentor_id == Mentor.id).filter(
            Favorite.user_id == user_id,
            Favorite.is_favorite.is_(True),
        )

    total = query.count()
    items = (
        query.order_by(Mentor.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    mentor_ids = [item.id for item in items]
    favorite_ids: set[int] = set()
    if mentor_ids:
        favorite_ids = {
            row.mentor_id
            for row in db.query(Favorite)
            .filter(Favorite.user_id == user_id, Favorite.mentor_id.in_(mentor_ids), Favorite.is_favorite.is_(True))
            .all()
        }

    return items, total, favorite_ids


def get_mentor_detail(db: Session, mentor_id: int, user_id: int) -> tuple[Mentor | None, Favorite | None, MentorNote | None]:
    mentor = db.get(Mentor, mentor_id)
    if mentor is None:
        return None, None, None

    favorite = db.query(Favorite).filter(Favorite.user_id == user_id, Favorite.mentor_id == mentor_id).first()
    note = db.query(MentorNote).filter(MentorNote.user_id == user_id, MentorNote.mentor_id == mentor_id).first()
    return mentor, favorite, note


def create_manual_mentor(
    db: Session,
    *,
    school: str,
    interested_field: str,
    name: str,
    title: str,
    research_direction: str,
    profile_urls: list[str] | None = None,
) -> tuple[Mentor, bool]:
    normalized_school = school.strip()
    normalized_field = interested_field.strip()
    normalized_name = name.strip()

    existing = (
        db.query(Mentor)
        .filter(
            Mentor.school == normalized_school,
            Mentor.interested_field == normalized_field,
            Mentor.name == normalized_name,
        )
        .first()
    )
    if existing is not None:
        return existing, False

    clean_urls = [url.strip() for url in (profile_urls or []) if url and url.strip()]
    raw_payload = {
        "source": "manual",
        "school": normalized_school,
        "interested_field": normalized_field,
        "name": normalized_name,
        "title": title,
        "research_direction": research_direction,
        "profile_url": clean_urls,
        "ai_keywords": _heuristic_keywords(research_direction, title),
    }

    mentor = Mentor(
        school=normalized_school,
        interested_field=normalized_field,
        name=normalized_name,
        title=title,
        research_direction=research_direction,
        profile_urls_json=json.dumps(clean_urls, ensure_ascii=False),
        structured_profile_json=json.dumps({"ai_keywords": raw_payload["ai_keywords"]}, ensure_ascii=False),
        publications_json=json.dumps([], ensure_ascii=False),
        papers_summary="",
        high_level_summary="",
        raw_payload_json=json.dumps(raw_payload, ensure_ascii=False),
    )

    db.add(mentor)
    db.commit()
    db.refresh(mentor)
    return mentor, True


def batch_enrich_mentors(db: Session, mentor_ids: list[int], sleep_seconds: float = 0.2) -> dict:
    unique_ids = list(dict.fromkeys(mentor_ids))
    if not unique_ids:
        return {
            "requested_count": 0,
            "enriched_count": 0,
            "skipped_count": 0,
            "updated_ids": [],
            "output_file": "",
        }

    rows = db.query(Mentor).filter(Mentor.id.in_(unique_ids)).all()
    mentor_by_id = {row.id: row for row in rows}

    enrich_payload: list[dict] = []
    for mentor_id in unique_ids:
        mentor = mentor_by_id.get(mentor_id)
        if mentor is None:
            continue
        enrich_payload.append(
            {
                "__mentor_id": mentor.id,
                "name": mentor.name,
                "title": mentor.title,
                "research_direction": mentor.research_direction,
                "profile_url": _extract_profile_urls(mentor),
            }
        )

    if not enrich_payload:
        return {
            "requested_count": len(unique_ids),
            "enriched_count": 0,
            "skipped_count": len(unique_ids),
            "updated_ids": [],
            "output_file": "",
        }

    settings.ensure_dirs()
    data_dir = Path(settings.data_dir)
    input_file = data_dir / f"manual_batch_enrich_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    with open(input_file, "w", encoding="utf-8") as f:
        json.dump(enrich_payload, f, ensure_ascii=False, indent=2)

    if str(settings.project_root) not in sys.path:
        sys.path.insert(0, str(settings.project_root))

    enrichment_module_name = "backend.app.pipeline.mentor_enrichment"
    if enrichment_module_name in sys.modules:
        mentor_enrichment = importlib.reload(sys.modules[enrichment_module_name])
    else:
        mentor_enrichment = importlib.import_module(enrichment_module_name)

    enriched_data, output_file = mentor_enrichment.run_enrichment(
        input_file=str(input_file),
        enrich_limit=len(enrich_payload),
        sleep_seconds=sleep_seconds,
    )

    updated_ids: list[int] = []
    for payload in enriched_data:
        mentor_id = payload.get("__mentor_id")
        if not isinstance(mentor_id, int):
            continue

        mentor = mentor_by_id.get(mentor_id)
        if mentor is None:
            continue

        structured_profile = payload.get("structured_profile", {})
        if not isinstance(structured_profile, dict):
            structured_profile = {}

        ai_keywords = _extract_ai_keywords(payload, structured_profile)
        if ai_keywords:
            structured_profile["ai_keywords"] = ai_keywords

        mentor.profile_urls_json = json.dumps(_normalize_profile_urls(payload), ensure_ascii=False)
        mentor.structured_profile_json = json.dumps(structured_profile, ensure_ascii=False)
        mentor.publications_json = json.dumps(payload.get("publications", []), ensure_ascii=False)
        mentor.papers_summary = str(payload.get("papers_summary", ""))
        mentor.high_level_summary = str(payload.get("high_level_summary", ""))
        mentor.raw_payload_json = json.dumps(payload, ensure_ascii=False)
        updated_ids.append(mentor_id)

    db.commit()

    return {
        "requested_count": len(unique_ids),
        "enriched_count": len(updated_ids),
        "skipped_count": len(unique_ids) - len(updated_ids),
        "updated_ids": updated_ids,
        "output_file": str(output_file),
    }


def set_favorite(db: Session, mentor_id: int, user_id: int, is_favorite: bool) -> Favorite:
    row = db.query(Favorite).filter(Favorite.user_id == user_id, Favorite.mentor_id == mentor_id).first()
    if row is None:
        row = Favorite(user_id=user_id, mentor_id=mentor_id, is_favorite=is_favorite)
        db.add(row)
    else:
        row.is_favorite = is_favorite

    db.commit()
    db.refresh(row)
    return row


def update_note(db: Session, mentor_id: int, user_id: int, note_text: str, tags: list[str]) -> MentorNote:
    row = db.query(MentorNote).filter(MentorNote.user_id == user_id, MentorNote.mentor_id == mentor_id).first()
    tags_json = json.dumps(tags, ensure_ascii=False)

    if row is None:
        row = MentorNote(user_id=user_id, mentor_id=mentor_id, note_text=note_text, tags_json=tags_json)
        db.add(row)
    else:
        row.note_text = note_text
        row.tags_json = tags_json

    db.commit()
    db.refresh(row)
    return row


def remove_from_library(db: Session, mentor_id: int, user_id: int) -> dict:
    deleted_favorites = (
        db.query(Favorite)
        .filter(Favorite.user_id == user_id, Favorite.mentor_id == mentor_id)
        .delete(synchronize_session=False)
    )
    deleted_notes = (
        db.query(MentorNote)
        .filter(MentorNote.user_id == user_id, MentorNote.mentor_id == mentor_id)
        .delete(synchronize_session=False)
    )
    deleted_timeline = (
        db.query(TimelineEvent)
        .filter(TimelineEvent.user_id == user_id, TimelineEvent.mentor_id == mentor_id)
        .delete(synchronize_session=False)
    )
    db.commit()

    return {
        "deleted_favorites": deleted_favorites,
        "deleted_notes": deleted_notes,
        "deleted_timeline": deleted_timeline,
    }


def delete_mentor_permanently(db: Session, mentor_id: int) -> dict:
    deleted_favorites = db.query(Favorite).filter(Favorite.mentor_id == mentor_id).delete(synchronize_session=False)
    deleted_notes = db.query(MentorNote).filter(MentorNote.mentor_id == mentor_id).delete(synchronize_session=False)
    deleted_timeline = db.query(TimelineEvent).filter(TimelineEvent.mentor_id == mentor_id).delete(synchronize_session=False)
    deleted_mentor = db.query(Mentor).filter(Mentor.id == mentor_id).delete(synchronize_session=False)
    db.commit()

    return {
        "deleted_mentor": deleted_mentor,
        "deleted_favorites": deleted_favorites,
        "deleted_notes": deleted_notes,
        "deleted_timeline": deleted_timeline,
    }


def parse_mentor_json_fields(mentor: Mentor) -> dict:
    structured_profile = _safe_json_loads(mentor.structured_profile_json, {})
    if not isinstance(structured_profile, dict):
        structured_profile = {}

    raw_payload = _safe_json_loads(mentor.raw_payload_json, {})
    if not isinstance(raw_payload, dict):
        raw_payload = {}

    ai_keywords = _collect_profile_keywords(structured_profile)
    if not ai_keywords:
        ai_keywords = _normalize_keywords(raw_payload.get("ai_keywords", []))
    if not ai_keywords:
        ai_keywords = _heuristic_keywords(mentor.research_direction, mentor.high_level_summary, mentor.papers_summary)

    return {
        "profile_urls": _safe_json_loads(mentor.profile_urls_json, []),
        "structured_profile": structured_profile,
        "publications": _safe_json_loads(mentor.publications_json, []),
        "ai_keywords": ai_keywords,
    }


def parse_note_tags(note: MentorNote | None) -> list[str]:
    if note is None:
        return []
    return _safe_json_loads(note.tags_json, [])



def batch_delete_mentors_permanently(db: Session, mentor_ids: list[int]) -> dict:
    unique_ids = list(dict.fromkeys(mentor_ids))
    if not unique_ids:
        return {
            "requested_count": 0,
            "deleted_count": 0,
            "not_found_count": 0,
            "deleted_ids": [],
            "not_found_ids": [],
            "deleted_favorites": 0,
            "deleted_notes": 0,
            "deleted_timeline": 0,
        }

    existing_rows = db.query(Mentor.id).filter(Mentor.id.in_(unique_ids)).all()
    existing_ids = {int(row[0]) for row in existing_rows}
    not_found_ids = [mentor_id for mentor_id in unique_ids if mentor_id not in existing_ids]

    deleted_favorites = 0
    deleted_notes = 0
    deleted_timeline = 0

    for mentor_id in existing_ids:
        deleted_favorites += db.query(Favorite).filter(Favorite.mentor_id == mentor_id).delete(synchronize_session=False)
        deleted_notes += db.query(MentorNote).filter(MentorNote.mentor_id == mentor_id).delete(synchronize_session=False)
        deleted_timeline += db.query(TimelineEvent).filter(TimelineEvent.mentor_id == mentor_id).delete(synchronize_session=False)

    deleted_mentors = db.query(Mentor).filter(Mentor.id.in_(existing_ids)).delete(synchronize_session=False)
    db.commit()

    deleted_ids = [mentor_id for mentor_id in unique_ids if mentor_id in existing_ids]

    return {
        "requested_count": len(unique_ids),
        "deleted_count": int(deleted_mentors),
        "not_found_count": len(not_found_ids),
        "deleted_ids": deleted_ids,
        "not_found_ids": not_found_ids,
        "deleted_favorites": int(deleted_favorites),
        "deleted_notes": int(deleted_notes),
        "deleted_timeline": int(deleted_timeline),
    }

