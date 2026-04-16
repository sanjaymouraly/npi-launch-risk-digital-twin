"""Scheduling and validation services."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Project
from app.scheduling.cpm import compute_cpm
from app.scheduling.cpsat import CpsatOptions, resource_constrained_schedule
from app.scheduling.model import validate_graph
from app.scheduling.sgs import resource_utilization, schedule_sgs
from app.simulation.context import build_context


def validate_project(db: Session, project: Project) -> dict:
    context = build_context(db, project)
    graph = validate_graph(context.model.tasks, context.model.edges)
    errors = list(graph.errors)
    warnings = list(graph.warnings)
    capacity_errors = []
    capacity_warnings = []
    for task in context.model.tasks:
        for resource_id, demand in task.resources:
            resource = context.model.resource_map().get(resource_id)
            if resource is None:
                capacity_errors.append(f"{task.code}: unknown resource {resource_id}")
                continue
            if demand <= 0:
                capacity_warnings.append(f"{task.code}: zero demand on {resource.name} ignored")
            elif demand > resource.effective_capacity + 1e-9:
                capacity_errors.append(
                    f"{task.code} demands {demand:g} of {resource.name} but effective capacity is "
                    f"{resource.effective_capacity:g} (capacity {resource.capacity:g} × availability {resource.availability:g})"
                )
    dist_errors: list[str] = []
    from app.simulation.distributions import InvalidDistribution, make_params

    for task in context.model.tasks:
        try:
            make_params(
                task.distribution,
                task.duration,
                task.duration_min,
                task.duration_mode,
                task.duration_max,
                task.std_dev,
            )
        except InvalidDistribution as exc:
            dist_errors.append(f"{task.code} ({task.name}): {exc}")

    if context.deadline_date is None:
        warnings.append("No launch deadline configured; on-time probability cannot be computed.")
    for milestone in context.milestones:
        if milestone.task_id is None:
            warnings.append(f"Milestone '{milestone.name}' is not linked to a task and will be ignored in forecasting.")
        elif milestone.due_offset is not None and context.model.deadline_offset is not None:
            if milestone.due_offset > context.model.deadline_offset:
                warnings.append(
                    f"Milestone '{milestone.name}' is due after the launch deadline."
                )
    for task_id, ready in context.model.material_ready.items():
        task = context.model.task_map().get(task_id)
        if task and context.model.deadline_offset and ready > context.model.deadline_offset:
            warnings.append(
                f"Material for {task.code} is released after the launch deadline ({ready:.0f} working days)."
            )
    cpm = compute_cpm(context.model, context.calendar)
    if cpm.deadline_margin_days is not None and cpm.deadline_margin_days < 0:
        warnings.append(
            f"Unconstrained critical path already misses the deadline by {abs(cpm.deadline_margin_days):.1f} working days."
        )
    return {
        "valid": not errors and not capacity_errors and not dist_errors,
        "errors": errors + capacity_errors + dist_errors,
        "warnings": warnings + capacity_warnings,
        "graph": graph.to_dict(),
        "calendar": {
            "start_date": project.start_date.isoformat(),
            "working_days_per_week": project.working_days_per_week,
            "holidays": list(project.holidays or []),
        },
        "counts": {
            "tasks": len(context.model.tasks),
            "dependencies": len(context.model.edges),
            "resources": len(context.model.resources),
            "milestones": len(context.milestones),
        },
        "cpm": {
            "project_duration": cpm.project_duration,
            "finish_date": cpm.finish_date,
            "meets_deadline": cpm.meets_deadline,
            "deadline_margin_days": cpm.deadline_margin_days,
        },
    }


def project_schedule(
    db: Session,
    project: Project,
    *,
    mode: str = "both",
    time_limit: float = 15.0,
    objective: str = "min_makespan",
) -> dict:
    context = build_context(db, project)
    cpm = compute_cpm(context.model, context.calendar)
    validation = validate_graph(context.model.tasks, context.model.edges)
    payload: dict = {
        "project_id": project.id,
        "project_key": project.key,
        "project_name": project.name,
        "mode": mode,
        "calendar": {
            "start_date": project.start_date.isoformat(),
            "working_days_per_week": project.working_days_per_week,
            "holidays": list(project.holidays or []),
            "timezone": project.timezone,
        },
        "deadline": project.launch_deadline.isoformat() if project.launch_deadline else None,
        "deadline_offset": context.model.deadline_offset,
        "validation": validation.to_dict(),
        "cpm": _cpm_payload(cpm),
        "assumptions": {
            "dates": "Working-day offsets converted exactly through the project calendar; holidays excluded.",
            "cpm": "Unconstrained by resources: logic only.",
            "cpsat": "Resource-constrained cumulative scheduling with material release dates.",
            "duration_rounding": "Solver durations rounded to whole working days.",
            "capacity": "Effective capacity = capacity × availability.",
        },
    }
    if not validation.valid:
        payload["constrained"] = {
            "status": "INVALID_GRAPH",
            "feasible": False,
            "conflicts": validation.errors,
        }
        return payload

    sgs = schedule_sgs(context.model, calendar=context.calendar, cpm=cpm)
    utilization = resource_utilization(context.model, sgs)
    payload["deterministic_heuristic"] = {
        "scheduler": "serial SGS",
        "makespan": round(sgs.makespan, 2),
        "finish_date": context.calendar.to_date(max(0.0, sgs.makespan - 1)).isoformat(),
        "critical_chain": [
            context.model.task_map()[tid].code for tid in sgs.critical_chain if tid in context.model.task_map()
        ],
    }
    payload["bottlenecks"] = sorted(
        utilization.values(), key=lambda u: (-u["utilization"], -u["demand_days"])
    )

    if mode in ("cpsat", "both"):
        options = CpsatOptions(
            time_limit_seconds=max(1.0, time_limit),
            objective=objective,
            respect_deadline=True,
            compute_float=True,
            milestone_targets=context.model.milestone_targets,
        )
        constrained = resource_constrained_schedule(context.model, context.calendar, options)
        payload["constrained"] = constrained
        if constrained.get("feasible"):
            payload["comparison"] = {
                "unconstrained_days": round(cpm.project_duration, 2),
                "unconstrained_finish": cpm.finish_date,
                "constrained_days": constrained.get("makespan"),
                "constrained_finish": constrained.get("project_finish_date"),
                "capacity_delay_days": constrained.get("capacity_delay_days"),
                "deadline_feasible": (constrained.get("deadline") or {}).get("feasible"),
                "headline": (
                    f"Logic needs {cpm.project_duration:.0f} working days; capacity and materials need "
                    f"{constrained.get('makespan')} working days "
                    f"(+{constrained.get('capacity_delay_days')} days)."
                ),
            }
    return payload


def supplier_exposure(db: Session, project: Project) -> dict:
    context = build_context(db, project)
    task_by_component: dict[str, list[str]] = {}
    for task_id, materials in context.task_materials.items():
        task = context.model.task_map().get(task_id)
        for material in materials:
            task_by_component.setdefault(material.component_id, []).append(task.code if task else task_id)
    components = []
    for component in context.components.values():
        supplier = context.suppliers.get(component.supplier_id or "")
        alternative = context.suppliers.get(component.alternative_supplier_id or "")
        net_ready = max(0.0, component.lead_time_days - component.inventory_days - component.safety_stock_days)
        risk = (supplier.disruption_prob if supplier else 0.0) * component.criticality
        if component.single_source:
            risk *= 1.35
        components.append(
            {
                "id": component.id,
                "name": component.name,
                "part_number": component.part_number,
                "supplier": supplier.name if supplier else None,
                "supplier_id": supplier.id if supplier else None,
                "region": supplier.region if supplier else None,
                "alternative_supplier": alternative.name if alternative else None,
                "alternative_qualified": bool(alternative.qualified) if alternative else False,
                "lead_time_days": component.lead_time_days,
                "inventory_days": component.inventory_days,
                "safety_stock_days": component.safety_stock_days,
                "net_ready_days": round(net_ready, 1),
                "unit_cost": component.unit_cost,
                "qty_per_unit": component.qty_per_unit,
                "criticality": component.criticality,
                "single_source": component.single_source,
                "disruption_probability": supplier.disruption_prob if supplier else 0.0,
                "expected_delay_days": round(
                    (supplier.disruption_prob * supplier.disruption_delay_days) if supplier else 0.0, 2
                ),
                "exposure_score": round(min(1.0, risk), 3),
                "used_by_tasks": sorted(set(task_by_component.get(component.id, []))),
                "monthly_spend": round(component.unit_cost * component.qty_per_unit * 2000, 0),
            }
        )
    components.sort(key=lambda c: -c["exposure_score"])
    suppliers = []
    for supplier in context.suppliers.values():
        comps = [c for c in components if c["supplier_id"] == supplier.id]
        suppliers.append(
            {
                "id": supplier.id,
                "name": supplier.name,
                "category": supplier.category,
                "region": supplier.region,
                "reliability": supplier.reliability,
                "lead_time_days": supplier.lead_time_days,
                "lead_time_cv": supplier.lead_time_cv,
                "disruption_probability": supplier.disruption_prob,
                "disruption_delay_days": supplier.disruption_delay_days,
                "qualified": supplier.qualified,
                "component_count": len(comps),
                "single_source_count": sum(1 for c in comps if c["single_source"]),
                "exposure_score": round(
                    max([c["exposure_score"] for c in comps], default=0.0), 3
                ),
                "expected_delay_days": round(
                    supplier.disruption_prob * supplier.disruption_delay_days, 2
                ),
            }
        )
    suppliers.sort(key=lambda s: -s["exposure_score"])
    return {
        "components": components,
        "suppliers": suppliers,
        "single_source_components": [c for c in components if c["single_source"]],
        "no_qualified_alternate": [
            c for c in components if not c["alternative_qualified"] and c["criticality"] >= 0.6
        ],
    }


def _cpm_payload(cpm) -> dict:  # noqa: ANN001
    return {
        "project_duration": cpm.project_duration,
        "finish_date": cpm.finish_date,
        "deadline_offset": cpm.deadline_offset,
        "deadline_margin_days": cpm.deadline_margin_days,
        "meets_deadline": cpm.meets_deadline,
        "critical_path": [
            cpm.tasks[tid].code if tid in cpm.tasks else tid for tid in cpm.critical_path
        ],
        "critical_task_ids": cpm.critical_task_ids,
        "validation": cpm.validation,
        "tasks": [
            {
                **{
                    key: value
                    for key, value in task.__dict__.items()
                }
            }
            for task in sorted(cpm.tasks.values(), key=lambda t: t.earliest_start)
        ],
    }
