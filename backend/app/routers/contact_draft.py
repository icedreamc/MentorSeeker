from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.contact_draft import (
    ContactDraftCommitRead,
    ContactDraftCommitRequest,
    ContactDraftGenerateRead,
    ContactDraftGenerateRequest,
)
from ..services.contact_draft_service import commit_contact_draft, generate_contact_draft

router = APIRouter(prefix="/api/contact-draft", tags=["contact-draft"])


@router.post("/generate", response_model=ContactDraftGenerateRead)
def post_contact_draft_generate(
    payload: ContactDraftGenerateRequest,
    db: Session = Depends(get_db),
) -> ContactDraftGenerateRead:
    try:
        result = generate_contact_draft(
            db,
            user_id=payload.user_id,
            mentor_id=payload.mentor_id,
            language=payload.language,
            extra_instruction=payload.extra_instruction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ContactDraftGenerateRead(**result)


@router.post("/commit", response_model=ContactDraftCommitRead)
def post_contact_draft_commit(
    payload: ContactDraftCommitRequest,
    db: Session = Depends(get_db),
) -> ContactDraftCommitRead:
    try:
        row = commit_contact_draft(
            db,
            user_id=payload.user_id,
            mentor_id=payload.mentor_id,
            event_date=payload.event_date,
            subject=payload.subject,
            body=payload.body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ContactDraftCommitRead(
        id=row.id,
        user_id=row.user_id,
        mentor_id=row.mentor_id,
        event_type=row.event_type,
        event_date=row.event_date,
        content=row.content,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
