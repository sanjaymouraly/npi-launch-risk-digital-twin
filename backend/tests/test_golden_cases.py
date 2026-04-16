"""Golden-file cases for the scheduling engines.

The expectations in ``data/benchmarks/deterministic_cases.json`` are small enough
to be checked by hand, so they act as an independent check on the CPM, the SGS and
the CP-SAT implementations rather than on a previously recorded output of them.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from app.core.calendar import WorkingCalendar
from app.scheduling.cpm import compute_cpm
from app.scheduling.cpsat import CpsatOptions, resource_constrained_schedule
from app.scheduling.model import Edge, PlanningModel, ResourceNode, TaskNode
from app.scheduling.sgs import schedule_sgs

CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "data" / "benchmarks" / "deterministic_cases.json").read_text()
)["cases"]
START = date(2026, 1, 5)


def _build(case: dict) -> PlanningModel:
    uses_resource = bool(case.get("resources"))
    tasks = []
    for index, duration in enumerate(case["durations"]):
        tasks.append(
            TaskNode(
                id=f"t{index}",
                code=f"T{index}",
                name=f"Task {index}",
                phase="Test",
                duration=float(duration),
                resources=(("r", 1.0),) if uses_resource else (),
            )
        )
    edges = [
        Edge(f"t{a}", f"t{b}", "FS", 0.0) for a, b in case.get("dependencies", [])
    ]
    resources: list[ResourceNode] = []
    if case.get("resources"):
        resources.append(
            ResourceNode(id="r", name="Resource", type="team", capacity=1.0, availability=1.0)
        )
    return PlanningModel(
        project_id="golden",
        start_date=START,
        tasks=tasks,
        edges=edges,
        resources=resources,
    )


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_cpm_matches_the_hand_checked_makespan(case):
    model = _build(case)
    cpm = compute_cpm(model, WorkingCalendar(start_date=START))
    expected = case.get("expected_makespan", case.get("expected_makespan_unconstrained"))
    assert cpm.project_duration == pytest.approx(float(expected))


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_sgs_and_cpsat_match_the_hand_checked_makespan(case):
    model = _build(case)
    calendar = WorkingCalendar(start_date=START)
    cpm = compute_cpm(model, calendar)
    schedule = schedule_sgs(model, calendar=calendar, cpm=cpm)
    expected = case.get("expected_makespan", case.get("expected_makespan_unconstrained"))
    if case.get("resources") and "expected_makespan_constrained" in case:
        expected = case["expected_makespan_constrained"]
    assert schedule.makespan == pytest.approx(float(expected))

    result = resource_constrained_schedule(
        model, calendar, CpsatOptions(time_limit_seconds=10, workers=2, compute_float=False)
    )
    assert result["feasible"] is True
    assert result["makespan"] == pytest.approx(float(expected))
