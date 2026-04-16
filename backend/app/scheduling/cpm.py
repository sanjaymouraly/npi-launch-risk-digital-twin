"""Unconstrained critical-path method with four precedence types and exact calendars.

This is the *unconstrained* reference schedule: it respects logical dependencies
but intentionally ignores resource capacity.  The resource-constrained schedule
is produced separately by :mod:`app.scheduling.cpsat`, and the two are reported
side by side so a meeting audience can see where capacity (not logic) drives
the launch date.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from app.core.calendar import WorkingCalendar
from app.scheduling.model import Edge, PlanningModel, TaskNode, build_graph, validate_graph

TOL = 1e-6


@dataclass
class CpmTask:
    id: str
    code: str
    name: str
    phase: str
    duration: float
    earliest_start: float
    earliest_finish: float
    latest_start: float
    latest_finish: float
    total_float: float
    is_critical: bool
    start_date: str
    finish_date: str
    late_start_date: str
    late_finish_date: str
    is_gate: bool = False


@dataclass
class CpmResult:
    project_duration: float
    tasks: dict[str, CpmTask] = field(default_factory=dict)
    critical_path: list[str] = field(default_factory=list)
    critical_task_ids: list[str] = field(default_factory=list)
    finish_date: str = ""
    deadline_offset: float | None = None
    deadline_margin_days: float | None = None
    meets_deadline: bool | None = None
    validation: dict = field(default_factory=dict)


def _dependency_bounds(
    task: TaskNode,
    predecessor: TaskNode,
    edge: Edge,
    pred_es: float,
    pred_ef: float,
    duration: float,
) -> float:
    """Earliest start implied by one incoming precedence edge."""
    if edge.type == "FS":
        return pred_ef + edge.lag
    if edge.type == "SS":
        return pred_es + edge.lag
    if edge.type == "FF":
        return pred_ef + edge.lag - duration
    if edge.type == "SF":
        return pred_es + edge.lag - duration
    raise ValueError(f"Unsupported precedence type {edge.type}")


def compute_cpm(model: PlanningModel, calendar: WorkingCalendar | None = None) -> CpmResult:
    calendar = calendar or WorkingCalendar(start_date=model.start_date)
    validation = validate_graph(model.tasks, model.edges)
    if not validation.valid or not model.tasks:
        return CpmResult(
            project_duration=0.0,
            validation={**validation.to_dict(), "skipped": True},
            deadline_offset=float(model.deadline_offset) if model.deadline_offset is not None else None,
        )

    tasks = model.task_map()
    durations = {t.id: t.base_duration for t in model.tasks}
    preds = model.predecessors()
    succs = model.successors()
    order = validation.topological_order

    es: dict[str, float] = {}
    ef: dict[str, float] = {}
    for tid in order:
        task = tasks[tid]
        lower = 0.0
        if task.fixed_start_offset is not None:
            lower = max(lower, float(task.fixed_start_offset))
        for edge in preds.get(tid, []):
            pred = tasks[edge.from_id]
            lower = max(
                lower,
                _dependency_bounds(
                    task, pred, edge, es[edge.from_id], ef[edge.from_id], durations[tid]
                ),
            )
        es[tid] = max(0.0, lower)
        ef[tid] = es[tid] + durations[tid]

    project_duration = max(ef.values()) if ef else 0.0

    ls: dict[str, float] = {}
    lf: dict[str, float] = {}
    for tid in reversed(order):
        task = tasks[tid]
        dur = durations[tid]
        upper = project_duration
        for edge in succs.get(tid, []):
            succ = edge.to_id
            if edge.type == "FS":
                upper = min(upper, ls[succ] - edge.lag)
            elif edge.type == "SS":
                upper = min(upper, ls[succ] - edge.lag + dur)
            elif edge.type == "FF":
                upper = min(upper, lf[succ] - edge.lag)
            elif edge.type == "SF":
                upper = min(upper, lf[succ] - edge.lag + dur)
        lf[tid] = upper
        ls[tid] = upper - dur

    result_tasks: dict[str, CpmTask] = {}
    for tid in order:
        task = tasks[tid]
        slack = ls[tid] - es[tid]
        start_date, finish_date = calendar.duration_to_dates(es[tid], durations[tid])
        late_start, late_finish = calendar.duration_to_dates(max(0.0, ls[tid]), durations[tid])
        result_tasks[tid] = CpmTask(
            id=tid,
            code=task.code,
            name=task.name,
            phase=task.phase,
            duration=durations[tid],
            earliest_start=round(es[tid], 4),
            earliest_finish=round(ef[tid], 4),
            latest_start=round(ls[tid], 4),
            latest_finish=round(lf[tid], 4),
            total_float=round(slack, 4),
            is_critical=abs(slack) <= TOL,
            start_date=start_date.isoformat(),
            finish_date=finish_date.isoformat(),
            late_start_date=late_start.isoformat(),
            late_finish_date=late_finish.isoformat(),
            is_gate=task.is_gate,
        )

    graph = build_graph(model.tasks, model.edges)
    for u, v in graph.edges:
        graph.edges[u, v]["weight"] = durations.get(v, 0.0)
    try:
        longest = list(nx.dag_longest_path(graph, weight="weight"))
    except Exception:  # pragma: no cover - guarded by validation
        longest = []
    if not longest and order:
        longest = [max(order, key=lambda t: ef[t])]

    finish_date = calendar.to_date(max(0.0, project_duration - 1))
    deadline_offset = float(model.deadline_offset) if model.deadline_offset is not None else None
    return CpmResult(
        project_duration=round(project_duration, 4),
        tasks=result_tasks,
        critical_path=longest,
        critical_task_ids=[t for t in order if result_tasks[t].is_critical],
        finish_date=finish_date.isoformat(),
        deadline_offset=deadline_offset,
        deadline_margin_days=round(deadline_offset - project_duration, 2)
        if deadline_offset is not None
        else None,
        meets_deadline=(project_duration <= deadline_offset + TOL)
        if deadline_offset is not None
        else None,
        validation=validation.to_dict(),
    )
