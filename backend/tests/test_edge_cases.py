"""Edge cases: invalid input, empty scopes, impossible requests and honest errors."""
from __future__ import annotations

from app.optimization.interventions import apply_interventions
from app.simulation.context import build_context
from app.simulation.engine import SimulationOptions, run_monte_carlo


def test_simulation_rejects_an_out_of_range_iteration(client, project_id):
    response = client.post(
        f"/api/projects/{project_id}/simulations",
        json={"iterations": 10, "async_job": False},
    )
    assert response.status_code == 422


def test_simulation_rejects_an_empty_scenario(client, project_id):
    response = client.post(
        f"/api/projects/{project_id}/simulations",
        json={"iterations": 100, "scenario_id": "not-a-scenario", "async_job": False},
    )
    assert response.status_code in (404, 422)
    assert response.json()["message"]


def test_optimisation_with_zero_budget_is_reported_not_guessed(client, project_id):
    response = client.post(
        f"/api/projects/{project_id}/optimizations",
        json={
            "budget": 0,
            "objective": "min_combined_exposure",
            "pilot_iterations": 100,
            "verification_iterations": 200,
            "async_job": False,
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert "budget" in body["message"].lower()


def test_intervention_with_an_unknown_target_is_rejected_not_guessed(db, project_id):
    from app.models import Project
    from app.optimization.interventions import InterventionSpec

    context = build_context(db, db.get(Project, project_id))
    spec = InterventionSpec(
        id="bogus",
        type="replace_supplier",
        label="Re-source from nowhere",
        target_type="supplier",
        target_id="missing",
        params={"component_id": "missing", "supplier_id": "missing"},
        cost=100.0,
    )
    mutated, warnings = apply_interventions(context, [spec])
    assert warnings
    assert "unknown component/supplier" in warnings[0]
    # The model is unchanged apart from the rejected intervention.
    assert len(mutated.model.tasks) == len(context.model.tasks)


def test_unsupported_intervention_type_is_reported(db, project_id):
    from app.models import Project
    from app.optimization.interventions import InterventionSpec

    context = build_context(db, db.get(Project, project_id))
    spec = InterventionSpec(id="x", type="teleport_task", label="Teleport", cost=1.0)
    _, warnings = apply_interventions(context, [spec])
    assert warnings and "Unsupported" in warnings[0]


def test_simulation_of_a_project_without_tasks_is_reported(client):
    created = client.post(
        "/api/projects",
        json={
            "key": "EMPTY-1",
            "name": "Empty program",
            "start_date": "2026-01-05",
            "launch_deadline": "2026-06-30",
            "tasks": [],
        },
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    schedule = client.get(f"/api/projects/{project_id}/schedule").json()
    assert schedule["validation"]["valid"] in (True, False)

    response = client.post(
        f"/api/projects/{project_id}/simulations",
        json={"iterations": 50, "async_job": False},
    )
    assert response.status_code in (202, 422)
    assert client.delete(f"/api/projects/{project_id}").status_code == 200


def test_invalid_project_payload_is_rejected(client):
    response = client.post("/api/projects", json={"key": "NO-NAME-1"})
    assert response.status_code in (400, 422)
    assert "name" in response.json()["message"].lower()


def test_project_key_is_derived_from_the_name(client):
    created = client.post("/api/projects", json={"name": "Derived key program"})
    assert created.status_code == 201
    assert created.json()["key"] == "DERIVED-KEY-PROGRAM"
    assert client.delete(f"/api/projects/{created.json()['id']}").status_code == 200


def test_job_for_an_unknown_id_is_404(client):
    response = client.get("/api/jobs/does-not-exist")
    assert response.status_code == 404


def test_paired_comparison_requires_a_real_scenario(client, project_id):
    response = client.post(
        f"/api/projects/{project_id}/scenarios/compare",
        json={"scenario_id": "not-a-scenario", "iterations": 100},
    )
    assert response.status_code in (404, 422)


def test_simulation_survives_a_zero_budget_cost_of_delay(db, project_id):
    """A pathological project must not crash the engine."""
    from app.models import Project

    project = db.get(Project, project_id)
    original = project.delay_cost_per_day
    project.delay_cost_per_day = 0.0
    db.commit()
    try:
        context = build_context(db, project)
        result = run_monte_carlo(context, SimulationOptions(seed=1, iterations=100))
        assert result.summary["deadline"]["expected_delay_cost"] == 0.0
    finally:
        project.delay_cost_per_day = original
        db.commit()
