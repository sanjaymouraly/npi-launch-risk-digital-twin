"""In-memory planning model shared by the CPM, simulation and optimisation layers.

The database is the source of truth, but engines operate on these immutable
dataclasses so they can be unit-tested without a database or web server, and so
scenario interventions can be applied to a copy without touching the baseline.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

import networkx as nx

VALID_PRECEDENCE = {"FS", "SS", "FF", "SF"}


@dataclass(frozen=True)
class MaterialNeed:
    component_id: str
    name: str
    supplier_id: str | None
    alternative_supplier_id: str | None
    lead_time_days: float
    inventory_days: float
    safety_stock_days: float
    criticality: float
    unit_cost: float


@dataclass(frozen=True)
class TaskNode:
    id: str
    code: str
    name: str
    phase: str
    duration: float
    distribution: str = "fixed"
    duration_min: float | None = None
    duration_mode: float | None = None
    duration_max: float | None = None
    std_dev: float | None = None
    buffer: float = 0.0
    cost: float = 0.0
    is_gate: bool = False
    is_milestone: bool = False
    optional: bool = False
    risk_factor: float = 0.0
    fixed_start_offset: float | None = None
    resources: tuple[tuple[str, float], ...] = ()
    materials: tuple[MaterialNeed, ...] = ()

    @property
    def base_duration(self) -> float:
        return max(0.0, float(self.duration) + float(self.buffer))

    def with_changes(self, **changes) -> "TaskNode":
        return replace(self, **changes)


@dataclass(frozen=True)
class Edge:
    from_id: str
    to_id: str
    type: str = "FS"
    lag: float = 0.0


@dataclass(frozen=True)
class ResourceNode:
    id: str
    name: str
    type: str
    capacity: float
    availability: float
    cost_per_day: float = 0.0

    @property
    def effective_capacity(self) -> float:
        return max(0.0, self.capacity * self.availability)


@dataclass
class PlanningModel:
    project_id: str
    start_date: object  # datetime.date
    tasks: list[TaskNode]
    edges: list[Edge]
    resources: list[ResourceNode]
    material_ready: dict[str, float] = field(default_factory=dict)  # task_id -> working-day offset
    deadline_offset: int | None = None
    delay_cost_per_day: float = 25000.0
    milestone_targets: list[dict] = field(default_factory=list)

    def task_map(self) -> dict[str, TaskNode]:
        return {t.id: t for t in self.tasks}

    def resource_map(self) -> dict[str, ResourceNode]:
        return {r.id: r for r in self.resources}

    def predecessors(self) -> dict[str, list[Edge]]:
        out: dict[str, list[Edge]] = {t.id: [] for t in self.tasks}
        for e in self.edges:
            out.setdefault(e.to_id, []).append(e)
        return out

    def successors(self) -> dict[str, list[Edge]]:
        out: dict[str, list[Edge]] = {t.id: [] for t in self.tasks}
        for e in self.edges:
            out.setdefault(e.from_id, []).append(e)
        return out

    def copy(self, **changes) -> "PlanningModel":
        return replace(self, **changes)


@dataclass
class GraphValidation:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    topological_order: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "cycles": self.cycles,
            "topological_order": self.topological_order,
        }


def build_graph(tasks: Iterable[TaskNode], edges: Iterable[Edge]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for task in tasks:
        graph.add_node(task.id, name=task.name, duration=task.base_duration, phase=task.phase)
    for edge in edges:
        if edge.from_id in graph and edge.to_id in graph:
            graph.add_edge(
                edge.from_id, edge.to_id, type=edge.type, lag=edge.lag, weight=0.0
            )
    return graph


def validate_graph(tasks: list[TaskNode], edges: list[Edge]) -> GraphValidation:
    errors: list[str] = []
    warnings: list[str] = []
    ids = [t.id for t in tasks]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate task identifiers detected")
    id_set = set(ids)
    seen: set[tuple[str, str]] = set()
    for edge in edges:
        if edge.from_id not in id_set:
            errors.append(f"Dependency references unknown source task {edge.from_id}")
        if edge.to_id not in id_set:
            errors.append(f"Dependency references unknown target task {edge.to_id}")
        if edge.from_id == edge.to_id:
            errors.append(f"Self-dependency on task {edge.from_id}")
        if edge.type not in VALID_PRECEDENCE:
            errors.append(f"Invalid precedence type '{edge.type}'")
        pair = (edge.from_id, edge.to_id)
        if pair in seen:
            errors.append(f"Duplicate dependency {edge.from_id} -> {edge.to_id}")
        seen.add(pair)

    graph = build_graph(tasks, edges)
    cycles: list[list[str]] = []
    if not nx.is_directed_acyclic_graph(graph):
        cycles = [list(c) for c in nx.simple_cycles(graph)][:10]
        errors.append(f"Dependency cycle detected ({len(cycles)} shown)")
    if not tasks:
        warnings.append("Project has no tasks")

    order: list[str] = []
    if not cycles and tasks:
        order = list(nx.topological_sort(graph))

    # Tasks without any predecessor/successor are legitimate but worth surfacing.
    if tasks and not errors:
        isolated = [t.name for t in tasks if graph.degree(t.id) == 0 and len(tasks) > 1]
        if isolated:
            warnings.append(
                f"{len(isolated)} task(s) have no dependencies and can start immediately: "
                + ", ".join(isolated[:5])
            )
    return GraphValidation(
        valid=not errors, errors=errors, warnings=warnings, cycles=cycles,
        topological_order=order,
    )
