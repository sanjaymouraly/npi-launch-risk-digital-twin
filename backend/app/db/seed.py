"""Idempotent demo-data seeding.

The four programs are synthetic but complete: tasks, calendars, resources,
suppliers, BOM, risks, validation tests, ECOs and milestones.  No forecast
numbers are stored here — simulations must be run to produce them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import logger
from app.core.security import hash_password
from app.db.base import SessionLocal
from app.models import Intervention, Project, Scenario, User
from app.services import project_service

SAMPLE_ORDER = [
    "npi_demo_project.json",
    "electronics_semiconductor_shortage.json",
    "industrial_tooling_capacity.json",
    "automotive_qualification_gates.json",
]


def data_dir() -> Path:
    """Locate the directory that holds the synthetic sample programs.

    The layout differs between a checkout (``backend/app/db/seed.py`` next to
    ``data/samples``) and the container image (``/app/app/db/seed.py`` with
    ``/app/data/samples``), so several candidates are probed.
    """
    override = os.getenv("DEMO_DATA_DIR")
    if override:
        return Path(override).resolve()
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "data" / "samples",   # repository checkout
        here.parents[2] / "data" / "samples",   # container: /app/app/db -> /app
        Path.cwd() / "data" / "samples",
        Path("/app/data/samples"),
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def ensure_demo_user(db: Session) -> User | None:
    if settings.environment == "production" and settings.auth_enabled:
        password = os.getenv("DEMO_ADMIN_PASSWORD")
        if not password:
            logger.info("Skipping demo user creation in production without DEMO_ADMIN_PASSWORD")
            return None
    else:
        password = os.getenv("DEMO_ADMIN_PASSWORD", "npi-demo-2026!")
    user = db.scalar(select(User).where(User.email == "demo@npi.local"))
    if user:
        return user
    user = User(
        email="demo@npi.local",
        display_name="Demo Program Manager",
        password_hash=hash_password(password),
        roles=["admin", "program_manager", "viewer"],
    )
    db.add(user)
    db.commit()
    return user


def ensure_baseline_scenario(db: Session, project: Project) -> Scenario:
    scenario = db.scalar(
        select(Scenario).where(Scenario.project_id == project.id, Scenario.is_baseline.is_(True))
    )
    if scenario:
        return scenario
    scenario = Scenario(
        project_id=project.id,
        name="Approved baseline",
        description="Approved plan as imported; no interventions applied.",
        is_baseline=True,
        status="approved",
        approved_by="system",
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return scenario


def _seed_scenarios(db: Session, project: Project) -> None:
    """Create a few catalog-derived scenarios so the demo is explorable immediately.

    Costs and targets come from the real generated catalog; nothing is hard-coded.
    The function is idempotent: a scenario is never created twice for a program.
    """
    existing_names = {
        row.name for row in db.scalars(select(Scenario).where(Scenario.project_id == project.id))
    }
    if existing_names - {"Approved baseline"}:
        return
    from app.optimization.engine import generate_catalog
    from app.simulation.context import build_context

    try:
        catalog = generate_catalog(build_context(db, project))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not generate demo scenarios for %s: %s", project.key, exc)
        return
    capacity = [c for c in catalog if c.type in ("add_capacity", "add_overtime", "add_resource")]
    supply = [c for c in catalog if c.type in ("replace_supplier", "increase_safety_stock", "split_procurement")]
    schedule = [c for c in catalog if c.type in ("expedite_task", "parallelize", "tooling_readiness")]
    plans = [
        ("Capacity relief", "Adds effective capacity at the largest contention point.", capacity[:1]),
        ("Supply resilience", "Reduces supplier disruption exposure on critical material.", supply[:2]),
        ("Schedule acceleration", "Compresses critical-path work; verify cost-effectiveness.", schedule[:2]),
    ]
    for name, description, specs in plans:
        if name in existing_names or not specs:
            continue
        scenario = Scenario(
            project_id=project.id,
            name=name,
            description=description,
            is_baseline=False,
            status="draft",
        )
        for spec in specs:
            scenario.interventions.append(
                Intervention(
                    type=spec.type,
                    target_type=spec.target_type,
                    target_id=spec.target_id,
                    params=dict(spec.params),
                    cost=round(spec.cost, 2),
                    label=spec.label,
                )
            )
        db.add(scenario)
    db.commit()


def seed_demo(db: Session | None = None, *, scenarios: bool = True) -> dict:
    own = db is None
    if own:
        from app.db.base import init_db

        init_db()
    db = db or SessionLocal()
    created = []
    try:
        ensure_demo_user(db)
        folder = data_dir()
        for filename in SAMPLE_ORDER:
            path = folder / filename
            if not path.exists():
                logger.warning("Sample dataset missing: %s", path)
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            key = payload.get("key")
            existing = db.scalar(select(Project).where(Project.key == key))
            if existing:
                ensure_baseline_scenario(db, existing)
                if scenarios:
                    _seed_scenarios(db, existing)
                continue
            project = project_service.create_project(db, payload, actor="seed", is_demo=True)
            ensure_baseline_scenario(db, project)
            if scenarios:
                _seed_scenarios(db, project)
            created.append({"id": project.id, "key": project.key, "name": project.name})
            logger.info("Seeded demo program %s", project.key)
        if created:
            logger.info("Seeded %d demo programs", len(created))
    finally:
        if own:
            db.close()
    return {"created": created, "data_dir": str(data_dir())}


def main() -> None:
    result = seed_demo()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
