"""Simulation orchestration, persistence and calibration reporting."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models import Project, Scenario, SimulationRun, SimulationSnapshot
from app.optimization.interventions import apply_interventions
from app.services import audit, job_service
from app.services.scenario_service import specs_for_scenario
from app.simulation.context import build_context
from app.simulation.engine import (
    ENGINE_VERSION,
    SimulationCancelled,
    SimulationOptions,
    run_monte_carlo,
)


def options_from_request(req) -> SimulationOptions:  # noqa: ANN001
    return SimulationOptions(
        iterations=req.iterations,
        seed=req.seed,
        correlation_rho=req.correlation_rho,
        capacity_loss_prob=req.capacity_loss_prob,
        absenteeism_prob=req.absenteeism_prob,
        transport_delay_prob=req.transport_delay_prob,
        supplier_disruption_enabled=req.supplier_disruption_enabled,
        material_constraints_enabled=req.material_constraints_enabled,
        validate_iterations=req.validate_iterations,
        solver_time_limit=req.solver_time_limit,
        label=req.label or "Monte Carlo",
    )


def build_scenario_context(db: Session, project: Project, scenario_id: str | None):
    context = build_context(db, project)
    scenario = None
    warnings: list[str] = []
    if scenario_id:
        scenario = db.get(Scenario, scenario_id)
        if not scenario or scenario.project_id != project.id:
            raise NotFoundError(f"Scenario {scenario_id} not found in this project")
        specs = specs_for_scenario(scenario)
        if specs:
            context, warnings = apply_interventions(context, specs)
    return context, scenario, warnings


def execute(
    db: Session,
    project: Project,
    req,
    *,
    actor: str = "system",
    progress=None,
    cancel_check=None,
) -> SimulationRun:
    context, scenario, warnings = build_scenario_context(db, project, req.scenario_id)
    options = options_from_request(req)
    options.progress_callback = progress
    options.cancel_check = cancel_check
    try:
        result = run_monte_carlo(context, options)
    except SimulationCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"Simulation failed: {exc}") from exc

    summary = result.summary
    summary["scenario"] = {
        "id": scenario.id if scenario else None,
        "name": scenario.name if scenario else "Baseline",
        "is_baseline": bool(scenario.is_baseline) if scenario else True,
        "intervention_count": len(scenario.interventions) if scenario else 0,
    }
    summary["warnings"] = list(summary.get("warnings", [])) + warnings
    sim = SimulationRun(
        project_id=project.id,
        scenario_id=scenario.id if scenario else None,
        job_id=None,
        label=req.label or (scenario.name if scenario else "Baseline"),
        seed=req.seed,
        iterations=req.iterations,
        status="completed",
        engine_version=ENGINE_VERSION,
        model_fingerprint=result.fingerprint,
        config={**options.to_dict(), "scenario_id": req.scenario_id},
        summary=summary,
        samples=result.samples,
    )
    db.add(sim)
    db.flush()
    db.add(
        SimulationSnapshot(
            project_id=project.id,
            simulation_id=sim.id,
            scenario_id=scenario.id if scenario else None,
            label=sim.label,
            p50_days=summary["makespan"]["p50"],
            p90_days=summary["makespan"]["p90"],
            on_time_probability=summary["deadline"]["on_time_probability"],
            payload={
                "summary": {
                    "makespan": summary["makespan"],
                    "deadline": summary["deadline"],
                    "cost": summary["cost"],
                    "engine": summary["engine"],
                },
                "milestones": summary.get("milestones", []),
                "warnings": summary.get("warnings", []),
            },
        )
    )
    audit.record(
        db,
        project_id=project.id,
        actor=actor,
        action="simulation.run",
        entity_type="simulation",
        entity_id=sim.id,
        summary=(
            f"Ran {req.iterations} trials (seed {req.seed}) for "
            f"{scenario.name if scenario else 'baseline'}: P50 {summary['makespan']['p50']}d, "
            f"P90 {summary['makespan']['p90']}d"
        ),
        payload={"scenario_id": req.scenario_id, "iterations": req.iterations, "seed": req.seed},
    )
    db.commit()
    db.refresh(sim)
    return sim


def submit_simulation(db: Session, project: Project, req, actor: str = "system") -> dict:
    if req.iterations > 50000:
        raise ValidationError("Maximum 50,000 iterations per run")
    if req.async_job:
        def runner(job_db, job, progress, cancelled):  # noqa: ANN001
            sim = execute(
                job_db,
                project,
                req,
                actor=actor,
                progress=progress,
                cancel_check=cancelled,
            )
            job.result = {"simulation_id": sim.id}
            return {"simulation_id": sim.id, "label": sim.label}

        job = job_service.submit(
            kind="simulation",
            project_id=project.id,
            payload={"scenario_id": req.scenario_id, "iterations": req.iterations, "seed": req.seed},
            fn=runner,
            idempotency_key=req.idempotency_key,
        )
        return {"job_id": job.id, "status": job.status, "async": True}
    sim = execute(db, project, req, actor=actor)
    return {"simulation_id": sim.id, "status": sim.status, "async": False}


def list_simulations(db: Session, project_id: str, limit: int = 25) -> list[dict]:
    rows = list(
        db.scalars(
            select(SimulationRun)
            .where(SimulationRun.project_id == project_id)
            .order_by(SimulationRun.created_at.desc())
            .limit(limit)
        )
    )
    out = []
    for sim in rows:
        summary = sim.summary or {}
        out.append(
            {
                "id": sim.id,
                "label": sim.label,
                "scenario_id": sim.scenario_id,
                "status": sim.status,
                "iterations": sim.iterations,
                "seed": sim.seed,
                "engine_version": sim.engine_version,
                "created_at": sim.created_at.isoformat() if sim.created_at else None,
                "p50": summary.get("makespan", {}).get("p50"),
                "p90": summary.get("makespan", {}).get("p90"),
                "on_time_probability": summary.get("deadline", {}).get("on_time_probability"),
                "p90_date": summary.get("makespan", {}).get("p90_date"),
                "scenario_name": summary.get("scenario", {}).get("name"),
                "expected_delay_cost": summary.get("deadline", {}).get("expected_delay_cost"),
                "incremental_cost": summary.get("cost", {}).get("expected_incremental_cost"),
            }
        )
    return out


def get_simulation(db: Session, simulation_id: str, include_samples: bool = False) -> dict:
    sim = db.get(SimulationRun, simulation_id)
    if not sim:
        raise NotFoundError(f"Simulation {simulation_id} not found")
    data = {
        "id": sim.id,
        "project_id": sim.project_id,
        "scenario_id": sim.scenario_id,
        "label": sim.label,
        "seed": sim.seed,
        "iterations": sim.iterations,
        "status": sim.status,
        "engine_version": sim.engine_version,
        "model_fingerprint": sim.model_fingerprint,
        "config": sim.config,
        "summary": sim.summary,
        "created_at": sim.created_at.isoformat() if sim.created_at else None,
    }
    if include_samples:
        data["samples"] = sim.samples
    return data


def latest_simulation(db: Session, project_id: str, scenario_id: str | None = None) -> SimulationRun | None:
    query = (
        select(SimulationRun)
        .where(SimulationRun.project_id == project_id, SimulationRun.status == "completed")
        .order_by(SimulationRun.created_at.desc())
        .limit(1)
    )
    if scenario_id:
        query = query.where(SimulationRun.scenario_id == scenario_id)
    return db.scalar(query)


def calibration_report(db: Session, project_id: str) -> dict:
    """Compare stored forecasts with observed outcomes where available.

    The synthetic demo has very few observations; the report states that plainly
    instead of presenting a meaningless calibration score as evidence.
    """
    from app.models import ActualEvent, CalibrationRecord

    records = list(
        db.scalars(select(CalibrationRecord).where(CalibrationRecord.project_id == project_id))
    )
    events = list(db.scalars(select(ActualEvent).where(ActualEvent.project_id == project_id)))
    if not records:
        return {
            "status": "insufficient_data",
            "message": (
                "No forecast/outcome pairs have been recorded. Calibration requires historical "
                "launches (predicted probability and observed outcome) — the platform does not "
                "fabricate a Brier score."
            ),
            "observed_events": len(events),
            "records": 0,
        }
    hits = sum(1 for r in records if bool(r.outcome))
    brier = sum((r.forecast_probability - (1.0 if r.outcome else 0.0)) ** 2 for r in records) / len(records)
    return {
        "status": "ok",
        "records": len(records),
        "observed_rate": round(hits / len(records), 4),
        "brier_score": round(brier, 4),
        "observed_events": len(events),
        "note": "Small samples make calibration statistics indicative only.",
    }
