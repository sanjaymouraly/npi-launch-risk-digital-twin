from __future__ import annotations

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import IdMixin


class Resource(Base, IdMixin):
    __tablename__ = "resources"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(40), default="team")  # team|machine|lab|line|supplier
    capacity: Mapped[float] = mapped_column(Float, default=1.0)
    availability: Mapped[float] = mapped_column(Float, default=1.0)  # 0..1
    cost_per_day: Mapped[float] = mapped_column(Float, default=0.0)
    overtime_available: Mapped[bool] = mapped_column(default=True)

    project: Mapped["Project"] = relationship(back_populates="resources")  # noqa: F821
    assignments: Mapped[list["TaskResource"]] = relationship(
        back_populates="resource", cascade="all, delete-orphan"
    )

    @property
    def effective_capacity(self) -> float:
        return max(0.0, self.capacity * self.availability)


class TaskResource(Base, IdMixin):
    __tablename__ = "task_resources"
    __table_args__ = (UniqueConstraint("task_id", "resource_id", name="uq_task_resource"),)

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("resources.id", ondelete="CASCADE"), index=True
    )
    demand: Mapped[float] = mapped_column(Float, default=1.0)

    task: Mapped["Task"] = relationship(back_populates="assignments")  # noqa: F821
    resource: Mapped[Resource] = relationship(back_populates="assignments")
