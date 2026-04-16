"""Project CRUD, import/export, task catalog and audit endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, Body, File, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ValidationError
from app.core.security import CurrentUser, WriterUser
from app.db.base import DbSession
from app.models import AuditLog, Project, SimulationSnapshot
from app.schemas.api import ProjectPatch
from app.services import project_service
from app.services.simulation_service import latest_simulation

router = APIRouter()


def _project_or_404(db: Session, user, project_id: str) -> Project:  # noqa: ANN001
    project = db.get(Project, project_id)
    if not project:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"Project {project_id} not found")
    user.require_project(project.id)
    return project


@router.get("")
def list_projects(
    user: CurrentUser,
    db: DbSession,
    include_archived: bool = Query(default=False),
) -> list[dict]:
    return [p for p in project_service.list_projects(db, include_archived)]


@router.post("", status_code=201)
def create_project(
    user: WriterUser,
    db: DbSession,
    payload: dict = Body(...),
) -> dict:
    project = project_service.create_project(
        db, payload, actor=user.email, is_demo=bool(payload.get("is_demo", False))
    )
    return {"id": project.id, "key": project.key, "name": project.name}


@router.post("/import", status_code=201)
async def import_projects(
    user: WriterUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> dict:
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise ValidationError("File exceeds the upload size limit")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Invalid JSON file: {exc}") from exc
    items = data if isinstance(data, list) else data.get("projects") if isinstance(data, dict) else None
    if items is None:
        items = [data]
    if not isinstance(items, list):
        raise ValidationError("JSON must be a project object, an array, or {'projects': [...]}")
    created = []
    for item in items:
        project = project_service.create_project(db, item, actor=user.email)
        created.append({"id": project.id, "key": project.key, "name": project.name})
    return {"created": len(created), "projects": created}


@router.get("/csv-template", response_class=PlainTextResponse)
def csv_template() -> str:
    return project_service.to_csv_template()


@router.get("/{project_id}")
def get_project(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    include_payload: bool = Query(default=True),
) -> dict:
    project = _project_or_404(db, user, project_id)
    payload: dict = {"id": project.id, "key": project.key, "name": project.name}
    if include_payload:
        payload = project_service.export_project_payload(db, project)
        payload["id"] = project.id
        payload["is_demo"] = project.is_demo
        payload["created_at"] = project.created_at.isoformat() if project.created_at else None
        payload["updated_at"] = project.updated_at.isoformat() if project.updated_at else None
        latest = latest_simulation(db, project.id)
        payload["latest_simulation"] = (
            {
                "id": latest.id,
                "label": latest.label,
                "created_at": latest.created_at.isoformat() if latest.created_at else None,
                "p50": (latest.summary or {}).get("makespan", {}).get("p50"),
                "p90": (latest.summary or {}).get("makespan", {}).get("p90"),
                "on_time_probability": (latest.summary or {}).get("deadline", {}).get("on_time_probability"),
                "iterations": latest.iterations,
                "seed": latest.seed,
            }
            if latest
            else None
        )
        payload["simulation_count"] = len(
            [s for s in project.simulations if s.status == "completed"]
        )
    return payload


@router.patch("/{project_id}")
def update_project(
    project_id: str,
    patch: ProjectPatch,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project_or_404(db, user, project_id)
    updated = project_service.update_project(
        db, project, patch.model_dump(exclude_none=True), actor=user.email
    )
    return {"id": updated.id, "key": updated.key, "name": updated.name, "status": updated.status}


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project_or_404(db, user, project_id)
    if project.is_demo and project.status != "archived":
        raise ValidationError("Demo programs must be archived, not deleted")
    db.delete(project)
    db.commit()
    return {"deleted": project_id}


@router.post("/{project_id}/duplicate", status_code=201)
def duplicate_project(
    project_id: str,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project_or_404(db, user, project_id)
    clone = project_service.duplicate_project(db, project, actor=user.email)
    return {"id": clone.id, "key": clone.key, "name": clone.name}


@router.post("/{project_id}/archive")
def archive_project(
    project_id: str,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project_or_404(db, user, project_id)
    archived = project_service.archive_project(db, project, actor=user.email)
    return {"id": archived.id, "status": archived.status}


@router.get("/{project_id}/export")
def export_project(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    download: bool = Query(default=False),
) -> Response:
    project = _project_or_404(db, user, project_id)
    payload = project_service.export_project_payload(db, project)
    body = json.dumps(payload, indent=2, default=str)
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{project.key.lower()}.json"'
    return Response(content=body, media_type="application/json", headers=headers)


@router.get("/{project_id}/tasks")
def task_catalog(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    project = _project_or_404(db, user, project_id)
    payload = project_service.export_project_payload(db, project)
    return {
        "tasks": payload["tasks"],
        "dependencies": payload["dependencies"],
        "resources": payload["resources"],
        "milestones": payload["milestones"],
    }


@router.get("/{project_id}/network")
def network(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    project = _project_or_404(db, user, project_id)
    payload = project_service.export_project_payload(db, project)
    return {
        "nodes": [
            {
                "id": task["code"],
                "label": f"{task['code']}\n{task['name']}",
                "name": task["name"],
                "phase": task["phase"],
                "duration": task["duration_days"],
                "is_gate": task["is_gate"],
            }
            for task in payload["tasks"]
        ],
        "edges": [
            {
                "source": dep["from"],
                "target": dep["to"],
                "type": dep["type"],
                "lag": dep["lag_days"],
            }
            for dep in payload["dependencies"]
        ],
    }


@router.get("/{project_id}/risks")
def risks(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    project = _project_or_404(db, user, project_id)
    payload = project_service.export_project_payload(db, project)
    return {
        "risks": payload["risks"],
        "validation_tests": payload["validation_tests"],
        "ecos": payload["ecos"],
        "component_exposure": payload["components"],
    }


@router.get("/{project_id}/audit")
def audit_log(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    _project_or_404(db, user, project_id)
    rows = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.project_id == project_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    )
    return [
        {
            "id": row.id,
            "actor": row.actor,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "summary": row.summary,
            "payload": row.payload,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.get("/{project_id}/snapshots")
def snapshots(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=30, ge=1, le=200),
) -> list[dict]:
    _project_or_404(db, user, project_id)
    rows = list(
        db.scalars(
            select(SimulationSnapshot)
            .where(SimulationSnapshot.project_id == project_id)
            .order_by(SimulationSnapshot.created_at.desc())
            .limit(limit)
        )
    )
    return [
        {
            "id": row.id,
            "simulation_id": row.simulation_id,
            "scenario_id": row.scenario_id,
            "label": row.label,
            "p50_days": row.p50_days,
            "p90_days": row.p90_days,
            "on_time_probability": row.on_time_probability,
            "payload": row.payload,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.post("/{project_id}/tasks/import")
async def import_tasks(
    project_id: str,
    user: WriterUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> dict:
    project = _project_or_404(db, user, project_id)
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise ValidationError("File exceeds the upload size limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("CSV must be UTF-8 encoded") from exc
    return project_service.import_tasks_csv(db, project, text, actor=user.email)
