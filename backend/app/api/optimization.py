"""Intervention optimisation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.security import CurrentUser, WriterUser
from app.db.base import DbSession
from app.models import OptimizationRun, Project
from app.schemas.api import OptimizationRequest
from app.services import optimization_service

router = APIRouter()


def _project(db: Session, user, project_id: str) -> Project:  # noqa: ANN001
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")
    user.require_project(project.id)
    return project


@router.post("/projects/{project_id}/optimizations", status_code=202)
def run_optimization(
    project_id: str,
    payload: OptimizationRequest,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    return optimization_service.submit_optimization(db, project, payload, actor=user.email)


@router.get("/projects/{project_id}/optimizations")
def list_optimizations(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    project = _project(db, user, project_id)
    return optimization_service.list_optimizations(db, project.id, limit=limit)


@router.get("/projects/{project_id}/optimizations/latest")
def latest_optimization(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    run = db.query(OptimizationRun).filter(OptimizationRun.project_id == project.id).order_by(
        OptimizationRun.created_at.desc()
    ).first()
    if not run:
        raise NotFoundError("No optimisation has been run for this project")
    return optimization_service.get_optimization(db, run.id)


@router.get("/optimizations/{optimization_id}")
def get_optimization(
    optimization_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    payload = optimization_service.get_optimization(db, optimization_id)
    _project(db, user, payload["project_id"])
    return payload
