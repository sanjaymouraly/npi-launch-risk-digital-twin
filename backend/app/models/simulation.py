from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import IdMixin, TimestampMixin


class SimulationRun(Base, IdMixin, TimestampMixin):
    __tablename__ = "simulation_runs"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str | None] = mapped_column(
        ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(300), default="")
    seed: Mapped[int] = mapped_column(Integer, default=42)
    iterations: Mapped[int] = mapped_column(Integer, default=2000)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    engine_version: Mapped[str] = mapped_column(String(30), default="1.0.0")
    model_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    samples: Mapped[list] = mapped_column(JSON, default=list)

    project: Mapped["Project"] = relationship(back_populates="simulations")  # noqa: F821
    scenario: Mapped["Scenario | None"] = relationship()  # noqa: F821


class OptimizationRun(Base, IdMixin, TimestampMixin):
    __tablename__ = "optimization_runs"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    baseline_simulation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    objective: Mapped[str] = mapped_column(String(60), default="max_probability")
    budget: Mapped[float] = mapped_column(Float, default=100000.0)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="completed")
    results: Mapped[dict] = mapped_column(JSON, default=dict)


class Job(Base, IdMixin, TimestampMixin):
    __tablename__ = "jobs"

    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(String(400), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
