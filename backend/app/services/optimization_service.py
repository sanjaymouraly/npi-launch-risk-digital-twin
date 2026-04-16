"""Optimisation orchestration: catalog -> CP-SAT selection -> simulation verification."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models import OptimizationRun, Project
from app.optimization.engine import (
    estimate_catalog,
    generate_catalog,
    select_portfolios,
    verify_portfolios,
)
from app.optimization.interventions import InterventionSpec
from app.services import audit, job_service
from app.simulation.context import build_context
from app.simulation.engine import SimulationCancelled, SimulationOptions


def _clean_selection(selection: dict) -> dict:
    data = {k: v for k, v in selection.items() if k not in ("selected_specs", "_catalog")}
    return data


def execute(
    db: Session,
    project: Project,
    req,
    *,
    actor: str = "system",
    progress=None,
    cancel_check=None,
) -> OptimizationRun:
    context = build_context(db, project)
    budget = float(req.budget if req.budget is not None else project.intervention_budget)
    base_options = SimulationOptions(seed=req.seed, iterations=req.pilot_iterations)
    catalog = generate_catalog(context)
    excluded = set(req.constraints.exclude_types or [])
    if excluded:
        catalog = [c for c in catalog if c.type not in excluded]
    if not catalog:
        raise ValidationError("No candidate interventions could be generated for this project")

    def report(value: float, message: str) -> None:
        if progress:
            progress(value, message)

    def ensure_not_cancelled() -> None:
        if cancel_check and cancel_check():
            raise SimulationCancelled("Optimisation cancelled by user")

    report(0.02, f"Generated {len(catalog)} candidate interventions")
    estimated, meta = estimate_catalog(
        context,
        catalog,
        base_options,
        iterations=req.pilot_iterations,
        progress=lambda v, m: report(0.02 + v * 0.9, m),
    )
    ensure_not_cancelled()
    report(0.3, "Selecting portfolios with CP-SAT")
    selection = select_portfolios(
        estimated,
        budget,
        objective=req.objective,
        weights=req.weights,
        constraints=req.constraints.model_dump(),
        delay_cost_per_day=context.delay_cost_per_day,
    )
    ensure_not_cancelled()

    by_id = {c.id: c for c in estimated}
    portfolios: list[list[InterventionSpec]] = []
    selected_specs = selection.get("selected_specs", [])
    if selected_specs:
        portfolios.append(list(selected_specs))
    for point in selection.get("pareto", []):
        portfolio = [by_id[i] for i in point.get("interventions", []) if i in by_id]
        signature = tuple(sorted(c.id for c in portfolio))
        if portfolio and signature not in {tuple(sorted(c.id for c in p)) for p in portfolios}:
            portfolios.append(portfolio)
        if len(portfolios) >= 4:
            break
    if not portfolios:
        raise ValidationError(
            "No feasible intervention portfolio fits the budget. Increase the budget or relax constraints."
        )

    report(0.4, f"Verifying {len(portfolios)} portfolio(s) by simulation")
    verification = verify_portfolios(
        context,
        portfolios,
        SimulationOptions(seed=req.seed, iterations=req.pilot_iterations),
        iterations=req.verification_iterations,
        progress=lambda v, m: report(0.4 + v * 0.55, m),
        budget=budget,
    )
    ensure_not_cancelled()
    report(0.97, "Persisting optimisation results")

    results = {
        "budget": budget,
        "objective": req.objective,
        "weights": req.weights,
        "constraints": req.constraints.model_dump(),
        "catalog": [c.to_dict() for c in estimated],
        "catalog_meta": meta,
        "selection": _clean_selection(selection),
        "verification": {
            "baseline": verification["baseline"],
            "portfolios": verification["portfolios"],
            "iterations": verification["iterations"],
            "selection_rule": verification["selection_rule"],
        },
        "recommendation": verification["portfolios"][0] if verification["portfolios"] else None,
        "method": {
            "steps": [
                "Candidate catalog generated from the real project (critical tasks, suppliers, bottlenecks, dependencies).",
                "Each candidate estimated with a paired Monte Carlo pilot using common random numbers.",
                "CP-SAT selects portfolios under budget, exclusivity, prerequisite, headcount and capacity constraints.",
                "Selected and Pareto-near portfolios are re-simulated at higher fidelity and checked against CP-SAT scheduling.",
            ],
            "benefit_additivity_warning": (
                "The optimiser scores candidates additively; interactions are captured by the simulation "
                "verification and can reduce or increase the combined benefit."
            ),
        },
    }
    run = OptimizationRun(
        project_id=project.id,
        baseline_simulation_id=None,
        objective=req.objective,
        budget=budget,
        weights=req.weights,
        constraints=req.constraints.model_dump(),
        status="completed",
        results=results,
    )
    db.add(run)
    db.flush()
    audit.record(
        db,
        project_id=project.id,
        actor=actor,
        action="optimization.run",
        entity_type="optimization",
        entity_id=run.id,
        summary=(
            f"Optimised {len(estimated)} candidates under ${budget:,.0f}; "
            f"recommended {len(results['recommendation']['intervention_ids']) if results['recommendation'] else 0} intervention(s)"
        ),
        payload={"objective": req.objective, "budget": budget},
    )
    db.commit()
    db.refresh(run)
    return run


def submit_optimization(db: Session, project: Project, req, actor: str = "system") -> dict:
    if req.async_job:
        def runner(job_db, job, progress, cancelled):  # noqa: ANN001
            run = execute(
                job_db, project, req, actor=actor, progress=progress, cancel_check=cancelled
            )
            job.result = {"optimization_id": run.id}
            return {"optimization_id": run.id}

        job = job_service.submit(
            kind="optimization",
            project_id=project.id,
            payload={"budget": req.budget, "objective": req.objective},
            fn=runner,
            idempotency_key=req.idempotency_key,
        )
        return {"job_id": job.id, "status": job.status, "async": True}
    run = execute(db, project, req, actor=actor)
    return {"optimization_id": run.id, "status": run.status, "async": False}


def list_optimizations(db: Session, project_id: str, limit: int = 20) -> list[dict]:
    runs = list(
        db.scalars(
            select(OptimizationRun)
            .where(OptimizationRun.project_id == project_id)
            .order_by(OptimizationRun.created_at.desc())
            .limit(limit)
        )
    )
    out = []
    for run in runs:
        results = run.results or {}
        recommendation = results.get("recommendation") or {}
        verification = results.get("verification", {})
        out.append(
            {
                "id": run.id,
                "objective": run.objective,
                "budget": run.budget,
                "status": run.status,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "recommended": recommendation.get("labels", []),
                "net_economic_benefit": recommendation.get("net_economic_benefit"),
                "intervention_cost": recommendation.get("intervention_cost"),
                "on_time_probability": (recommendation.get("simulation") or {}).get("on_time_probability"),
                "baseline_on_time_probability": (verification.get("baseline") or {}).get(
                    "on_time_probability"
                ),
                "p90_reduction": (
                    (verification.get("baseline") or {}).get("p90", 0)
                    - (recommendation.get("simulation") or {}).get("p90", 0)
                )
                if recommendation
                else None,
            }
        )
    return out


def get_optimization(db: Session, optimization_id: str) -> dict:
    run = db.get(OptimizationRun, optimization_id)
    if not run:
        raise NotFoundError(f"Optimization {optimization_id} not found")
    return {
        "id": run.id,
        "project_id": run.project_id,
        "objective": run.objective,
        "budget": run.budget,
        "weights": run.weights,
        "constraints": run.constraints,
        "status": run.status,
        "results": run.results,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
