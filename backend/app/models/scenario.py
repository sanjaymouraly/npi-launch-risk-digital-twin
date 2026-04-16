from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import IdMixin, TimestampMixin


class Scenario(Base, IdMixin, TimestampMixin):
    __tablename__ = "scenarios"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="draft")  # draft|approved|archived
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="scenarios")  # noqa: F821
    interventions: Mapped[list["Intervention"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )


class Intervention(Base, IdMixin):
    __tablename__ = "interventions"

    scenario_id: Mapped[str] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[str] = mapped_column(String(30), default="task")
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    label: Mapped[str] = mapped_column(String(300), default="")

    scenario: Mapped[Scenario] = relationship(back_populates="interventions")
