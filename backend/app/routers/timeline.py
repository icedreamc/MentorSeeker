from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Mentor, TimelineEvent
from ..schemas.timeline import (
    TimelineCreateRequest,
    TimelineDailyOverviewRead,
    TimelineDailyPointRead,
    TimelineListRead,
    TimelineRead,
    TimelineUpdateRequest,
)

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


def _build_timeline_read(row: TimelineEvent, mentor_name: str) -> TimelineRead:
    return TimelineRead(
        id=row.id,
        user_id=row.user_id,
        mentor_id=row.mentor_id,
        mentor_name=mentor_name,
        event_type=row.event_type,
        event_date=row.event_date,
        content=row.content,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=TimelineListRead)
def get_timeline(
    user_id: int = Query(default=1, ge=1),
    mentor_id: int | None = Query(default=None, ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> TimelineListRead:
    query = db.query(TimelineEvent).filter(TimelineEvent.user_id == user_id)
    if mentor_id is not None:
        query = query.filter(TimelineEvent.mentor_id == mentor_id)

    total = query.count()
    rows = (
        query.order_by(TimelineEvent.event_date.desc(), TimelineEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    mentor_ids = {row.mentor_id for row in rows}
    mentor_map = {
        mentor.id: mentor.name
        for mentor in db.query(Mentor).filter(Mentor.id.in_(mentor_ids)).all()
    } if mentor_ids else {}

    items = [_build_timeline_read(row, mentor_map.get(row.mentor_id, "Unknown")) for row in rows]
    return TimelineListRead(items=items, page=page, page_size=page_size, total=total)


@router.get("/overview/daily", response_model=TimelineDailyOverviewRead)
def get_timeline_daily_overview(
    user_id: int = Query(default=1, ge=1),
    mentor_id: int | None = Query(default=None, ge=1),
    event_type: str | None = Query(default=None),
    days: int = Query(default=182, ge=30, le=730),
    db: Session = Depends(get_db),
) -> TimelineDailyOverviewRead:
    start_date = date.today() - timedelta(days=days - 1)

    query = db.query(
        TimelineEvent.event_date,
        TimelineEvent.event_type,
        func.count(TimelineEvent.id),
    ).filter(
        TimelineEvent.user_id == user_id,
        TimelineEvent.event_date >= start_date,
    )

    if mentor_id is not None:
        query = query.filter(TimelineEvent.mentor_id == mentor_id)
    if event_type:
        query = query.filter(TimelineEvent.event_type == event_type)

    grouped_rows = (
        query.group_by(TimelineEvent.event_date, TimelineEvent.event_type)
        .order_by(TimelineEvent.event_date.asc(), TimelineEvent.event_type.asc())
        .all()
    )

    day_map: dict[date, dict[str, int] | int] = {}
    for event_date, row_event_type, row_count in grouped_rows:
        typed_count = int(row_count)
        if event_date not in day_map:
            day_map[event_date] = {
                "count": 0,
                "type_counts": {},
            }

        day_payload = day_map[event_date]
        day_payload["count"] = int(day_payload["count"]) + typed_count
        type_counts = day_payload["type_counts"]
        if isinstance(type_counts, dict):
            type_key = str(row_event_type or "unknown")
            type_counts[type_key] = typed_count

    items = [
        TimelineDailyPointRead(
            event_date=event_date,
            count=int(payload["count"]),
            type_counts=(payload["type_counts"] if isinstance(payload["type_counts"], dict) else {}),
        )
        for event_date, payload in sorted(day_map.items(), key=lambda item: item[0])
    ]
    return TimelineDailyOverviewRead(items=items)


@router.post("", response_model=TimelineRead)
def create_timeline(payload: TimelineCreateRequest, db: Session = Depends(get_db)) -> TimelineRead:
    mentor = db.get(Mentor, payload.mentor_id)
    if mentor is None:
        raise HTTPException(status_code=404, detail="Mentor not found")

    row = TimelineEvent(
        user_id=payload.user_id,
        mentor_id=payload.mentor_id,
        event_type=payload.event_type,
        event_date=payload.event_date,
        content=payload.content,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _build_timeline_read(row, mentor.name)


@router.patch("/{event_id}", response_model=TimelineRead)
def patch_timeline(event_id: int, payload: TimelineUpdateRequest, db: Session = Depends(get_db)) -> TimelineRead:
    row = db.get(TimelineEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Timeline event not found")

    if payload.event_type is not None:
        row.event_type = payload.event_type
    if payload.event_date is not None:
        row.event_date = payload.event_date
    if payload.content is not None:
        row.content = payload.content

    db.commit()
    db.refresh(row)

    mentor = db.get(Mentor, row.mentor_id)
    return _build_timeline_read(row, mentor.name if mentor else "Unknown")


@router.delete("/{event_id}", response_model=dict)
def delete_timeline(event_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(TimelineEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Timeline event not found")
    db.delete(row)
    db.commit()
    return {"deleted": True, "event_id": event_id}
