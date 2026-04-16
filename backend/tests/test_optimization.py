"""Interventions and portfolio optimisation."""
from __future__ import annotations

import pytest
from app.optimization.engine import (
    estimate_catalog,
    generate_catalog,
    pareto_alternative_portfolios,
    select_portfolios,
    verify_portfolios,
)
from app.optimization.interventions import SUPPORTED_INTERVENTIONS, apply_interventions
from app.simulation.context import build_context
from app.simulation.engine import SimulationOptions


@pytest.fixture()
def context(db, project_id):
    from app.models import Project

    return build_context(db, db.get(Project, project_id))


def test_catalog_is_derived_from_the_real_project(context):
    catalog = generate_catalog(context)
    assert catalog
    for spec in catalog:
        assert spec.type in SUPPORTED_INTERVENTIONS
        assert spec.cost >= 0
        assert spec.label


def test_expedite_task_shortens_the_task(context):
    catalog = generate_catalog(context)
    spec = next(item for item in catalog if item.type == "expedite_task")
    mutated, warnings = apply_interventions(context, [spec])
    assert not warnings
    original = context.model.task_map()[spec.params["task_id"]]
    changed = mutated.model.task_map()[spec.params["task_id"]]
    assert changed.duration < original.duration


def test_replace_supplier_updates_material_release(context):
    catalog = generate_catalog(context)
    spec = next((item for item in catalog if item.type == "replace_supplier"), None)
    if spec is None:
        pytest.skip("no replace_supplier candidate for this program")
    mutated, warnings = apply_interventions(context, [spec])
    assert not warnings
    component_id = spec.params["component_id"]
    original = context.components[component_id]
    changed = mutated.components[component_id]
    assert changed.supplier_id != original.supplier_id
    # The per-task material requirement must follow the new supplier, otherwise
    # the intervention would be a no-op inside the simulation.
    needs = [
        need
        for task in mutated.model.tasks
        for need in task.materials
        if need.component_id == component_id
    ]
    assert needs
    assert all(need.supplier_id == changed.supplier_id for need in needs)


def test_split_procurement_lowers_disruption_exposure(context):
    catalog = generate_catalog(context)
    spec = next((item for item in catalog if item.type == "split_procurement"), None)
    if spec is None:
        pytest.skip("no split_procurement candidate for this program")
    mutated, warnings = apply_interventions(context, [spec])
    assert not warnings
    component = mutated.components[spec.params["component_id"]]
    supplier = mutated.suppliers[component.supplier_id]
    assert supplier.dual_source is True
    assert supplier.disruption_prob < 1.0


def test_selection_respects_the_budget(context):
    catalog = generate_catalog(context)
    options = SimulationOptions(seed=42, iterations=120)
    catalog, _ = estimate_catalog(context, catalog, options, iterations=120, limit=4)
    selection = select_portfolios(
        catalog,
        budget=5000.0,
        objective="min_combined_exposure",
        constraints={"max_selected": 3},
    )
    assert selection["total_cost"] <= 5000.0
    assert selection["feasibility"]["budget_ok"] is True
    assert len(selection["selected"]) <= 3


def test_verification_returns_a_baseline_and_portfolios(context):
    catalog = generate_catalog(context)
    options = SimulationOptions(seed=42, iterations=120)
    catalog, _ = estimate_catalog(context, catalog, options, iterations=120, limit=4)
    selection = select_portfolios(
        catalog,
        budget=20000.0,
        objective="min_combined_exposure",
        constraints={"max_selected": 2},
    )
    specs = selection.get("selected_specs") or []
    verification = verify_portfolios(
        context,
        [specs] if specs else [],
        options,
        iterations=150,
        budget=20000.0,
    )
    assert verification["baseline"]["iterations"] == 150
    assert "portfolios" in verification
    for portfolio in verification["portfolios"]:
        assert portfolio["simulation"]["summary"]["engine"]["iterations"] == 150
        assert portfolio["schedule_verification"]["feasible"] is True
        assert portfolio["budget_utilization"] is not None
        assert portfolio["net_economic_benefit"] is not None


def test_pareto_alternatives_are_distinct(context):
    catalog = generate_catalog(context)
    options = SimulationOptions(seed=42, iterations=120)
    catalog, _ = estimate_catalog(context, catalog, options, iterations=120, limit=4)
    selection = select_portfolios(
        catalog,
        budget=50000.0,
        objective="min_combined_exposure",
        constraints={"max_selected": 3},
    )
    alternatives = pareto_alternative_portfolios(selection, limit=3)
    assert len(alternatives) <= 3
    for alternative in alternatives:
        assert alternative != selection["selected"]
