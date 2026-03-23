import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Mentor
from ..schemas.mentor import (
    FavoriteUpdateRequest,
    MentorBatchDeleteRequest,
    MentorBatchDeleteResult,
    MentorBatchEnrichRequest,
    MentorBatchEnrichResult,
    MentorCreateRequest,
    MentorDetailRead,
    MentorListRead,
    MentorSummaryRead,
    NoteRead,
    NoteUpdateRequest,
)
from ..services.mentor_service import (
    batch_delete_mentors_permanently,
    batch_enrich_mentors,
    create_manual_mentor,
    delete_mentor_permanently,
    get_mentor_detail,
    is_mentor_auto_enriched,
    list_mentors,
    parse_mentor_json_fields,
    parse_note_tags,
    remove_from_library,
    set_favorite,
    update_note,
)

router = APIRouter(prefix="/api/mentors", tags=["mentors"])


@router.get("", response_model=MentorListRead)
def get_mentors(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    school: str | None = Query(default=None),
    interested_field: str | None = Query(default=None),
    favorite_only: bool = Query(default=False),
    user_id: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
) -> MentorListRead:
    rows, total, favorite_ids = list_mentors(
        db,
        page=page,
        page_size=page_size,
        q=q,
        school=school,
        interested_field=interested_field,
        favorite_only=favorite_only,
        user_id=user_id,
    )

    items: list[MentorSummaryRead] = []
    for row in rows:
        parsed = parse_mentor_json_fields(row)
        items.append(
            MentorSummaryRead(
                id=row.id,
                school=row.school,
                interested_field=row.interested_field,
                name=row.name,
                title=row.title,
                research_direction=row.research_direction,
                high_level_summary=row.high_level_summary,
                ai_keywords=parsed["ai_keywords"],
                is_favorite=row.id in favorite_ids,
                is_auto_enriched=is_mentor_auto_enriched(row),
                updated_at=row.updated_at,
            )
        )

    return MentorListRead(items=items, page=page, page_size=page_size, total=total)


@router.post("", response_model=MentorSummaryRead, status_code=status.HTTP_201_CREATED)
def create_mentor(payload: MentorCreateRequest, db: Session = Depends(get_db)) -> MentorSummaryRead:
    mentor, created = create_manual_mentor(
        db,
        school=payload.school,
        interested_field=payload.interested_field,
        name=payload.name,
        title=payload.title,
        research_direction=payload.research_direction,
        profile_urls=payload.profile_urls,
    )
    if not created:
        raise HTTPException(status_code=409, detail="Mentor already exists under the same school and field")

    parsed = parse_mentor_json_fields(mentor)
    return MentorSummaryRead(
        id=mentor.id,
        school=mentor.school,
        interested_field=mentor.interested_field,
        name=mentor.name,
        title=mentor.title,
        research_direction=mentor.research_direction,
        high_level_summary=mentor.high_level_summary,
        ai_keywords=parsed["ai_keywords"],
        is_favorite=False,
        is_auto_enriched=is_mentor_auto_enriched(mentor),
        updated_at=mentor.updated_at,
    )


@router.post("/enrich", response_model=MentorBatchEnrichResult)
def enrich_mentors(payload: MentorBatchEnrichRequest, db: Session = Depends(get_db)) -> MentorBatchEnrichResult:
    try:
        result = batch_enrich_mentors(db, mentor_ids=payload.mentor_ids, sleep_seconds=payload.sleep_seconds)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Batch enrichment failed: {exc}") from exc
    return MentorBatchEnrichResult(**result)


@router.post("/batch-delete", response_model=MentorBatchDeleteResult)
def batch_delete_mentors(payload: MentorBatchDeleteRequest, db: Session = Depends(get_db)) -> MentorBatchDeleteResult:
    result = batch_delete_mentors_permanently(db, mentor_ids=payload.mentor_ids)
    return MentorBatchDeleteResult(**result)


@router.get("/{mentor_id}", response_model=MentorDetailRead)
def get_mentor(mentor_id: int, user_id: int = Query(default=1, ge=1), db: Session = Depends(get_db)) -> MentorDetailRead:
    mentor, favorite, note = get_mentor_detail(db, mentor_id=mentor_id, user_id=user_id)
    if mentor is None:
        raise HTTPException(status_code=404, detail="Mentor not found")

    parsed = parse_mentor_json_fields(mentor)
    return MentorDetailRead(
        id=mentor.id,
        school=mentor.school,
        interested_field=mentor.interested_field,
        name=mentor.name,
        title=mentor.title,
        research_direction=mentor.research_direction,
        profile_urls=parsed["profile_urls"],
        structured_profile=parsed["structured_profile"],
        publications=parsed["publications"],
        papers_summary=mentor.papers_summary,
        high_level_summary=mentor.high_level_summary,
        ai_keywords=parsed["ai_keywords"],
        user_note="" if note is None else note.note_text,
        user_tags=parse_note_tags(note),
        is_favorite=bool(favorite and favorite.is_favorite),
        is_auto_enriched=is_mentor_auto_enriched(mentor),
        updated_at=mentor.updated_at,
    )


@router.post("/{mentor_id}/favorite", response_model=dict)
def update_favorite(mentor_id: int, payload: FavoriteUpdateRequest, db: Session = Depends(get_db)) -> dict:
    mentor = db.get(Mentor, mentor_id)
    if mentor is None:
        raise HTTPException(status_code=404, detail="Mentor not found")

    row = set_favorite(db, mentor_id=mentor_id, user_id=payload.user_id, is_favorite=payload.is_favorite)
    return {"mentor_id": mentor_id, "user_id": payload.user_id, "is_favorite": row.is_favorite}


@router.patch("/{mentor_id}/note", response_model=NoteRead)
def patch_note(mentor_id: int, payload: NoteUpdateRequest, db: Session = Depends(get_db)) -> NoteRead:
    mentor = db.get(Mentor, mentor_id)
    if mentor is None:
        raise HTTPException(status_code=404, detail="Mentor not found")

    row = update_note(
        db,
        mentor_id=mentor_id,
        user_id=payload.user_id,
        note_text=payload.note_text,
        tags=payload.tags,
    )
    return NoteRead(
        mentor_id=mentor_id,
        user_id=payload.user_id,
        note_text=row.note_text,
        tags=json.loads(row.tags_json),
        updated_at=row.updated_at,
    )


@router.delete("/{mentor_id}/library", response_model=dict)
def delete_from_my_library(mentor_id: int, user_id: int = Query(default=1, ge=1), db: Session = Depends(get_db)) -> dict:
    mentor = db.get(Mentor, mentor_id)
    if mentor is None:
        raise HTTPException(status_code=404, detail="Mentor not found")

    result = remove_from_library(db, mentor_id=mentor_id, user_id=user_id)
    return {
        "mentor_id": mentor_id,
        "user_id": user_id,
        "deleted": True,
        **result,
    }


@router.delete("/{mentor_id}", response_model=dict)
def delete_mentor(mentor_id: int, db: Session = Depends(get_db)) -> dict:
    mentor = db.get(Mentor, mentor_id)
    if mentor is None:
        raise HTTPException(status_code=404, detail="Mentor not found")

    result = delete_mentor_permanently(db, mentor_id=mentor_id)
    return {
        "mentor_id": mentor_id,
        "deleted": bool(result["deleted_mentor"]),
        **result,
    }

