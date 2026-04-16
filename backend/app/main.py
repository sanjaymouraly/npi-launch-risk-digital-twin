"""NPI Launch Risk Digital Twin — FastAPI application."""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import ai, analysis, auth, jobs, optimization, projects, scenarios, simulations, system
from app.api import settings as settings_api
from app.core.config import settings
from app.core.errors import install_error_handlers
from app.core.logging import logger, setup_logging
from app.db.base import SessionLocal, init_db
from app.db.seed import seed_demo
from app.services.job_service import recover_stale_jobs


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    init_db()
    if settings.seed_demo_on_startup:
        try:
            with SessionLocal() as db:
                from sqlalchemy import func, select

                from app.models import Project

                count = int(db.scalar(select(func.count()).select_from(Project)) or 0)
            if count == 0:
                seed_demo(scenarios=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Demo seeding skipped: %s", exc)
    recovered = recover_stale_jobs()
    if recovered:
        logger.info("Recovered %d stale job(s)", recovered)
    logger.info("Application started", extra={"status_code": 200})
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "NPI launch risk digital twin: exact CPM, resource-constrained CP-SAT, "
        "Monte Carlo simulation, risk attribution, scenario comparison and "
        "budget-constrained intervention optimisation with a grounded AI copilot."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Content-Disposition"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):  # noqa: ANN001
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed", extra={"path": request.url.path, "request_id": request_id}
        )
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    if request.url.path not in ("/api/health", "/api/ready"):
        logger.info(
            "request",
            extra={
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "request_id": request_id,
            },
        )
    return response


install_error_handlers(app)

app.include_router(system.router, prefix="/api", tags=["system"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(analysis.router, prefix="/api", tags=["analysis"])
app.include_router(simulations.router, prefix="/api", tags=["simulations"])
app.include_router(scenarios.router, prefix="/api", tags=["scenarios"])
app.include_router(optimization.router, prefix="/api", tags=["optimization"])
app.include_router(ai.router, prefix="/api", tags=["ai"])
app.include_router(settings_api.router, prefix="/api/settings", tags=["settings"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])


@app.get("/", include_in_schema=False)
def root() -> JSONResponse:
    return JSONResponse(
        {
            "app": settings.app_name,
            "version": settings.version,
            "docs": "/docs",
            "health": "/api/health",
            "ui": "Run the Vite frontend at http://localhost:5173",
        }
    )
