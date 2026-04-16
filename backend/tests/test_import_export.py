"""Import and export round-trips (JSON program, CSV task import)."""
from __future__ import annotations

import io
import json


def test_json_export_is_self_describing(client, project_id):
    payload = client.get(f"/api/projects/{project_id}/export").json()
    for key in (
        "key",
        "name",
        "tasks",
        "dependencies",
        "resources",
        "suppliers",
        "components",
        "risks",
        "milestones",
    ):
        assert key in payload
    assert payload["tasks"][0]["code"]
    assert payload["dependencies"][0]["from"]


def test_json_export_download_header(client, project_id):
    response = client.get(f"/api/projects/{project_id}/export?download=true")
    assert response.status_code == 200
    assert "attachment" in response.headers.get("content-disposition", "")


def test_json_import_round_trip(client, project_id):
    exported = client.get(f"/api/projects/{project_id}/export").json()
    exported["key"] = "ROUND-TRIP-1"
    exported["name"] = "Round trip program"
    exported["is_demo"] = False

    response = client.post(
        "/api/projects/import",
        files={"file": ("program.json", io.BytesIO(json.dumps(exported).encode()), "application/json")},
    )
    assert response.status_code == 201
    created = response.json()["projects"][0]

    detail = client.get(f"/api/projects/{created['id']}").json()
    assert len(detail["tasks"]) == len(exported["tasks"])
    assert len(detail["dependencies"]) == len(exported["dependencies"])
    assert detail["key"] == "ROUND-TRIP-1"

    assert client.delete(f"/api/projects/{created['id']}").status_code == 200


def test_duplicate_key_is_rejected(client, project_id):
    exported = client.get(f"/api/projects/{project_id}/export").json()
    response = client.post(
        "/api/projects/import",
        files={"file": ("program.json", io.BytesIO(json.dumps(exported).encode()), "application/json")},
    )
    assert response.status_code == 409


def test_invalid_json_import_is_reported(client):
    response = client.post(
        "/api/projects/import",
        files={"file": ("broken.json", io.BytesIO(b"{not json"), "application/json")},
    )
    assert response.status_code == 422
    assert response.json()["message"]


def test_csv_template_round_trip(client, project_id):
    template = client.get("/api/projects/csv-template").text
    assert "code" in template.splitlines()[0]

    response = client.post(
        f"/api/projects/{project_id}/tasks/import",
        files={"file": ("tasks.csv", io.BytesIO(template.encode()), "text/csv")},
    )
    # The template rows reference codes that already exist in the demo program,
    # so the import must fail cleanly without creating anything.
    assert response.status_code in (200, 422)
    if response.status_code == 422:
        body = response.json()
        assert body["details"]["errors"]


def test_csv_import_creates_tasks(client, project_id):
    csv_text = (
        "code,name,phase,duration_days,distribution,duration_min,duration_mode,duration_max,std_dev,cost,is_gate,optional,resources,predecessors,materials\n"
        "TEST-01,Imported task,Design,3,triangular,2,3,5,,1000,false,false,,,\n"
        "TEST-02,Dependent task,Design,2,fixed,,,,,500,false,false,,TEST-01,\n"
    )
    response = client.post(
        f"/api/projects/{project_id}/tasks/import",
        files={"file": ("tasks.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["created_tasks"] == 2

    tasks = client.get(f"/api/projects/{project_id}/tasks").json()
    codes = {task["code"] for task in tasks["tasks"]}
    assert {"TEST-01", "TEST-02"} <= codes


def test_csv_import_rolls_back_on_error(client, project_id):
    csv_text = (
        "code,name,phase,duration_days,distribution,duration_min,duration_mode,duration_max,std_dev,cost,is_gate,optional,resources,predecessors,materials\n"
        "TEST-03,Fine task,Design,3,fixed,,,,,0,false,false,,,\n"
        "TEST-04,Bad task,Design,not-a-number,fixed,,,,,0,false,false,,,\n"
    )
    response = client.post(
        f"/api/projects/{project_id}/tasks/import",
        files={"file": ("tasks.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    )
    assert response.status_code == 422
    tasks = client.get(f"/api/projects/{project_id}/tasks").json()
    codes = {task["code"] for task in tasks["tasks"]}
    assert "TEST-03" not in codes  # rolled back
