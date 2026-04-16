"""Background job inspection and cancellation."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.errors import ForbiddenError
from app.core.security import CurrentUser, WriterUser
from app.db.base import DbSession
from app.services import job_service

router = APIRouter()


def _serialize(job) -> dict:  # noqa: ANN001
    return {
        "id": job.id,
        "project_id": job.project_id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "payload": job.payload,
        "result": job.result,
        "error": job.error,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("")
def list_jobs(
    user: CurrentUser,
    db: DbSession,
    project_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    if project_id:
        user.require_project(project_id)
    jobs = job_service.list_jobs(project_id, limit=limit)
    out = []
    for job in jobs:
        if job.project_id and not user.can_access(job.project_id):
            continue
        out.append(_serialize(job))
    return out


@router.get("/{job_id}")
def get_job(
    job_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    job = job_service.get_job(job_id)
    if job.project_id:
        user.require_project(job.project_id)
    elif not user.is_admin:
        raise ForbiddenError("Administrator role required")
    payload = _serialize(job)
    if job.status == "completed" and job.result:
        simulation_id = job.result.get("simulation_id")
        optimization_id = job.result.get("optimization_id")
        if simulation_id:
            payload["simulation_id"] = simulation_id
        if optimization_id:
            payload["optimization_id"] = optimization_id
    return payload


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: str,
    user: WriterUser,
    db: DbSession,
) -> dict:
    job = job_service.get_job(job_id)
    if job.project_id:
        user.require_project(job.project_id)
    elif not user.is_admin:
        raise ForbiddenError("Administrator role required")
    updated = job_service.request_cancel(job_id)
    return {"id": updated.id, "status": updated.status, "message": updated.message}
