"""CPM, SGS and CP-SAT behaviour on hand-built models."""
from __future__ import annotations

from datetime import date

from app.core.calendar import WorkingCalendar
from app.scheduling.cpm import compute_cpm
from app.scheduling.cpsat import CpsatOptions, resource_constrained_schedule
from app.scheduling.model import Edge, PlanningModel, ResourceNode, TaskNode
from app.scheduling.sgs import schedule_sgs

START = date(2026, 1, 5)


def task(task_id: str, duration: float, **kwargs) -> TaskNode:
    return TaskNode(
        id=task_id,
        code=task_id.upper(),
        name=task_id,
        phase="Test",
        duration=duration,
        **kwargs,
    )


def model(tasks, edges=(), resources=(), **kwargs) -> PlanningModel:
    return PlanningModel(
        project_id="test",
        start_date=START,
        tasks=list(tasks),
        edges=list(edges),
        resources=list(resources),
        **kwargs,
    )


def test_fs_dependency_sequencing():
    m = model(
        [task("a", 3), task("b", 2)],
        [Edge("a", "b", "FS")],
    )
    cpm = compute_cpm(m, WorkingCalendar(start_date=START))
    assert cpm.project_duration == 5
    assert cpm.critical_path == ["a", "b"]


def test_ss_dependency_shares_start():
    m = model(
        [task("a", 5), task("b", 2)],
        [Edge("a", "b", "SS")],
    )
    cpm = compute_cpm(m, WorkingCalendar(start_date=START))
    assert cpm.tasks["b"].earliest_start == 0
    assert cpm.tasks["b"].earliest_finish == 2
    assert cpm.project_duration == 5


def test_ff_dependency_shares_finish():
    m = model(
        [task("a", 5), task("b", 2)],
        [Edge("a", "b", "FF")],
    )
    cpm = compute_cpm(m, WorkingCalendar(start_date=START))
    assert cpm.tasks["b"].earliest_finish == 5
    assert cpm.project_duration == 5


def test_sf_dependency_lag():
    """SF links the successor *finish* to the predecessor *start* (MS Project)."""
    m = model(
        [task("a", 5), task("b", 2)],
        [Edge("a", "b", "SF", 1.0)],
    )
    cpm = compute_cpm(m, WorkingCalendar(start_date=START))
    assert cpm.tasks["b"].earliest_finish == 2  # finish >= a.start + lag
    assert cpm.project_duration == 5


def test_cycle_is_detected():
    m = model(
        [task("a", 1), task("b", 1)],
        [Edge("a", "b"), Edge("b", "a")],
    )
    cpm = compute_cpm(m, WorkingCalendar(start_date=START))
    assert not cpm.validation["valid"]
    assert cpm.validation["cycles"]


def test_sgs_respects_capacity():
    m = model(
        [task("a", 4), task("b", 4)],
        [],
        [ResourceNode(id="r", name="Team", type="team", capacity=1.0, availability=1.0)],
    )
    for t in m.tasks:
        object.__setattr__(t, "resources", (("r", 1.0),))
    schedule = schedule_sgs(m, calendar=WorkingCalendar(start_date=START))
    assert schedule.feasible
    assert schedule.makespan == 8  # serialised on a single resource
    assert schedule.starts["a"] == 0
    assert schedule.starts["b"] == 4


def test_sgs_is_deterministic():
    m = model(
        [task("a", 4), task("b", 4)],
        [],
        [ResourceNode(id="r", name="Team", type="team", capacity=1.0, availability=1.0)],
    )
    for t in m.tasks:
        object.__setattr__(t, "resources", (("r", 1.0),))
    calendar = WorkingCalendar(start_date=START)
    first = schedule_sgs(m, calendar=calendar)
    second = schedule_sgs(m, calendar=calendar)
    assert first.starts == second.starts
    assert first.makespan == second.makespan


def test_cpsat_makespan_never_below_cpm():
    m = model(
        [task("a", 6), task("b", 6)],
        [],
        [ResourceNode(id="r", name="Team", type="team", capacity=1.0, availability=1.0)],
    )
    for t in m.tasks:
        object.__setattr__(t, "resources", (("r", 1.0),))
    calendar = WorkingCalendar(start_date=START)
    cpm = compute_cpm(m, calendar)
    result = resource_constrained_schedule(
        m, calendar, CpsatOptions(time_limit_seconds=10, workers=2)
    )
    assert result["feasible"]
    assert result["makespan"] >= cpm.project_duration
    assert result["makespan"] == 12


def test_cpsat_reports_infeasible_deadline():
    m = model(
        [task("a", 10), task("b", 10)],
        [],
        [ResourceNode(id="r", name="Team", type="team", capacity=1.0, availability=1.0)],
    )
    for t in m.tasks:
        object.__setattr__(t, "resources", (("r", 1.0),))
    m.deadline_offset = 5
    result = resource_constrained_schedule(
        m, WorkingCalendar(start_date=START), CpsatOptions(time_limit_seconds=10, workers=2)
    )
    assert result["status"] == "FEASIBLE_DEADLINE_MISSED"
    assert result["deadline"]["feasible"] is False
    assert result["deadline"]["conflicting_constraints"]
    assert result["makespan"] > 5  # relaxed optimum is reported, not a silent pass


def test_material_release_pushes_task_start():
    m = model([task("a", 2)], [], [])
    m.material_ready = {"a": 10.0}
    calendar = WorkingCalendar(start_date=START)
    schedule = schedule_sgs(m, calendar=calendar, material_ready={"a": 10.0})
    assert schedule.starts["a"] == 10.0
    assert schedule.makespan == 12.0


def test_availability_scales_effective_capacity():
    resource = ResourceNode(id="r", name="Team", type="team", capacity=2.0, availability=0.5)
    assert resource.effective_capacity == 1.0
