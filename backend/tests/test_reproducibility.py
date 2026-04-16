"""Reproducibility: the same program JSON must produce the same entity ids and the
same Monte Carlo result, even after the database is rebuilt.

The check runs in a subprocess against two throw-away databases, because that is
the only way to prove the property end to end (a rebuild really does assign new
rows, new snapshots and new audit entries).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

PAYLOAD = {
    "key": "REPRO-1",
    "name": "Reproducibility probe",
    "start_date": "2026-01-05",
    "launch_deadline": "2026-09-30",
    "delay_cost_per_day": 20000,
    "resources": [
        {"ref": "ENG", "name": "Engineering", "type": "team", "capacity": 2, "availability": 1.0},
    ],
    "suppliers": [
        {
            "ref": "SUP",
            "name": "Supplier",
            "category": "electronics",
            "region": "APAC",
            "reliability": 0.9,
            "lead_time_days": 30,
            "lead_time_cv": 0.2,
            "disruption_prob": 0.1,
            "disruption_delay_days": 12,
        }
    ],
    "components": [
        {
            "ref": "C1",
            "name": "Component",
            "part_number": "PN-1",
            "supplier": "SUP",
            "lead_time_days": 30,
            "criticality": 0.6,
        }
    ],
    "tasks": [
        {"ref": "T1", "code": "T-01", "name": "Design", "duration_days": 5, "distribution": "triangular",
         "duration_min": 4, "duration_mode": 5, "duration_max": 7, "resources": {"ENG": 1}},
        {"ref": "T2", "code": "T-02", "name": "Build", "duration_days": 6, "distribution": "lognormal",
         "std_dev": 1.2, "materials": ["C1"], "resources": {"ENG": 1}},
        {"ref": "T3", "code": "T-03", "name": "Launch", "duration_days": 2},
    ],
    "dependencies": [{"from": "T1", "to": "T2"}, {"from": "T2", "to": "T3"}],
    "risks": [
        {"name": "Late test", "category": "quality", "target_type": "task", "target": "T2",
         "probability": 0.2, "impact_days": 6, "impact_cost": 5000}
    ],
    "milestones": [
        {"name": "Launch gate", "task": "T3", "due_date": "2026-09-30", "customer_commitment": True}
    ],
}

PROBE = textwrap.dedent(
    """
    import hashlib, json, sys
    sys.path.insert(0, {backend!r})
    from app.db.base import SessionLocal, init_db
    from app.models import Project, Task
    from app.services import project_service
    from app.simulation.context import build_context
    from app.simulation.engine import SimulationOptions, run_monte_carlo

    init_db()
    payload = json.loads({payload!r})
    with SessionLocal() as db:
        project = project_service.create_project(db, payload, actor="probe")
        ids = sorted(t.id for t in db.query(Task).filter(Task.project_id == project.id))
        context = build_context(db, project)
        result = run_monte_carlo(context, SimulationOptions(seed=7, iterations=300))
    print(json.dumps({{
        "ids": ids,
        "digest": hashlib.sha256(json.dumps(result.samples).encode()).hexdigest(),
        "p50": result.summary["makespan"]["p50"],
        "on_time": result.summary["deadline"]["on_time_probability"],
    }}))
    """
)


def _run_probe(database_path: Path) -> dict:
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{database_path}"
    env["SEED_DEMO_ON_STARTUP"] = "false"
    env["AI_ACTIVE_PROVIDER"] = "offline"
    env["PYTHONPATH"] = str(BACKEND)
    script = PROBE.format(backend=str(BACKEND), payload=json.dumps(PAYLOAD))
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=300
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_two_fresh_databases_produce_the_same_ids_and_forecast(tmp_path):
    first = _run_probe(tmp_path / "first.db")
    second = _run_probe(tmp_path / "second.db")

    assert first["ids"] == second["ids"]
    assert first["digest"] == second["digest"]
    assert first["p50"] == second["p50"]
    assert first["on_time"] == second["on_time"]


def test_entity_ids_are_stable_for_the_same_program(db):
    from app.services.project_service import deterministic_id

    expected = deterministic_id("REPRO-1", "task", "T1")
    assert expected == deterministic_id("REPRO-1", "task", "T1")
    assert expected != deterministic_id("REPRO-2", "task", "T1")
    assert len(expected) == 36
