from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import IdMixin, TimestampMixin


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    roles: Mapped[list] = mapped_column(JSON, default=lambda: ["viewer"])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Project(Base, IdMixin, TimestampMixin):
    __tablename__ = "projects"

    key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    product: Mapped[str] = mapped_column(String(200), default="")
    version: Mapped[str] = mapped_column(String(40), default="1.0")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)  # planned|active|archived
    currency: Mapped[str] = mapped_column(String(8), default="USD")

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    launch_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_launch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    working_days_per_week: Mapped[int] = mapped_column(Integer, default=5)
    holidays: Mapped[list] = mapped_column(JSON, default=list)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")

    delay_cost_per_day: Mapped[float] = mapped_column(Float, default=25000.0)
    intervention_budget: Mapped[float] = mapped_column(Float, default=150000.0)
    yield_start: Mapped[float] = mapped_column(Float, default=0.62)
    yield_target: Mapped[float] = mapped_column(Float, default=0.95)
    ramp_days: Mapped[int] = mapped_column(Integer, default=60)
    unit_margin: Mapped[float] = mapped_column(Float, default=180.0)
    planned_volume: Mapped[int] = mapped_column(Integer, default=50000)

    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    owner: Mapped[str] = mapped_column(String(200), default="Program Office")
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)

    tasks: Mapped[list["Task"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan", order_by="Task.sort_order"
    )
    dependencies: Mapped[list["Dependency"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    resources: Mapped[list["Resource"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    suppliers: Mapped[list["Supplier"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    components: Mapped[list["Component"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    milestones: Mapped[list["Milestone"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    risks: Mapped[list["Risk"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    scenarios: Mapped[list["Scenario"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )
    simulations: Mapped[list["SimulationRun"]] = relationship(  # noqa: F821
        back_populates="project", cascade="all, delete-orphan"
    )


class Milestone(Base, IdMixin):
    __tablename__ = "milestones"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    customer_commitment: Mapped[bool] = mapped_column(Boolean, default=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    project: Mapped[Project] = relationship(back_populates="milestones")


class ProjectMember(Base, IdMixin):
    __tablename__ = "project_members"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(40), default="viewer")
