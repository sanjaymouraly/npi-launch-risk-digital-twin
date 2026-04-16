"""Model registry — importing this module registers every mapper."""
from app.models.audit import (
    AIConversation,
    AIMessage,
    AIProviderConfig,
    AuditLog,
    CalibrationRecord,
    SimulationSnapshot,
)
from app.models.project import Milestone, Project, ProjectMember, User
from app.models.resource import Resource, TaskResource
from app.models.risk import ECO, MitigationPlan, Risk, ValidationTest
from app.models.scenario import Intervention, Scenario
from app.models.simulation import Job, OptimizationRun, SimulationRun
from app.models.supply import (
    ActualEvent,
    Component,
    Inventory,
    PurchaseOrder,
    Quote,
    Supplier,
    TaskComponent,
)
from app.models.task import Dependency, Task

__all__ = [
    "AIConversation",
    "AIMessage",
    "AIProviderConfig",
    "ActualEvent",
    "AuditLog",
    "CalibrationRecord",
    "Component",
    "Dependency",
    "ECO",
    "Intervention",
    "Inventory",
    "Job",
    "Milestone",
    "MitigationPlan",
    "OptimizationRun",
    "Project",
    "ProjectMember",
    "PurchaseOrder",
    "Quote",
    "Resource",
    "Risk",
    "Scenario",
    "SimulationRun",
    "SimulationSnapshot",
    "Supplier",
    "Task",
    "TaskComponent",
    "TaskResource",
    "User",
    "ValidationTest",
]
