"""Scenario CRUD, preview and common-random-number comparison."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models import Intervention, Project, Scenario
from app.optimization.interventions import (
    SUPPORTED_INTERVENTIONS,
    InterventionSpec,
    apply_interventions,
    intervention_cost_estimate,
)
from app.scheduling.cpm import compute_cpm
from app.scheduling.cpsat import CpsatOptions, resource_constrained_schedule
from app.services import audit
from app.simulation.attribution import paired_delta
from app.simulation.context import build_context
from app.simulation.engine import SimulationOptions, run_monte_carlo


def specs_for_scenario(scenario: Scenario) -> list[InterventionSpec]:
    return [
        InterventionSpec(
            id=row.id,
            type=row.type,
            label=row.label or row.type,
            target_type=row.target_type,
            target_id=row.target_id,
            params=dict(row.params or {}),
            cost=float(row.cost or 0.0),
        )
        for row in scenario.interventions
    ]


def list_scenarios(db: Session, project_id: str) -> list[dict]:
    scenarios = list(
        db.scalars(
            select(Scenario).where(Scenario.project_id == project_id).order_by(Scenario.created_at)
        )
    )
    out = []
    for scenario in scenarios:
        out.append(
            {
                "id": scenario.id,
                "name": scenario.name,
                "description": scenario.description,
                "is_baseline": scenario.is_baseline,
                "status": scenario.status,
                "parent_id": scenario.parent_id,
                "intervention_count": len(scenario.interventions),
                "total_cost": round(sum(i.cost for i in scenario.interventions), 2),
                "interventions": [
                    {
                        "id": i.id,
                        "type": i.type,
                        "label": i.label,
                        "target_type": i.target_type,
                        "target_id": i.target_id,
                        "params": i.params,
                        "cost": i.cost,
                    }
                    for i in scenario.interventions
                ],
                "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
                "approved_at": scenario.approved_at.isoformat() if scenario.approved_at else None,
                "approved_by": scenario.approved_by,
            }
        )
    return out


def get_scenario(db: Session, scenario_id: str) -> Scenario:
    scenario = db.get(Scenario, scenario_id)
    if not scenario:
        raise NotFoundError(f"Scenario {scenario_id} not found")
    return scenario


def _validate_interventions(db: Session, project: Project, rows: list) -> list[Intervention]:
    context = build_context(db, project)
    tasks = context.model.task_map()
    resources = context.model.resource_map()
    suppliers = context.suppliers
    components = context.components
    built: list[Intervention] = []
    for index, row in enumerate(rows):
        kind = (row.type or "").strip()
        if kind not in SUPPORTED_INTERVENTIONS:
            raise ValidationError(
                f"Intervention {index + 1}: unsupported type '{kind}'",
                details={"supported": sorted(SUPPORTED_INTERVENTIONS)},
            )
        params = dict(row.params or {})
        target_id = row.target_id
        cost = float(row.cost or 0.0)
        label = row.label or kind.replace("_", " ").title()
        if kind in ("expedite_task", "tooling_readiness", "reduce_scope", "move_qualification_date", "delay_design_freeze"):
            task_id = params.get("task_id") or target_id
            task = tasks.get(task_id or "")
            if not task:
                raise ValidationError(f"Intervention {index + 1}: unknown task '{task_id}'")
            params.setdefault("task_id", task.id)
            if cost == 0:
                cost = intervention_cost_estimate(kind, task=task)
            label = label if row.label else f"{kind.replace('_', ' ').title()}: {task.name}"
        elif kind in ("add_capacity", "add_resource", "add_overtime"):
            resource_id = params.get("resource_id") or target_id
            resource = resources.get(resource_id or "")
            if not resource:
                raise ValidationError(f"Intervention {index + 1}: unknown resource '{resource_id}'")
            params.setdefault("resource_id", resource.id)
            if cost == 0:
                cost = intervention_cost_estimate(kind, resource=resource)
            label = label if row.label else f"{kind.replace('_', ' ').title()}: {resource.name}"
        elif kind in ("replace_supplier", "split_procurement", "expedite_supplier", "increase_safety_stock"):
            component_id = params.get("component_id") or target_id
            component = components.get(component_id or "")
            if not component:
                raise ValidationError(f"Intervention {index + 1}: unknown component '{component_id}'")
            params.setdefault("component_id", component.id)
            supplier = suppliers.get(params.get("supplier_id") or component.supplier_id or "")
            if cost == 0:
                cost = intervention_cost_estimate(
                    kind,
                    component=component,
                    supplier=supplier,
                    planned_volume=project.planned_volume,
                )
            label = label if row.label else f"{kind.replace('_', ' ').title()}: {component.name}"
        elif kind == "parallelize":
            from_id = params.get("from_task_id")
            to_id = params.get("to_task_id")
            if from_id not in tasks or to_id not in tasks:
                raise ValidationError(
                    f"Intervention {index + 1}: parallelize needs existing from_task_id and to_task_id"
                )
            label = label if row.label else f"Overlap {tasks[from_id].name} → {tasks[to_id].name}"
        elif kind == "introduce_eco":
            targets = params.get("task_ids") or ([target_id] if target_id else [])
            targets = [t for t in targets if t in tasks]
            if not targets:
                raise ValidationError(f"Intervention {index + 1}: introduce_eco needs task_ids")
            params["task_ids"] = targets
            if cost == 0:
                cost = float(params.get("cost", 10000.0))
        built.append(
            Intervention(
                type=kind,
                target_type=row.target_type or "task",
                target_id=target_id or params.get("task_id") or params.get("resource_id") or params.get("component_id"),
                params=params,
                cost=max(0.0, round(cost, 2)),
                label=label,
            )
        )
    return built


def create_scenario(db: Session, project: Project, payload, actor: str = "system") -> Scenario:
    source = None
    if payload.clone_from:
        source = get_scenario(db, payload.clone_from)
        if source.project_id != project.id:
            raise ValidationError("Cannot clone a scenario from another project")
    rows = source.interventions if source and not payload.interventions else payload.interventions
    built = _validate_interventions(db, project, rows)
    scenario = Scenario(
        project_id=project.id,
        name=payload.name,
        description=payload.description or (source.description if source else ""),
        is_baseline=False,
        parent_id=payload.parent_id or (source.id if source else None),
        status="draft",
    )
    for intervention in built:
        scenario.interventions.append(intervention)
    db.add(scenario)
    db.flush()
    audit.record(
        db,
        project_id=project.id,
        actor=actor,
        action="scenario.create",
        entity_type="scenario",
        entity_id=scenario.id,
        summary=f"Created scenario '{scenario.name}' with {len(built)} interventions",
        payload={"interventions": [i.type for i in built]},
    )
    db.commit()
    db.refresh(scenario)
    return scenario


def update_scenario(db: Session, project: Project, scenario: Scenario, payload, actor: str = "system") -> Scenario:
    if scenario.is_baseline and payload.interventions is not None:
        raise ValidationError("The approved baseline cannot be edited; clone it instead")
    if payload.name is not None:
        scenario.name = payload.name
    if payload.description is not None:
        scenario.description = payload.description
    if payload.status is not None:
        scenario.status = payload.status
        if payload.status == "approved":
            scenario.approved_by = actor
            scenario.approved_at = datetime.now(timezone.utc)
    if payload.interventions is not None:
        built = _validate_interventions(db, project, payload.interventions)
        scenario.interventions.clear()
        db.flush()
        for intervention in built:
            scenario.interventions.append(intervention)
    audit.record(
        db,
        project_id=project.id,
        actor=actor,
        action="scenario.update",
        entity_type="scenario",
        entity_id=scenario.id,
        summary=f"Updated scenario '{scenario.name}'",
    )
    db.commit()
    db.refresh(scenario)
    return scenario


def delete_scenario(db: Session, project: Project, scenario: Scenario, actor: str = "system") -> None:
    if scenario.is_baseline:
        raise ValidationError("The approved baseline cannot be deleted")
    audit.record(
        db,
        project_id=project.id,
        actor=actor,
        action="scenario.delete",
        entity_type="scenario",
        entity_id=scenario.id,
        summary=f"Deleted scenario '{scenario.name}'",
    )
    db.delete(scenario)
    db.commit()


def preview_scenario(db: Session, project: Project, scenario: Scenario) -> dict:
    context = build_context(db, project)
    specs = specs_for_scenario(scenario)
    mutated, warnings = apply_interventions(context, specs)
    graph_validation = __import__(
        "app.scheduling.model", fromlist=["validate_graph"]
    ).validate_graph(mutated.model.tasks, mutated.model.edges)
    cpm = compute_cpm(mutated.model, mutated.calendar)
    baseline_cpm = compute_cpm(context.model, context.calendar)
    constrained = resource_constrained_schedule(
        mutated.model,
        mutated.calendar,
        CpsatOptions(time_limit_seconds=10, compute_float=False),
    )
    baseline_constrained = resource_constrained_schedule(
        context.model, context.calendar, CpsatOptions(time_limit_seconds=10, compute_float=False)
    )
    return {
        "scenario_id": scenario.id,
        "name": scenario.name,
        "interventions": [
            {"id": s.id, "type": s.type, "label": s.label, "cost": s.cost, "params": s.params}
            for s in specs
        ],
        "total_cost": round(sum(s.cost for s in specs), 2),
        "warnings": warnings,
        "validation": graph_validation.to_dict(),
        "baseline": {
            "cpm_days": baseline_cpm.project_duration,
            "cpm_finish": baseline_cpm.finish_date,
            "constrained_days": baseline_constrained.get("makespan"),
            "constrained_finish": baseline_constrained.get("project_finish_date"),
        },
        "scenario": {
            "cpm_days": cpm.project_duration,
            "cpm_finish": cpm.finish_date,
            "constrained_days": constrained.get("makespan"),
            "constrained_finish": constrained.get("project_finish_date"),
            "status": constrained.get("status"),
            "deadline": constrained.get("deadline"),
            "bottlenecks": constrained.get("bottlenecks", [])[:4],
        },
        "deterministic_delta_days": (
            round(baseline_constrained.get("makespan", 0) - constrained.get("makespan", 0), 2)
            if baseline_constrained.get("makespan") and constrained.get("makespan")
            else None
        ),
        "cost_per_day_saved": _cost_per_day(
            baseline_constrained.get("makespan"),
            constrained.get("makespan"),
            sum(s.cost for s in specs),
        ),
    }


def _cost_per_day(baseline: float | None, scenario: float | None, cost: float) -> float | None:
    if baseline is None or scenario is None:
        return None
    saved = baseline - scenario
    if saved <= 0:
        return None
    return round(cost / saved, 2)


def compare(db: Session, project: Project, req) -> dict:
    def run(scenario_id: str | None):
        context = build_context(db, project)
        scenario = None
        warnings = []
        if scenario_id:
            scenario = get_scenario(db, scenario_id)
            specs = specs_for_scenario(scenario)
            if specs:
                context, warnings = apply_interventions(context, specs)
        result = run_monte_carlo(
            context,
            SimulationOptions(
                iterations=req.iterations,
                seed=req.seed,
                label=f"compare-{scenario.name if scenario else 'baseline'}",
            ),
        )
        return result, scenario, warnings

    baseline_result, baseline_scenario, _ = run(req.baseline_scenario_id)
    scenario_result, scenario, scenario_warnings = run(req.scenario_id)
    delta = paired_delta(baseline_result.samples, scenario_result.samples)
    base_cost = baseline_result.summary["deadline"]["expected_delay_cost"]
    scen_cost = scenario_result.summary["deadline"]["expected_delay_cost"]
    intervention_cost = (
        sum(i.cost for i in scenario.interventions) if scenario else 0.0
    )
    net = (base_cost - scen_cost) - intervention_cost
    payload: dict = {
        "baseline": {
            "scenario_id": baseline_scenario.id if baseline_scenario else None,
            "name": baseline_scenario.name if baseline_scenario else "Baseline",
            "summary": baseline_result.summary,
        },
        "scenario": {
            "scenario_id": scenario.id if scenario else None,
            "name": scenario.name if scenario else "Baseline",
            "summary": scenario_result.summary,
            "intervention_cost": round(intervention_cost, 2),
            "warnings": scenario_warnings,
        },
        "paired_delta": delta,
        "economics": {
            "baseline_expected_delay_cost": base_cost,
            "scenario_expected_delay_cost": scen_cost,
            "intervention_cost": round(intervention_cost, 2),
            "net_expected_benefit": round(net, 2),
            "roi": round(net / intervention_cost, 3) if intervention_cost > 0 else None,
            "payback_days_equivalent": round(intervention_cost / max(1.0, project.delay_cost_per_day), 2),
        },
        "comparison_method": {
            "common_random_numbers": True,
            "seed": req.seed,
            "iterations": req.iterations,
            "note": (
                "Both scenarios reuse the same entity-keyed random streams, so the paired delta "
                "isolates the intervention effect from sampling noise."
            ),
        },
    }
    if req.include_samples:
        payload["baseline"]["samples"] = baseline_result.samples
        payload["scenario"]["samples"] = scenario_result.samples
    return payload
