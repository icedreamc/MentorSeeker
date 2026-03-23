from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.discovery import DiscoveryJobCreate, DiscoveryJobRead
from ..services.job_runner import cancel_job, create_job, get_job, list_jobs, submit_job

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


@router.post("/jobs", response_model=DiscoveryJobRead)
def create_discovery_job(payload: DiscoveryJobCreate, db: Session = Depends(get_db)) -> DiscoveryJobRead:
    job = create_job(
        db,
        school=payload.school,
        interested_field=payload.interested_field,
        max_steps=payload.max_steps,
        target_mentor_count=payload.target_mentor_count,
        enrich_limit=payload.enrich_limit,
    )
    if payload.run_immediately:
        submit_job(job.id)
    return DiscoveryJobRead.model_validate(job)


@router.get("/jobs", response_model=list[DiscoveryJobRead])
def get_discovery_jobs(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)) -> list[DiscoveryJobRead]:
    jobs = list_jobs(db, limit=limit)
    return [DiscoveryJobRead.model_validate(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=DiscoveryJobRead)
def get_discovery_job(job_id: str, db: Session = Depends(get_db)) -> DiscoveryJobRead:
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return DiscoveryJobRead.model_validate(job)


@router.post("/jobs/{job_id}/run", response_model=DiscoveryJobRead)
def run_discovery_job(job_id: str, db: Session = Depends(get_db)) -> DiscoveryJobRead:
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "pending":
        raise HTTPException(status_code=409, detail=f"Only pending jobs can run (current: {job.status})")

    ok = submit_job(job_id)
    if not ok:
        raise HTTPException(status_code=409, detail="Job is already running")

    db.refresh(job)
    return DiscoveryJobRead.model_validate(job)


@router.post("/jobs/{job_id}/cancel", response_model=DiscoveryJobRead)
def cancel_discovery_job(job_id: str, db: Session = Depends(get_db)) -> DiscoveryJobRead:
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    ok, message = cancel_job(db, job_id)
    if not ok:
        raise HTTPException(status_code=409, detail=message)

    db.refresh(job)
    return DiscoveryJobRead.model_validate(job)
