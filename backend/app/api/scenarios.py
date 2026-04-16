"""Scenario creation, preview and common-random-number comparison."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.security import CurrentUser, WriterUser
from app.db.base import DbSession
from app.models import Project, Scenario
from app.schemas.api import CompareRequest, ScenarioCreate, ScenarioPatch
from app.services import scenario_service
from app.services.scenario_service import list_scenarios

router = APIRouter()


def _project(db: Session, user, project_id: str) -> Project:  # noqa: ANN001
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")
    user.require_project(project.id)
    return project


def _scenario(db: Session, user, scenario_id: str) -> Scenario:  # noqa: ANN001
    scenario = db.get(Scenario, scenario_id)
    if not scenario:
        raise NotFoundError(f"Scenario {scenario_id} not found")
    user.require_project(scenario.project_id)
    return scenario


@router.get("/projects/{project_id}/scenarios")
def get_scenarios(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> list[dict]:
    project = _project(db, user, project_id)
    return list_scenarios(db, project.id)


@router.post("/projects/{project_id}/scenarios", status_code=201)
def create_scenario(
    project_id: str,
    payload: ScenarioCreate,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    scenario = scenario_service.create_scenario(db, project, payload, actor=user.email)
    return {"id": scenario.id, "name": scenario.name}


@router.get("/scenarios/{scenario_id}")
def get_scenario(
    scenario_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    scenario = _scenario(db, user, scenario_id)
    return {
        "id": scenario.id,
        "project_id": scenario.project_id,
        "name": scenario.name,
        "description": scenario.description,
        "is_baseline": scenario.is_baseline,
        "status": scenario.status,
        "parent_id": scenario.parent_id,
        "approved_by": scenario.approved_by,
        "approved_at": scenario.approved_at.isoformat() if scenario.approved_at else None,
        "interventions": [
            {
                "id": row.id,
                "type": row.type,
                "label": row.label,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "params": row.params,
                "cost": row.cost,
            }
            for row in scenario.interventions
        ],
        "total_cost": round(sum(row.cost for row in scenario.interventions), 2),
    }


@router.patch("/scenarios/{scenario_id}")
def update_scenario(
    scenario_id: str,
    payload: ScenarioPatch,
    user: WriterUser,
    db: DbSession,
) -> dict:
    scenario = _scenario(db, user, scenario_id)
    project = _project(db, user, scenario.project_id)
    updated = scenario_service.update_scenario(db, project, scenario, payload, actor=user.email)
    return {"id": updated.id, "name": updated.name, "status": updated.status}


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(
    scenario_id: str,
    user: WriterUser,
    db: DbSession,
) -> dict:
    scenario = _scenario(db, user, scenario_id)
    project = _project(db, user, scenario.project_id)
    scenario_service.delete_scenario(db, project, scenario, actor=user.email)
    return {"deleted": scenario_id}


@router.post("/scenarios/{scenario_id}/clone", status_code=201)
def clone_scenario(
    scenario_id: str,
    payload: dict,
    user: WriterUser,
    db: DbSession,
) -> dict:
    source = _scenario(db, user, scenario_id)
    project = _project(db, user, source.project_id)
    clone_payload = ScenarioCreate(
        name=payload.get("name") or f"{source.name} (copy)",
        description=payload.get("description") or source.description,
        interventions=[],
        parent_id=source.id,
        clone_from=source.id,
    )
    scenario = scenario_service.create_scenario(db, project, clone_payload, actor=user.email)
    return {"id": scenario.id, "name": scenario.name}


@router.post("/projects/{project_id}/scenarios/{scenario_id}/preview")
def preview_scenario(
    project_id: str,
    scenario_id: str,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    scenario = _scenario(db, user, scenario_id)
    if scenario.project_id != project.id:
        raise NotFoundError("Scenario does not belong to this project")
    return scenario_service.preview_scenario(db, project, scenario)


@router.post("/projects/{project_id}/scenarios/compare")
def compare_scenarios(
    project_id: str,
    payload: CompareRequest,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    return scenario_service.compare(db, project, payload)


@router.get("/projects/{project_id}/interventions")
def intervention_catalog(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    from app.optimization.engine import generate_catalog
    from app.simulation.context import build_context

    context = build_context(db, project)
    catalog = generate_catalog(context)
    return {
        "interventions": [candidate.to_dict() for candidate in catalog],
        "count": len(catalog),
        "targets": {
            "tasks": [
                {"id": task.id, "code": task.code, "name": task.name, "phase": task.phase}
                for task in context.model.tasks
            ],
            "resources": [
                {"id": resource.id, "name": resource.name, "capacity": resource.capacity}
                for resource in context.model.resources
            ],
            "components": [
                {"id": component.id, "name": component.name, "part_number": component.part_number}
                for component in context.components.values()
            ],
        },
    }
