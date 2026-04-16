"""Project CRUD, versioning, import/export and portfolio summaries."""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models import (
    ECO,
    ActualEvent,
    Component,
    Dependency,
    Inventory,
    Milestone,
    Project,
    PurchaseOrder,
    Quote,
    Resource,
    Risk,
    Scenario,
    SimulationRun,
    Supplier,
    Task,
    TaskComponent,
    TaskResource,
    ValidationTest,
)
from app.services import audit


def _as_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValidationError(f"Invalid date for {field}: {value!r} (expected YYYY-MM-DD)") from exc


def _num(value: Any, field: str, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid number for {field}: {value!r}") from exc



# Entity ids are derived deterministically from the program key and the
# entity reference.  Two consequences that matter:
#   * a program imported twice from the same JSON produces the same ids, and
#   * the Monte Carlo engine — whose random streams are keyed by entity id —
#     therefore reproduces the same forecast on a freshly rebuilt database.
DETERMINISTIC_NAMESPACE = uuid.UUID("1f0c9d2e-5f4b-5a1e-9c3d-6b7a8e9d0c1b")


def deterministic_id(project_key: str, kind: str, ref: str) -> str:
    return str(uuid.uuid5(DETERMINISTIC_NAMESPACE, f"{project_key}|{kind}|{ref}"))


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").upper()[:32]


def create_project(
    db: Session,
    payload: dict,
    *,
    actor: str = "system",
    is_demo: bool = False,
) -> Project:
    """Create a complete project graph from a normalized JSON payload.

    The operation is transactional: any validation error rolls back every row,
    so a failed import never leaves a half-built program.
    """
    if not isinstance(payload, dict):
        raise ValidationError("Payload must be a JSON object")
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValidationError("Project name is required")
    key = (payload.get("key") or _slug(name)).strip().upper()
    if not key:
        raise ValidationError("Project key could not be derived from the name")
    if db.scalar(select(Project).where(Project.key == key)):
        raise ConflictError(f"Project key '{key}' already exists")

    start = _as_date(payload.get("start_date"), "start_date") or date.today()
    deadline = _as_date(payload.get("launch_deadline"), "launch_deadline")
    if deadline and deadline < start:
        raise ValidationError("launch_deadline cannot be before start_date")
    baseline = _as_date(payload.get("baseline_launch_date"), "baseline_launch_date")

    project = Project(
        id=deterministic_id(key, "project", key),
        key=key,
        name=name,
        description=payload.get("description", ""),
        product=payload.get("product", ""),
        version=str(payload.get("version", "1.0")),
        status=payload.get("status", "active"),
        currency=payload.get("currency", "USD"),
        start_date=start,
        launch_deadline=deadline,
        baseline_launch_date=baseline,
        working_days_per_week=int(payload.get("working_days_per_week", 5)),
        holidays=list(payload.get("holidays", [])),
        timezone=payload.get("timezone", "UTC"),
        delay_cost_per_day=float(payload.get("delay_cost_per_day", 25000)),
        intervention_budget=float(payload.get("intervention_budget", 150000)),
        yield_start=float(payload.get("yield_start", 0.6)),
        yield_target=float(payload.get("yield_target", 0.95)),
        ramp_days=int(payload.get("ramp_days", 60)),
        unit_margin=float(payload.get("unit_margin", 150)),
        planned_volume=int(payload.get("planned_volume", 50000)),
        is_demo=is_demo,
        tags=list(payload.get("tags", [])),
        owner=payload.get("owner", "Program Office"),
    )
    if not 1 <= project.working_days_per_week <= 7:
        raise ValidationError("working_days_per_week must be between 1 and 7")
    db.add(project)
    db.flush()

    resource_refs: dict[str, Resource] = {}
    for i, row in enumerate(payload.get("resources", [])):
        ref = str(row.get("ref") or row.get("name") or f"R{i}")
        if ref in resource_refs:
            raise ValidationError(f"Duplicate resource ref '{ref}'")
        resource = Resource(
            id=deterministic_id(key, "resource", ref),
            project_id=project.id,
            name=row.get("name", ref),
            type=row.get("type", "team"),
            capacity=_num(row.get("capacity"), "resource.capacity", 1.0),
            availability=_num(row.get("availability"), "resource.availability", 1.0),
            cost_per_day=_num(row.get("cost_per_day"), "resource.cost_per_day", 0.0),
            overtime_available=bool(row.get("overtime_available", True)),
        )
        if resource.capacity <= 0:
            raise ValidationError(f"Resource '{resource.name}' capacity must be > 0")
        if not 0 < resource.availability <= 1:
            raise ValidationError(f"Resource '{resource.name}' availability must be in (0, 1]")
        db.add(resource)
        resource_refs[ref] = resource
    db.flush()

    supplier_refs: dict[str, Supplier] = {}
    for i, row in enumerate(payload.get("suppliers", [])):
        ref = str(row.get("ref") or row.get("name") or f"S{i}")
        if ref in supplier_refs:
            raise ValidationError(f"Duplicate supplier ref '{ref}'")
        supplier = Supplier(
            id=deterministic_id(key, "supplier", ref),
            project_id=project.id,
            name=row.get("name", ref),
            category=row.get("category", "electronics"),
            region=row.get("region", ""),
            reliability=min(1.0, max(0.0, _num(row.get("reliability"), "supplier.reliability", 0.9))),
            lead_time_days=max(0.0, _num(row.get("lead_time_days"), "supplier.lead_time_days", 30.0)),
            lead_time_cv=max(0.0, _num(row.get("lead_time_cv"), "supplier.lead_time_cv", 0.2)),
            disruption_prob=min(1.0, max(0.0, _num(row.get("disruption_prob"), "supplier.disruption_prob", 0.05))),
            disruption_delay_days=max(0.0, _num(row.get("disruption_delay_days"), "supplier.disruption_delay_days", 20.0)),
            cost_factor=max(0.01, _num(row.get("cost_factor"), "supplier.cost_factor", 1.0)),
            qualification_required=bool(row.get("qualification_required", False)),
            qualified=bool(row.get("qualified", True)),
            dual_source=bool(row.get("dual_source", False)),
            notes=row.get("notes", ""),
        )
        db.add(supplier)
        supplier_refs[ref] = supplier
    db.flush()

    component_refs: dict[str, Component] = {}
    for i, row in enumerate(payload.get("components", [])):
        ref = str(row.get("ref") or row.get("part_number") or f"C{i}")
        if ref in component_refs:
            raise ValidationError(f"Duplicate component ref '{ref}'")
        supplier = supplier_refs.get(str(row.get("supplier"))) if row.get("supplier") else None
        alt = supplier_refs.get(str(row.get("alternative_supplier"))) if row.get("alternative_supplier") else None
        if row.get("supplier") and supplier is None:
            raise ValidationError(f"Component '{ref}' references unknown supplier '{row.get('supplier')}'")
        component = Component(
            id=deterministic_id(key, "component", ref),
            project_id=project.id,
            name=row.get("name", ref),
            part_number=row.get("part_number", ref),
            supplier_id=supplier.id if supplier else None,
            alternative_supplier_id=alt.id if alt else None,
            unit_cost=_num(row.get("unit_cost"), "component.unit_cost", 10.0),
            qty_per_unit=_num(row.get("qty_per_unit"), "component.qty_per_unit", 1.0),
            lead_time_days=_num(row.get("lead_time_days"), "component.lead_time_days", 30.0),
            safety_stock_days=_num(row.get("safety_stock_days"), "component.safety_stock_days", 0.0),
            inventory_days=_num(row.get("inventory_days"), "component.inventory_days", 0.0),
            criticality=min(1.0, max(0.0, _num(row.get("criticality"), "component.criticality", 0.5))),
            single_source=bool(row.get("single_source", alt is None)),
        )
        db.add(component)
        component_refs[ref] = component
    db.flush()

    task_refs: dict[str, Task] = {}
    for i, row in enumerate(payload.get("tasks", [])):
        ref = str(row.get("ref") or row.get("code") or f"T{i}")
        if ref in task_refs:
            raise ValidationError(f"Duplicate task ref '{ref}'")
        code = str(row.get("code") or f"T{i + 1:02d}")
        duration = _num(row.get("duration_days"), f"task {code}.duration_days", 5.0)
        if duration is None or duration < 0:
            raise ValidationError(f"Task {code}: duration must be >= 0")
        distribution = (row.get("distribution") or "fixed").lower()
        task = Task(
            id=deterministic_id(key, "task", ref),
            project_id=project.id,
            code=code,
            name=row.get("name", code),
            phase=row.get("phase", "Design"),
            description=row.get("description", ""),
            wbs=row.get("wbs", ""),
            sort_order=int(row.get("sort_order", i)),
            duration_days=duration,
            distribution=distribution,
            duration_min=_num(row.get("duration_min"), f"task {code}.duration_min"),
            duration_mode=_num(row.get("duration_mode"), f"task {code}.duration_mode"),
            duration_max=_num(row.get("duration_max"), f"task {code}.duration_max"),
            std_dev=_num(row.get("std_dev"), f"task {code}.std_dev"),
            buffer_days=_num(row.get("buffer_days"), f"task {code}.buffer_days", 0.0),
            risk_factor=_num(row.get("risk_factor"), f"task {code}.risk_factor", 0.0),
            cost=_num(row.get("cost"), f"task {code}.cost", 0.0),
            is_gate=bool(row.get("is_gate", False)),
            optional=bool(row.get("optional", False)),
            is_milestone=bool(row.get("is_milestone", False)),
            fixed_start_offset=_num(row.get("fixed_start_offset"), f"task {code}.fixed_start_offset"),
        )
        if distribution not in {"fixed", "triangular", "pert", "normal", "lognormal", "uniform", "gamma", "weibull"}:
            raise ValidationError(f"Task {code}: unsupported distribution '{distribution}'")
        if distribution in ("triangular", "pert"):
            lo = task.duration_min if task.duration_min is not None else duration * 0.8
            mo = task.duration_mode if task.duration_mode is not None else duration
            hi = task.duration_max if task.duration_max is not None else duration * 1.25
            if not (0 <= lo <= mo <= hi) or hi <= lo:
                raise ValidationError(
                    f"Task {code}: require 0 <= duration_min <= duration_mode <= duration_max and min < max"
                )
        if distribution != "fixed" and duration <= 0:
            raise ValidationError(f"Task {code}: stochastic tasks need duration_days > 0")
        db.add(task)
        task_refs[ref] = task
    db.flush()

    for i, row in enumerate(payload.get("dependencies", [])):
        a = task_refs.get(str(row.get("from"))) or _task_by_ref(db, project.id, str(row.get("from")))
        b = task_refs.get(str(row.get("to"))) or _task_by_ref(db, project.id, str(row.get("to")))
        if a is None or b is None:
            raise ValidationError(
                f"Dependency {i + 1} references unknown task(s): {row.get('from')} -> {row.get('to')}"
            )
        if a.id == b.id:
            raise ValidationError(f"Dependency {a.code} -> {b.code} is a self-loop")
        typ = str(row.get("type", "FS")).upper()
        if typ not in {"FS", "SS", "FF", "SF"}:
            raise ValidationError(f"Dependency {a.code} -> {b.code}: invalid type '{typ}'")
        db.add(
            Dependency(
                id=deterministic_id(key, "dependency", f"{a.code}->{b.code}#{i}"),
                project_id=project.id, from_task_id=a.id, to_task_id=b.id, type=typ,
                lag_days=_num(row.get("lag_days"), "dependency.lag_days", 0.0),
                rationale=row.get("rationale", ""),
            )
        )
    db.flush()

    for i, row in enumerate(payload.get("tasks", [])):
        ref = str(row.get("ref") or row.get("code") or f"T{i}")
        task = task_refs.get(ref)
        if task is None:
            continue
        for resource_name, demand in (row.get("resources") or {}).items():
            resource = resource_refs.get(str(resource_name))
            if resource is None:
                raise ValidationError(f"Task {task.code} references unknown resource '{resource_name}'")
            db.add(TaskResource(task_id=task.id, resource_id=resource.id, demand=float(demand)))
        for component_name in row.get("materials") or []:
            component = component_refs.get(str(component_name))
            if component is None:
                raise ValidationError(f"Task {task.code} references unknown component '{component_name}'")
            db.add(TaskComponent(task_id=task.id, component_id=component.id, quantity=1.0))
    db.flush()

    for index, row in enumerate(payload.get("risks", [])):
        target_id = _resolve_target(db, project.id, row.get("target_type", "task"), row.get("target"),
                                    task_refs, supplier_refs, component_refs, resource_refs)
        db.add(
            Risk(
                id=deterministic_id(key, "risk", str(row.get("name") or row.get("code") or index)),
                project_id=project.id,
                name=row.get("name", "Unnamed risk"),
                category=row.get("category", "schedule"),
                target_type=row.get("target_type", "task"),
                target_id=target_id,
                probability=min(1.0, max(0.0, _num(row.get("probability"), "risk.probability", 0.1))),
                impact_days=max(0.0, _num(row.get("impact_days"), "risk.impact_days", 5.0)),
                impact_cost=max(0.0, _num(row.get("impact_cost"), "risk.impact_cost", 0.0)),
                distribution=row.get("distribution", "lognormal"),
                correlation_group=row.get("correlation_group"),
                owner=row.get("owner", ""),
                evidence=row.get("evidence", ""),
            )
        )
    for index, row in enumerate(payload.get("validation_tests", [])):
        task = task_refs.get(str(row.get("task")))
        db.add(
            ValidationTest(
                id=deterministic_id(key, "validation", str(row.get("name") or index)),
                project_id=project.id,
                task_id=task.id if task else None,
                name=row.get("name", "Validation test"),
                test_type=row.get("test_type", "DVT"),
                failure_probability=min(1.0, max(0.0, _num(row.get("failure_probability"), "test.failure_probability", 0.1))),
                retest_days=max(0.0, _num(row.get("retest_days"), "test.retest_days", 10.0)),
                is_gate=bool(row.get("is_gate", False)),
                correlation_group=row.get("correlation_group"),
            )
        )
    for index, row in enumerate(payload.get("ecos", [])):
        impacts = [
            task_refs[t].id for t in row.get("impact_tasks", []) if t in task_refs
        ]
        db.add(
            ECO(
                id=deterministic_id(key, "eco", str(row.get("code") or index)),
                project_id=project.id,
                code=row.get("code", "ECO"),
                title=row.get("title", "Engineering change"),
                description=row.get("description", ""),
                status=row.get("status", "pending"),
                probability=min(1.0, max(0.0, _num(row.get("probability"), "eco.probability", 0.0))),
                rework_days=max(0.0, _num(row.get("rework_days"), "eco.rework_days", 5.0)),
                impact_task_ids=impacts,
                cost=max(0.0, _num(row.get("cost"), "eco.cost", 0.0)),
            )
        )
    for index, row in enumerate(payload.get("milestones", [])):
        task = task_refs.get(str(row.get("task")))
        db.add(
            Milestone(
                id=deterministic_id(key, "milestone", str(row.get("name") or index)),
                project_id=project.id,
                name=row.get("name", "Milestone"),
                task_id=task.id if task else None,
                due_date=_as_date(row.get("due_date"), "milestone.due_date"),
                customer_commitment=bool(row.get("customer_commitment", False)),
                weight=_num(row.get("weight"), "milestone.weight", 1.0),
            )
        )
    for index, row in enumerate(payload.get("quotes", [])):
        supplier = supplier_refs.get(str(row.get("supplier")))
        component = component_refs.get(str(row.get("component")))
        if supplier and component:
            db.add(
                Quote(
                    id=deterministic_id(key, "quote", f"{row.get('supplier')}->{row.get('component')}#{index}"),
                    project_id=project.id, supplier_id=supplier.id, component_id=component.id,
                    unit_cost=_num(row.get("unit_cost"), "quote.unit_cost", 10.0),
                    lead_time_days=_num(row.get("lead_time_days"), "quote.lead_time_days", 30.0),
                    moq=int(_num(row.get("moq"), "quote.moq", 100)),
                    qualified=bool(row.get("qualified", True)),
                    notes=row.get("notes", ""),
                )
            )
    for index, row in enumerate(payload.get("purchase_orders", [])):
        supplier = supplier_refs.get(str(row.get("supplier")))
        component = component_refs.get(str(row.get("component")))
        if supplier and component:
            db.add(
                PurchaseOrder(
                    id=deterministic_id(key, "po", f"{row.get('supplier')}->{row.get('component')}#{index}"),
                    project_id=project.id, supplier_id=supplier.id, component_id=component.id,
                    quantity=_num(row.get("quantity"), "po.quantity", 100),
                    unit_cost=_num(row.get("unit_cost"), "po.unit_cost", 10.0),
                    ordered_offset=_num(row.get("ordered_offset"), "po.ordered_offset", 0.0),
                    expected_offset=_num(row.get("expected_offset"), "po.expected_offset", 0.0),
                    status=row.get("status", "open"),
                    expedite_cost=_num(row.get("expedite_cost"), "po.expedite_cost", 0.0),
                )
            )
    for index, row in enumerate(payload.get("inventory", [])):
        component = component_refs.get(str(row.get("component")))
        if component:
            db.add(
                Inventory(
                    id=deterministic_id(key, "inventory", str(row.get("component") or index)),
                    project_id=project.id, component_id=component.id,
                    on_hand_qty=_num(row.get("on_hand_qty"), "inventory.on_hand_qty", 0.0),
                    safety_stock_qty=_num(row.get("safety_stock_qty"), "inventory.safety_stock_qty", 0.0),
                    location=row.get("location", "DC-1"),
                )
            )
    for index, row in enumerate(payload.get("actual_events", [])):
        task = task_refs.get(str(row.get("task"))) if row.get("task") else None
        supplier = supplier_refs.get(str(row.get("supplier"))) if row.get("supplier") else None
        db.add(
            ActualEvent(
                id=deterministic_id(key, "event", str(row.get("event_type") or index)),
                project_id=project.id,
                task_id=task.id if task else None,
                supplier_id=supplier.id if supplier else None,
                event_type=row.get("event_type", "delay"),
                observed_delay_days=_num(row.get("observed_delay_days"), "actual.delay", 0.0),
                observed_cost=_num(row.get("observed_cost"), "actual.cost", 0.0),
                occurred_on=_as_date(row.get("occurred_on"), "actual.occurred_on"),
                evidence=row.get("evidence", ""),
                source=row.get("source", "ERP"),
            )
        )

    # Baseline scenario is created automatically.
    db.add(
        Scenario(
            project_id=project.id,
            name="Approved baseline",
            description="Baseline plan as imported. Simulations compare against this scenario.",
            is_baseline=True,
            status="approved",
        )
    )
    db.flush()
    audit.record(
        db, project_id=project.id, actor=actor, action="project.create",
        entity_type="project", entity_id=project.id,
        summary=f"Created project {project.key} with {len(task_refs)} tasks",
        payload={"key": project.key, "is_demo": is_demo},
    )
    db.commit()
    db.refresh(project)
    return project


def _task_by_ref(db: Session, project_id: str, ref: str) -> Task | None:
    return db.scalar(
        select(Task).where(Task.project_id == project_id, (Task.code == ref) | (Task.id == ref))
    )


def _resolve_target(db, project_id, target_type, target, task_refs, supplier_refs, component_refs, resource_refs):  # noqa: ANN001
    if not target:
        return None
    if target_type == "task":
        task = task_refs.get(str(target)) or _task_by_ref(db, project_id, str(target))
        return task.id if task else None
    if target_type == "supplier":
        supplier = supplier_refs.get(str(target))
        return supplier.id if supplier else None
    if target_type == "component":
        comp = component_refs.get(str(target))
        return comp.id if comp else None
    if target_type == "resource":
        res = resource_refs.get(str(target))
        return res.id if res else None
    return None


def export_project_payload(db: Session, project: Project) -> dict:
    tasks = list(db.scalars(select(Task).where(Task.project_id == project.id).order_by(Task.sort_order)))
    task_ids = [t.id for t in tasks]
    deps = list(db.scalars(select(Dependency).where(Dependency.project_id == project.id)))
    resources = list(db.scalars(select(Resource).where(Resource.project_id == project.id)))
    suppliers = list(db.scalars(select(Supplier).where(Supplier.project_id == project.id)))
    components = list(db.scalars(select(Component).where(Component.project_id == project.id)))
    links = list(db.scalars(select(TaskComponent).where(TaskComponent.task_id.in_(task_ids or [""]))))
    assignments = list(db.scalars(select(TaskResource).where(TaskResource.task_id.in_(task_ids or [""]))))
    task_code = {t.id: t.code for t in tasks}
    res_name = {r.id: r.name for r in resources}
    sup_name = {s.id: s.name for s in suppliers}
    comp_ref = {c.id: c.part_number for c in components}

    payload = {
        "key": project.key,
        "name": project.name,
        "description": project.description,
        "product": project.product,
        "version": project.version,
        "status": project.status,
        "currency": project.currency,
        "start_date": project.start_date.isoformat(),
        "launch_deadline": project.launch_deadline.isoformat() if project.launch_deadline else None,
        "baseline_launch_date": project.baseline_launch_date.isoformat() if project.baseline_launch_date else None,
        "working_days_per_week": project.working_days_per_week,
        "holidays": project.holidays,
        "timezone": project.timezone,
        "delay_cost_per_day": project.delay_cost_per_day,
        "intervention_budget": project.intervention_budget,
        "yield_start": project.yield_start,
        "yield_target": project.yield_target,
        "ramp_days": project.ramp_days,
        "unit_margin": project.unit_margin,
        "planned_volume": project.planned_volume,
        "owner": project.owner,
        "tags": project.tags,
        "resources": [
            {
                "ref": r.name, "name": r.name, "type": r.type, "capacity": r.capacity,
                "availability": r.availability, "cost_per_day": r.cost_per_day,
            }
            for r in resources
        ],
        "suppliers": [
            {
                "ref": s.name, "name": s.name, "category": s.category, "region": s.region,
                "reliability": s.reliability, "lead_time_days": s.lead_time_days,
                "lead_time_cv": s.lead_time_cv, "disruption_prob": s.disruption_prob,
                "disruption_delay_days": s.disruption_delay_days, "cost_factor": s.cost_factor,
                "qualification_required": s.qualification_required, "qualified": s.qualified,
                "dual_source": s.dual_source,
            }
            for s in suppliers
        ],
        "components": [
            {
                "ref": c.part_number, "name": c.name, "part_number": c.part_number,
                "supplier": sup_name.get(c.supplier_id), "alternative_supplier": sup_name.get(c.alternative_supplier_id),
                "unit_cost": c.unit_cost, "qty_per_unit": c.qty_per_unit, "lead_time_days": c.lead_time_days,
                "safety_stock_days": c.safety_stock_days, "inventory_days": c.inventory_days,
                "criticality": c.criticality, "single_source": c.single_source,
            }
            for c in components
        ],
        "tasks": [
            {
                "ref": t.code, "code": t.code, "name": t.name, "phase": t.phase,
                "duration_days": t.duration_days, "distribution": t.distribution,
                "duration_min": t.duration_min, "duration_mode": t.duration_mode,
                "duration_max": t.duration_max, "std_dev": t.std_dev,
                "buffer_days": t.buffer_days, "risk_factor": t.risk_factor, "cost": t.cost,
                "is_gate": t.is_gate, "optional": t.optional, "is_milestone": t.is_milestone,
                "fixed_start_offset": t.fixed_start_offset, "sort_order": t.sort_order,
                "resources": {
                    res_name[a.resource_id]: a.demand
                    for a in assignments if a.task_id == t.id and a.resource_id in res_name
                },
                "materials": [
                    comp_ref[m.component_id]
                    for m in links if m.task_id == t.id and m.component_id in comp_ref
                ],
            }
            for t in tasks
        ],
        "dependencies": [
            {
                "from": task_code.get(d.from_task_id), "to": task_code.get(d.to_task_id),
                "type": d.type, "lag_days": d.lag_days,
            }
            for d in deps
        ],
        "risks": [
            {
                "name": r.name, "category": r.category, "target_type": r.target_type,
                "target": (
                    task_code.get(r.target_id) if r.target_type == "task"
                    else sup_name.get(r.target_id) if r.target_type == "supplier"
                    else comp_ref.get(r.target_id) if r.target_type == "component"
                    else res_name.get(r.target_id) if r.target_type == "resource"
                    else r.target_id
                ),
                "probability": r.probability, "impact_days": r.impact_days,
                "impact_cost": r.impact_cost, "distribution": r.distribution,
                "correlation_group": r.correlation_group, "owner": r.owner, "evidence": r.evidence,
            }
            for r in db.scalars(select(Risk).where(Risk.project_id == project.id))
        ],
        "validation_tests": [
            {
                "task": task_code.get(v.task_id), "name": v.name, "test_type": v.test_type,
                "failure_probability": v.failure_probability, "retest_days": v.retest_days,
                "is_gate": v.is_gate, "correlation_group": v.correlation_group,
            }
            for v in db.scalars(select(ValidationTest).where(ValidationTest.project_id == project.id))
        ],
        "ecos": [
            {
                "code": e.code, "title": e.title, "status": e.status, "probability": e.probability,
                "rework_days": e.rework_days, "cost": e.cost,
                "impact_tasks": [task_code.get(t) for t in (e.impact_task_ids or []) if t in task_code],
                "description": e.description,
            }
            for e in db.scalars(select(ECO).where(ECO.project_id == project.id))
        ],
        "milestones": [
            {
                "name": m.name, "task": task_code.get(m.task_id),
                "due_date": m.due_date.isoformat() if m.due_date else None,
                "customer_commitment": m.customer_commitment, "weight": m.weight,
            }
            for m in db.scalars(select(Milestone).where(Milestone.project_id == project.id))
        ],
        "quotes": [
            {
                "supplier": sup_name.get(q.supplier_id), "component": comp_ref.get(q.component_id),
                "unit_cost": q.unit_cost, "lead_time_days": q.lead_time_days, "moq": q.moq,
                "qualified": q.qualified, "notes": q.notes,
            }
            for q in db.scalars(select(Quote).where(Quote.project_id == project.id))
        ],
        "purchase_orders": [
            {
                "supplier": sup_name.get(p.supplier_id), "component": comp_ref.get(p.component_id),
                "quantity": p.quantity, "unit_cost": p.unit_cost, "ordered_offset": p.ordered_offset,
                "expected_offset": p.expected_offset, "status": p.status, "expedite_cost": p.expedite_cost,
            }
            for p in db.scalars(select(PurchaseOrder).where(PurchaseOrder.project_id == project.id))
        ],
        "inventory": [
            {
                "component": comp_ref.get(i.component_id), "on_hand_qty": i.on_hand_qty,
                "safety_stock_qty": i.safety_stock_qty, "location": i.location,
            }
            for i in db.scalars(select(Inventory).where(Inventory.project_id == project.id))
        ],
        "actual_events": [
            {
                "task": task_code.get(a.task_id), "supplier": sup_name.get(a.supplier_id),
                "event_type": a.event_type, "observed_delay_days": a.observed_delay_days,
                "observed_cost": a.observed_cost, "occurred_on": a.occurred_on.isoformat() if a.occurred_on else None,
                "evidence": a.evidence, "source": a.source,
            }
            for a in db.scalars(select(ActualEvent).where(ActualEvent.project_id == project.id))
        ],
    }
    return payload


def list_projects(db: Session, include_archived: bool = False) -> list[dict]:
    query = select(Project).order_by(Project.created_at.desc())
    if not include_archived:
        query = query.where(Project.status != "archived")
    projects = list(db.scalars(query))
    out = []
    for p in projects:
        task_count = db.scalar(select(func.count(Task.id)).where(Task.project_id == p.id)) or 0
        latest = db.scalar(
            select(SimulationRun)
            .where(SimulationRun.project_id == p.id, SimulationRun.status == "completed")
            .order_by(SimulationRun.created_at.desc())
            .limit(1)
        )
        sim = None
        if latest and latest.summary:
            summary = latest.summary
            sim = {
                "id": latest.id,
                "created_at": latest.created_at.isoformat() if latest.created_at else None,
                "p50": summary.get("makespan", {}).get("p50"),
                "p90": summary.get("makespan", {}).get("p90"),
                "on_time_probability": summary.get("deadline", {}).get("on_time_probability"),
                "p90_date": summary.get("makespan", {}).get("p90_date"),
                "iterations": latest.iterations,
            }
        out.append(
            {
                "id": p.id,
                "key": p.key,
                "name": p.name,
                "product": p.product,
                "status": p.status,
                "owner": p.owner,
                "tags": p.tags,
                "start_date": p.start_date.isoformat(),
                "launch_deadline": p.launch_deadline.isoformat() if p.launch_deadline else None,
                "baseline_launch_date": p.baseline_launch_date.isoformat() if p.baseline_launch_date else None,
                "delay_cost_per_day": p.delay_cost_per_day,
                "intervention_budget": p.intervention_budget,
                "is_demo": p.is_demo,
                "task_count": task_count,
                "latest_simulation": sim,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
        )
    return out


def get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise NotFoundError(f"Project {project_id} not found")
    return project


def update_project(db: Session, project: Project, patch: dict, actor: str = "system") -> Project:
    allowed = {
        "name", "description", "product", "version", "status", "currency", "start_date",
        "launch_deadline", "baseline_launch_date", "working_days_per_week", "holidays",
        "timezone", "delay_cost_per_day", "intervention_budget", "yield_start", "yield_target",
        "ramp_days", "unit_margin", "planned_volume", "owner", "tags",
    }
    for field, value in patch.items():
        if field not in allowed:
            continue
        if field in ("start_date", "launch_deadline", "baseline_launch_date"):
            value = _as_date(value, field)
        setattr(project, field, value)
    if project.launch_deadline and project.launch_deadline < project.start_date:
        raise ValidationError("launch_deadline cannot be before start_date")
    audit.record(
        db, project_id=project.id, actor=actor, action="project.update",
        entity_type="project", entity_id=project.id,
        summary=f"Updated project fields: {', '.join(sorted(patch))}",
        payload={"fields": sorted(patch)},
    )
    db.commit()
    db.refresh(project)
    return project


def duplicate_project(db: Session, project: Project, actor: str = "system") -> Project:
    payload = export_project_payload(db, project)
    payload["name"] = f"{project.name} (copy)"
    base_key = _slug(payload["name"])
    suffix = 2
    key = base_key
    while db.scalar(select(Project).where(Project.key == key)):
        key = f"{base_key}-{suffix}"
        suffix += 1
    payload["key"] = key
    payload["status"] = "planned"
    return create_project(db, payload, actor=actor, is_demo=project.is_demo)


def archive_project(db: Session, project: Project, actor: str = "system") -> Project:
    project.status = "archived"
    project.archived_at = datetime.now(timezone.utc)
    audit.record(
        db, project_id=project.id, actor=actor, action="project.archive",
        entity_type="project", entity_id=project.id, summary=f"Archived {project.key}",
    )
    db.commit()
    return project


TASK_CSV_COLUMNS = [
    "code", "name", "phase", "duration_days", "distribution", "duration_min", "duration_mode",
    "duration_max", "std_dev", "cost", "is_gate", "optional", "resources", "predecessors", "materials",
]


def import_tasks_csv(db: Session, project: Project, text: str, actor: str = "system") -> dict:
    """Import/append tasks, dependencies and assignments from CSV with full rollback."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationError("CSV is empty or has no header row")
    missing = {"code", "name", "duration_days"} - set(reader.fieldnames)
    if missing:
        raise ValidationError(f"CSV missing required columns: {', '.join(sorted(missing))}")
    resources = {r.name: r for r in db.scalars(select(Resource).where(Resource.project_id == project.id))}
    components = {c.part_number: c for c in db.scalars(select(Component).where(Component.project_id == project.id))}
    existing = {t.code: t for t in db.scalars(select(Task).where(Task.project_id == project.id))}
    created = []
    errors: list[str] = []
    try:
        for line_no, row in enumerate(reader, start=2):
            code = (row.get("code") or "").strip()
            if not code:
                errors.append(f"Row {line_no}: code is required")
                continue
            if code in existing:
                errors.append(f"Row {line_no}: task code '{code}' already exists")
                continue
            try:
                duration = float(row["duration_days"] or 5)
            except ValueError:
                errors.append(f"Row {line_no}: duration_days must be numeric")
                continue
            task = Task(
                project_id=project.id,
                code=code,
                name=(row.get("name") or code).strip(),
                phase=(row.get("phase") or "Design").strip(),
                duration_days=duration,
                distribution=(row.get("distribution") or "fixed").strip().lower(),
                duration_min=float(row["duration_min"]) if row.get("duration_min") else None,
                duration_mode=float(row["duration_mode"]) if row.get("duration_mode") else None,
                duration_max=float(row["duration_max"]) if row.get("duration_max") else None,
                std_dev=float(row["std_dev"]) if row.get("std_dev") else None,
                cost=float(row.get("cost") or 0),
                is_gate=str(row.get("is_gate", "")).lower() in ("1", "true", "yes"),
                optional=str(row.get("optional", "")).lower() in ("1", "true", "yes"),
                sort_order=len(existing) + len(created),
            )
            if task.distribution not in {"fixed", "triangular", "pert", "normal", "lognormal", "uniform", "gamma", "weibull"}:
                errors.append(f"Row {line_no}: unsupported distribution '{task.distribution}'")
                continue
            db.add(task)
            db.flush()
            for token in (row.get("resources") or "").split(";"):
                if not token.strip():
                    continue
                try:
                    res_name, demand = token.split(":")
                except ValueError:
                    errors.append(f"Row {line_no}: resource '{token}' must use Name:Demand")
                    continue
                resource = resources.get(res_name.strip())
                if not resource:
                    errors.append(f"Row {line_no}: unknown resource '{res_name.strip()}'")
                    continue
                db.add(TaskResource(task_id=task.id, resource_id=resource.id, demand=float(demand)))
            for token in (row.get("materials") or "").split(";"):
                if not token.strip():
                    continue
                comp = components.get(token.strip())
                if not comp:
                    errors.append(f"Row {line_no}: unknown component part number '{token.strip()}'")
                    continue
                db.add(TaskComponent(task_id=task.id, component_id=comp.id, quantity=1.0))
            created.append((task, row.get("predecessors") or ""))
            existing[code] = task
        if errors:
            raise ValidationError("CSV import failed validation", details={"errors": errors[:50], "count": len(errors)})
        for task, preds in created:
            for token in preds.split(";"):
                if not token.strip():
                    continue
                match = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*(?::\s*([A-Z]{2})\s*([+-]\d+(?:\.\d+)?)?)?\s*$", token)
                if not match:
                    raise ValidationError(f"Invalid predecessor expression '{token}' for {task.code}")
                pred_code, typ, lag = match.groups()
                pred = existing.get(pred_code)
                if not pred:
                    raise ValidationError(f"Task {task.code} references unknown predecessor '{pred_code}'")
                db.add(
                    Dependency(
                        project_id=project.id, from_task_id=pred.id, to_task_id=task.id,
                        type=(typ or "FS").upper(), lag_days=float(lag or 0),
                    )
                )
        audit.record(
            db, project_id=project.id, actor=actor, action="project.import_csv",
            entity_type="project", entity_id=project.id,
            summary=f"Imported {len(created)} tasks from CSV",
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"created_tasks": len(created)}


def to_csv_template() -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=TASK_CSV_COLUMNS)
    writer.writeheader()
    writer.writerow(
        {
            "code": "REQ-01", "name": "Customer requirements", "phase": "Requirements",
            "duration_days": "10", "distribution": "triangular", "duration_min": "8",
            "duration_mode": "10", "duration_max": "14", "std_dev": "", "cost": "20000",
            "is_gate": "false", "optional": "false", "resources": "Systems Engineering:1",
            "predecessors": "", "materials": "",
        }
    )
    writer.writerow(
        {
            "code": "DES-01", "name": "System design", "phase": "Design",
            "duration_days": "15", "distribution": "uniform", "duration_min": "12",
            "duration_mode": "", "duration_max": "20", "std_dev": "", "cost": "30000",
            "is_gate": "true", "optional": "false", "resources": "Systems Engineering:1;Hardware & Firmware:0.5",
            "predecessors": "REQ-01:FS", "materials": "",
        }
    )
    return buffer.getvalue()
