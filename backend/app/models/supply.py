from __future__ import annotations

from datetime import date

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import IdMixin


class Supplier(Base, IdMixin):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_supplier_project_name"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80), default="electronics")
    region: Mapped[str] = mapped_column(String(80), default="")
    reliability: Mapped[float] = mapped_column(Float, default=0.92)  # on-time delivery rate 0..1
    lead_time_days: Mapped[float] = mapped_column(Float, default=30.0)
    lead_time_cv: Mapped[float] = mapped_column(Float, default=0.2)  # coefficient of variation
    disruption_prob: Mapped[float] = mapped_column(Float, default=0.05)
    disruption_delay_days: Mapped[float] = mapped_column(Float, default=21.0)
    cost_factor: Mapped[float] = mapped_column(Float, default=1.0)
    qualification_required: Mapped[bool] = mapped_column(Boolean, default=False)
    qualified: Mapped[bool] = mapped_column(Boolean, default=True)
    dual_source: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")

    project: Mapped["Project"] = relationship(back_populates="suppliers")  # noqa: F821
    components: Mapped[list["Component"]] = relationship(
        back_populates="supplier", foreign_keys="Component.supplier_id"
    )


class Component(Base, IdMixin):
    __tablename__ = "components"
    __table_args__ = (UniqueConstraint("project_id", "part_number", name="uq_component_project_pn"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    part_number: Mapped[str] = mapped_column(String(80), default="")
    supplier_id: Mapped[str | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    alternative_supplier_id: Mapped[str | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    unit_cost: Mapped[float] = mapped_column(Float, default=10.0)
    qty_per_unit: Mapped[float] = mapped_column(Float, default=1.0)
    lead_time_days: Mapped[float] = mapped_column(Float, default=30.0)
    safety_stock_days: Mapped[float] = mapped_column(Float, default=0.0)
    inventory_days: Mapped[float] = mapped_column(Float, default=0.0)
    criticality: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1
    single_source: Mapped[bool] = mapped_column(Boolean, default=True)

    project: Mapped["Project"] = relationship(back_populates="components")  # noqa: F821
    supplier: Mapped[Supplier | None] = relationship(
        back_populates="components", foreign_keys=[supplier_id]
    )


class TaskComponent(Base, IdMixin):
    __tablename__ = "task_components"
    __table_args__ = (UniqueConstraint("task_id", "component_id", name="uq_task_component"),)

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    component_id: Mapped[str] = mapped_column(
        ForeignKey("components.id", ondelete="CASCADE"), index=True
    )
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    required_by_offset: Mapped[float | None] = mapped_column(Float, nullable=True)

    task: Mapped["Task"] = relationship(back_populates="material_links")  # noqa: F821
    component: Mapped[Component] = relationship()


class Quote(Base, IdMixin):
    __tablename__ = "quotes"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"))
    component_id: Mapped[str] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"))
    unit_cost: Mapped[float] = mapped_column(Float, default=10.0)
    lead_time_days: Mapped[float] = mapped_column(Float, default=30.0)
    moq: Mapped[int] = mapped_column(Integer, default=100)
    qualified: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(String(400), default="")


class PurchaseOrder(Base, IdMixin):
    __tablename__ = "purchase_orders"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    component_id: Mapped[str] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"))
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"))
    quantity: Mapped[float] = mapped_column(Float, default=100)
    unit_cost: Mapped[float] = mapped_column(Float, default=10.0)
    ordered_offset: Mapped[float] = mapped_column(Float, default=0.0)
    expected_offset: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="open")  # open|expedited|received|cancelled
    expedite_cost: Mapped[float] = mapped_column(Float, default=0.0)


class Inventory(Base, IdMixin):
    __tablename__ = "inventories"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    component_id: Mapped[str] = mapped_column(ForeignKey("components.id", ondelete="CASCADE"))
    on_hand_qty: Mapped[float] = mapped_column(Float, default=0.0)
    safety_stock_qty: Mapped[float] = mapped_column(Float, default=0.0)
    location: Mapped[str] = mapped_column(String(120), default="DC-1")


class ActualEvent(Base, IdMixin):
    """Observed real-world outcomes, used for calibration (kept separate from assumptions)."""

    __tablename__ = "actual_events"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    supplier_id: Mapped[str | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(60), default="delay")
    observed_delay_days: Mapped[float] = mapped_column(Float, default=0.0)
    observed_cost: Mapped[float] = mapped_column(Float, default=0.0)
    occurred_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(120), default="ERP")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
