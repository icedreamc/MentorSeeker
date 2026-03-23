from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.advisor_ai import (
    AdvisorAskRead,
    AdvisorAskRequest,
    AdvisorLibrarySummaryGenerateRead,
    AdvisorLibrarySummaryGenerateRequest,
    AdvisorMemoryRead,
    AdvisorMemoryUpdateRequest,
    AdvisorSessionCreateRequest,
    AdvisorSessionDetailRead,
    AdvisorSessionSummaryRead,
    AdvisorVectorIndexRebuildRead,
    AdvisorVectorIndexRebuildRequest,
    AdvisorVectorIndexStatusRead,
)
from ..services.advisor_ai_service import (
    ask_advisor,
    create_session,
    delete_session,
    generate_library_summary,
    get_or_create_memory,
    get_session,
    get_session_messages,
    get_vector_index_status,
    list_sessions_with_counts,
    sync_vector_index,
)

router = APIRouter(prefix="/api/advisor-ai", tags=["advisor-ai"])


@router.get("/sessions", response_model=list[AdvisorSessionSummaryRead])
def list_advisor_sessions(
    user_id: int = Query(default=1, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[AdvisorSessionSummaryRead]:
    rows = list_sessions_with_counts(db, user_id=user_id, limit=limit)
    return [AdvisorSessionSummaryRead(**item) for item in rows]


@router.post("/sessions", response_model=AdvisorSessionSummaryRead)
def create_advisor_session(payload: AdvisorSessionCreateRequest, db: Session = Depends(get_db)) -> AdvisorSessionSummaryRead:
    row = create_session(db, user_id=payload.user_id, title=payload.title)
    return AdvisorSessionSummaryRead(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        message_count=0,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/sessions/{session_id}", response_model=AdvisorSessionDetailRead)
def get_advisor_session(
    session_id: int,
    user_id: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
) -> AdvisorSessionDetailRead:
    row = get_session(db, user_id=user_id, session_id=session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = get_session_messages(db, session_id=session_id)
    return AdvisorSessionDetailRead(
        id=row.id,
        user_id=row.user_id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        messages=messages,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_advisor_session(
    session_id: int,
    user_id: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
) -> Response:
    deleted = delete_session(db, user_id=user_id, session_id=session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ask", response_model=AdvisorAskRead)
def post_advisor_ask(payload: AdvisorAskRequest, db: Session = Depends(get_db)) -> AdvisorAskRead:
    try:
        result = ask_advisor(
            db,
            user_id=payload.user_id,
            session_id=payload.session_id,
            query=payload.query,
            top_k=payload.top_k,
            personalized_boost=payload.personalized_boost,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return AdvisorAskRead(**result)


@router.get("/memory", response_model=AdvisorMemoryRead)
def get_advisor_memory(
    user_id: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
) -> AdvisorMemoryRead:
    row = get_or_create_memory(db, user_id=user_id)
    return AdvisorMemoryRead(user_id=row.user_id, memory_text=row.memory_text, updated_at=row.updated_at)


@router.patch("/memory", response_model=AdvisorMemoryRead)
def patch_advisor_memory(payload: AdvisorMemoryUpdateRequest, db: Session = Depends(get_db)) -> AdvisorMemoryRead:
    row = get_or_create_memory(db, user_id=payload.user_id)
    row.memory_text = payload.memory_text.strip()
    db.commit()
    db.refresh(row)
    return AdvisorMemoryRead(user_id=row.user_id, memory_text=row.memory_text, updated_at=row.updated_at)


@router.post("/library-summary/generate", response_model=AdvisorLibrarySummaryGenerateRead)
def post_library_summary_generate(
    payload: AdvisorLibrarySummaryGenerateRequest,
    db: Session = Depends(get_db),
) -> AdvisorLibrarySummaryGenerateRead:
    result = generate_library_summary(db, user_id=payload.user_id, scope=payload.scope)
    return AdvisorLibrarySummaryGenerateRead(**result)


@router.get("/vector-index/status", response_model=AdvisorVectorIndexStatusRead)
def get_advisor_vector_index_status(db: Session = Depends(get_db)) -> AdvisorVectorIndexStatusRead:
    return AdvisorVectorIndexStatusRead(**get_vector_index_status(db))


@router.post("/vector-index/rebuild", response_model=AdvisorVectorIndexRebuildRead)
def rebuild_advisor_vector_index(
    payload: AdvisorVectorIndexRebuildRequest,
    db: Session = Depends(get_db),
) -> AdvisorVectorIndexRebuildRead:
    result = sync_vector_index(db, force=payload.force, batch_size=payload.batch_size)
    return AdvisorVectorIndexRebuildRead(**result)
