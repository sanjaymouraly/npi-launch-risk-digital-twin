from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import IdMixin, TimestampMixin


class AuditLog(Base, IdMixin):
    __tablename__ = "audit_logs"

    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(200), default="system")
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class AIProviderConfig(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_provider_configs"

    provider: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    base_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=120.0)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    monthly_budget_usd: Mapped[float] = mapped_column(Float, default=25.0)
    input_price_per_mtok: Mapped[float] = mapped_column(Float, default=0.0)
    output_price_per_mtok: Mapped[float] = mapped_column(Float, default=0.0)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


class AIConversation(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_conversations"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="New conversation")
    provider: Mapped[str] = mapped_column(String(40), default="offline")
    model: Mapped[str] = mapped_column(String(200), default="")


class AIMessage(Base, IdMixin):
    __tablename__ = "ai_messages"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))  # user|assistant|system|tool
    content: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[list] = mapped_column(JSON, default=list)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list)
    provider: Mapped[str] = mapped_column(String(40), default="")
    model: Mapped[str] = mapped_column(String(200), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class SimulationSnapshot(Base, IdMixin):
    """Immutable forecast snapshot referenced by decisions and the AI assistant."""

    __tablename__ = "simulation_snapshots"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    simulation_id: Mapped[str] = mapped_column(String(36), index=True)
    scenario_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    label: Mapped[str] = mapped_column(String(300), default="")
    p50_days: Mapped[float] = mapped_column(Float, default=0.0)
    p90_days: Mapped[float] = mapped_column(Float, default=0.0)
    on_time_probability: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class CalibrationRecord(Base, IdMixin):
    """Holds label/forecast pairs used for Brier score and interval coverage."""

    __tablename__ = "calibration_records"

    project_id: Mapped[str] = mapped_column(String(36), index=True)
    milestone: Mapped[str] = mapped_column(String(200))
    forecast_probability: Mapped[float] = mapped_column(Float)
    outcome: Mapped[bool] = mapped_column(Boolean)
    forecast_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    outcome_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="synthetic_holdout")
