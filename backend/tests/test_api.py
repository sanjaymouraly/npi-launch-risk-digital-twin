"""API contract tests: status codes, payload shapes, jobs and import/export."""
from __future__ import annotations

import io
import json


def test_health_and_meta(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    meta = client.get("/api/meta")
    assert meta.status_code == 200
    body = meta.json()
    assert body["engines"]["simulation"]
    assert body["capabilities"]
    assert body["ai"]["offline_available"] is True


def test_ready_reports_the_database(client):
    response = client.get("/api/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"


def test_projects_list_and_detail(client, project_id):
    projects = client.get("/api/projects").json()
    assert projects
    assert any(item["id"] == project_id for item in projects)

    detail = client.get(f"/api/projects/{project_id}").json()
    assert detail["key"] == "AURORA-X1"
    assert len(detail["tasks"]) > 10
    assert detail["dependencies"]
    assert detail["resources"]


def test_unknown_project_returns_404_with_error_shape(client):
    response = client.get("/api/projects/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["code"]
    assert body["message"]
    assert "request_id" in body


def test_schedule_endpoint_separates_cpm_and_constrained(client, project_id):
    payload = client.get(f"/api/projects/{project_id}/schedule?mode=both&time_limit=8").json()
    assert payload["cpm"]["project_duration"] > 0
    assert payload["constrained"]["makespan"] >= payload["cpm"]["project_duration"]
    assert payload["comparison"]["capacity_delay_days"] >= 0
    assert payload["validation"]["valid"] is True


def test_suppliers_and_milestones_endpoints(client, project_id):
    suppliers = client.get(f"/api/projects/{project_id}/suppliers").json()
    assert suppliers["components"]
    assert "suppliers" in suppliers

    milestones = client.get(f"/api/projects/{project_id}/milestones").json()
    assert milestones["milestones"]


def test_simulation_runs_and_is_retrievable(client, project_id):
    response = client.post(
        f"/api/projects/{project_id}/simulations",
        json={"iterations": 120, "seed": 99, "async_job": False, "label": "pytest"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["async"] is False

    detail = client.get(f"/api/simulations/{body['simulation_id']}").json()
    assert detail["iterations"] == 120
    assert detail["summary"]["makespan"]["p50"] > 0
    assert 0 <= detail["summary"]["deadline"]["on_time_probability"] <= 1

    history = client.get(f"/api/projects/{project_id}/simulations").json()
    assert any(item["id"] == body["simulation_id"] for item in history)


def test_simulation_rejects_too_many_iterations(client, project_id):
    response = client.post(
        f"/api/projects/{project_id}/simulations",
        json={"iterations": 999999, "async_job": False},
    )
    assert response.status_code == 422


def test_scenario_list_preview_and_compare(client, project_id):
    scenarios = client.get(f"/api/projects/{project_id}/scenarios").json()
    assert scenarios
    target = next(item for item in scenarios if not item["is_baseline"])

    preview = client.post(
        f"/api/projects/{project_id}/scenarios/{target['id']}/preview"
    ).json()
    assert preview["interventions"]
    assert preview["baseline"]["constrained_days"] > 0

    comparison = client.post(
        f"/api/projects/{project_id}/scenarios/compare",
        json={"scenario_id": target["id"], "iterations": 200, "seed": 5},
    ).json()
    assert comparison["paired_delta"]["paired"] is True
    assert comparison["paired_delta"]["iterations"] == 200
    assert "economics" in comparison


def test_scenario_create_clone_and_delete(client, project_id):
    created = client.post(
        f"/api/projects/{project_id}/scenarios",
        json={
            "name": "pytest scenario",
            "description": "created by the test suite",
            "interventions": [],
        },
    )
    assert created.status_code == 201
    scenario_id = created.json()["id"]

    clone = client.post(f"/api/scenarios/{scenario_id}/clone", json={"name": "pytest clone"})
    assert clone.status_code == 201

    assert client.delete(f"/api/scenarios/{clone.json()['id']}").status_code == 200
    assert client.delete(f"/api/scenarios/{scenario_id}").status_code == 200


def test_optimization_job_runs_and_is_listed(client, project_id):
    response = client.post(
        f"/api/projects/{project_id}/optimizations",
        json={
            "budget": 20000,
            "objective": "min_combined_exposure",
            "pilot_iterations": 100,
            "verification_iterations": 200,
            "seed": 3,
            "async_job": True,
        },
    )
    assert response.status_code == 202
    job = response.json()
    assert job["async"] is True

    import time

    for _ in range(120):
        status = client.get(f"/api/jobs/{job['job_id']}").json()
        if status["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.5)
    assert status["status"] == "completed", status.get("error")
    assert status["result"]["optimization_id"]

    optimization = client.get(f"/api/optimizations/{status['result']['optimization_id']}").json()
    assert optimization["results"]["recommendation"]
    assert optimization["results"]["recommendation"]["intervention_cost"] <= 20000


def test_export_and_import_round_trip(client, project_id):
    exported = client.get(f"/api/projects/{project_id}/export").json()
    assert exported["key"] == "AURORA-X1"
    assert exported["tasks"]

    exported["key"] = "AURORA-COPY"
    exported["name"] = "Aurora copy for the round trip"
    payload = json.dumps(exported).encode("utf-8")
    response = client.post(
        "/api/projects/import",
        files={"file": ("aurora.json", io.BytesIO(payload), "application/json")},
    )
    assert response.status_code == 201
    created = response.json()["projects"][0]
    assert created["key"] != "AURORA-X1"  # unique key enforced
    assert client.delete(f"/api/projects/{created['id']}").status_code == 200


def test_csv_template_is_served(client):
    response = client.get("/api/projects/csv-template")
    assert response.status_code == 200
    assert "code" in response.text.lower()


def test_audit_trail_records_activity(client, project_id):
    client.post(
        f"/api/projects/{project_id}/simulations",
        json={"iterations": 60, "seed": 4, "async_job": False, "label": "audit-probe"},
    )
    entries = client.get(f"/api/projects/{project_id}/audit").json()
    assert entries
    assert any(entry["action"] == "simulation.run" for entry in entries)
    assert all("actor" in entry for entry in entries)


def test_job_cancellation_is_accepted(client, project_id):
    response = client.post(
        f"/api/projects/{project_id}/simulations",
        json={"iterations": 20000, "seed": 2, "async_job": True, "label": "cancel-me"},
    )
    job_id = response.json()["job_id"]
    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] in ("cancelled", "running", "queued")


def test_settings_providers_never_return_keys(client):
    providers = client.get("/api/settings/providers").json()["providers"]
    assert providers
    for provider in providers:
        assert "api_key" not in provider
        masked = provider.get("api_key_masked")
        if masked:
            assert "*" in masked or "…" in masked or "•" in masked


def test_calibration_reports_insufficient_data_instead_of_inventing(client, project_id):
    payload = client.get(f"/api/projects/{project_id}/calibration").json()
    assert payload["status"] in ("insufficient_data", "ok")
    if payload["status"] == "insufficient_data":
        assert payload["message"]
        assert "brier" not in payload
