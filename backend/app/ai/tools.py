"""Read-only, evidence-grounded tools used by the AI assistant.

Every tool returns a compact ``data`` payload plus explicit citation records so
the assistant can ground claims in a specific simulation, schedule or scenario.
No tool mutates project state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    OptimizationRun,
    Project,
    Risk,
    Scenario,
    SimulationRun,
    SimulationSnapshot,
)
from app.services.scheduling_service import project_schedule, supplier_exposure
from app.simulation.context import build_context


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cite(kind: str, identifier: str, detail: str) -> dict:
    return {"kind": kind, "id": identifier, "detail": detail}


def _latest_simulation(db: Session, project_id: str) -> SimulationRun | None:
    return db.scalar(
        select(SimulationRun)
        .where(SimulationRun.project_id == project_id, SimulationRun.status == "completed")
        .order_by(SimulationRun.created_at.desc())
        .limit(1)
    )


def _latest_optimization(db: Session, project_id: str) -> OptimizationRun | None:
    return db.scalar(
        select(OptimizationRun)
        .where(OptimizationRun.project_id == project_id, OptimizationRun.status == "completed")
        .order_by(OptimizationRun.created_at.desc())
        .limit(1)
    )


def _sim_citation(sim: SimulationRun) -> dict:
    summary = sim.summary or {}
    return _cite(
        "simulation",
        sim.id,
        (
            f"{sim.iterations} Monte Carlo trials, seed {sim.seed}, "
            f"P50 {summary.get('makespan', {}).get('p50')}d, "
            f"on-time {summary.get('deadline', {}).get('on_time_probability')}"
        ),
    )


def project_overview(db: Session, project: Project) -> dict:
    context = build_context(db, project)
    sim = _latest_simulation(db, project.id)
    scenario_count = len(
        list(db.scalars(select(Scenario).where(Scenario.project_id == project.id)))
    )
    optimization = _latest_optimization(db, project.id)
    summary = sim.summary if sim else {}
    data = {
        "project": {
            "id": project.id,
            "key": project.key,
            "name": project.name,
            "product": project.product,
            "version": project.version,
            "status": project.status,
            "owner": project.owner,
            "start_date": project.start_date.isoformat(),
            "launch_deadline": project.launch_deadline.isoformat() if project.launch_deadline else None,
            "delay_cost_per_day": project.delay_cost_per_day,
            "currency": project.currency,
            "intervention_budget": project.intervention_budget,
        },
        "scope": {
            "tasks": len(context.model.tasks),
            "dependencies": len(context.model.edges),
            "resources": len(context.model.resources),
            "suppliers": len(context.suppliers),
            "components": len(context.components),
            "risks": len(context.risks),
            "scenarios": scenario_count,
        },
        "latest_simulation": None
        if not sim
        else {
            "id": sim.id,
            "label": sim.label,
            "iterations": sim.iterations,
            "seed": sim.seed,
            "created_at": sim.created_at.isoformat() if sim.created_at else None,
            "p50_days": summary.get("makespan", {}).get("p50"),
            "p90_days": summary.get("makespan", {}).get("p90"),
            "p90_date": summary.get("makespan", {}).get("p90_date"),
            "on_time_probability": summary.get("deadline", {}).get("on_time_probability"),
            "on_time_ci": summary.get("deadline", {}).get("on_time_ci"),
            "expected_delay_days": summary.get("deadline", {}).get("expected_delay_days"),
            "expected_delay_cost": summary.get("deadline", {}).get("expected_delay_cost"),
            "cvar90_delay_cost": summary.get("deadline", {}).get("cvar90_delay_cost"),
            "engine": summary.get("engine"),
            "deterministic": summary.get("deterministic"),
        },
        "latest_optimization": None
        if not optimization
        else {
            "id": optimization.id,
            "objective": optimization.objective,
            "budget": optimization.budget,
            "created_at": optimization.created_at.isoformat() if optimization.created_at else None,
            "recommendation": (optimization.results or {}).get("recommendation"),
        },
    }
    citations = [_cite("project", project.id, f"{project.key} project record")]
    if sim:
        citations.append(_sim_citation(sim))
    if optimization:
        citations.append(
            _cite("optimization", optimization.id, f"{optimization.objective} optimisation run")
        )
    return {
        "tool": "project_overview",
        "as_of": _now(),
        "data": data,
        "citations": citations,
    }


def schedule_analysis(db: Session, project: Project) -> dict:
    schedule = project_schedule(db, project, mode="both", time_limit=6)
    cpm = schedule.get("cpm", {})
    constrained = schedule.get("constrained", {})
    comparison = schedule.get("comparison", {})
    milestones = (schedule.get("validation") or {}).get("counts", {})
    bottlenecks = schedule.get("bottlenecks", [])
    data = {
        "calendar": schedule.get("calendar"),
        "deadline": schedule.get("deadline"),
        "unconstrained_cpm": {
            "duration_days": cpm.get("project_duration"),
            "finish_date": cpm.get("finish_date"),
            "critical_path": cpm.get("critical_path"),
            "meets_deadline": cpm.get("meets_deadline"),
            "deadline_margin_days": cpm.get("deadline_margin_days"),
        },
        "resource_constrained": {
            "feasible": constrained.get("feasible"),
            "status": constrained.get("status"),
            "makespan_days": constrained.get("makespan"),
            "finish_date": constrained.get("project_finish_date"),
            "capacity_delay_days": constrained.get("capacity_delay_days"),
            "deadline": constrained.get("deadline"),
            "conflicts": (constrained.get("conflicts") or [])[:6],
            "solver": constrained.get("solver"),
            "gap": constrained.get("gap"),
        },
        "comparison": comparison,
        "bottlenecks": bottlenecks[:6],
        "counts": milestones,
        "assumptions": schedule.get("assumptions"),
    }
    citations = [_cite("schedule", project.id, "Deterministic CPM + CP-SAT resource-constrained schedule")]
    return {
        "tool": "schedule_analysis",
        "as_of": _now(),
        "data": data,
        "citations": citations,
    }


def simulation_summary(db: Session, project: Project) -> dict:
    sim = _latest_simulation(db, project.id)
    if not sim:
        return {
            "tool": "simulation_summary",
            "as_of": _now(),
            "data": {
                "available": False,
                "message": "No completed Monte Carlo simulation exists for this project yet.",
            },
            "citations": [],
        }
    summary = sim.summary or {}
    data = {
        "available": True,
        "simulation_id": sim.id,
        "label": sim.label,
        "scenario_id": sim.scenario_id,
        "iterations": sim.iterations,
        "seed": sim.seed,
        "engine": summary.get("engine"),
        "makespan": {
            key: summary.get("makespan", {}).get(key)
            for key in ("mean", "std", "p10", "p50", "p80", "p90", "p95", "cvar90", "sem", "ci95_mean", "p50_date", "p80_date", "p90_date")
        },
        "deadline": summary.get("deadline"),
        "cost": summary.get("cost"),
        "convergence": summary.get("convergence"),
        "milestones": summary.get("milestones", []),
        "deterministic": summary.get("deterministic"),
        "warnings": summary.get("warnings", []),
        "solver_validation": summary.get("solver_validation"),
        "scenario": summary.get("scenario"),
    }
    return {
        "tool": "simulation_summary",
        "as_of": sim.created_at.isoformat() if sim.created_at else _now(),
        "data": data,
        "citations": [_sim_citation(sim)],
    }


def risk_analysis(db: Session, project: Project) -> dict:
    sim = _latest_simulation(db, project.id)
    if sim:
        summary = sim.summary or {}
        attribution = summary.get("attribution", {})
        data = {
            "source": "latest_simulation",
            "simulation_id": sim.id,
            "sensitivity": attribution.get("sensitivity", [])[:12],
            "tornado": attribution.get("tornado", [])[:10],
            "dependency_criticality": attribution.get("dependency_criticality", [])[:8],
            "risk_events": summary.get("risks", [])[:10],
            "notes": attribution.get("notes", []),
        }
        citations = [_sim_citation(sim)]
    else:
        risks = list(
            db.scalars(select(Risk).where(Risk.project_id == project.id).order_by(Risk.probability.desc()).limit(12))
        )
        data = {
            "source": "risk_register (no simulation yet)",
            "sensitivity": [],
            "tornado": [],
            "dependency_criticality": [],
            "risk_events": [
                {
                    "id": r.id,
                    "name": r.name,
                    "category": r.category,
                    "probability": r.probability,
                    "impact_days": r.impact_days,
                    "impact_cost": r.impact_cost,
                }
                for r in risks
            ],
            "notes": [
                "A Monte Carlo simulation is required for empirical risk attribution; "
                "these are register values only."
            ],
        }
        citations = [_cite("risk_register", project.id, "Risk register (no simulation yet)")]
    return {
        "tool": "risk_analysis",
        "as_of": sim.created_at.isoformat() if sim and sim.created_at else _now(),
        "data": data,
        "citations": citations,
    }


def supplier_risk(db: Session, project: Project) -> dict:
    exposure = supplier_exposure(db, project)
    sim = _latest_simulation(db, project.id)
    data = {
        "top_components": exposure["components"][:8],
        "top_suppliers": exposure["suppliers"][:8],
        "single_source_components": exposure["single_source_components"][:8],
        "no_qualified_alternate": exposure["no_qualified_alternate"][:8],
        "simulated_supplier_impact": (sim.summary or {}).get("suppliers", [])[:8] if sim else [],
    }
    citations = [_cite("supply_chain", project.id, "Bill of materials and supplier exposure")]
    if sim:
        citations.append(_sim_citation(sim))
    return {
        "tool": "supplier_risk",
        "as_of": _now(),
        "data": data,
        "citations": citations,
    }


def milestone_status(db: Session, project: Project) -> dict:
    sim = _latest_simulation(db, project.id)
    if sim and (sim.summary or {}).get("milestones"):
        milestones = (sim.summary or {}).get("milestones", [])
        citations = [_sim_citation(sim)]
        source = "latest_simulation"
    else:
        context = build_context(db, project)
        from app.scheduling.cpm import compute_cpm

        cpm = compute_cpm(context.model, context.calendar)
        milestones = []
        for m in context.milestones:
            if not m.task_id or m.task_id not in cpm.tasks:
                continue
            task = cpm.tasks[m.task_id]
            milestones.append(
                {
                    "id": m.id,
                    "name": m.name,
                    "due_date": m.due_date,
                    "customer_commitment": m.customer_commitment,
                    "p50_date": context.calendar.to_date(task.earliest_finish).isoformat(),
                    "p90_date": None,
                    "on_time_probability": None,
                    "slack_vs_due_days": round(m.due_offset - task.earliest_finish, 2)
                    if m.due_offset is not None
                    else None,
                    "note": "Deterministic CPM date; run a simulation for a probability.",
                }
            )
        citations = [_cite("schedule", project.id, "Deterministic CPM milestone forecast")]
        source = "cpm_only"
    for row in milestones:
        if row.get("due_date") is None and row.get("due_offset") is not None:
            row["due_date"] = "not set"
    return {
        "tool": "milestone_status",
        "as_of": sim.created_at.isoformat() if sim and sim.created_at else _now(),
        "data": {"source": source, "milestones": milestones},
        "citations": citations,
    }


def scenario_portfolio(db: Session, project: Project) -> dict:
    scenarios = list(
        db.scalars(
            select(Scenario).where(Scenario.project_id == project.id).order_by(Scenario.created_at)
        )
    )
    optimization = _latest_optimization(db, project.id)
    data = {
        "scenarios": [
            {
                "id": s.id,
                "name": s.name,
                "is_baseline": s.is_baseline,
                "status": s.status,
                "intervention_count": len(s.interventions),
                "total_cost": round(sum(i.cost for i in s.interventions), 2),
                "interventions": [
                    {"type": i.type, "label": i.label, "cost": i.cost} for i in s.interventions
                ],
            }
            for s in scenarios
        ],
        "latest_optimization": None
        if not optimization
        else {
            "id": optimization.id,
            "objective": optimization.objective,
            "budget": optimization.budget,
            "recommendation": (optimization.results or {}).get("recommendation"),
            "alternatives": ((optimization.results or {}).get("verification") or {}).get("portfolios", [])[:4],
            "method": (optimization.results or {}).get("method"),
        },
    }
    citations = []
    if optimization:
        citations.append(
            _cite("optimization", optimization.id, "Latest verified optimisation run")
        )
    for s in scenarios[:5]:
        citations.append(_cite("scenario", s.id, f"Scenario '{s.name}' ({len(s.interventions)} interventions)"))
    return {
        "tool": "scenario_portfolio",
        "as_of": _now(),
        "data": data,
        "citations": citations,
    }


def decision_history(db: Session, project: Project) -> dict:
    logs = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.project_id == project.id)
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )
    )
    snapshots = list(
        db.scalars(
            select(SimulationSnapshot)
            .where(SimulationSnapshot.project_id == project.id)
            .order_by(SimulationSnapshot.created_at.desc())
            .limit(10)
        )
    )
    data = {
        "audit_log": [
            {
                "action": log.action,
                "actor": log.actor,
                "summary": log.summary,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
            }
            for log in logs
        ],
        "forecast_snapshots": [
            {
                "id": snap.id,
                "simulation_id": snap.simulation_id,
                "label": snap.label,
                "p50_days": snap.p50_days,
                "p90_days": snap.p90_days,
                "on_time_probability": snap.on_time_probability,
                "created_at": snap.created_at.isoformat() if snap.created_at else None,
            }
            for snap in snapshots
        ],
    }
    return {
        "tool": "decision_history",
        "as_of": _now(),
        "data": data,
        "citations": [
            _cite("audit", project.id, "Project audit trail"),
            *[_cite("snapshot", s.id, f"Forecast snapshot {s.label}") for s in snapshots[:3]],
        ],
    }


def methodology(db: Session, project: Project) -> dict:
    sim = _latest_simulation(db, project.id)
    data = {
        "scheduling": {
            "cpm": "Logic-only critical path with FS/SS/FF/SF dependencies, lags and a working-day calendar.",
            "cpsat": "OR-Tools CP-SAT cumulative scheduling with resource capacity and material release dates.",
            "difference": "CPM ignores resource contention; CP-SAT reports the delay caused by capacity and materials.",
        },
        "simulation": {
            "method": "Monte Carlo over task durations, supplier disruptions, risk events, validation failures, ECOs and capacity loss using a serial schedule-generation scheme.",
            "feasibility": "Every trial is resource- and material-feasible; waiting is inserted when capacity is exceeded.",
            "percentiles": (sim.summary or {}).get("engine", {}).get("percentile_method")
            if sim
            else "Linear interpolation between order statistics (numpy.percentile).",
            "seed": "Entity-keyed independent random streams; the same seed reproduces the run and enables common random numbers across scenarios.",
        },
        "attribution": {
            "sensitivity": "Spearman rank correlation between sampled inputs and makespan (association, not causation).",
            "tornado": "One-at-a-time deterministic schedule reruns with +/-20% duration and +/-30% supplier lead time.",
            "sobol": "Saltelli/Sobol first-order indices for continuous inputs, with bootstrap uncertainty.",
        },
        "optimisation": {
            "selection": "CP-SAT portfolio selection under budget, exclusivity, prerequisites, headcount and capacity constraints.",
            "verification": "Selected portfolios are re-simulated and re-scheduled; the recommendation is the highest verified net economic benefit.",
            "caveat": "Additive candidate scoring ignores interactions; verification captures them.",
        },
        "assumptions": (sim.summary or {}).get("assumptions") if sim else [],
        "provenance": {
            "latest_simulation_id": sim.id if sim else None,
            "simulation_created_at": sim.created_at.isoformat() if sim and sim.created_at else None,
        },
    }
    citations = [_cite("methodology", "docs/validation.md", "Documented methods and assumptions")]
    if sim:
        citations.append(_sim_citation(sim))
    return {"tool": "methodology", "as_of": _now(), "data": data, "citations": citations}


TOOL_FUNCTIONS = {
    "project_overview": project_overview,
    "schedule_analysis": schedule_analysis,
    "simulation_summary": simulation_summary,
    "risk_analysis": risk_analysis,
    "supplier_risk": supplier_risk,
    "milestone_status": milestone_status,
    "scenario_portfolio": scenario_portfolio,
    "decision_history": decision_history,
    "methodology": methodology,
}


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "project_overview",
            "description": "Project metadata, scope counts, latest simulation headline and latest optimisation recommendation.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_analysis",
            "description": "Compare the unconstrained CPM schedule with the CP-SAT resource-constrained schedule, critical path, deadline feasibility and bottlenecks.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulation_summary",
            "description": "Latest Monte Carlo distribution: P10/P50/P90 makespan, on-time probability, delay cost, convergence and solver validation.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "risk_analysis",
            "description": "Empirical risk attribution: rank-correlation sensitivity, tornado impacts, critical dependencies and discrete risk events.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "supplier_risk",
            "description": "Supplier and component exposure: lead time, inventory, single-source flags, disruption probability and simulated impact.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "milestone_status",
            "description": "Milestone forecast dates, on-time probability and slack versus due dates.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scenario_portfolio",
            "description": "Scenario definitions and the latest optimisation portfolio, alternatives and verified economics.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "decision_history",
            "description": "Recent audit trail entries and immutable forecast snapshots.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "methodology",
            "description": "How the platform computes schedules, simulations, attribution and optimisation, including assumptions and caveats.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]


def execute_tool(db: Session, project: Project, name: str, arguments: dict | None = None) -> dict:
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return {
            "tool": name,
            "error": f"Unknown tool '{name}'",
            "citations": [],
        }
    return fn(db, project)
