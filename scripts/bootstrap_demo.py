"""Populate the demo database with real, reproducible forecasts.

The script is idempotent: it never overwrites an existing run, so it can be
re-executed safely.  Nothing here fabricates a number — every forecast comes
from the Monte Carlo engine, every recommendation from the CP-SAT optimiser
plus its verification stage.

Usage
-----
    python scripts/bootstrap_demo.py                # all programs
    python scripts/bootstrap_demo.py --iterations 5000
    python scripts/bootstrap_demo.py --no-optimize
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.db.base import SessionLocal, init_db  # noqa: E402
from app.db.seed import seed_demo  # noqa: E402
from app.models import OptimizationRun, Project, Scenario, SimulationRun  # noqa: E402
from app.schemas.api import OptimizationRequest, SimulationRequest  # noqa: E402
from app.services import optimization_service, simulation_service  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _has_simulation(db, project: Project, label: str, scenario_id: str | None) -> bool:
    query = select(SimulationRun).where(
        SimulationRun.project_id == project.id,
        SimulationRun.label == label,
        SimulationRun.status == "completed",
    )
    if scenario_id is None:
        query = query.where(SimulationRun.scenario_id.is_(None))
    else:
        query = query.where(SimulationRun.scenario_id == scenario_id)
    return db.scalar(query) is not None


def ensure_simulation(db, project: Project, label: str, scenario_id: str | None, iterations: int, seed: int):
    if _has_simulation(db, project, label, scenario_id):
        print(f"  · {project.key} · {label}: already present")
        return None
    started = time.perf_counter()
    request = SimulationRequest(
        iterations=iterations,
        seed=seed,
        scenario_id=scenario_id,
        label=label,
        async_job=False,
    )
    sim = simulation_service.execute(db, project, request, actor="bootstrap")
    elapsed = time.perf_counter() - started
    summary = sim.summary or {}
    print(
        f"  · {project.key} · {label}: P50 {summary['makespan']['p50']}d, "
        f"P90 {summary['makespan']['p90']}d, on-time "
        f"{summary['deadline']['on_time_probability']:.1%} ({elapsed:.1f}s)"
    )
    return sim


def ensure_optimization(db, project: Project, budget: float, pilot: int, verification: int, seed: int):
    existing = db.scalar(
        select(OptimizationRun)
        .where(OptimizationRun.project_id == project.id, OptimizationRun.status == "completed")
    )
    if existing:
        print(f"  · {project.key} · optimisation: already present ({existing.id[:8]})")
        return None
    started = time.perf_counter()
    request = OptimizationRequest(
        budget=budget,
        objective="min_combined_exposure",
        pilot_iterations=pilot,
        verification_iterations=verification,
        seed=seed,
        async_job=False,
    )
    run = optimization_service.execute(db, project, request, actor="bootstrap")
    elapsed = time.perf_counter() - started
    results = run.results or {}
    recommendation = results.get("recommendation") or {}
    print(
        f"  · {project.key} · optimisation: {len(recommendation.get('labels', []))} interventions, "
        f"net {recommendation.get('net_economic_benefit', 0):,.0f} "
        f"(ROI {recommendation.get('roi', 0):.2f}) in {elapsed:.1f}s"
    )
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description="Populate the demo database with real forecasts")
    parser.add_argument("--iterations", type=int, default=2000, help="Trials per simulation")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--optimize", dest="optimize", action="store_true", default=True)
    parser.add_argument("--no-optimize", dest="optimize", action="store_false")
    parser.add_argument("--budget", type=float, default=150000.0)
    parser.add_argument("--pilot", type=int, default=300)
    parser.add_argument("--verification", type=int, default=800)
    parser.add_argument("--only", nargs="*", default=None, help="Limit to these program keys")
    args = parser.parse_args()

    init_db()
    seed_demo(scenarios=True)

    summary: dict[str, dict] = {}
    with SessionLocal() as db:
        projects = list(db.scalars(select(Project).order_by(Project.key)))
        if args.only:
            projects = [project for project in projects if project.key in set(args.only)]
        for project in projects:
            print(f"\n{project.key} — {project.name}")
            scenarios = list(
                db.scalars(select(Scenario).where(Scenario.project_id == project.id).order_by(Scenario.created_at))
            )
            for scenario in scenarios:
                if scenario.is_baseline:
                    continue
                ensure_simulation(
                    db,
                    project,
                    label=f"Forecast · {scenario.name}",
                    scenario_id=scenario.id,
                    iterations=args.iterations,
                    seed=args.seed,
                )
            # The plan forecast is executed last so it is the newest completed run.
            ensure_simulation(
                db,
                project,
                label="Plan forecast",
                scenario_id=None,
                iterations=args.iterations,
                seed=args.seed,
            )
            if args.optimize:
                ensure_optimization(
                    db,
                    project,
                    budget=args.budget,
                    pilot=args.pilot,
                    verification=args.verification,
                    seed=args.seed,
                )
            summary[project.key] = {
                "simulations": len(
                    list(
                        db.scalars(
                            select(SimulationRun).where(
                                SimulationRun.project_id == project.id,
                                SimulationRun.status == "completed",
                            )
                        )
                    )
                ),
                "optimizations": len(
                    list(
                        db.scalars(
                            select(OptimizationRun).where(
                                OptimizationRun.project_id == project.id,
                                OptimizationRun.status == "completed",
                            )
                        )
                    )
                ),
            }

    print("\n" + json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
