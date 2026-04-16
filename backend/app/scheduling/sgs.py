"""Serial schedule generation scheme (SGS) used inside Monte Carlo trials.

SGS is an exact *feasibility* generator for precedence- and capacity-constrained
schedules: every produced schedule respects all logic and resource limits.  It
is a heuristic for *optimality* — its makespan is an upper bound on the CP-SAT
optimum.  The platform quantifies that gap on demand (``validate_with_cpsat``)
and in the research validation suite, rather than hiding it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core.calendar import WorkingCalendar
from app.scheduling.cpm import CpmResult, compute_cpm
from app.scheduling.model import PlanningModel


class CapacityInfeasible(ValueError):
    """Raised when a task demands more of a resource than exists."""


@dataclass
class SgsTaskResult:
    id: str
    start: float
    finish: float
    duration: float
    driver: str  # "start" | "precedence:<id>" | "resource:<id>"
    driver_task: str | None = None


@dataclass
class ScheduleResult:
    starts: dict[str, float]
    ends: dict[str, float]
    makespan: float
    feasible: bool = True
    critical_chain: list[str] = field(default_factory=list)
    drivers: dict[str, dict] = field(default_factory=dict)
    resource_intervals: dict[str, list[tuple[float, float, float]]] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)


def _peak_load(intervals: list[tuple[float, float, float]], start: float, end: float) -> float:
    events: list[tuple[float, float]] = []
    for s, e, d in intervals:
        if e <= start or s >= end:
            continue
        events.append((max(s, start), d))
        events.append((min(e, end), -d))
    if not events:
        return 0.0
    events.sort(key=lambda item: (item[0], item[1]))
    load = 0.0
    peak = 0.0
    for _, delta in events:
        load += delta
        peak = max(peak, load)
    return peak


def _earliest_feasible(
    intervals: list[tuple[float, float, float]],
    capacity: float,
    demand: float,
    est: float,
    duration: float,
) -> float:
    """Earliest start >= est with enough spare capacity for ``duration`` days."""
    if demand <= 0 or duration <= 0:
        return est
    if demand > capacity + 1e-9:
        raise CapacityInfeasible(f"demand {demand} exceeds capacity {capacity}")
    horizon = max([e for _, e, _ in intervals], default=est) + duration + 1.0
    t = est
    guard = 0
    while t <= horizon:
        guard += 1
        if guard > 100_000:  # pragma: no cover - defensive
            return t
        peak = _peak_load(intervals, t, t + duration)
        if peak + demand <= capacity + 1e-9:
            return t
        ends = [e for s, e, _ in intervals if s < t + duration and e > t]
        if not ends:
            return t
        nxt = min(ends)
        t = nxt if nxt > t else t + 0.25
    return t


def _priority_order(model: PlanningModel, cpm: CpmResult) -> list[str]:
    """Minimum-latest-finish-time rule, a strong SGS priority heuristic."""
    if not cpm.tasks:
        return [t.id for t in model.tasks]
    return [
        t.id
        for t in sorted(
            cpm.tasks.values(), key=lambda t: (t.latest_finish, -t.duration, t.earliest_start)
        )
    ]


def schedule_sgs(
    model: PlanningModel,
    durations: dict[str, float] | None = None,
    calendar: WorkingCalendar | None = None,
    cpm: CpmResult | None = None,
    priorities: list[str] | None = None,
    material_ready: dict[str, float] | None = None,
) -> ScheduleResult:
    tasks = model.task_map()
    durations = durations or {t.id: t.base_duration for t in model.tasks}
    calendar = calendar or WorkingCalendar(start_date=model.start_date)
    cpm = cpm or compute_cpm(model, calendar)
    if not cpm.validation.get("valid", False):
        return ScheduleResult(
            starts={}, ends={}, makespan=math.inf, feasible=False,
            conflicts=list(cpm.validation.get("errors", [])),
        )
    order = priorities or _priority_order(model, cpm)
    if not priorities:
        # Ensure the priority list still satisfies precedence (topological).
        topo_pos = {tid: i for i, tid in enumerate(cpm.validation["topological_order"])}
        order = sorted(order, key=lambda tid: topo_pos.get(tid, 10**9))

    resources = model.resource_map()
    preds = model.predecessors()
    busy: dict[str, list[tuple[float, float, float]]] = {r.id: [] for r in model.resources}

    starts: dict[str, float] = {}
    ends: dict[str, float] = {}
    drivers: dict[str, dict] = {}
    conflicts: list[str] = []

    for tid in order:
        task = tasks[tid]
        duration = max(0.0, float(durations.get(tid, task.base_duration)))
        est = 0.0
        if task.fixed_start_offset is not None:
            est = max(est, float(task.fixed_start_offset))
        ready_map = material_ready if material_ready is not None else model.material_ready
        material = ready_map.get(tid)
        if material is not None:
            est = max(est, float(material))

        driver_kind = "start"
        driver_task: str | None = None
        for edge in preds.get(tid, []):
            pred_id = edge.from_id
            if pred_id not in starts:
                continue
            if edge.type == "FS":
                bound = ends[pred_id] + edge.lag
            elif edge.type == "SS":
                bound = starts[pred_id] + edge.lag
            elif edge.type == "FF":
                bound = ends[pred_id] + edge.lag - duration
            else:  # SF
                bound = starts[pred_id] + edge.lag - duration
            if bound > est + 1e-9:
                est = bound
                driver_kind = "precedence"
                driver_task = pred_id

        precedence_est = est
        start = est
        resource_driver: str | None = None
        for _ in range(20):
            advanced = False
            for resource_id, demand in task.resources:
                resource = resources.get(resource_id)
                if resource is None:
                    conflicts.append(f"Task {task.code or task.id} references unknown resource {resource_id}")
                    continue
                try:
                    candidate = _earliest_feasible(
                        busy[resource_id], resource.effective_capacity, demand, start, duration
                    )
                except CapacityInfeasible as exc:
                    conflicts.append(f"Task {task.code or task.id}: {exc}")
                    candidate = start
                if candidate > start + 1e-9:
                    # Identify blocking task for the driving chain.
                    blocker = None
                    for s, e, _d in busy[resource_id]:
                        if s < candidate + duration and e > candidate - 1e-9:
                            if blocker is None or e < blocker[1]:
                                blocker = (s, e)
                    resource_driver = resource_id
                    if blocker is not None:
                        for other_id, other_end in ends.items():
                            if abs(other_end - blocker[1]) < 1e-9:
                                driver_task = other_id
                                break
                    driver_kind = "resource"
                    start = candidate
                    advanced = True
            if not advanced:
                break

        end = start + duration
        starts[tid] = start
        ends[tid] = end
        for resource_id, demand in task.resources:
            if resource_id in busy and demand > 0 and duration > 0:
                busy[resource_id].append((start, end, demand))
        drivers[tid] = {
            "kind": "resource" if start > precedence_est + 1e-9 else (driver_kind if start > 1e-9 else "start"),
            "precedence_est": round(precedence_est, 3),
            "driver_task": driver_task if start > 1e-9 else None,
            "resource_id": resource_driver,
        }

    makespan = max(ends.values()) if ends else 0.0

    # Realised driving chain: walk backwards from the last-finishing task.
    chain: list[str] = []
    if ends:
        current = max(ends, key=lambda k: (ends[k], -starts[k]))
        seen: set[str] = set()
        while current and current not in seen:
            chain.append(current)
            seen.add(current)
            info = drivers.get(current, {})
            nxt = info.get("driver_task")
            if not nxt or nxt in seen:
                break
            current = nxt
        chain.reverse()

    for resource_id in busy:
        busy[resource_id].sort()
    return ScheduleResult(
        starts=starts,
        ends=ends,
        makespan=makespan,
        feasible=not conflicts,
        critical_chain=chain,
        drivers=drivers,
        resource_intervals=busy,
        conflicts=conflicts,
    )


def resource_utilization(model: PlanningModel, schedule: ScheduleResult) -> dict[str, dict]:
    makespan = max(1e-9, schedule.makespan)
    out: dict[str, dict] = {}
    for resource in model.resources:
        intervals = schedule.resource_intervals.get(resource.id, [])
        capacity = max(1e-9, resource.effective_capacity)
        demand_days = sum((e - s) * d for s, e, d in intervals)
        idle_days = max(0.0, makespan * capacity - demand_days)
        out[resource.id] = {
            "resource_id": resource.id,
            "name": resource.name,
            "type": resource.type,
            "capacity": round(capacity, 3),
            "utilization": round(min(1.0, demand_days / (makespan * capacity)), 4),
            "demand_days": round(demand_days, 2),
            "available_days": round(makespan * capacity, 2),
            "idle_days": round(idle_days, 2),
            "cost": round(demand_days * resource.cost_per_day, 2),
            "task_count": len(intervals),
        }
    return out
