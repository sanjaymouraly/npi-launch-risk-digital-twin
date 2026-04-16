"""Shared pytest fixtures.

The test database is an isolated SQLite file in a temporary directory, created
before the application modules are imported so that ``DATABASE_URL`` is picked
up by the settings singleton.  The four synthetic demo programs are seeded
once per session; every test works against real engine output.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

TEST_TMP = pathlib.Path(tempfile.mkdtemp(prefix="npi-tests-"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_TMP / 'test.db'}")
os.environ["SEED_DEMO_ON_STARTUP"] = "false"
os.environ["AUTH_ENABLED"] = "false"
os.environ["AI_ACTIVE_PROVIDER"] = "offline"
os.environ["DEMO_DATA_DIR"] = str(
    pathlib.Path(__file__).resolve().parents[2] / "data" / "samples"
)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from app.db.base import SessionLocal, init_db  # noqa: E402
from app.db.seed import seed_demo  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Project  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    init_db()
    with SessionLocal() as db:
        seed_demo(db, scenarios=True)


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def _projects() -> dict:
    with SessionLocal() as db:
        return {project.key: project.id for project in db.scalars(select(Project))}


@pytest.fixture()
def project_id(_projects: dict) -> str:
    return _projects["AURORA-X1"]


@pytest.fixture()
def vector_project_id(_projects: dict) -> str:
    return _projects["VECTOR-5G"]


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client
