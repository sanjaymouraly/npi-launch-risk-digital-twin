"""Resource-constrained scheduling with Google OR-Tools CP-SAT.

The model enforces, simultaneously:
  * all four precedence types with working-day lags,
  * cumulative resource capacities (fractional capacities supported via x10 ints),
  * material release dates derived from supplier lead times and inventory,
  * fixed-date constraints and the customer launch deadline.

It reports the *unconstrained* CPM baseline alongside the constrained optimum so
the capacity-driven delay is explicit.  When a deadline makes the model
infeasible, CP-SAT's assumption core is used to explain which constraints
conflict instead of returning a generic error.
"""
from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field

from ortools.sat.python import cp_model

from app.core.calendar import WorkingCalendar
from app.scheduling.cpm import compute_cpm
from app.scheduling.model import PlanningModel
from app.scheduling.sgs import resource_utilization, schedule_sgs

SCALE = 10


@dataclass
class CpsatOptions:
    time_limit_seconds: float = 20.0
    workers: int = 8
    seed: int = 0
    objective: str = "min_makespan"  # min_makespan | min_tardiness
    respect_deadline: bool = True
    compute_float: bool = True
    milestone_targets: list[dict] = field(default_factory=list)  # {task_id, due_offset, weight}
    label: str = "resource-constrained"


def _task_duration(task) -> int:  # noqa: ANN001
    raw = float(task.base_duration)
    if raw <= 0:
        return 0
    return max(1, int(round(raw)))


def resource_constrained_schedule(
    model: PlanningModel,
    calendar: WorkingCalendar | None = None,
    options: CpsatOptions | None = None,
) -> dict:
    options = options or CpsatOptions()
    calendar = calendar or WorkingCalendar(start_date=model.start_date)
    cpm = compute_cpm(model, calendar)
    if not cpm.validation.get("valid", False) or not model.tasks:
        return {
            "status": "INVALID_GRAPH",
            "feasible": False,
            "conflicts": cpm.validation.get("errors", []),
            "validation": cpm.validation,
            "cpm": _cpm_payload(cpm),
        }

    resources = model.resource_map()
    durations = {t.id: _task_duration(t) for t in model.tasks}
    total_duration = sum(durations.values())
    max_material = max(model.material_ready.values(), default=0)
    horizon = int(total_duration + max_material + sum(abs(e.lag) for e in model.edges) + 60)
    horizon = max(horizon, int(cpm.project_duration) + 60, int(model.deadline_offset or 0) + 60)

    # Validate capacity before solving; clearer than a generic infeasible status.
    capacity_conflicts = []
    for task in model.tasks:
        for resource_id, demand in task.resources:
            resource = resources.get(resource_id)
            if resource is None:
                capacity_conflicts.append(f"Unknown resource {resource_id} on {task.code}")
            elif demand > resource.effective_capacity + 1e-9:
                capacity_conflicts.append(
                    f"{task.code} needs {demand:g} of {resource.name} but only "
                    f"{resource.effective_capacity:g} is available"
                )
    if capacity_conflicts:
        return {
            "status": "INFEASIBLE_CAPACITY",
            "feasible": False,
            "conflicts": capacity_conflicts,
            "cpm": _cpm_payload(cpm),
            "diagnostics": {
                "hint": "Increase capacity/availability, reduce demand, or split the task.",
                "resource_shortfalls": capacity_conflicts,
            },
        }

    cp = cp_model.CpModel()
    starts: dict[str, cp_model.IntVar] = {}
    ends: dict[str, cp_model.IntVar] = {}
    intervals: dict[str, cp_model.IntervalVar] = {}

    for task in model.tasks:
        dur = durations[task.id]
        start = cp.NewIntVar(0, horizon, f"s_{task.id}")
        end = cp.NewIntVar(0, horizon, f"e_{task.id}")
        cp.Add(end == start + dur)
        if dur > 0:
            intervals[task.id] = cp.NewIntervalVar(start, dur, end, f"i_{task.id}")
        starts[task.id] = start
        ends[task.id] = end
        if task.fixed_start_offset is not None:
            cp.Add(start >= int(math.ceil(task.fixed_start_offset)))
        material = model.material_ready.get(task.id)
        if material is not None and material > 0:
            cp.Add(start >= int(math.ceil(material)))

    for edge in model.edges:
        lag = int(round(edge.lag))
        a, b = edge.from_id, edge.to_id
        if a not in starts or b not in starts:
            continue
        if edge.type == "FS":
            cp.Add(starts[b] >= ends[a] + lag)
        elif edge.type == "SS":
            cp.Add(starts[b] >= starts[a] + lag)
        elif edge.type == "FF":
            cp.Add(ends[b] >= ends[a] + lag)
        elif edge.type == "SF":
            cp.Add(ends[b] >= starts[a] + lag)

    by_resource: dict[str, list[tuple[cp_model.IntervalVar, int]]] = {}
    for task in model.tasks:
        for resource_id, demand in task.resources:
            interval = intervals.get(task.id)
            if interval is None:
                continue
            scaled = max(1, int(round(demand * SCALE)))
            by_resource.setdefault(resource_id, []).append((interval, scaled))

    for resource in model.resources:
        entries = by_resource.get(resource.id)
        if not entries:
            continue
        capacity = max(1, int(round(resource.effective_capacity * SCALE)))
        cp.AddCumulative([iv for iv, _ in entries], [d for _, d in entries], capacity)

    makespan = cp.NewIntVar(0, horizon, "makespan")
    for task in model.tasks:
        cp.Add(makespan >= ends[task.id])

    on_time = cp.NewBoolVar("on_time")
    deadline = model.deadline_offset
    if deadline is not None and options.respect_deadline:
        cp.Add(makespan <= int(round(deadline))).OnlyEnforceIf(on_time)
        cp.Add(makespan >= int(round(deadline)) + 1).OnlyEnforceIf(on_time.Not())
        cp.AddAssumption(on_time)

    tardiness_terms = []
    for target in options.milestone_targets:
        task_id = target.get("task_id")
        due = target.get("due_offset")
        if task_id in ends and due is not None:
            weight = max(1, int(round(float(target.get("weight", 1.0)) * 10)))
            late = cp.NewIntVar(0, horizon, f"late_{task_id}")
            cp.Add(late >= ends[task_id] - int(round(due)))
            tardiness_terms.append(weight * late)

    if options.objective == "min_tardiness" and tardiness_terms:
        cp.Minimize(sum(tardiness_terms) * 1000 + makespan)
    else:
        cp.Minimize(makespan)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(1.0, options.time_limit_seconds)
    solver.parameters.num_search_workers = max(1, options.workers)
    solver.parameters.random_seed = options.seed
    started = time.perf_counter()
    status = solver.Solve(cp)
    elapsed = time.perf_counter() - started

    status_name = solver.StatusName(status)
    conflicts: list[str] = []
    deadline_report: dict | None = None

    if status == cp_model.INFEASIBLE and deadline is not None:
        core = list(solver.SufficientAssumptionsForInfeasibility())
        conflicting = [f"Customer deadline of {int(round(deadline))} working days" for _ in core[:1]]
        deadline_report = {
            "feasible": False,
            "requested_deadline_offset": float(deadline),
            "conflicting_constraints": conflicting or ["deadline vs. precedence/capacity"],
            "core_size": len(core),
            "explanation": (
                "The deadline cannot be met under the current precedence, capacity, and "
                "material constraints. The schedule below is the relaxed optimum."
            ),
        }
        conflicts.extend(deadline_report["conflicting_constraints"])
        # Relax the deadline and solve for a usable schedule.
        relaxed_options = CpsatOptions(**{**asdict(options), "respect_deadline": False})
        relaxed_result = resource_constrained_schedule(model, calendar, relaxed_options)
        relaxed_result["deadline"] = deadline_report
        relaxed_result["cpm"] = _cpm_payload(cpm)
        relaxed_result["status"] = "FEASIBLE_DEADLINE_MISSED"
        relaxed_result["feasible"] = True
        relaxed_result["relaxed"] = True
        relaxed_result["solver_stats"]["wall_time_seconds"] = round(
            elapsed + relaxed_result["solver_stats"]["wall_time_seconds"], 3
        )
        return relaxed_result

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "status": status_name,
            "feasible": False,
            "conflicts": conflicts or ["No feasible schedule found for the current constraints."],
            "cpm": _cpm_payload(cpm),
            "diagnostics": {
                "hint": "Check resource capacity, material release dates and dependency lags.",
                "conflict_count": len(conflicts),
            },
            "solver_stats": {"wall_time_seconds": round(elapsed, 3), "status": status_name},
        }

    start_vals = {tid: solver.Value(var) for tid, var in starts.items()}
    end_vals = {tid: solver.Value(var) for tid, var in ends.items()}
    makespan_val = int(solver.Value(makespan))
    objective_val = solver.ObjectiveValue() if status == cp_model.OPTIMAL else None

    # As-late-as-possible solve to derive resource-constrained float.
    latest: dict[str, int] = {}
    float_status = "SKIPPED"
    if options.compute_float and options.time_limit_seconds >= 1.0:
        cp2 = cp_model.CpModel()
        s2: dict[str, cp_model.IntVar] = {}
        e2: dict[str, cp_model.IntVar] = {}
        iv2: dict[str, cp_model.IntervalVar] = {}
        for task in model.tasks:
            dur = durations[task.id]
            s = cp2.NewIntVar(0, horizon, f"ls_{task.id}")
            e = cp2.NewIntVar(0, horizon, f"le_{task.id}")
            cp2.Add(e == s + dur)
            if dur > 0:
                iv2[task.id] = cp2.NewIntervalVar(s, dur, e, f"li_{task.id}")
            s2[task.id] = s
            e2[task.id] = e
            cp2.Add(s >= start_vals[task.id])  # do not start earlier than ASAP plan
            if task.fixed_start_offset is not None:
                cp2.Add(s >= int(math.ceil(task.fixed_start_offset)))
            material = model.material_ready.get(task.id)
            if material is not None and material > 0:
                cp2.Add(s >= int(math.ceil(material)))
        for edge in model.edges:
            lag = int(round(edge.lag))
            a, b = edge.from_id, edge.to_id
            if a not in s2 or b not in s2:
                continue
            if edge.type == "FS":
                cp2.Add(s2[b] >= e2[a] + lag)
            elif edge.type == "SS":
                cp2.Add(s2[b] >= s2[a] + lag)
            elif edge.type == "FF":
                cp2.Add(e2[b] >= e2[a] + lag)
            elif edge.type == "SF":
                cp2.Add(e2[b] >= s2[a] + lag)
        by_res2: dict[str, list[tuple[cp_model.IntervalVar, int]]] = {}
        for task in model.tasks:
            for resource_id, demand in task.resources:
                if task.id in iv2:
                    by_res2.setdefault(resource_id, []).append(
                        (iv2[task.id], max(1, int(round(demand * SCALE))))
                    )
        for resource in model.resources:
            entries = by_res2.get(resource.id)
            if entries:
                cp2.AddCumulative(
                    [iv for iv, _ in entries], [d for _, d in entries],
                    max(1, int(round(resource.effective_capacity * SCALE))),
                )
        for task in model.tasks:
            cp2.Add(e2[task.id] <= makespan_val)
        cp2.Maximize(sum(s2.values()))
        solver2 = cp_model.CpSolver()
        solver2.parameters.max_time_in_seconds = min(8.0, max(2.0, options.time_limit_seconds / 2))
        solver2.parameters.num_search_workers = max(1, options.workers)
        solver2.parameters.random_seed = options.seed
        status2 = solver2.Solve(cp2)
        float_status = solver2.StatusName(status2)
        if status2 in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            latest = {tid: solver2.Value(var) for tid, var in s2.items()}

    task_payload = []
    critical: list[str] = []
    for task in model.tasks:
        tid = task.id
        start = start_vals[tid]
        end = end_vals[tid]
        start_date, finish_date = calendar.duration_to_dates(start, durations[tid])
        latest_start = latest.get(tid)
        float_days = (latest_start - start) if latest_start is not None else None
        is_critical = float_days is not None and float_days <= 0
        if is_critical:
            critical.append(tid)
        task_payload.append(
            {
                "id": tid,
                "code": task.code,
                "name": task.name,
                "phase": task.phase,
                "duration": durations[tid],
                "start": start,
                "finish": end,
                "start_date": start_date.isoformat(),
                "finish_date": finish_date.isoformat(),
                "total_float": float_days,
                "is_critical": is_critical,
                "is_gate": task.is_gate,
                "resources": [
                    {"id": rid, "demand": demand, "name": resources[rid].name}
                    for rid, demand in task.resources
                    if rid in resources
                ],
            }
        )

    sgs = schedule_sgs(model, {t.id: float(durations[t.id]) for t in model.tasks}, calendar, cpm)
    utilization = resource_utilization(model, sgs)
    bottlenecks = sorted(
        utilization.values(), key=lambda u: (-u["utilization"], -u["demand_days"])
    )[:4]

    makespan_cpm = cpm.project_duration
    finish_date = calendar.to_date(max(0, makespan_val - 1))
    infeasible_optional = _milestone_deadline_check(model, start_vals, end_vals, calendar)

    return {
        "status": status_name,
        "feasible": True,
        "objective": options.objective,
        "makespan": makespan_val,
        "makespan_days": makespan_val,
        "project_finish_date": finish_date.isoformat(),
        "cpm_makespan": makespan_cpm,
        "capacity_delay_days": round(makespan_val - makespan_cpm, 2),
        "tasks": task_payload,
        "starts": start_vals,
        "ends": end_vals,
        "critical_task_ids": critical,
        "critical_path": [
            t["id"] for t in sorted(task_payload, key=lambda t: t["start"]) if t["is_critical"]
        ],
        "resource_utilization": utilization,
        "bottlenecks": bottlenecks,
        "milestone_checks": infeasible_optional,
        "deadline": deadline_report
        or (
            {
                "feasible": True,
                "requested_deadline_offset": float(deadline),
                "slack_days": round(float(deadline) - makespan_val, 2),
            }
            if deadline is not None
            else None
        ),
        "conflicts": conflicts,
        "cpm": _cpm_payload(cpm),
        "solver_stats": {
            "status": status_name,
            "wall_time_seconds": round(elapsed, 3),
            "objective_value": objective_val,
            "num_branches": solver.NumBranches(),
            "num_conflicts": solver.NumConflicts(),
            "float_status": float_status,
            "optimal": status == cp_model.OPTIMAL,
            "engine": "ortools-cp-sat",
        },
        "assumptions": {
            "calendar": f"{calendar.working_days_per_week}-day working week, holidays excluded",
            "duration_rounding": "durations rounded to whole working days for the solver",
            "float_method": "as-late-as-possible re-solve holding makespan at the optimum",
            "capacity": "cumulative, effective capacity = capacity x availability",
        },
    }


def _milestone_deadline_check(model, starts, ends, calendar) -> list[dict]:  # noqa: ANN001
    out = []
    task_map = model.task_map()
    for target in getattr(model, "milestone_targets", []) or []:
        tid = target.get("task_id")
        due = target.get("due")
        if tid in ends and due is not None:
            finish = calendar.to_date(max(0, ends[tid] - 1)).isoformat()
            out.append(
                {
                    "task_id": tid,
                    "name": task_map.get(tid).name if tid in task_map else tid,
                    "due_date": str(due),
                    "forecast_finish": finish,
                    "on_time": finish <= str(due),
                }
            )
    return out


def _cpm_payload(cpm) -> dict:  # noqa: ANN001
    return {
        "project_duration": cpm.project_duration,
        "finish_date": cpm.finish_date,
        "critical_path": cpm.critical_path,
        "critical_task_ids": cpm.critical_task_ids,
        "deadline_margin_days": cpm.deadline_margin_days,
        "meets_deadline": cpm.meets_deadline,
        "tasks": {tid: asdict(t) for tid, t in cpm.tasks.items()},
        "validation": cpm.validation,
    }
