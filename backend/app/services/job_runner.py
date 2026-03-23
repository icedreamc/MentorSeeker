from __future__ import annotations

import importlib
import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import SearchJob
from .mentor_service import upsert_mentors

_executor = ThreadPoolExecutor(max_workers=2)
_running_jobs: set[str] = set()
_cancel_requests: set[str] = set()
_jobs_lock = Lock()


def create_job(
    db: Session,
    *,
    school: str,
    interested_field: str,
    max_steps: int,
    target_mentor_count: int,
    enrich_limit: int,
) -> SearchJob:
    job = SearchJob(
        school=school,
        interested_field=interested_field,
        max_steps=max_steps,
        target_mentor_count=target_mentor_count,
        enrich_limit=enrich_limit,
        status="pending",
        progress_message="Job created",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def list_jobs(db: Session, limit: int = 20) -> list[SearchJob]:
    return db.query(SearchJob).order_by(SearchJob.created_at.desc()).limit(limit).all()


def get_job(db: Session, job_id: str) -> SearchJob | None:
    return db.get(SearchJob, job_id)


def recover_interrupted_jobs(db: Session) -> int:
    rows = db.query(SearchJob).filter(SearchJob.status.in_(["running", "cancelling"])).all()
    if not rows:
        return 0

    for job in rows:
        job.status = "cancelled"
        job.progress_message = "任务因后端重启而中断，请重新提交。"

    db.commit()
    return len(rows)


def backfill_raw_mentors_for_legacy_jobs(db: Session, limit: int = 120) -> int:
    jobs = (
        db.query(SearchJob)
        .filter(SearchJob.raw_output_file != "")
        .order_by(SearchJob.updated_at.desc())
        .limit(limit)
        .all()
    )

    backfilled_jobs = 0
    for job in jobs:
        # Legacy runs often persisted only enrich_count (<= enrich_limit) as mentor_count.
        if int(job.mentor_count or 0) > int(job.enrich_limit or 0):
            continue

        raw_mentors = _load_raw_mentors(Path(job.raw_output_file))
        if not raw_mentors:
            continue

        saved_count = upsert_mentors(
            db,
            mentors=raw_mentors,
            school=job.school,
            interested_field=job.interested_field,
            job_id=job.id,
        )

        if saved_count <= int(job.mentor_count or 0):
            continue

        job.mentor_count = saved_count
        db.commit()
        backfilled_jobs += 1

    return backfilled_jobs


def submit_job(job_id: str) -> bool:
    with _jobs_lock:
        if job_id in _running_jobs:
            return False
        _running_jobs.add(job_id)

    _executor.submit(_run_job, job_id)
    return True


def cancel_job(db: Session, job_id: str) -> tuple[bool, str]:
    job = db.get(SearchJob, job_id)
    if job is None:
        return False, "Job not found"

    if job.status in {"success", "failed", "cancelled"}:
        return False, f"Job is already {job.status}"

    if job.status == "cancelling":
        return True, "Cancellation already requested"

    if job.status == "pending":
        job.status = "cancelled"
        job.progress_message = "Cancelled before execution"
        db.commit()
        return True, "Job cancelled"

    if job.status == "running":
        with _jobs_lock:
            _cancel_requests.add(job_id)
        job.status = "cancelling"
        job.progress_message = "Cancellation requested"
        db.commit()
        return True, "Cancellation requested"

    return False, f"Unsupported status: {job.status}"


def _update_job(job_id: str, **changes: Any) -> None:
    with SessionLocal() as db:
        job = db.get(SearchJob, job_id)
        if job is None:
            return
        for key, value in changes.items():
            setattr(job, key, value)
        db.commit()


def _load_job(job_id: str) -> SearchJob | None:
    with SessionLocal() as db:
        job = db.get(SearchJob, job_id)
        if job is None:
            return None
        db.expunge(job)
        return job


def _is_cancel_requested(job_id: str) -> bool:
    with _jobs_lock:
        return job_id in _cancel_requests


def _mark_cancelled(job_id: str, message: str, **extra: Any) -> None:
    payload = {
        "status": "cancelled",
        "progress_message": message,
    }
    payload.update(extra)
    _update_job(job_id, **payload)


def _load_raw_mentors(raw_path: Path) -> list[dict]:
    if not raw_path.exists():
        return []

    try:
        with open(raw_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:  # noqa: BLE001
        return []

    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _run_job(job_id: str) -> None:
    raw_saved_count = 0
    raw_output = ""

    try:
        settings.ensure_dirs()
        snapshot = _load_job(job_id)
        if snapshot is None:
            return

        if _is_cancel_requested(job_id):
            _mark_cancelled(job_id, "Cancelled before execution")
            return

        _update_job(job_id, status="running", progress_message="Discovery pipeline started", error_message="")

        if str(settings.project_root) not in sys.path:
            sys.path.insert(0, str(settings.project_root))

        # Local imports keep API startup fast and avoid hard dependency at import time.
        true_search_module = importlib.import_module("backend.app.pipeline.true_mentor_search")
        curiosity_driven_search = true_search_module.curiosity_driven_search

        enrichment_module_name = "backend.app.pipeline.mentor_enrichment"
        if enrichment_module_name in sys.modules:
            mentor_enrichment = importlib.reload(sys.modules[enrichment_module_name])
        else:
            mentor_enrichment = importlib.import_module(enrichment_module_name)
        run_enrichment = mentor_enrichment.run_enrichment

        should_stop = lambda: _is_cancel_requested(job_id)

        raw_path_str = curiosity_driven_search(
            snapshot.school,
            snapshot.interested_field,
            max_steps=snapshot.max_steps,
            target_mentor_count=snapshot.target_mentor_count,
            output_dir=settings.data_dir,
            should_stop=should_stop,
        )
        raw_path = Path(raw_path_str)
        raw_output = str(raw_path)

        raw_mentors = _load_raw_mentors(raw_path)
        if raw_mentors:
            with SessionLocal() as db:
                raw_saved_count = upsert_mentors(
                    db,
                    mentors=raw_mentors,
                    school=snapshot.school,
                    interested_field=snapshot.interested_field,
                    job_id=job_id,
                )

        _update_job(
            job_id,
            progress_message=f"Discovery finished, saved {raw_saved_count} mentors, enrichment started",
            raw_output_file=raw_output,
            mentor_count=raw_saved_count,
        )

        if should_stop():
            _mark_cancelled(
                job_id,
                "Cancelled after discovery",
                raw_output_file=raw_output,
                mentor_count=raw_saved_count,
            )
            return

        enriched_data, enriched_path = run_enrichment(
            input_file=raw_output,
            enrich_limit=snapshot.enrich_limit,
            sleep_seconds=0.2,
            should_stop=should_stop,
        )

        enriched_saved_count = 0
        if enriched_data:
            with SessionLocal() as db:
                enriched_saved_count = upsert_mentors(
                    db,
                    mentors=enriched_data,
                    school=snapshot.school,
                    interested_field=snapshot.interested_field,
                    job_id=job_id,
                )

        if should_stop():
            _mark_cancelled(
                job_id,
                "Cancelled during enrichment",
                raw_output_file=raw_output,
                enriched_output_file=str(enriched_path),
                mentor_count=raw_saved_count,
            )
            return

        _update_job(
            job_id,
            status="success",
            progress_message=f"Pipeline completed (total: {raw_saved_count}, enriched: {enriched_saved_count})",
            enriched_output_file=str(enriched_path),
            mentor_count=raw_saved_count,
        )
    except Exception as exc:  # noqa: BLE001
        _update_job(
            job_id,
            status="failed",
            progress_message="Pipeline failed",
            raw_output_file=raw_output,
            mentor_count=raw_saved_count,
            error_message=f"{exc}\n{traceback.format_exc()}",
        )
    finally:
        with _jobs_lock:
            _running_jobs.discard(job_id)
            _cancel_requests.discard(job_id)




