"""Deterministic scheduling, validation, supplier exposure and milestone views."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.security import CurrentUser
from app.db.base import DbSession
from app.models import Project
from app.services import scheduling_service
from app.services.simulation_service import latest_simulation

router = APIRouter()


def _project(db: Session, user, project_id: str) -> Project:  # noqa: ANN001
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")
    user.require_project(project.id)
    return project


@router.get("/projects/{project_id}/schedule")
def schedule(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    mode: str = Query(default="both", pattern="^(cpm|cpsat|both)$"),
    time_limit: float = Query(default=15, ge=2, le=60),
    objective: str = Query(default="min_makespan", pattern="^(min_makespan|max_probability)$"),
) -> dict:
    project = _project(db, user, project_id)
    return scheduling_service.project_schedule(
        db, project, mode=mode, time_limit=time_limit, objective=objective
    )


@router.get("/projects/{project_id}/validation")
def validation(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    return scheduling_service.validate_project(db, project)


@router.get("/projects/{project_id}/suppliers")
def suppliers(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    payload = scheduling_service.supplier_exposure(db, project)
    sim = latest_simulation(db, project.id)
    payload["simulated_supplier_impact"] = (sim.summary or {}).get("suppliers", []) if sim else []
    payload["simulation_id"] = sim.id if sim else None
    return payload


@router.get("/projects/{project_id}/milestones")
def milestones(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    sim = latest_simulation(db, project.id)
    if sim and (sim.summary or {}).get("milestones"):
        return {
            "source": "simulation",
            "simulation_id": sim.id,
            "as_of": sim.created_at.isoformat() if sim.created_at else None,
            "milestones": (sim.summary or {}).get("milestones", []),
        }
    schedule_payload = scheduling_service.project_schedule(db, project, mode="cpm")
    from app.scheduling.cpm import compute_cpm
    from app.simulation.context import build_context

    context = build_context(db, project)
    cpm = compute_cpm(context.model, context.calendar)
    rows = []
    for milestone in context.milestones:
        if not milestone.task_id or milestone.task_id not in cpm.tasks:
            continue
        task = cpm.tasks[milestone.task_id]
        rows.append(
            {
                "id": milestone.id,
                "name": milestone.name,
                "due_date": milestone.due_date,
                "customer_commitment": milestone.customer_commitment,
                "p50_date": context.calendar.to_date(task.earliest_finish).isoformat(),
                "p90_date": None,
                "on_time_probability": None,
                "slack_vs_due_days": round(milestone.due_offset - task.earliest_finish, 2)
                if milestone.due_offset is not None
                else None,
                "note": "Deterministic CPM estimate — run a simulation for probabilities.",
            }
        )
    return {
        "source": "cpm",
        "simulation_id": None,
        "as_of": None,
        "milestones": rows,
        "cpm_finish": schedule_payload["cpm"]["finish_date"],
    }
