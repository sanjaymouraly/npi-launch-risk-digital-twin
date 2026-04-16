"""Monte Carlo engine behaviour: reproducibility, uncertainty and feasibility."""
from __future__ import annotations

import numpy as np
import pytest
from app.simulation.attribution import paired_delta
from app.simulation.context import build_context
from app.simulation.engine import SimulationOptions, run_monte_carlo
from hypothesis import given, settings
from hypothesis import strategies as st


@pytest.fixture()
def context(db, project_id):
    from app.models import Project

    project = db.get(Project, project_id)
    return build_context(db, project)


def test_same_seed_reproduces_the_run(context):
    options = SimulationOptions(seed=1234, iterations=400)
    first = run_monte_carlo(context, options)
    second = run_monte_carlo(context, SimulationOptions(seed=1234, iterations=400))
    assert first.samples == second.samples
    assert first.summary["makespan"]["p50"] == second.summary["makespan"]["p50"]


def test_different_seeds_differ(context):
    first = run_monte_carlo(context, SimulationOptions(seed=1, iterations=400))
    second = run_monte_carlo(context, SimulationOptions(seed=2, iterations=400))
    assert first.samples != second.samples


def test_percentiles_are_monotone(context):
    result = run_monte_carlo(context, SimulationOptions(seed=7, iterations=600))
    makespan = result.summary["makespan"]
    assert makespan["min"] <= makespan["p10"] <= makespan["p50"]
    assert makespan["p50"] <= makespan["p80"] <= makespan["p90"] <= makespan["p95"]
    assert makespan["p95"] <= makespan["max"]


def test_no_infeasible_trials(context):
    result = run_monte_carlo(context, SimulationOptions(seed=3, iterations=300))
    assert result.summary["engine"]["infeasible_trials"] == 0


def test_convergence_criterion_is_reported(context):
    result = run_monte_carlo(context, SimulationOptions(seed=5, iterations=800))
    convergence = result.summary["convergence"]
    assert convergence["relative_se"] >= 0
    assert convergence["criterion"]
    assert convergence["converged"] in (True, False)


def test_probability_is_a_probability(context):
    result = run_monte_carlo(context, SimulationOptions(seed=11, iterations=500))
    probability = result.summary["deadline"]["on_time_probability"]
    assert 0.0 <= probability <= 1.0
    ci = result.summary["deadline"]["on_time_ci"]
    assert ci[0] <= probability <= ci[1]


def test_cpm_is_not_blended_with_the_distribution(context):
    result = run_monte_carlo(context, SimulationOptions(seed=13, iterations=300))
    deterministic = result.summary["deterministic"]
    assert deterministic["cpm_makespan"] < result.summary["makespan"]["p50"]
    assert deterministic["sgs_base_makespan"] <= result.summary["makespan"]["p50"]


def test_iterations_scale_the_sample_count(context):
    result = run_monte_carlo(context, SimulationOptions(seed=17, iterations=250))
    assert len(result.samples) == 250


def test_paired_delta_detects_a_uniform_improvement():
    baseline = list(np.linspace(100, 200, 500))
    scenario = [value - 5 for value in baseline]
    stats = paired_delta(baseline, scenario)
    assert stats["paired"] is True
    assert stats["mean_delta"] == pytest.approx(-5, abs=1e-6)
    assert stats["probability_improvement"] == 1.0
    assert stats["probability_of_harm"] == 0.0
    assert stats["ci95_delta"][0] <= stats["mean_delta"] <= stats["ci95_delta"][1]


def test_paired_delta_of_identical_samples_is_zero():
    samples = list(np.linspace(10, 20, 200))
    stats = paired_delta(samples, samples)
    assert stats["mean_delta"] == 0.0
    assert stats["probability_improvement"] == 0.0


@settings(max_examples=40, deadline=None)
@given(
    durations=st.lists(
        st.integers(min_value=1, max_value=30), min_size=3, max_size=8
    ),
    capacity=st.floats(min_value=1.0, max_value=4.0, allow_nan=False),
)
def test_sgs_never_exceeds_capacity(durations, capacity):
    from datetime import date

    from app.core.calendar import WorkingCalendar
    from app.scheduling.model import PlanningModel, ResourceNode, TaskNode
    from app.scheduling.sgs import schedule_sgs

    tasks = [
        TaskNode(
            id=f"t{i}",
            code=f"T{i}",
            name=f"Task {i}",
            phase="Test",
            duration=duration,
            resources=(("r", 1.0),),
        )
        for i, duration in enumerate(durations)
    ]
    model = PlanningModel(
        project_id="prop",
        start_date=date(2026, 1, 5),
        tasks=tasks,
        edges=[],
        resources=[
            ResourceNode(id="r", name="Team", type="team", capacity=capacity, availability=1.0)
        ],
    )
    schedule = schedule_sgs(model, calendar=WorkingCalendar(start_date=model.start_date))
    assert schedule.feasible
    # The number of simultaneously running tasks must never exceed the capacity.
    intervals = [
        (schedule.starts[t.id], schedule.ends[t.id]) for t in tasks
    ]
    for start, _ in intervals:
        concurrent = sum(
            1 for other_start, other_end in intervals if other_start <= start < other_end
        )
        assert concurrent <= capacity + 1e-9
