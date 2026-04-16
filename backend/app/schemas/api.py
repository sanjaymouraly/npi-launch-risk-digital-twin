"""Request models shared by the API layer."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    product: str | None = None
    version: str | None = None
    status: Literal["planned", "active", "archived"] | None = None
    currency: str | None = None
    start_date: str | None = None
    launch_deadline: str | None = None
    baseline_launch_date: str | None = None
    working_days_per_week: int | None = Field(default=None, ge=1, le=7)
    holidays: list[str] | None = None
    timezone: str | None = None
    delay_cost_per_day: float | None = Field(default=None, ge=0)
    intervention_budget: float | None = Field(default=None, ge=0)
    yield_start: float | None = Field(default=None, ge=0, le=1)
    yield_target: float | None = Field(default=None, ge=0, le=1)
    ramp_days: int | None = Field(default=None, ge=1)
    unit_margin: float | None = Field(default=None, ge=0)
    planned_volume: int | None = Field(default=None, ge=0)
    owner: str | None = None
    tags: list[str] | None = None


class SimulationRequest(BaseModel):
    iterations: int = Field(default=2000, ge=50, le=50000)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    scenario_id: str | None = None
    label: str = ""
    correlation_rho: float = Field(default=0.6, ge=0, le=0.99)
    capacity_loss_prob: float = Field(default=0.02, ge=0, le=1)
    absenteeism_prob: float = Field(default=0.02, ge=0, le=1)
    transport_delay_prob: float = Field(default=0.015, ge=0, le=1)
    supplier_disruption_enabled: bool = True
    material_constraints_enabled: bool = True
    validate_iterations: int = Field(default=0, ge=0, le=10)
    solver_time_limit: float = Field(default=3.0, ge=1, le=60)
    async_job: bool = True
    idempotency_key: str | None = None


class InterventionIn(BaseModel):
    type: str
    target_type: str = "task"
    target_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    cost: float = 0.0
    label: str = ""
    id: str | None = None


class ScenarioCreate(BaseModel):
    name: str
    description: str = ""
    interventions: list[InterventionIn] = Field(default_factory=list)
    parent_id: str | None = None
    clone_from: str | None = None


class ScenarioPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    status: Literal["draft", "approved", "archived"] | None = None
    interventions: list[InterventionIn] | None = None


class CompareRequest(BaseModel):
    scenario_id: str
    baseline_scenario_id: str | None = None
    iterations: int = Field(default=800, ge=100, le=20000)
    seed: int = 42
    include_samples: bool = False


class OptimizationConstraints(BaseModel):
    max_selected: int = Field(default=4, ge=1, le=10)
    min_benefit_days: float = Field(default=0, ge=0)
    max_added_capacity: float = Field(default=4.0, ge=0)
    min_reliability: float = Field(default=0, ge=0, le=1)
    exclude_types: list[str] = Field(default_factory=list)


class OptimizationRequest(BaseModel):
    budget: float | None = Field(default=None, ge=0)
    objective: Literal[
        "max_probability",
        "min_expected_delay",
        "min_cost",
        "min_downside_risk",
        "min_combined_exposure",
        "weighted",
    ] = "min_combined_exposure"
    weights: dict[str, float] = Field(
        default_factory=lambda: {"delay": 1.0, "probability": 1.0, "cost": 1.0}
    )
    constraints: OptimizationConstraints = Field(default_factory=OptimizationConstraints)
    pilot_iterations: int = Field(default=300, ge=100, le=2000)
    verification_iterations: int = Field(default=800, ge=200, le=5000)
    seed: int = 42
    async_job: bool = True
    idempotency_key: str | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    provider: str | None = None
    offline: bool = False


class ProviderPatch(BaseModel):
    enabled: bool | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    timeout_seconds: float | None = Field(default=None, ge=5, le=600)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    monthly_budget_usd: float | None = Field(default=None, ge=0)
    input_price_per_mtok: float | None = Field(default=None, ge=0)
    output_price_per_mtok: float | None = Field(default=None, ge=0)
    extra: dict[str, Any] | None = None

    @field_validator("api_key")
    @classmethod
    def _trim_key(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SobolRequest(BaseModel):
    input_ids: list[str] = Field(default_factory=list, max_length=8)
    n_base: int = Field(default=256, ge=64, le=2048)
    iterations: int = Field(default=200, ge=1, le=2000)
    seed: int = 7


class LeaveOneOutRequest(BaseModel):
    iterations: int = Field(default=600, ge=200, le=5000)
    limit: int = Field(default=6, ge=1, le=10)
    seed: int = 42
