"""Monte Carlo simulation, attribution and calibration endpoints."""
from __future__ import annotations

import csv
import io
import json

import numpy as np
from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.security import CurrentUser, WriterUser
from app.db.base import DbSession
from app.models import Project
from app.scheduling.sgs import schedule_sgs
from app.schemas.api import LeaveOneOutRequest, SimulationRequest, SobolRequest
from app.services import simulation_service
from app.services.simulation_service import latest_simulation
from app.simulation.attribution import leave_one_out_attribution, sobol_first_order
from app.simulation.context import build_context
from app.simulation.engine import SimulationOptions

router = APIRouter()


def _project(db: Session, user, project_id: str) -> Project:  # noqa: ANN001
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")
    user.require_project(project.id)
    return project


@router.post("/projects/{project_id}/simulations", status_code=202)
def run_simulation(
    project_id: str,
    payload: SimulationRequest,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    return simulation_service.submit_simulation(db, project, payload, actor=user.email)


@router.get("/projects/{project_id}/simulations")
def list_simulations(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=25, ge=1, le=100),
) -> list[dict]:
    project = _project(db, user, project_id)
    return simulation_service.list_simulations(db, project.id, limit=limit)


@router.get("/projects/{project_id}/simulations/latest")
def latest(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
    scenario_id: str | None = Query(default=None),
) -> dict:
    project = _project(db, user, project_id)
    sim = latest_simulation(db, project.id, scenario_id)
    if not sim:
        raise NotFoundError("No completed simulation for this project/scenario")
    return simulation_service.get_simulation(db, sim.id)


@router.get("/simulations/{simulation_id}")
def get_simulation(
    simulation_id: str,
    user: CurrentUser,
    db: DbSession,
    include_samples: bool = Query(default=False),
) -> dict:
    sim = simulation_service.get_simulation(db, simulation_id, include_samples=include_samples)
    project = db.get(Project, sim["project_id"])
    if project:
        user.require_project(project.id)
    return sim


@router.get("/simulations/{simulation_id}/download")
def download_simulation(
    simulation_id: str,
    user: CurrentUser,
    db: DbSession,
    format: str = Query(default="json", pattern="^(json|csv)$"),
) -> Response:
    sim = simulation_service.get_simulation(db, simulation_id, include_samples=True)
    project = db.get(Project, sim["project_id"])
    if project:
        user.require_project(project.id)
    if format == "json":
        return Response(
            content=json.dumps(sim, indent=2, default=str),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="simulation-{simulation_id[:8]}.json"'
            },
        )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["trial", "makespan_working_days"])
    for index, value in enumerate(sim.get("samples") or []):
        writer.writerow([index + 1, value])
    summary = sim.get("summary") or {}
    writer.writerow([])
    writer.writerow(["summary_key", "value"])
    for key in ("mean", "std", "p10", "p50", "p80", "p90", "p95", "cvar90", "sem"):
        writer.writerow([f"makespan.{key}", (summary.get("makespan") or {}).get(key)])
    for key in ("on_time_probability", "expected_delay_days", "expected_delay_cost", "p90_delay_cost"):
        writer.writerow([f"deadline.{key}", (summary.get("deadline") or {}).get(key)])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="simulation-{simulation_id[:8]}.csv"'
        },
    )


@router.get("/projects/{project_id}/calibration")
def calibration(
    project_id: str,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    return simulation_service.calibration_report(db, project.id)


@router.post("/projects/{project_id}/attribution/sobol")
def sobol(
    project_id: str,
    payload: SobolRequest,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    context = build_context(db, project)
    task_map = context.model.task_map()
    selected = [tid for tid in payload.input_ids if tid in task_map]
    if not selected:
        ordered = sorted(
            context.model.tasks,
            key=lambda task: (-task.base_duration, task.code),
        )
        selected = [task.id for task in ordered[: min(4, len(ordered))]]
    if not selected:
        raise ValidationError("No tasks available for Sobol analysis")
    if len(selected) > 6:
        raise ValidationError("At most 6 inputs are supported per Sobol run")
    bounds = []
    for task_id in selected:
        task = task_map[task_id]
        base = max(1.0, task.base_duration)
        bounds.append((max(0.25, base * 0.5), max(0.5, base * 1.5)))

    def evaluator(matrix: np.ndarray) -> np.ndarray:
        outputs = []
        for row in matrix:
            durations = {task.id: task.base_duration for task in context.model.tasks}
            for index, task_id in enumerate(selected):
                durations[task_id] = float(row[index])
            try:
                schedule = schedule_sgs(context.model, durations=durations, calendar=context.calendar)
                outputs.append(schedule.makespan if np.isfinite(schedule.makespan) else 9999.0)
            except Exception:  # noqa: BLE001
                outputs.append(9999.0)
        return np.asarray(outputs, dtype=float)

    result = sobol_first_order(
        evaluator, bounds, n_base=min(payload.n_base, 512), seed=payload.seed
    )
    for row, task_id in zip(result["indices"], selected, strict=False):
        task = task_map[task_id]
        row.update(
            {
                "task_id": task_id,
                "task": task.name,
                "code": task.code,
                "bounds_days": list(
                    next(b for i, b in enumerate(bounds) if i == row["index"])
                ),
            }
        )
    result["inputs"] = [task_map[t].name for t in selected]
    result["caveat"] = (
        "Sobol indices are computed inside the deterministic scheduling model; "
        "they are not estimates of real-world causal effects."
    )
    return result


@router.post("/projects/{project_id}/attribution/leave-one-out")
def leave_one_out(
    project_id: str,
    payload: LeaveOneOutRequest,
    user: WriterUser,
    db: DbSession,
) -> dict:
    project = _project(db, user, project_id)
    sim = latest_simulation(db, project.id)
    if not sim:
        raise ValidationError("Run a simulation first; leave-one-out uses its empirical drivers")
    summary = sim.summary or {}
    sensitivity = (summary.get("attribution") or {}).get("sensitivity", [])
    kind_map = {
        "task_duration": "task",
        "risk_event": "risk",
        "supplier_disruption": "supplier",
    }
    drivers = []
    for row in sensitivity:
        kind = kind_map.get(row.get("kind"))
        if not kind:
            continue
        drivers.append({"kind": kind, "id": row.get("input_id"), "name": row.get("input")})
    if not drivers:
        raise ValidationError("No attributable drivers found in the latest simulation")
    context = build_context(db, project)
    result = leave_one_out_attribution(
        context,
        SimulationOptions(seed=sim.seed, iterations=payload.iterations),
        drivers,
        iterations=payload.iterations,
        limit=payload.limit,
    )
    result["source_simulation_id"] = sim.id
    return result
