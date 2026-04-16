from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import IdMixin


class Risk(Base, IdMixin):
    __tablename__ = "risks"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(60), default="schedule")
    target_type: Mapped[str] = mapped_column(String(30), default="task")  # task|supplier|component|resource|project
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    probability: Mapped[float] = mapped_column(Float, default=0.1)
    impact_days: Mapped[float] = mapped_column(Float, default=5.0)
    impact_cost: Mapped[float] = mapped_column(Float, default=0.0)
    distribution: Mapped[str] = mapped_column(String(30), default="lognormal")
    correlation_group: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner: Mapped[str] = mapped_column(String(120), default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped["Project"] = relationship(back_populates="risks")  # noqa: F821
    mitigations: Mapped[list["MitigationPlan"]] = relationship(
        back_populates="risk", cascade="all, delete-orphan"
    )


class MitigationPlan(Base, IdMixin):
    __tablename__ = "mitigation_plans"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    risk_id: Mapped[str | None] = mapped_column(
        ForeignKey("risks.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(300))
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    expected_benefit_days: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="proposed")

    risk: Mapped[Risk | None] = relationship(back_populates="mitigations")


class ValidationTest(Base, IdMixin):
    __tablename__ = "validation_tests"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    test_type: Mapped[str] = mapped_column(String(40), default="DVT")  # EVT|DVT|PVT|qualification|reliability
    required_passes: Mapped[int] = mapped_column(Integer, default=1)
    failure_probability: Mapped[float] = mapped_column(Float, default=0.1)
    retest_days: Mapped[float] = mapped_column(Float, default=10.0)
    is_gate: Mapped[bool] = mapped_column(Boolean, default=False)
    correlation_group: Mapped[str | None] = mapped_column(String(80), nullable=True)


class ECO(Base, IdMixin):
    __tablename__ = "ecos"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending|approved|implemented|rejected
    probability: Mapped[float] = mapped_column(Float, default=0.0)
    rework_days: Mapped[float] = mapped_column(Float, default=5.0)
    impact_task_ids: Mapped[list] = mapped_column(JSON, default=list)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
