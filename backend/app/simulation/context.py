"""Builds the immutable planning/simulation context from persisted project data."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.calendar import WorkingCalendar
from app.models import (
    ECO,
    Component,
    Dependency,
    Inventory,
    Milestone,
    Project,
    PurchaseOrder,
    Resource,
    Risk,
    Supplier,
    Task,
    TaskComponent,
    TaskResource,
    ValidationTest,
)
from app.scheduling.model import (
    Edge,
    MaterialNeed,
    PlanningModel,
    ResourceNode,
    TaskNode,
)


@dataclass(frozen=True)
class SupplierSpec:
    id: str
    name: str
    category: str
    region: str
    reliability: float
    lead_time_days: float
    lead_time_cv: float
    disruption_prob: float
    disruption_delay_days: float
    cost_factor: float
    qualified: bool
    dual_source: bool


@dataclass(frozen=True)
class ComponentSpec:
    id: str
    name: str
    part_number: str
    supplier_id: str | None
    alternative_supplier_id: str | None
    unit_cost: float
    qty_per_unit: float
    lead_time_days: float
    inventory_days: float
    safety_stock_days: float
    criticality: float
    single_source: bool


@dataclass(frozen=True)
class TaskMaterial:
    component_id: str
    quantity: float


@dataclass(frozen=True)
class RiskSpec:
    id: str
    name: str
    category: str
    target_type: str
    target_id: str | None
    probability: float
    impact_days: float
    impact_cost: float
    distribution: str
    correlation_group: str | None


@dataclass(frozen=True)
class ValidationSpec:
    id: str
    name: str
    task_id: str | None
    test_type: str
    failure_probability: float
    retest_days: float
    correlation_group: str | None


@dataclass(frozen=True)
class EcoSpec:
    id: str
    code: str
    title: str
    probability: float
    rework_days: float
    impact_task_ids: tuple[str, ...]
    cost: float


@dataclass(frozen=True)
class MilestoneSpec:
    id: str
    name: str
    task_id: str | None
    due_offset: float | None
    due_date: str | None
    customer_commitment: bool
    weight: float


@dataclass
class SimulationContext:
    model: PlanningModel
    calendar: WorkingCalendar
    suppliers: dict[str, SupplierSpec]
    components: dict[str, ComponentSpec]
    task_materials: dict[str, tuple[TaskMaterial, ...]]
    risks: tuple[RiskSpec, ...]
    validations: tuple[ValidationSpec, ...]
    ecos: tuple[EcoSpec, ...]
    milestones: tuple[MilestoneSpec, ...]
    deadline_date: date | None
    delay_cost_per_day: float
    currency: str
    planned_volume: int
    unit_margin: float
    yield_start: float
    yield_target: float
    ramp_days: int
    assumptions: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    project_name: str = ""
    project_key: str = ""

    def copy(self, **changes) -> "SimulationContext":
        return replace(self, **changes)


def _iso(value) -> str | None:  # noqa: ANN001
    return value.isoformat() if value else None


def build_context(db: Session, project: Project) -> SimulationContext:
    tasks = list(db.scalars(select(Task).where(Task.project_id == project.id)))
    deps = list(db.scalars(select(Dependency).where(Dependency.project_id == project.id)))
    resources = list(db.scalars(select(Resource).where(Resource.project_id == project.id)))
    task_resources = list(
        db.scalars(
            select(TaskResource).where(
                TaskResource.task_id.in_([t.id for t in tasks] or [""])
            )
        )
    )
    suppliers = list(db.scalars(select(Supplier).where(Supplier.project_id == project.id)))
    components = list(db.scalars(select(Component).where(Component.project_id == project.id)))
    links = list(
        db.scalars(
            select(TaskComponent).where(
                TaskComponent.task_id.in_([t.id for t in tasks] or [""])
            )
        )
    )
    risks = list(db.scalars(select(Risk).where(Risk.project_id == project.id)))
    validations = list(
        db.scalars(select(ValidationTest).where(ValidationTest.project_id == project.id))
    )
    ecos = list(db.scalars(select(ECO).where(ECO.project_id == project.id)))
    milestones = list(db.scalars(select(Milestone).where(Milestone.project_id == project.id)))
    purchase_orders = list(
        db.scalars(select(PurchaseOrder).where(PurchaseOrder.project_id == project.id))
    )
    inventory = list(db.scalars(select(Inventory).where(Inventory.project_id == project.id)))

    calendar = WorkingCalendar.from_project(
        project.start_date, project.working_days_per_week, list(project.holidays or [])
    )

    supplier_map = {
        s.id: SupplierSpec(
            id=s.id, name=s.name, category=s.category, region=s.region,
            reliability=s.reliability, lead_time_days=s.lead_time_days,
            lead_time_cv=s.lead_time_cv, disruption_prob=s.disruption_prob,
            disruption_delay_days=s.disruption_delay_days, cost_factor=s.cost_factor,
            qualified=s.qualified, dual_source=s.dual_source,
        )
        for s in suppliers
    }
    component_map = {
        c.id: ComponentSpec(
            id=c.id, name=c.name, part_number=c.part_number, supplier_id=c.supplier_id,
            alternative_supplier_id=c.alternative_supplier_id, unit_cost=c.unit_cost,
            qty_per_unit=c.qty_per_unit, lead_time_days=c.lead_time_days,
            inventory_days=c.inventory_days, safety_stock_days=c.safety_stock_days,
            criticality=c.criticality, single_source=c.single_source,
        )
        for c in components
    }

    materials_by_task: dict[str, list[TaskMaterial]] = {t.id: [] for t in tasks}
    for link in links:
        if link.task_id in materials_by_task and link.component_id in component_map:
            materials_by_task[link.task_id].append(
                TaskMaterial(component_id=link.component_id, quantity=link.quantity)
            )

    po_by_component = {po.component_id: po for po in purchase_orders if po.status != "cancelled"}
    inv_by_component = {inv.component_id: inv for inv in inventory}

    task_nodes: list[TaskNode] = []
    material_ready: dict[str, float] = {}
    for task in sorted(tasks, key=lambda t: (t.sort_order, t.code or t.name)):
        needs = []
        for mat in materials_by_task.get(task.id, []):
            comp = component_map[mat.component_id]
            needs.append(
                MaterialNeed(
                    component_id=comp.id, name=comp.name, supplier_id=comp.supplier_id,
                    alternative_supplier_id=comp.alternative_supplier_id,
                    lead_time_days=comp.lead_time_days, inventory_days=comp.inventory_days,
                    safety_stock_days=comp.safety_stock_days, criticality=comp.criticality,
                    unit_cost=comp.unit_cost,
                )
            )
        # Deterministic material release: PO expected date, else lead time net of stock.
        ready = 0.0
        for mat in materials_by_task.get(task.id, []):
            comp = component_map[mat.component_id]
            po = po_by_component.get(comp.id)
            inv = inv_by_component.get(comp.id)
            if po is not None:
                base_ready = float(po.expected_offset)
            else:
                net = comp.lead_time_days - comp.inventory_days - comp.safety_stock_days
                base_ready = max(0.0, net)
            if inv is not None and inv.on_hand_qty > 0:
                base_ready = max(0.0, base_ready - 2.0)
            ready = max(ready, base_ready)
        if ready > 0:
            material_ready[task.id] = ready

        task_nodes.append(
            TaskNode(
                id=task.id,
                code=task.code or task.name[:12],
                name=task.name,
                phase=task.phase,
                duration=task.duration_days,
                distribution=task.distribution,
                duration_min=task.duration_min,
                duration_mode=task.duration_mode,
                duration_max=task.duration_max,
                std_dev=task.std_dev,
                buffer=task.buffer_days,
                cost=task.cost,
                is_gate=task.is_gate,
                is_milestone=task.is_milestone,
                optional=task.optional,
                risk_factor=task.risk_factor,
                fixed_start_offset=task.fixed_start_offset,
                resources=tuple(
                    (tr.resource_id, tr.demand)
                    for tr in task_resources
                    if tr.task_id == task.id and tr.demand > 0
                ),
                materials=tuple(needs),
            )
        )

    resource_nodes = [
        ResourceNode(
            id=r.id, name=r.name, type=r.type, capacity=r.capacity,
            availability=r.availability, cost_per_day=r.cost_per_day,
        )
        for r in resources
    ]

    milestone_specs = tuple(
        MilestoneSpec(
            id=m.id,
            name=m.name,
            task_id=m.task_id,
            due_offset=calendar.from_date(m.due_date) if m.due_date else None,
            due_date=_iso(m.due_date),
            customer_commitment=bool(m.customer_commitment),
            weight=m.weight,
        )
        for m in sorted(milestones, key=lambda m: (m.due_date or date.max, m.name))
    )

    deadline_offset = calendar.from_date(project.launch_deadline) if project.launch_deadline else None
    task_map = {t.id: t for t in task_nodes}
    milestone_targets = [
        {
            "task_id": m.task_id,
            "due_offset": m.due_offset,
            "due": m.due_date,
            "weight": m.weight,
            "name": m.name,
        }
        for m in milestone_specs
        if m.task_id in task_map and m.due_offset is not None
    ]

    model = PlanningModel(
        project_id=project.id,
        start_date=project.start_date,
        tasks=task_nodes,
        edges=[
            Edge(from_id=d.from_task_id, to_id=d.to_task_id, type=d.type, lag=d.lag_days)
            for d in deps
        ],
        resources=resource_nodes,
        material_ready=material_ready,
        deadline_offset=deadline_offset,
        delay_cost_per_day=project.delay_cost_per_day,
        milestone_targets=milestone_targets,
    )

    assumptions = [
        "Durations are expressed in working days on the project calendar; dates exclude holidays.",
        "Supplier lead times are stochastic in simulation and net of on-hand inventory and safety stock.",
        "Material release is assumed at project start plus net lead time (PO expected date when present).",
        "Resource capacity is cumulative; effective capacity = capacity x availability.",
        "Monte Carlo percentiles use linear interpolation between order statistics (NumPy method='linear').",
        "The Monte Carlo scheduler is a serial schedule-generation heuristic; its optimality gap vs CP-SAT is reported separately.",
        "Costs are USD-planning estimates, not audited financials.",
    ]
    if not purchase_orders:
        assumptions.append("No purchase orders exist, so material availability uses supplier lead time only.")

    return SimulationContext(
        model=model,
        calendar=calendar,
        suppliers=supplier_map,
        components=component_map,
        task_materials={k: tuple(v) for k, v in materials_by_task.items()},
        risks=tuple(
            RiskSpec(
                id=r.id, name=r.name, category=r.category, target_type=r.target_type,
                target_id=r.target_id, probability=r.probability, impact_days=r.impact_days,
                impact_cost=r.impact_cost, distribution=r.distribution,
                correlation_group=r.correlation_group,
            )
            for r in risks
            if r.is_active
        ),
        validations=tuple(
            ValidationSpec(
                id=v.id, name=v.name, task_id=v.task_id, test_type=v.test_type,
                failure_probability=v.failure_probability, retest_days=v.retest_days,
                correlation_group=v.correlation_group,
            )
            for v in validations
        ),
        ecos=tuple(
            EcoSpec(
                id=e.id, code=e.code, title=e.title, probability=e.probability,
                rework_days=e.rework_days, impact_task_ids=tuple(e.impact_task_ids or []),
                cost=e.cost,
            )
            for e in ecos
            if e.status in ("pending", "approved")
        ),
        milestones=milestone_specs,
        deadline_date=project.launch_deadline,
        delay_cost_per_day=project.delay_cost_per_day,
        currency=project.currency,
        planned_volume=project.planned_volume,
        unit_margin=project.unit_margin,
        yield_start=project.yield_start,
        yield_target=project.yield_target,
        ramp_days=project.ramp_days,
        assumptions=assumptions,
        project_name=project.name,
        project_key=project.key,
        provenance={
            "project_id": project.id,
            "task_count": len(task_nodes),
            "dependency_count": len(deps),
            "resource_count": len(resource_nodes),
            "supplier_count": len(supplier_map),
            "component_count": len(component_map),
            "risk_count": len(risks),
            "milestone_count": len(milestone_specs),
            "calendar": {
                "start_date": project.start_date.isoformat(),
                "working_days_per_week": project.working_days_per_week,
                "holidays": list(project.holidays or []),
            },
        },
    )
