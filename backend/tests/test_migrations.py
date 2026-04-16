"""Alembic migration tests: the schema can be built from scratch and rolled back."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

BACKEND = Path(__file__).resolve().parents[1]


def _alembic_config(url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_alembic_files_exist():
    assert (BACKEND / "alembic.ini").exists()
    assert (BACKEND / "alembic" / "env.py").exists()
    versions = list((BACKEND / "alembic" / "versions").glob("*.py"))
    assert versions, "no migration scripts found"


def test_upgrade_head_creates_the_schema(tmp_path, monkeypatch):
    from app.core.config import settings

    url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    command.upgrade(_alembic_config(url), "head")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    for expected in (
        "projects",
        "tasks",
        "dependencies",
        "resources",
        "suppliers",
        "components",
        "risks",
        "scenarios",
        "interventions",
        "simulation_runs",
        "optimization_runs",
        "audit_logs",
        "ai_messages",
    ):
        assert expected in tables, f"{expected} missing from the migrated schema"

    # The migrated schema must match the ORM metadata.
    import app.models  # noqa: F401
    from app.db.base import Base

    metadata_tables = set(Base.metadata.tables) - {"alembic_version"}
    assert metadata_tables <= tables


def test_downgrade_removes_the_schema(tmp_path, monkeypatch):
    from app.core.config import settings

    url = f"sqlite:///{tmp_path / 'downgrade.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    config = _alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert "projects" not in tables


def test_migration_is_single_head():
    from alembic.script import ScriptDirectory

    scripts = ScriptDirectory(str(BACKEND / "alembic"))
    heads = scripts.get_heads()
    assert len(heads) == 1
