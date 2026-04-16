"""Scenario interventions as *real* mutations of the planning model.

Every supported intervention changes precedence, duration, capacity, supplier,
material or risk inputs and therefore flows through the same CPM / CP-SAT /
Monte Carlo engines as the baseline.  No intervention has a hard-coded benefit.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from app.scheduling.model import PlanningModel, ResourceNode, TaskNode, validate_graph
from app.simulation.context import (
    ComponentSpec,
    EcoSpec,
    SimulationContext,
    SupplierSpec,
)

SUPPORTED_INTERVENTIONS = {
    "replace_supplier",
    "split_procurement",
    "expedite_supplier",
    "expedite_task",
    "add_capacity",
    "add_resource",
    "add_overtime",
    "parallelize",
    "increase_safety_stock",
    "reduce_scope",
    "move_qualification_date",
    "tooling_readiness",
    "delay_design_freeze",
    "introduce_eco",
}


@dataclass(frozen=True)
class InterventionSpec:
    id: str
    type: str
    label: str
    target_type: str = "task"
    target_id: str | None = None
    params: dict = field(default_factory=dict)
    cost: float = 0.0
    category: str = "schedule"
    exclusivity_group: str | None = None
    requires: tuple[str, ...] = ()
    expected_benefit_days: float | None = None
    expected_on_time_gain: float | None = None
    estimate_iterations: int = 0
    estimated: bool = True
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "params": self.params,
            "cost": round(self.cost, 2),
            "category": self.category,
            "exclusivity_group": self.exclusivity_group,
            "requires": list(self.requires),
            "expected_benefit_days": self.expected_benefit_days,
            "expected_on_time_gain": self.expected_on_time_gain,
            "estimate_iterations": self.estimate_iterations,
            "estimated": self.estimated,
            "notes": self.notes,
        }


def _recompute_material_ready(model: PlanningModel, components: dict[str, ComponentSpec]) -> dict[str, float]:
    ready: dict[str, float] = {}
    for task in model.tasks:
        if not task.materials:
            continue
        value = 0.0
        for need in task.materials:
            comp = components.get(need.component_id)
            if comp is None:
                continue
            net = comp.lead_time_days - comp.inventory_days - comp.safety_stock_days
            value = max(value, max(0.0, net))
        if value > 0:
            ready[task.id] = value
    return ready


def apply_interventions(
    context: SimulationContext, specs: list[InterventionSpec] | list[dict]
) -> tuple[SimulationContext, list[str]]:
    """Apply interventions to a copy of the context. Unknown/invalid changes are rejected, not guessed."""
    warnings: list[str] = []
    suppliers = dict(context.suppliers)
    components = dict(context.components)
    tasks = list(context.model.tasks)
    resources = list(context.model.resources)
    edges = list(context.model.edges)
    risks = list(context.risks)
    ecos = list(context.ecos)

    normalized: list[InterventionSpec] = []
    for spec in specs:
        normalized.append(spec if isinstance(spec, InterventionSpec) else InterventionSpec(**spec))

    for spec in normalized:
        kind = spec.type
        params = spec.params or {}
        if kind not in SUPPORTED_INTERVENTIONS:
            warnings.append(f"Unsupported intervention type '{kind}' ignored")
            continue

        if kind == "replace_supplier":
            component_id = params.get("component_id") or spec.target_id
            new_supplier_id = params.get("supplier_id")
            comp = components.get(component_id or "")
            supplier = suppliers.get(new_supplier_id or "")
            if not comp or not supplier:
                warnings.append(f"replace_supplier: unknown component/supplier for {spec.id}")
                continue
            if not supplier.qualified:
                warnings.append(f"replace_supplier: {supplier.name} is not qualified; intervention rejected")
                continue
            components[comp.id] = replace(
                comp,
                supplier_id=supplier.id,
                single_source=False,
                lead_time_days=supplier.lead_time_days,
            )

        elif kind == "split_procurement":
            component_id = params.get("component_id") or spec.target_id
            comp = components.get(component_id or "")
            if not comp or not comp.supplier_id or comp.supplier_id not in suppliers:
                warnings.append(f"split_procurement: component {component_id} has no primary supplier")
                continue
            primary = suppliers[comp.supplier_id]
            clone_id = f"{primary.id}::split"
            clone = replace(
                primary,
                id=clone_id,
                name=f"{primary.name} (dual-source)",
                disruption_prob=primary.disruption_prob * 0.45,
                lead_time_days=primary.lead_time_days * 0.9,
                dual_source=True,
            )
            suppliers[clone_id] = clone
            components[comp.id] = replace(
                comp,
                supplier_id=clone_id,
                alternative_supplier_id=primary.id,
                single_source=False,
                lead_time_days=clone.lead_time_days,
            )

        elif kind == "expedite_supplier":
            supplier_id = params.get("supplier_id") or spec.target_id
            pct = float(params.get("reduction_pct", 0.2))
            supplier = suppliers.get(supplier_id or "")
            if not supplier:
                warnings.append(f"expedite_supplier: unknown supplier {supplier_id}")
                continue
            suppliers[supplier_id] = replace(
                supplier, lead_time_days=max(1.0, supplier.lead_time_days * (1 - pct))
            )
            for cid, comp in list(components.items()):
                if comp.supplier_id == supplier_id:
                    components[cid] = replace(
                        comp, lead_time_days=max(1.0, comp.lead_time_days * (1 - pct))
                    )

        elif kind in ("expedite_task", "tooling_readiness", "delay_design_freeze", "reduce_scope"):
            task_id = params.get("task_id") or spec.target_id
            index = next((i for i, t in enumerate(tasks) if t.id == task_id), None)
            if index is None:
                warnings.append(f"{kind}: unknown task {task_id}")
                continue
            task = tasks[index]
            if kind == "delay_design_freeze":
                days = float(params.get("days", 5))
                tasks[index] = task.with_changes(duration=task.duration + days)
            else:
                pct = float(
                    params.get(
                        "reduction_pct",
                        0.35 if kind == "tooling_readiness" else (0.5 if kind == "reduce_scope" else 0.2),
                    )
                )
                new_duration = max(0.5, task.duration * (1 - pct))
                ratio = new_duration / task.duration if task.duration > 0 else 1.0
                tasks[index] = replace(
                    task,
                    duration=new_duration,
                    duration_min=task.duration_min * ratio if task.duration_min is not None else None,
                    duration_mode=task.duration_mode * ratio if task.duration_mode is not None else None,
                    duration_max=task.duration_max * ratio if task.duration_max is not None else None,
                )

        elif kind in ("add_capacity", "add_resource", "add_overtime"):
            resource_id = params.get("resource_id") or spec.target_id
            index = next((i for i, r in enumerate(resources) if r.id == resource_id), None)
            if index is None:
                warnings.append(f"{kind}: unknown resource {resource_id}")
                continue
            resource = resources[index]
            if kind == "add_overtime":
                delta = float(params.get("availability_delta", 0.15))
                resources[index] = replace(
                    resource, availability=min(1.0, resource.availability + delta)
                )
            else:
                delta = float(params.get("capacity_delta", 0.5))
                resources[index] = replace(resource, capacity=resource.capacity + delta)

        elif kind == "parallelize":
            from_id = params.get("from_task_id")
            to_id = params.get("to_task_id")
            if not from_id or not to_id:
                warnings.append(f"parallelize: missing dependency endpoints for {spec.id}")
                continue
            remaining = [e for e in edges if not (e.from_id == from_id and e.to_id == to_id)]
            if len(remaining) == len(edges):
                warnings.append(f"parallelize: dependency {from_id}->{to_id} not found")
                continue
            trial_edges = remaining
            validation = validate_graph(tasks, trial_edges)
            if not validation.valid:
                warnings.append(f"parallelize: removing {from_id}->{to_id} creates a cycle; rejected")
                continue
            edges = trial_edges

        elif kind == "increase_safety_stock":
            component_id = params.get("component_id") or spec.target_id
            comp = components.get(component_id or "")
            if not comp:
                warnings.append(f"increase_safety_stock: unknown component {component_id}")
                continue
            days = float(params.get("days", 5))
            components[comp.id] = replace(comp, safety_stock_days=comp.safety_stock_days + days)

        elif kind == "move_qualification_date":
            task_id = params.get("task_id") or spec.target_id
            index = next((i for i, t in enumerate(tasks) if t.id == task_id), None)
            if index is None:
                warnings.append(f"move_qualification_date: unknown task {task_id}")
                continue
            days = float(params.get("days", -5))
            current = tasks[index].fixed_start_offset or 0.0
            tasks[index] = tasks[index].with_changes(fixed_start_offset=max(0.0, current + days))

        elif kind == "introduce_eco":
            task_ids = tuple(params.get("task_ids", []))
            if not task_ids:
                warnings.append("introduce_eco: no affected tasks supplied")
                continue
            ecos.append(
                EcoSpec(
                    id=f"eco-{spec.id}",
                    code=str(params.get("code", "ECO-SCN")),
                    title=spec.label,
                    probability=float(params.get("probability", 1.0)),
                    rework_days=float(params.get("rework_days", 8)),
                    impact_task_ids=task_ids,
                    cost=float(params.get("cost", spec.cost)),
                )
            )

    # Keep the per-task material requirements in sync with any component or
    # supplier change.  Without this, re-sourcing a supplier would not move the
    # material release dates or the disruption exposure used by the Monte
    # Carlo engine, and the intervention would silently be a no-op.
    if components != context.components:
        synced_tasks: list[TaskNode] = []
        for task in tasks:
            needs: list = []
            changed = False
            for need in task.materials:
                comp = components.get(need.component_id)
                if comp is None:
                    needs.append(need)
                    continue
                if comp.supplier_id != need.supplier_id or comp.lead_time_days != need.lead_time_days:
                    changed = True
                needs.append(
                    replace(
                        need,
                        supplier_id=comp.supplier_id,
                        alternative_supplier_id=comp.alternative_supplier_id,
                        lead_time_days=comp.lead_time_days,
                        inventory_days=comp.inventory_days,
                        safety_stock_days=comp.safety_stock_days,
                    )
                )
            synced_tasks.append(replace(task, materials=tuple(needs)) if changed else task)
        tasks = synced_tasks

    model = PlanningModel(
        project_id=context.model.project_id,
        start_date=context.model.start_date,
        tasks=tasks,
        edges=edges,
        resources=resources,
        material_ready=_recompute_material_ready(context.model.copy(tasks=tasks), components),
        deadline_offset=context.model.deadline_offset,
        delay_cost_per_day=context.model.delay_cost_per_day,
        milestone_targets=context.model.milestone_targets,
    )
    return (
        context.copy(
            model=model,
            suppliers=suppliers,
            components=components,
            risks=tuple(risks),
            ecos=tuple(e for e in ecos if e is not None),
            task_materials=context.task_materials,
        ),
        warnings,
    )


def intervention_cost_estimate(
    kind: str,
    task: TaskNode | None = None,
    resource: ResourceNode | None = None,
    component: ComponentSpec | None = None,
    supplier: SupplierSpec | None = None,
    planned_volume: int = 50000,
) -> float:
    """Transparent cost model for each intervention family.

    These are planning estimates, documented in README/assumptions.  They are
    derived from project data (task cost, resource day-rate, component spend)
    rather than invented per scenario.
    """
    if kind == "expedite_task" and task is not None:
        daily = max(task.cost / max(task.duration, 1.0), 500.0)
        return round(daily * max(1.0, task.duration * 0.2) * 1.4, 2)
    if kind in ("tooling_readiness",) and task is not None:
        daily = max(task.cost / max(task.duration, 1.0), 800.0)
        return round(daily * max(1.0, task.duration * 0.35) * 1.6, 2)
    if kind == "add_capacity" and resource is not None:
        return round(resource.cost_per_day * 25 * 0.5, 2)
    if kind == "add_resource" and resource is not None:
        return round(max(8000.0, resource.cost_per_day * 20), 2)
    if kind == "add_overtime" and resource is not None:
        return round(max(3000.0, resource.cost_per_day * 8), 2)
    if kind == "replace_supplier" and component is not None and supplier is not None:
        batch = max(100.0, planned_volume * 0.05)
        premium = max(0.0, supplier.cost_factor - 1.0)
        return round(batch * component.unit_cost * (0.08 + premium * 0.5), 2)
    if kind == "split_procurement" and component is not None:
        batch = max(100.0, planned_volume * 0.05)
        return round(batch * component.unit_cost * 0.06 + 6000.0, 2)
    if kind == "expedite_supplier" and component is not None:
        return round(component.unit_cost * component.qty_per_unit * 800 * 0.12 + 4000.0, 2)
    if kind == "increase_safety_stock" and component is not None:
        return round(component.unit_cost * component.qty_per_unit * 30 * 0.02 + 1500.0, 2)
    if kind == "parallelize":
        return 9000.0
    if kind == "reduce_scope":
        return -7500.0
    return 5000.0
