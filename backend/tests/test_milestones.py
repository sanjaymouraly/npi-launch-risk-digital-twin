"""Milestone projection from the simulation and from the deterministic CPM."""
from __future__ import annotations

import pytest
from app.simulation.context import build_context
from app.simulation.engine import SimulationOptions, run_monte_carlo


@pytest.fixture()
def context(db, project_id):
    from app.models import Project

    return build_context(db, db.get(Project, project_id))


def test_simulation_reports_milestone_confidence(context):
    result = run_monte_carlo(context, SimulationOptions(seed=21, iterations=400))
    milestones = result.summary["milestones"]
    assert milestones
    for row in milestones:
        assert row["p50_date"]
        assert row["p90_date"]
        assert 0.0 <= row["on_time_probability"] <= 1.0
        assert row["slack_vs_due_days"] is not None or row["due_date"] is None


def test_milestone_percentiles_are_ordered(context):
    result = run_monte_carlo(context, SimulationOptions(seed=22, iterations=400))
    for row in result.summary["milestones"]:
        assert row["p50_offset"] <= row["p90_offset"]
        assert row["p10_date"] <= row["p50_date"] <= row["p90_date"]


def test_milestone_targets_are_attached_to_the_model(context):
    assert context.model.milestone_targets
    for target in context.model.milestone_targets:
        assert target["task_id"]
        assert target["due_offset"] is not None


def test_milestone_endpoint_prefers_the_simulation(client, project_id):
    client.post(
        f"/api/projects/{project_id}/simulations",
        json={"iterations": 120, "seed": 31, "async_job": False, "label": "milestone-probe"},
    )
    payload = client.get(f"/api/projects/{project_id}/milestones").json()
    assert payload["source"] == "simulation"
    assert payload["simulation_id"]
    assert payload["milestones"][0]["on_time_probability"] is not None


def test_milestone_endpoint_falls_back_to_cpm(client, project_id):
    payload = client.get(f"/api/projects/{project_id}/milestones").json()
    assert payload["source"] in ("simulation", "cpm")
    if payload["source"] == "cpm":
        for row in payload["milestones"]:
            assert row["p50_date"]
            assert row["on_time_probability"] is None
            assert "CPM" in (row["note"] or "")
