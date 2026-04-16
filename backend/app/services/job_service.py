"""Database-backed background jobs with progress, cancellation and recovery.

Jobs run in a bounded thread pool.  Every state transition is persisted so a
page reload (or a second API worker) still sees progress.  Celery can be enabled
for horizontal scaling, but the platform has no hard dependency on Redis or a
message broker.
"""
from __future__ import annotations

import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError
from app.core.logging import redact
from app.db.base import SessionLocal
from app.models import Job

JobFn = Callable[[object, Job, Callable[[float, str], None], Callable[[], bool]], dict]

_executor = ThreadPoolExecutor(max_workers=max(1, settings.job_workers), thread_name_prefix="npi-job")
_cancel_events: dict[str, threading.Event] = {}
_lock = threading.Lock()


class JobCancelled(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _set(job_id: str, **fields) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        db.commit()


def submit(
    *,
    kind: str,
    project_id: str | None,
    payload: dict,
    fn: JobFn,
    idempotency_key: str | None = None,
) -> Job:
    with SessionLocal() as db:
        if idempotency_key:
            existing = db.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
            if existing and existing.status in ("queued", "running"):
                return existing
        job = Job(
            kind=kind,
            project_id=project_id,
            status="queued",
            progress=0.0,
            message="Queued",
            payload=payload,
            idempotency_key=idempotency_key,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
        snapshot = job
    event = threading.Event()
    with _lock:
        _cancel_events[job_id] = event
    _executor.submit(_run, job_id, fn, event)
    return snapshot


def _run(job_id: str, fn: JobFn, event: threading.Event) -> None:
    _set(job_id, status="running", started_at=_utcnow(), message="Starting", progress=0.01)

    def progress(value: float, message: str) -> None:
        _set(
            job_id,
            progress=max(0.0, min(1.0, float(value))),
            message=str(message)[:380],
        )

    def cancelled() -> bool:
        return event.is_set()

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        try:
            result = fn(db, job, progress, cancelled)
            if event.is_set():
                _set(job_id, status="cancelled", finished_at=_utcnow(), message="Cancelled by user")
                return
            _set(
                job_id,
                status="completed",
                progress=1.0,
                message="Completed",
                result=result or {},
                finished_at=_utcnow(),
            )
        except Exception as exc:  # noqa: BLE001
            if event.is_set():
                _set(job_id, status="cancelled", finished_at=_utcnow(), message="Cancelled by user")
            else:
                detail = redact(str(exc))
                _set(
                    job_id,
                    status="failed",
                    finished_at=_utcnow(),
                    message=f"Failed: {detail[:300]}",
                    error=detail + "\n" + redact(traceback.format_exc())[-4000:],
                )
        finally:
            with _lock:
                _cancel_events.pop(job_id, None)


def request_cancel(job_id: str) -> Job:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")
        if job.status in ("completed", "failed", "cancelled"):
            raise ConflictError(f"Job is already {job.status}")
        job.cancel_requested = True
        job.message = "Cancellation requested"
        db.commit()
        db.refresh(job)
    with _lock:
        event = _cancel_events.get(job_id)
        if event:
            event.set()
    return job


def get_job(job_id: str) -> Job:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if not job:
            raise NotFoundError(f"Job {job_id} not found")
        db.expunge(job)
        return job


def list_jobs(project_id: str | None = None, limit: int = 50) -> list[Job]:
    with SessionLocal() as db:
        query = select(Job).order_by(Job.created_at.desc()).limit(limit)
        if project_id:
            query = query.where(Job.project_id == project_id)
        jobs = list(db.scalars(query))
        for job in jobs:
            db.expunge(job)
        return jobs


def recover_stale_jobs(max_age_minutes: int = 30) -> int:
    """Mark abandoned jobs failed after a crash/restart instead of hanging forever."""
    cutoff = _utcnow() - timedelta(minutes=max_age_minutes)
    recovered = 0
    with SessionLocal() as db:
        jobs = list(
            db.scalars(select(Job).where(Job.status.in_(["queued", "running"])))
        )
        for job in jobs:
            created = job.started_at or job.created_at
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created and created < cutoff:
                job.status = "failed"
                job.message = "Interrupted by server restart"
                job.error = "Job did not complete before the server restarted."
                job.finished_at = _utcnow()
                recovered += 1
        db.commit()
    return recovered
