from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AdvisorMessage, AdvisorSession, Favorite, Mentor, MentorNote, MentorVectorIndex, UserPreferenceMemory
from .local_env_service import LIBRARY_SUMMARY_TEXT_KEY, apply_runtime_values, encode_text_to_b64, read_profile_state, update_env_file

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "about",
    "this",
    "that",
    "you",
    "your",
    "are",
    "was",
    "were",
    "have",
    "has",
    "希望",
    "需要",
    "导师",
    "老师",
    "一个",
    "一些",
}

DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

RAG_SYSTEM_PROMPT = (
    "You are an academic mentor recommendation assistant. "
    "Use only the retrieved mentor candidates as evidence. "
    "Return practical, concise, and preference-aware recommendations."
)

RAG_USER_PROMPT_TEMPLATE = """
Task:
1) Read user query and dynamic memory.
2) Rank and recommend the best mentors from candidate list only.
3) Provide concrete reasons tied to candidate fields.
4) Update memory with stable preference signals.

Output JSON schema:
{
  "answer": "string",
  "recommendations": [
    {"mentor_id": 123, "reason": "string"}
  ],
  "memory_update": "string"
}

Rules:
- Do not invent mentors not in candidate list.
- recommendation mentor_id must exist in candidate list.
- Prefer 3-5 recommendations.
- Keep answer actionable.
""".strip()


def _safe_json_loads(raw: str, default: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return default


def _clean_text(value: str) -> str:
    return value.strip()


def _tokenize(text: str) -> list[str]:
    normalized = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", " ", text.lower()).strip()
    if not normalized:
        return []

    tokens: list[str] = []
    seen: set[str] = set()
    for token in normalized.split(" "):
        if len(token) < 2:
            continue
        if token in STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _mentor_document_text(mentor: Mentor) -> str:
    parts = [
        mentor.school,
        mentor.interested_field,
        mentor.name,
        mentor.title,
        mentor.research_direction,
        mentor.papers_summary,
        mentor.high_level_summary,
    ]

    structured_profile = _safe_json_loads(mentor.structured_profile_json, {})
    publications = _safe_json_loads(mentor.publications_json, [])

    if isinstance(structured_profile, dict) and structured_profile:
        parts.append(json.dumps(structured_profile, ensure_ascii=False))
    if isinstance(publications, list) and publications:
        parts.append(json.dumps(publications[:8], ensure_ascii=False))

    return " ".join([str(item) for item in parts if str(item).strip()]).strip()


def _mentor_content_hash(document: str) -> str:
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


def _build_reason(mentor: Mentor, tokens: list[str]) -> str:
    reason_parts: list[str] = []
    lower_research = (mentor.research_direction or "").lower()
    lower_field = (mentor.interested_field or "").lower()
    lower_title = (mentor.title or "").lower()

    matched_tokens = [token for token in tokens if token in lower_research or token in lower_field or token in lower_title]
    if matched_tokens:
        reason_parts.append(f"keyword hits: {', '.join(matched_tokens[:4])}")

    if mentor.interested_field:
        reason_parts.append(f"field: {mentor.interested_field}")

    if mentor.research_direction:
        preview = mentor.research_direction.strip().replace("\n", " ")
        if len(preview) > 80:
            preview = preview[:80] + "..."
        reason_parts.append(f"research: {preview}")

    if not reason_parts:
        return "Semantically relevant to the query and memory context."
    return "; ".join(reason_parts)


def _build_openai_client() -> OpenAI | None:
    # Prefer runtime env var (can be updated without restart), then fallback to persisted settings.
    api_key = (os.getenv("LLM_API_KEY", "") or settings.llm_api_key or "").strip()
    if not api_key:
        return None

    base_url = (settings.llm_base_url or "").strip() or None
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def _embed_texts(client: OpenAI, texts: list[str], model: str) -> list[list[float]]:
    if not texts:
        return []
    response = client.embeddings.create(model=model, input=texts)
    vectors: list[list[float]] = []
    for row in response.data:
        vectors.append([float(item) for item in row.embedding])
    return vectors


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b

    if norm_a <= 0 or norm_b <= 0:
        return 0.0

    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def get_vector_index_status(db: Session) -> dict:
    total_mentors = int(db.query(func.count(Mentor.id)).scalar() or 0)
    indexed_mentors = int(db.query(func.count(MentorVectorIndex.id)).scalar() or 0)
    embedding_model = DEFAULT_EMBEDDING_MODEL
    vector_enabled = _build_openai_client() is not None

    outdated = 0
    if total_mentors > 0 and indexed_mentors > 0:
        mentors = db.query(Mentor).all()
        index_map = {row.mentor_id: row for row in db.query(MentorVectorIndex).all()}

        for mentor in mentors:
            row = index_map.get(mentor.id)
            if row is None:
                outdated += 1
                continue
            document = _mentor_document_text(mentor)
            content_hash = _mentor_content_hash(document)
            if row.embedding_model != embedding_model or row.content_hash != content_hash:
                outdated += 1
    elif total_mentors > 0:
        outdated = total_mentors

    return {
        "vector_enabled": vector_enabled,
        "embedding_model": embedding_model,
        "total_mentors": total_mentors,
        "indexed_mentors": indexed_mentors,
        "outdated_mentors": outdated,
    }


def _upsert_vector_row(
    db: Session,
    *,
    mentor_id: int,
    embedding_model: str,
    content_hash: str,
    vector: list[float],
) -> None:
    row = db.query(MentorVectorIndex).filter(MentorVectorIndex.mentor_id == mentor_id).first()
    vector_json = json.dumps(vector, ensure_ascii=False)

    if row is None:
        row = MentorVectorIndex(
            mentor_id=mentor_id,
            embedding_model=embedding_model,
            content_hash=content_hash,
            vector_dim=len(vector),
            vector_json=vector_json,
        )
        db.add(row)
    else:
        row.embedding_model = embedding_model
        row.content_hash = content_hash
        row.vector_dim = len(vector)
        row.vector_json = vector_json


def sync_vector_index(db: Session, *, force: bool = False, batch_size: int = 32) -> dict:
    client = _build_openai_client()
    embedding_model = DEFAULT_EMBEDDING_MODEL
    mentors = db.query(Mentor).order_by(Mentor.id.asc()).all()
    total_mentors = len(mentors)

    if client is None:
        return {
            "vector_enabled": False,
            "embedding_model": embedding_model,
            "total_mentors": total_mentors,
            "updated_mentors": 0,
            "skipped_mentors": total_mentors,
        }

    existing = {row.mentor_id: row for row in db.query(MentorVectorIndex).all()}

    pending: list[tuple[Mentor, str, str]] = []
    for mentor in mentors:
        document = _mentor_document_text(mentor)
        content_hash = _mentor_content_hash(document)
        row = existing.get(mentor.id)

        needs_update = force or row is None or row.embedding_model != embedding_model or row.content_hash != content_hash
        if needs_update:
            pending.append((mentor, document, content_hash))

    updated_mentors = 0

    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        if not batch:
            continue

        texts = [item[1] for item in batch]
        vectors = _embed_texts(client, texts, embedding_model)

        for (mentor, _, content_hash), vector in zip(batch, vectors):
            _upsert_vector_row(
                db,
                mentor_id=mentor.id,
                embedding_model=embedding_model,
                content_hash=content_hash,
                vector=vector,
            )
            updated_mentors += 1

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # Handle rare concurrent upsert races deterministically.
            for (mentor, _, content_hash), vector in zip(batch, vectors):
                _upsert_vector_row(
                    db,
                    mentor_id=mentor.id,
                    embedding_model=embedding_model,
                    content_hash=content_hash,
                    vector=vector,
                )
            db.commit()

    skipped_mentors = total_mentors - updated_mentors

    return {
        "vector_enabled": True,
        "embedding_model": embedding_model,
        "total_mentors": total_mentors,
        "updated_mentors": updated_mentors,
        "skipped_mentors": skipped_mentors,
    }


def _lexical_candidates(db: Session, query: str, memory_text: str, top_k: int) -> list[dict]:
    mentors = db.query(Mentor).all()
    if not mentors:
        return []

    merged_query = f"{query} {memory_text}".strip()
    tokens = _tokenize(merged_query)
    query_lower = query.lower()

    scored: list[tuple[float, Mentor]] = []
    for mentor in mentors:
        doc = _mentor_document_text(mentor).lower()
        score = 0.0

        for token in tokens:
            if token in (mentor.name or "").lower():
                score += 4.0
            elif token in (mentor.research_direction or "").lower():
                score += 3.2
            elif token in (mentor.interested_field or "").lower():
                score += 2.8
            elif token in doc:
                score += 1.1

        if query_lower and query_lower in doc:
            score += 3.0

        scored.append((score, mentor))

    scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)

    rows: list[dict] = []
    for score, mentor in scored[: top_k * 3]:
        rows.append(
            {
                "mentor_id": mentor.id,
                "name": mentor.name,
                "school": mentor.school,
                "title": mentor.title,
                "research_direction": mentor.research_direction,
                "match_score": round(float(score), 4),
                "reason": _build_reason(mentor, tokens),
                "_vector_score": 0.0,
                "_lexical_score": float(score),
            }
        )
    return rows


def _vector_candidates(db: Session, query: str, memory_text: str, top_k: int) -> list[dict]:
    sync_status = sync_vector_index(db, force=False, batch_size=32)
    if not sync_status["vector_enabled"]:
        return []

    client = _build_openai_client()
    if client is None:
        return []

    query_text = f"User query: {query}\nUser preference memory: {memory_text}".strip()
    query_vector = _embed_texts(client, [query_text], sync_status["embedding_model"])
    if not query_vector:
        return []

    qvec = query_vector[0]
    vector_rows = db.query(MentorVectorIndex).all()
    if not vector_rows:
        return []

    mentor_ids = [row.mentor_id for row in vector_rows]
    mentor_map = {row.id: row for row in db.query(Mentor).filter(Mentor.id.in_(mentor_ids)).all()}

    tokens = _tokenize(f"{query} {memory_text}")
    scored: list[dict] = []
    for row in vector_rows:
        mentor = mentor_map.get(row.mentor_id)
        if mentor is None:
            continue

        raw_vector = _safe_json_loads(row.vector_json, [])
        if not isinstance(raw_vector, list) or not raw_vector:
            continue

        vec = [float(item) for item in raw_vector]
        similarity = _cosine_similarity(qvec, vec)

        reason = f"vector similarity: {similarity:.3f}; {_build_reason(mentor, tokens)}"
        scored.append(
            {
                "mentor_id": mentor.id,
                "name": mentor.name,
                "school": mentor.school,
                "title": mentor.title,
                "research_direction": mentor.research_direction,
                "match_score": round(float(similarity), 4),
                "reason": reason,
                "_vector_score": float(max(similarity, 0.0)),
                "_lexical_score": 0.0,
            }
        )

    scored.sort(key=lambda item: item["_vector_score"], reverse=True)
    return scored[: top_k * 3]


def _hybrid_merge(vector_rows: list[dict], lexical_rows: list[dict], top_k: int) -> list[dict]:
    merged: dict[int, dict] = {}

    for item in lexical_rows:
        merged[item["mentor_id"]] = {**item}

    for item in vector_rows:
        mentor_id = item["mentor_id"]
        if mentor_id not in merged:
            merged[mentor_id] = {**item}
        else:
            base = merged[mentor_id]
            base["_vector_score"] = max(float(base.get("_vector_score", 0.0)), float(item.get("_vector_score", 0.0)))
            if item.get("reason") and item["reason"] not in base.get("reason", ""):
                base["reason"] = f"{base.get('reason', '')}; {item['reason']}".strip("; ")

    rows: list[dict] = []
    for item in merged.values():
        vec = float(item.get("_vector_score", 0.0))
        lex_raw = float(item.get("_lexical_score", 0.0))
        lex = min(lex_raw / 12.0, 1.0)

        if vec > 0:
            hybrid = 0.78 * vec + 0.22 * lex
        else:
            hybrid = 0.55 * lex

        row = {**item}
        row["match_score"] = round(hybrid * 100.0, 2)
        rows.append(row)

    rows.sort(key=lambda item: item["match_score"], reverse=True)

    output: list[dict] = []
    for item in rows[:top_k]:
        clean = {k: v for k, v in item.items() if not k.startswith("_")}
        output.append(clean)
    return output


def retrieve_candidates(db: Session, query: str, memory_text: str, top_k: int) -> list[dict]:
    vector_rows = _vector_candidates(db, query, memory_text, top_k)
    lexical_rows = _lexical_candidates(db, query, memory_text, top_k)
    return _hybrid_merge(vector_rows, lexical_rows, top_k)


def _fallback_answer(query: str, candidates: list[dict]) -> tuple[str, list[dict], bool, str]:
    if not candidates:
        answer = (
            "No strong mentor candidates were found for the current query. "
            "Try adding clearer preferences (field, methods, location, publication preference)."
        )
        return answer, [], False, f"focus: {query[:80]}"

    picks = candidates[:5]
    ranked_names = ", ".join([item["name"] for item in picks[:3]])
    answer = (
        "Based on vector retrieval + metadata matching, I selected top candidates for your next outreach round. "
        f"Start with: {ranked_names}."
    )
    memory_update = f"focus: {query[:120]}"
    return answer, picks, False, memory_update


def _parse_llm_json(raw_content: str) -> dict[str, Any]:
    try:
        return json.loads(raw_content)
    except Exception:  # noqa: BLE001
        return {}


def generate_answer_with_rag(query: str, memory_text: str, candidates: list[dict]) -> tuple[str, list[dict], bool, str]:
    client = _build_openai_client()
    if client is None:
        return _fallback_answer(query, candidates)

    payload = [
        {
            "mentor_id": item["mentor_id"],
            "name": item["name"],
            "school": item["school"],
            "title": item["title"],
            "research_direction": item["research_direction"],
            "match_score": item["match_score"],
            "retrieval_reason": item["reason"],
        }
        for item in candidates[:10]
    ]

    user_payload = {
        "query": query,
        "dynamic_memory": memory_text,
        "candidate_mentors": payload,
        "prompt_template": RAG_USER_PROMPT_TEMPLATE,
    }

    model_name = settings.llm_model or "gpt-5-mini"
    messages = [
        {"role": "system", "content": RAG_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]

    # Compatibility-first call: do not pass temperature / reasoning.
    # Some OpenAI-compatible providers also reject response_format, so retry once without it.
    try:
        response = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            messages=messages,
        )
    except Exception:  # noqa: BLE001
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
            )
        except Exception:  # noqa: BLE001
            return _fallback_answer(query, candidates)

    raw = response.choices[0].message.content or "{}"
    parsed = _parse_llm_json(raw)

    # If provider returned non-strict text, try to recover the first JSON object from it.
    if not parsed and raw.strip():
        json_match = re.search(r"\{[\s\S]*\}", raw)
        if json_match:
            parsed = _parse_llm_json(json_match.group(0))

    llm_answer = str(parsed.get("answer", "")).strip()
    if not llm_answer:
        llm_answer = "I ranked mentors using retrieved evidence and generated outreach priorities for you."

    reason_map: dict[int, str] = {}
    for row in parsed.get("recommendations", []):
        if not isinstance(row, dict):
            continue
        mentor_id_raw = row.get("mentor_id")
        reason = str(row.get("reason", "")).strip()
        try:
            mentor_id = int(mentor_id_raw)
        except Exception:  # noqa: BLE001
            continue
        if reason:
            reason_map[mentor_id] = reason

    selected: list[dict] = []
    for item in candidates:
        mentor_id = int(item["mentor_id"])
        if mentor_id in reason_map:
            selected.append({**item, "reason": reason_map[mentor_id]})

    if not selected:
        selected = candidates[:5]

    memory_update = str(parsed.get("memory_update", "")).strip()
    return llm_answer, selected[:5], True, memory_update

def _extract_preference_hints(query: str) -> list[str]:
    text = _clean_text(query)
    if not text:
        return []

    patterns = [
        r"(?:\u504f\u597d|\u5e0c\u671b|\u5173\u6ce8|\u4e0d\u60f3)\s*([^\u3002\uff1b;,\n]{1,60})",
        r"(?:prefer|focus on|interested in)\s*([^.;,\n]{1,60})",
    ]

    hints: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            item = _clean_text(str(match))
            if item:
                hints.append(item)

    if not hints:
        hints.append(text[:100])

    return hints[:6]


def merge_dynamic_memory(previous_memory: str, query: str, llm_memory_update: str) -> str:
    latest_signal = _clean_text(llm_memory_update)
    if not latest_signal:
        latest_signal = "; ".join(_extract_preference_hints(query))

    return _rewrite_dynamic_memory(
        previous_memory=previous_memory,
        query=query,
        latest_signal=latest_signal,
    )


def get_or_create_memory(db: Session, user_id: int) -> UserPreferenceMemory:
    row = db.query(UserPreferenceMemory).filter(UserPreferenceMemory.user_id == user_id).first()
    if row is not None:
        return row

    row = UserPreferenceMemory(user_id=user_id, memory_text="")
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        # Concurrent create: another request inserted the same user_id first.
        db.rollback()
        existed = db.query(UserPreferenceMemory).filter(UserPreferenceMemory.user_id == user_id).first()
        if existed is not None:
            return existed
        raise


def create_session(db: Session, user_id: int, title: str | None = None) -> AdvisorSession:
    normalized_title = _clean_text(title or "")
    row = AdvisorSession(user_id=user_id, title=normalized_title or "New Session")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_session(db: Session, user_id: int, session_id: int) -> AdvisorSession | None:
    return (
        db.query(AdvisorSession)
        .filter(AdvisorSession.user_id == user_id, AdvisorSession.id == session_id)
        .first()
    )


def delete_session(db: Session, user_id: int, session_id: int) -> bool:
    row = get_session(db, user_id=user_id, session_id=session_id)
    if row is None:
        return False

    # SQLite may not enforce FK on-delete cascade by default; delete messages explicitly.
    db.query(AdvisorMessage).filter(AdvisorMessage.session_id == session_id).delete(synchronize_session=False)
    db.delete(row)
    db.commit()
    return True


def list_sessions_with_counts(db: Session, user_id: int, limit: int) -> list[dict]:
    sessions = (
        db.query(AdvisorSession)
        .filter(AdvisorSession.user_id == user_id)
        .order_by(AdvisorSession.updated_at.desc(), AdvisorSession.id.desc())
        .limit(limit)
        .all()
    )

    ids = [row.id for row in sessions]
    count_map: dict[int, int] = {}
    if ids:
        grouped = (
            db.query(AdvisorMessage.session_id, func.count(AdvisorMessage.id))
            .filter(AdvisorMessage.session_id.in_(ids))
            .group_by(AdvisorMessage.session_id)
            .all()
        )
        count_map = {int(session_id): int(count) for session_id, count in grouped}

    return [
        {
            "id": row.id,
            "user_id": row.user_id,
            "title": row.title,
            "message_count": count_map.get(row.id, 0),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in sessions
    ]


def get_session_messages(db: Session, session_id: int) -> list[dict]:
    rows = (
        db.query(AdvisorMessage)
        .filter(AdvisorMessage.session_id == session_id)
        .order_by(AdvisorMessage.id.asc())
        .all()
    )

    items: list[dict] = []
    for row in rows:
        recommendations = _safe_json_loads(row.recommendations_json, [])
        if not isinstance(recommendations, list):
            recommendations = []
        items.append(
            {
                "id": row.id,
                "role": row.role,
                "content": row.content,
                "recommendations": recommendations,
                "created_at": row.created_at,
            }
        )
    return items


def ask_advisor(
    db: Session,
    *,
    user_id: int,
    session_id: int | None,
    query: str,
    top_k: int,
) -> dict:
    session_created = False

    if session_id is None:
        session = create_session(db, user_id=user_id, title=_clean_text(query)[:30])
        session_created = True
    else:
        session = get_session(db, user_id=user_id, session_id=session_id)
        if session is None:
            raise ValueError("Session not found")

    memory_row = get_or_create_memory(db, user_id=user_id)
    candidates = retrieve_candidates(db, query=query, memory_text=memory_row.memory_text, top_k=top_k)

    answer, recommendations, used_llm, llm_memory_update = generate_answer_with_rag(
        query=query,
        memory_text=memory_row.memory_text,
        candidates=candidates,
    )

    updated_memory = merge_dynamic_memory(memory_row.memory_text, query, llm_memory_update)
    memory_row.memory_text = updated_memory

    user_msg = AdvisorMessage(
        session_id=session.id,
        role="user",
        content=_clean_text(query),
        retrieved_mentor_ids_json="[]",
        recommendations_json="[]",
    )
    assistant_msg = AdvisorMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        retrieved_mentor_ids_json=json.dumps([item["mentor_id"] for item in candidates], ensure_ascii=False),
        recommendations_json=json.dumps(recommendations, ensure_ascii=False),
    )

    session.updated_at = datetime.now(timezone.utc)
    if session.title in {"New Session", "新会话"}:
        session.title = _clean_text(query)[:30] or session.title

    db.add(user_msg)
    db.add(assistant_msg)
    db.commit()
    db.refresh(memory_row)

    return {
        "session_id": session.id,
        "session_created": session_created,
        "answer": answer,
        "used_llm": used_llm,
        "memory_text": memory_row.memory_text,
        "recommendations": recommendations,
    }






# ---- Personalized retrieval and library-summary extensions ----
QUERY_REWRITE_SYSTEM_PROMPT = """
你是“检索查询重写器”。目标：提升导师召回相关性与多样性，禁止过度收敛。
输出 JSON：
{
  "semantic_query": "...",
  "keyword_query": "...",
  "must_have": ["..."],
  "nice_to_have": ["..."],
  "avoid": ["..."],
  "diversity_guard": "..."
}
规则：
- 以 user_query 为主，不偏离核心诉求。
- library_summary_text 仅提炼 1-2 条高层偏好，不可当硬过滤。
- 不得引入输入中不存在的事实。
""".strip()

LIBRARY_SUMMARY_SYSTEM_PROMPT = """
You are an academic preference summarizer.
Summarize user mentor-library preference into a concise Chinese brief.
Output JSON: {"summary_text": "..."}
Rules:
- Keep exactly 4 lines, each line <= 24 Chinese characters when possible.
- Focus on: topic preference / method preference / advisor style / risk boundary.
- No fluff, no repeated phrases, no fabricated facts.
""".strip()

MEMORY_UPDATE_SYSTEM_PROMPT = """
You are a preference-memory editor.
Rewrite and consolidate memory; do NOT append logs.
Output JSON: {"memory_text": "..."}
Rules:
- Keep 3-6 stable preference items in concise Chinese.
- If old and new conflict, prefer latest user query.
- Remove stale or redundant items.
- Return semicolon-separated short phrases.
""".strip()


def _chat_json(model_name: str, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
    client = _build_openai_client()
    if client is None:
        return {}

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
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
            response = client.chat.completions.create(model=model_name, messages=messages)
            raw = response.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            return {}

    parsed = _safe_json_loads(raw, {})
    if isinstance(parsed, dict) and parsed:
        return parsed

    if raw.strip():
        matched = re.search(r"\{[\s\S]*\}", raw)
        if matched:
            recovered = _safe_json_loads(matched.group(0), {})
            if isinstance(recovered, dict):
                return recovered
    return {}


def _extract_top_lines(text: str, *, max_lines: int, max_len: int = 80) -> list[str]:
    if not text.strip():
        return []
    parts = re.split(r"[\n;；。]", text)
    picked: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        clean = raw.strip()
        if not clean:
            continue
        if len(clean) > max_len:
            clean = clean[:max_len].strip()
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        picked.append(clean)
        if len(picked) >= max_lines:
            break
    return picked



def _compact_text_lines(text: str, *, max_items: int, max_len: int) -> list[str]:
    if not text.strip():
        return []

    parts = re.split(r"[\n;\uFF1B\u3002]+", text)
    picked: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        clean = _clean_text(raw)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        if len(clean) > max_len:
            clean = clean[: max_len - 3].rstrip() + "..."
        picked.append(clean)
        if len(picked) >= max_items:
            break
    return picked


def _compact_library_summary(text: str) -> str:
    lines = _compact_text_lines(text, max_items=4, max_len=28)
    if not lines:
        return ""
    return "\n".join([f"- {line}" for line in lines])


def _rewrite_dynamic_memory(previous_memory: str, query: str, latest_signal: str) -> str:
    model_name = settings.llm_model or "gpt-5-mini"
    parsed = _chat_json(
        model_name,
        MEMORY_UPDATE_SYSTEM_PROMPT,
        {
            "previous_memory": previous_memory,
            "latest_query": query,
            "latest_signal": latest_signal,
            "output_style": "short_cn_semicolon",
        },
    )

    if isinstance(parsed, dict):
        rewritten = str(parsed.get("memory_text", "")).strip()
        compact = _compact_text_lines(rewritten, max_items=6, max_len=32)
        if compact:
            return "; ".join(compact)

    latest_compact = _compact_text_lines(latest_signal, max_items=6, max_len=32)
    if latest_compact:
        return "; ".join(latest_compact)

    hint_compact = _compact_text_lines("; ".join(_extract_preference_hints(query)), max_items=6, max_len=32)
    if hint_compact:
        return "; ".join(hint_compact)

    old_compact = _compact_text_lines(previous_memory, max_items=6, max_len=32)
    return "; ".join(old_compact)


def _collect_structured_keywords(mentor: Mentor) -> list[str]:
    structured = _safe_json_loads(mentor.structured_profile_json, {})
    if not isinstance(structured, dict):
        return []
    raw_keywords = structured.get("ai_keywords", [])
    if isinstance(raw_keywords, list):
        return [str(item).strip() for item in raw_keywords if str(item).strip()][:10]
    if isinstance(raw_keywords, str):
        return [item.strip() for item in re.split(r"[,，;；]", raw_keywords) if item.strip()][:10]
    return []


def _collect_favorite_mentor_signals(db: Session, user_id: int, limit: int = 80) -> dict[str, Any]:
    rows = (
        db.query(Mentor, MentorNote)
        .join(Favorite, Favorite.mentor_id == Mentor.id)
        .outerjoin(
            MentorNote,
            (MentorNote.mentor_id == Mentor.id) & (MentorNote.user_id == user_id),
        )
        .filter(Favorite.user_id == user_id, Favorite.is_favorite.is_(True))
        .order_by(Mentor.updated_at.desc())
        .limit(limit)
        .all()
    )

    field_counter: Counter[str] = Counter()
    keyword_counter: Counter[str] = Counter()
    snippets: list[str] = []
    mentor_names: list[str] = []

    for mentor, note in rows:
        mentor_names.append(mentor.name)

        field = (mentor.interested_field or "").strip()
        if field:
            field_counter[field] += 1

        for kw in _collect_structured_keywords(mentor):
            keyword_counter[kw] += 1

        if note is not None:
            tags = _safe_json_loads(note.tags_json, [])
            if isinstance(tags, list):
                for tag in tags:
                    clean_tag = str(tag).strip()
                    if clean_tag:
                        keyword_counter[clean_tag] += 1

        summary = (mentor.high_level_summary or mentor.research_direction or "").strip()
        if summary:
            snippets.append(summary[:220])

    return {
        "source_count": len(rows),
        "mentor_names": mentor_names[:12],
        "top_fields": [item for item, _ in field_counter.most_common(5)],
        "top_keywords": [item for item, _ in keyword_counter.most_common(10)],
        "snippets": snippets[:10],
    }


def _fallback_library_summary(signals: dict[str, Any]) -> str:
    source_count = int(signals.get("source_count", 0))
    if source_count <= 0:
        return ""

    fields = signals.get("top_fields", [])
    keywords = signals.get("top_keywords", [])

    lines: list[str] = [f"样本：{source_count} 位收藏导师"]
    if isinstance(fields, list) and fields:
        lines.append(f"主题偏好：{', '.join([str(x) for x in fields[:2]])}")
    if isinstance(keywords, list) and keywords:
        lines.append(f"关键词：{', '.join([str(x) for x in keywords[:4]])}")
    lines.append("策略：主方向优先，保留少量探索")

    return "\n".join(lines)


def _rewrite_personalized_query(
    *,
    query: str,
    memory_text: str,
    profile_text: str,
    library_summary_text: str,
    favorite_signals: dict[str, Any],
) -> dict[str, Any]:
    model_name = settings.llm_model or "gpt-5-mini"
    parsed = _chat_json(
        model_name,
        QUERY_REWRITE_SYSTEM_PROMPT,
        {
            "user_query": query,
            "dynamic_memory": memory_text,
            "profile_text": "\n".join(_extract_top_lines(profile_text, max_lines=3)),
            "library_summary_text": "\n".join(_extract_top_lines(library_summary_text, max_lines=2)),
            "favorite_mentor_signals": favorite_signals,
        },
    )

    semantic_query = str(parsed.get("semantic_query", "")).strip() if isinstance(parsed, dict) else ""
    keyword_query = str(parsed.get("keyword_query", "")).strip() if isinstance(parsed, dict) else ""

    if not semantic_query:
        semantic_query = query.strip()
    if not keyword_query:
        top_keywords = favorite_signals.get("top_keywords", [])
        if isinstance(top_keywords, list) and top_keywords:
            keyword_query = " ".join([query.strip(), " ".join([str(item) for item in top_keywords[:4]])]).strip()
        else:
            keyword_query = query.strip()

    return {
        "semantic_query": semantic_query,
        "keyword_query": keyword_query,
        "must_have": [str(item).strip() for item in parsed.get("must_have", []) if str(item).strip()][:5] if isinstance(parsed, dict) else [],
        "diversity_guard": str(parsed.get("diversity_guard", "")).strip() if isinstance(parsed, dict) else "",
    }


def _compose_weighted_memory(
    *,
    memory_text: str,
    profile_text: str,
    library_summary_text: str,
    use_library_summary: bool,
) -> str:
    lines: list[str] = []
    if memory_text.strip():
        lines.append(memory_text.strip())

    profile_hints = _extract_top_lines(profile_text, max_lines=2)
    if profile_hints:
        lines.append("profile_hints: " + "; ".join(profile_hints))

    if use_library_summary:
        summary_hints = _extract_top_lines(library_summary_text, max_lines=2)
        if summary_hints:
            lines.append("library_hints(low_weight): " + "; ".join(summary_hints))

    return "\n".join(lines).strip()


def _merge_personalized_candidates(primary: list[dict], secondary: list[dict], top_k: int) -> list[dict]:
    merged: dict[int, dict[str, Any]] = {}

    for item in primary:
        merged[item["mentor_id"]] = {
            "payload": {**item},
            "primary_score": float(item.get("match_score", 0.0)),
            "secondary_score": 0.0,
        }

    for item in secondary:
        row = merged.get(item["mentor_id"])
        if row is None:
            merged[item["mentor_id"]] = {
                "payload": {**item},
                "primary_score": 0.0,
                "secondary_score": float(item.get("match_score", 0.0)),
            }
            continue
        row["secondary_score"] = max(row["secondary_score"], float(item.get("match_score", 0.0)))
        if item.get("reason") and item["reason"] not in row["payload"].get("reason", ""):
            row["payload"]["reason"] = f"{row['payload'].get('reason', '')}; {item['reason']}".strip("; ")

    ranked: list[dict] = []
    for row in merged.values():
        blended = 0.78 * float(row["primary_score"]) + 0.22 * float(row["secondary_score"])
        if float(row["primary_score"]) <= 0 and float(row["secondary_score"]) > 0:
            blended *= 0.82

        payload = {**row["payload"]}
        payload["match_score"] = round(min(blended, 100.0), 2)
        ranked.append(payload)

    ranked.sort(key=lambda item: item.get("match_score", 0.0), reverse=True)
    return ranked[:top_k]


def _normalize_match_text(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", (value or "").lower()).strip()


SCHOOL_CITY_ALIAS: dict[str, str] = {
    "\u5317\u4eac": "beijing",
    "\u4e0a\u6d77": "shanghai",
    "\u6b66\u6c49": "wuhan",
    "\u5357\u4eac": "nanjing",
    "\u676d\u5dde": "hangzhou",
    "\u5e7f\u5dde": "guangzhou",
    "\u6df1\u5733": "shenzhen",
    "\u5929\u6d25": "tianjin",
    "\u6210\u90fd": "chengdu",
    "\u897f\u5b89": "xian",
    "\u9999\u6e2f": "hongkong",
}


def _strip_school_generic_terms(norm: str) -> str:
    cleaned = norm
    for term in (
        "university",
        "college",
        "institute",
        "school",
        "faculty",
        "department",
        "of",
        "\u5927\u5b66",
        "\u5b66\u9662",
        "\u7814\u7a76\u9662",
    ):
        cleaned = cleaned.replace(term, "")
    return cleaned


def _expand_school_aliases(value: str) -> set[str]:
    norm = _normalize_match_text(value)
    if not norm:
        return set()

    aliases: set[str] = {norm}

    stripped = _strip_school_generic_terms(norm)
    if len(stripped) >= 4:
        aliases.add(stripped)

    for zh, en in SCHOOL_CITY_ALIAS.items():
        zh_norm = _normalize_match_text(zh)
        en_norm = _normalize_match_text(en)

        if zh_norm in norm:
            swapped = norm.replace(zh_norm, en_norm)
            aliases.add(swapped)
            swapped_stripped = _strip_school_generic_terms(swapped)
            if len(swapped_stripped) >= 4:
                aliases.add(swapped_stripped)

            if norm == f"{zh_norm}\u5927\u5b66":
                aliases.add(f"{en_norm}university")

        if en_norm in norm:
            swapped = norm.replace(en_norm, zh_norm)
            aliases.add(swapped)
            swapped_stripped = _strip_school_generic_terms(swapped)
            if len(swapped_stripped) >= 4:
                aliases.add(swapped_stripped)

            if norm == f"{en_norm}university":
                aliases.add(f"{zh_norm}\u5927\u5b66")

    city_tokens = {_normalize_match_text(k) for k in SCHOOL_CITY_ALIAS.keys()} | {
        _normalize_match_text(v) for v in SCHOOL_CITY_ALIAS.values()
    }
    return {alias for alias in aliases if alias and alias not in city_tokens}


def _school_text_matches(left: str, right: str) -> bool:
    left_aliases = _expand_school_aliases(left)
    right_aliases = _expand_school_aliases(right)
    if not left_aliases or not right_aliases:
        return False

    for la in left_aliases:
        for ra in right_aliases:
            if len(la) < 3 or len(ra) < 3:
                continue
            if la in ra or ra in la:
                return True
    return False


def _extract_school_mentions_from_query(query: str, limit: int = 3) -> list[str]:
    text = _clean_text(query)
    if not text:
        return []

    patterns = [
        r"([\u4e00-\u9fff]{2,24}(?:\u5927\u5b66|\u5b66\u9662|\u7814\u7a76\u9662))",
        r"([A-Za-z][A-Za-z\s]{2,48}(?:University|College|Institute|School))",
    ]

    cn_prefixes = [
        "\u6211\u60f3\u5728",
        "\u5e0c\u671b\u5728",
        "\u8ba1\u5212\u5728",
        "\u6253\u7b97\u5728",
        "\u60f3\u5728",
        "\u5728",
    ]
    en_prefixes = [
        "recommend in ",
        "in ",
        "at ",
        "for ",
    ]

    found: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for raw in re.findall(pattern, text, flags=re.IGNORECASE):
            candidate = _clean_text(str(raw))
            if not candidate:
                continue

            cn_tail = re.search(r"([\u4e00-\u9fff]{2,20}(?:\u5927\u5b66|\u5b66\u9662|\u7814\u7a76\u9662))$", candidate)
            if cn_tail:
                candidate = cn_tail.group(1)
                for prefix in cn_prefixes:
                    if candidate.startswith(prefix) and len(candidate) > len(prefix) + 1:
                        candidate = candidate[len(prefix):]
                        break

            if re.search(r"[A-Za-z]", candidate):
                candidate = re.sub(r"\s+", " ", candidate).strip()
                lower_candidate = candidate.lower()
                for prefix in en_prefixes:
                    if lower_candidate.startswith(prefix):
                        candidate = candidate[len(prefix):].strip()
                        lower_candidate = candidate.lower()
                        break
                tokens = candidate.split(" ")
                if len(tokens) > 4:
                    candidate = " ".join(tokens[-4:])

            candidate = _clean_text(candidate)
            if not candidate:
                continue

            key = candidate.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(candidate)
            if len(found) >= limit:
                return found
    return found


def _extract_explicit_school_constraints(db: Session, query: str, limit: int = 3) -> list[str]:
    query_text = _clean_text(query)
    if not query_text:
        return []

    query_mentions = _extract_school_mentions_from_query(query_text, limit=limit)

    school_rows = (
        db.query(Mentor.school)
        .filter(Mentor.school.isnot(None), Mentor.school != "")
        .distinct()
        .all()
    )
    schools = [str(row[0]).strip() for row in school_rows if str(row[0]).strip()]

    matched: list[str] = []
    seen: set[str] = set()

    if schools:
        probes = query_mentions if query_mentions else [query_text]
        for probe in probes:
            for school in schools:
                if not _school_text_matches(probe, school):
                    continue
                key = school.lower()
                if key in seen:
                    continue
                seen.add(key)
                matched.append(school)
                if len(matched) >= limit:
                    return matched

    if matched:
        return matched

    # If user explicitly names a school but the current mentor corpus has no match,
    # still keep it as a hard constraint to avoid recommending the wrong school.
    return query_mentions[:limit]


def _school_matches(candidate_school: str, required_schools: list[str]) -> bool:
    if not candidate_school.strip():
        return False
    for school in required_schools:
        if _school_text_matches(candidate_school, school):
            return True
    return False


def _augment_school_scoped_candidates(
    db: Session,
    *,
    candidates: list[dict],
    required_schools: list[str],
    query: str,
    pool_limit: int,
) -> list[dict]:
    if not required_schools:
        return candidates

    merged: dict[int, dict[str, Any]] = {int(item["mentor_id"]): {**item} for item in candidates}
    mentors = db.query(Mentor).all()
    tokens = _tokenize(query)

    for mentor in mentors:
        school_value = str(mentor.school or "").strip()
        if not school_value or not _school_matches(school_value, required_schools):
            continue

        doc_lower = _mentor_document_text(mentor).lower()
        token_hits = sum(1 for token in tokens if token in doc_lower)
        scoped_score = 62.0 + min(token_hits * 3.0, 12.0)

        scoped_reason = f"school constraint match: {school_value}"
        if token_hits > 0:
            scoped_reason += f"; keyword hits in school scope: {token_hits}"

        row = merged.get(mentor.id)
        if row is None:
            merged[mentor.id] = {
                "mentor_id": mentor.id,
                "name": mentor.name,
                "school": mentor.school,
                "title": mentor.title,
                "research_direction": mentor.research_direction,
                "match_score": round(scoped_score, 2),
                "reason": scoped_reason,
            }
            continue

        row["match_score"] = round(max(float(row.get("match_score", 0.0)), scoped_score), 2)
        existing_reason = str(row.get("reason", "")).strip()
        if scoped_reason and scoped_reason not in existing_reason:
            row["reason"] = f"{existing_reason}; {scoped_reason}".strip("; ")

    ranked = sorted(merged.values(), key=lambda item: float(item.get("match_score", 0.0)), reverse=True)
    return ranked[:pool_limit]


def _apply_school_constraint(candidates: list[dict], required_schools: list[str], top_k: int) -> tuple[list[dict], dict[str, str]]:
    if not required_schools:
        return candidates[:top_k], {
            "school_constraint": "",
            "school_constraint_applied": "false",
            "school_constraint_no_match": "false",
            "school_constraint_matched_count": "0",
        }

    filtered = [item for item in candidates if _school_matches(str(item.get("school", "")), required_schools)]
    if filtered:
        return filtered[:top_k], {
            "school_constraint": ", ".join(required_schools),
            "school_constraint_applied": "true",
            "school_constraint_no_match": "false",
            "school_constraint_matched_count": str(len(filtered)),
        }

    return [], {
        "school_constraint": ", ".join(required_schools),
        "school_constraint_applied": "true",
        "school_constraint_no_match": "true",
        "school_constraint_matched_count": "0",
    }

def generate_library_summary(db: Session, *, user_id: int, scope: str = "favorites") -> dict[str, Any]:
    if scope != "favorites":
        raise ValueError("Only favorites scope is supported")

    signals = _collect_favorite_mentor_signals(db, user_id=user_id)
    source_count = int(signals.get("source_count", 0))
    if source_count <= 0:
        return {
            "summary_text": "暂无收藏导师，先在导师库收藏后再生成总结。",
            "used_llm": False,
            "source_count": 0,
            "updated": False,
        }

    model_name = settings.llm_model or "gpt-5-mini"
    parsed = _chat_json(
        model_name,
        LIBRARY_SUMMARY_SYSTEM_PROMPT,
        {
            "scope": scope,
            "favorite_mentor_signals": signals,
            "required_style": "简洁、可执行、不过度收敛",
        },
    )

    summary_text = str(parsed.get("summary_text", "")).strip() if isinstance(parsed, dict) else ""
    used_llm = bool(summary_text)
    if not summary_text:
        summary_text = _fallback_library_summary(signals)

    summary_text = _compact_library_summary(summary_text)

    changes = {LIBRARY_SUMMARY_TEXT_KEY: encode_text_to_b64(summary_text) if summary_text else None}
    update_env_file(changes)
    apply_runtime_values(changes)

    return {
        "summary_text": summary_text,
        "used_llm": used_llm,
        "source_count": source_count,
        "updated": True,
    }


def _extract_preference_hints(query: str) -> list[str]:
    text = _clean_text(query)
    if not text:
        return []

    patterns = [
        r"(?:\u504f\u597d|\u5e0c\u671b|\u5173\u6ce8|\u4e0d\u60f3)\s*([^\u3002\uff1b;,\n]{1,60})",
        r"(?:prefer|focus on|interested in)\s*([^.;,\n]{1,60})",
    ]

    hints: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            item = _clean_text(str(match))
            if item:
                hints.append(item)

    if not hints:
        hints.append(text[:100])

    return hints[:6]


def merge_dynamic_memory(previous_memory: str, query: str, llm_memory_update: str) -> str:
    latest_signal = _clean_text(llm_memory_update)
    if not latest_signal:
        latest_signal = "; ".join(_extract_preference_hints(query))

    return _rewrite_dynamic_memory(
        previous_memory=previous_memory,
        query=query,
        latest_signal=latest_signal,
    )


def ask_advisor(
    db: Session,
    *,
    user_id: int,
    session_id: int | None,
    query: str,
    top_k: int,
    personalized_boost: bool = False,
) -> dict:
    session_created = False

    if session_id is None:
        session = create_session(db, user_id=user_id, title=_clean_text(query)[:30])
        session_created = True
    else:
        session = get_session(db, user_id=user_id, session_id=session_id)
        if session is None:
            raise ValueError("Session not found")

    memory_row = get_or_create_memory(db, user_id=user_id)
    retrieval_debug: dict[str, str] = {}
    required_schools = _extract_explicit_school_constraints(db, query)

    if personalized_boost:
        profile_state = read_profile_state()
        profile_text = str(profile_state.get("profile_text", ""))
        library_summary_text = str(profile_state.get("library_summary_text", ""))
        favorite_signals = _collect_favorite_mentor_signals(db, user_id=user_id)

        rewritten = _rewrite_personalized_query(
            query=query,
            memory_text=memory_row.memory_text,
            profile_text=profile_text,
            library_summary_text=library_summary_text,
            favorite_signals=favorite_signals,
        )

        primary = retrieve_candidates(
            db,
            query=query,
            memory_text=_compose_weighted_memory(
                memory_text=memory_row.memory_text,
                profile_text=profile_text,
                library_summary_text=library_summary_text,
                use_library_summary=False,
            ),
            top_k=max(top_k, 10),
        )

        semantic_query = str(rewritten.get("semantic_query", "")).strip() or query
        keyword_query = str(rewritten.get("keyword_query", "")).strip()
        secondary_query = semantic_query if not keyword_query else f"{semantic_query} {keyword_query}".strip()

        secondary = retrieve_candidates(
            db,
            query=secondary_query,
            memory_text=_compose_weighted_memory(
                memory_text=memory_row.memory_text,
                profile_text=profile_text,
                library_summary_text=library_summary_text,
                use_library_summary=True,
            ),
            top_k=max(top_k, 10),
        )

        candidates = _merge_personalized_candidates(primary, secondary, top_k)
        retrieval_debug = {
            "primary_query": query,
            "secondary_query": secondary_query[:240],
            "must_have": ", ".join(rewritten.get("must_have", []))[:180],
            "diversity_guard": str(rewritten.get("diversity_guard", ""))[:180],
        }
    else:
        candidates = retrieve_candidates(db, query=query, memory_text=memory_row.memory_text, top_k=top_k)

    if required_schools:
        candidates = _augment_school_scoped_candidates(
            db,
            candidates=candidates,
            required_schools=required_schools,
            query=query,
            pool_limit=max(top_k * 4, 40),
        )

    candidates, school_debug = _apply_school_constraint(candidates, required_schools, top_k)
    retrieval_debug.update(school_debug)

    if not candidates and required_schools:
        constrained = ", ".join(required_schools)
        answer = f"已按学校约束检索：{constrained}。当前导师库中暂无匹配导师。建议先在“探索导师”中补充该校数据后再试。"
        recommendations = []
        used_llm = False
        llm_memory_update = f"school_preference: {constrained}"
    else:
        answer, recommendations, used_llm, llm_memory_update = generate_answer_with_rag(
            query=query,
            memory_text=memory_row.memory_text,
            candidates=candidates,
        )

    updated_memory = merge_dynamic_memory(memory_row.memory_text, query, llm_memory_update)
    memory_row.memory_text = updated_memory

    user_msg = AdvisorMessage(
        session_id=session.id,
        role="user",
        content=_clean_text(query),
        retrieved_mentor_ids_json="[]",
        recommendations_json="[]",
    )
    assistant_msg = AdvisorMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        retrieved_mentor_ids_json=json.dumps([item["mentor_id"] for item in candidates], ensure_ascii=False),
        recommendations_json=json.dumps(recommendations, ensure_ascii=False),
    )

    session.updated_at = datetime.now(timezone.utc)
    if session.title in {"New Session", "新会话", "æ–°ä¼šè¯"}:
        session.title = _clean_text(query)[:30] or session.title

    db.add(user_msg)
    db.add(assistant_msg)
    db.commit()
    db.refresh(memory_row)

    return {
        "session_id": session.id,
        "session_created": session_created,
        "answer": answer,
        "used_llm": used_llm,
        "memory_text": memory_row.memory_text,
        "recommendations": recommendations,
        "used_personalization": personalized_boost,
        "retrieval_debug": retrieval_debug,
    }

