"""Operational endpoints: liveness, readiness, capabilities and workspace stats."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select, text

from app.ai.providers import resolve
from app.core.config import settings
from app.db.base import DbSession
from app.models import (
    Component,
    OptimizationRun,
    Project,
    Risk,
    Scenario,
    SimulationRun,
    Supplier,
    Task,
)
from app.simulation.engine import ENGINE_VERSION

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
    }


@router.get("/ready")
def ready(db: DbSession) -> dict:
    try:
        db.execute(text("SELECT 1"))
        database = "connected"
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "database": "unavailable", "error": str(exc)[:200]}
    return {"status": "ready", "database": database, "engine_version": ENGINE_VERSION}


@router.get("/meta")
def meta(db: DbSession) -> dict:
    provider = resolve(db, settings.ai_active_provider)
    return {
        "app": settings.app_name,
        "version": settings.version,
        "environment": settings.environment,
        "auth_enabled": settings.auth_enabled,
        "engines": {
            "simulation": ENGINE_VERSION,
            "scheduler": "OR-Tools CP-SAT + serial SGS",
            "cpm": "exact activity-on-node with FS/SS/FF/SF and lags",
            "attribution": "Spearman, tornado, leave-one-out, Saltelli Sobol",
        },
        "capabilities": [
            "CPM with calendars and all precedence types",
            "Resource-constrained CP-SAT with material release dates",
            "Monte Carlo with correlated risks and resource-feasible SGS",
            "Risk attribution and scenario comparison with common random numbers",
            "Budget-constrained intervention optimisation with simulation verification",
            "Grounded AI copilot with offline mode",
            "JSON/CSV import and export, audit trail and background jobs",
        ],
        "ai": {
            "active_provider": provider.provider,
            "model": provider.model,
            "configured": provider.configured,
            "offline_available": True,
        },
        "limits": {
            "simulation_max_iterations": settings.simulation_max_iterations,
            "simulation_max_tasks": settings.simulation_max_tasks,
            "upload_bytes": settings.max_upload_bytes,
        },
    }


@router.get("/stats")
def stats(db: DbSession) -> dict:
    def count(model) -> int:  # noqa: ANN001
        return int(db.scalar(select(func.count()).select_from(model)) or 0)

    return {
        "projects": count(Project),
        "active_projects": int(
            db.scalar(select(func.count()).select_from(Project).where(Project.status == "active")) or 0
        ),
        "tasks": count(Task),
        "suppliers": count(Supplier),
        "components": count(Component),
        "risks": count(Risk),
        "scenarios": count(Scenario),
        "simulations": count(SimulationRun),
        "optimizations": count(OptimizationRun),
    }
