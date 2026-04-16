from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import IdMixin


class Task(Base, IdMixin):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_task_project_code"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40), default="")
    name: Mapped[str] = mapped_column(String(300))
    phase: Mapped[str] = mapped_column(String(100), default="Design", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    wbs: Mapped[str] = mapped_column(String(40), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    duration_days: Mapped[float] = mapped_column(Float, default=5.0)
    distribution: Mapped[str] = mapped_column(String(20), default="triangular")
    duration_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_mode: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    std_dev: Mapped[float | None] = mapped_column(Float, nullable=True)
    buffer_days: Mapped[float] = mapped_column(Float, default=0.0)
    risk_factor: Mapped[float] = mapped_column(Float, default=0.05)

    cost: Mapped[float] = mapped_column(Float, default=0.0)
    is_gate: Mapped[bool] = mapped_column(Boolean, default=False)
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False)
    fixed_start_offset: Mapped[float | None] = mapped_column(Float, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="tasks")  # noqa: F821
    assignments: Mapped[list["TaskResource"]] = relationship(  # noqa: F821
        back_populates="task", cascade="all, delete-orphan"
    )
    material_links: Mapped[list["TaskComponent"]] = relationship(  # noqa: F821
        back_populates="task", cascade="all, delete-orphan"
    )


class Dependency(Base, IdMixin):
    __tablename__ = "dependencies"
    __table_args__ = (
        UniqueConstraint("from_task_id", "to_task_id", name="uq_dependency_pair"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    from_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    to_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(2), default="FS")  # FS | SS | FF | SF
    lag_days: Mapped[float] = mapped_column(Float, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, default="")

    project: Mapped["Project"] = relationship(back_populates="dependencies")  # noqa: F821
