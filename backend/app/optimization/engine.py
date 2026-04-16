"""Constrained selection of launch-recovery portfolios, verified by simulation.

Pipeline
--------
1. Build a candidate catalog from the *actual* project (suppliers, critical tasks,
   bottlenecks, parallelisable dependencies).
2. Estimate each candidate's effect with a small paired Monte Carlo pilot
   (common random numbers) -- estimates are labelled and carry sampling noise.
3. Select portfolios with OR-Tools CP-SAT under budget, exclusivity, prerequisite,
   headcount and reliability constraints, and trace a cost/benefit Pareto front.
4. Re-simulate the selected and near-optimal portfolios with more iterations and
   report the verified benefit, net economic value and new bottlenecks.
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Callable

from ortools.sat.python import cp_model

from app.optimization.interventions import (
    InterventionSpec,
    apply_interventions,
    intervention_cost_estimate,
)
from app.scheduling.cpsat import CpsatOptions, resource_constrained_schedule
from app.scheduling.sgs import resource_utilization, schedule_sgs
from app.simulation.attribution import paired_delta
from app.simulation.context import SimulationContext
from app.simulation.engine import SimulationOptions, run_monte_carlo

OBJECTIVES = {
    "max_probability",
    "min_expected_delay",
    "min_cost",
    "min_downside_risk",
    "min_combined_exposure",
    "weighted",
}


def generate_catalog(context: SimulationContext) -> list[InterventionSpec]:
    model = context.model
    tasks = model.task_map()
    resources = model.resource_map()
    sgs = schedule_sgs(model, calendar=context.calendar)
    utilization = resource_utilization(model, sgs)
    critical_chain = set(sgs.critical_chain)
    catalog: list[InterventionSpec] = []
    seen: set[str] = set()

    def add(spec: InterventionSpec) -> None:
        if spec.id not in seen:
            catalog.append(spec)
            seen.add(spec.id)

    # --- supplier interventions -------------------------------------------
    supplier_risk = sorted(
        context.suppliers.values(),
        key=lambda s: -(s.disruption_prob * max(1.0, s.disruption_delay_days)),
    )
    for supplier in supplier_risk[:2]:
        if supplier.disruption_prob <= 0.005:
            continue
        comps = [c for c in context.components.values() if c.supplier_id == supplier.id]
        if not comps:
            continue
        comp = max(comps, key=lambda c: c.criticality * c.unit_cost * c.qty_per_unit)
        alternatives = [
            s for s in context.suppliers.values()
            if s.id != supplier.id and s.qualified and s.disruption_prob < supplier.disruption_prob
        ]
        if alternatives:
            alt = min(alternatives, key=lambda s: (s.disruption_prob, s.lead_time_days))
            add(
                InterventionSpec(
                    id=f"replace-{supplier.id[:8]}",
                    type="replace_supplier",
                    label=f"Re-source {comp.name} from {alt.name}",
                    target_type="supplier",
                    target_id=supplier.id,
                    params={"component_id": comp.id, "supplier_id": alt.id},
                    cost=intervention_cost_estimate(
                        "replace_supplier", component=comp, supplier=alt,
                        planned_volume=context.planned_volume,
                    ),
                    category="supply",
                    exclusivity_group=f"source-{comp.id}",
                    notes=f"Replaces {supplier.name} (disruption {supplier.disruption_prob:.0%}) with {alt.name}.",
                )
            )
        add(
            InterventionSpec(
                id=f"split-{comp.id[:8]}",
                type="split_procurement",
                label=f"Dual-source {comp.name} (60/40 split)",
                target_type="component",
                target_id=comp.id,
                params={"component_id": comp.id},
                cost=intervention_cost_estimate(
                    "split_procurement", component=comp, planned_volume=context.planned_volume
                ),
                category="supply",
                exclusivity_group=f"source-{comp.id}",
                notes="Creates a qualified secondary source; disruption probability and lead time are reduced, not eliminated.",
            )
        )
        add(
            InterventionSpec(
                id=f"expedite-sup-{supplier.id[:8]}",
                type="expedite_supplier",
                label=f"Expedite {supplier.name} deliveries (-20% lead time)",
                target_type="supplier",
                target_id=supplier.id,
                params={"supplier_id": supplier.id, "reduction_pct": 0.2},
                cost=intervention_cost_estimate(
                    "expedite_supplier", component=comp, planned_volume=context.planned_volume
                ),
                category="supply",
                notes="Air-freight/premium freight assumption on affected components.",
            )
        )

    # --- schedule interventions on critical, long tasks -------------------
    candidates = sorted(
        model.tasks,
        key=lambda t: (-(t.base_duration * (2.0 if t.id in critical_chain else 1.0))),
    )
    for task in candidates[:5]:
        if task.base_duration < 2 or task.is_milestone:
            continue
        add(
            InterventionSpec(
                id=f"expedite-{task.id[:8]}",
                type="expedite_task",
                label=f"Expedite {task.name} (-20% duration)",
                target_type="task",
                target_id=task.id,
                params={"task_id": task.id, "reduction_pct": 0.2},
                cost=intervention_cost_estimate("expedite_task", task=task),
                category="schedule",
                notes="Adds crew/overtime to compress the activity.",
            )
        )
        if "tool" in task.phase.lower() or "tool" in task.name.lower():
            add(
                InterventionSpec(
                    id=f"tooling-{task.id[:8]}",
                    type="tooling_readiness",
                    label=f"Accelerate tooling: {task.name} (-35%)",
                    target_type="task",
                    target_id=task.id,
                    params={"task_id": task.id, "reduction_pct": 0.35},
                    cost=intervention_cost_estimate("tooling_readiness", task=task),
                    category="tooling",
                    notes="Parallel tool trials / external tool shop.",
                )
            )

    # --- capacity interventions on bottlenecks ---------------------------
    bottlenecks = sorted(utilization.values(), key=lambda u: -u["utilization"])[:3]
    for entry in bottlenecks:
        resource = resources.get(entry["resource_id"])
        if resource is None or entry["utilization"] < 0.55:
            continue
        add(
            InterventionSpec(
                id=f"capacity-{resource.id[:8]}",
                type="add_capacity",
                label=f"Add {resource.name} capacity (+0.5)",
                target_type="resource",
                target_id=resource.id,
                params={"resource_id": resource.id, "capacity_delta": 0.5},
                cost=intervention_cost_estimate("add_capacity", resource=resource),
                category="capacity",
                exclusivity_group=f"capacity-{resource.id}",
                notes=f"Current utilization {entry['utilization']:.0%}.",
            )
        )
        add(
            InterventionSpec(
                id=f"overtime-{resource.id[:8]}",
                type="add_overtime",
                label=f"Overtime on {resource.name} (+15% availability)",
                target_type="resource",
                target_id=resource.id,
                params={"resource_id": resource.id, "availability_delta": 0.15},
                cost=intervention_cost_estimate("add_overtime", resource=resource),
                category="capacity",
                exclusivity_group=f"capacity-{resource.id}",
                notes="Temporary shift extension; capacity, not calendar, changes.",
            )
        )

    # --- parallelisation candidates --------------------------------------
    gate_ids = {t.id for t in model.tasks if t.is_gate}
    parallel_candidates = [
        e for e in model.edges
        if e.type == "FS" and e.from_id not in gate_ids and e.to_id not in gate_ids
    ]
    for edge in parallel_candidates[:2]:
        a = tasks.get(edge.from_id)
        b = tasks.get(edge.to_id)
        if not a or not b:
            continue
        add(
            InterventionSpec(
                id=f"parallel-{a.id[:6]}-{b.id[:6]}",
                type="parallelize",
                label=f"Overlap {a.name} and {b.name}",
                target_type="dependency",
                target_id=f"{a.id}->{b.id}",
                params={"from_task_id": a.id, "to_task_id": b.id},
                cost=intervention_cost_estimate("parallelize"),
                category="schedule",
                notes="Removes one finish-to-start link; rejected automatically if it creates a cycle.",
            )
        )

    # --- material buffering and scope ------------------------------------
    single_source = sorted(
        (c for c in context.components.values() if c.single_source and c.criticality >= 0.6),
        key=lambda c: -c.criticality,
    )[:2]
    for comp in single_source:
        add(
            InterventionSpec(
                id=f"safety-{comp.id[:8]}",
                type="increase_safety_stock",
                label=f"Buffer {comp.name} (+10 days safety stock)",
                target_type="component",
                target_id=comp.id,
                params={"component_id": comp.id, "days": 10},
                cost=intervention_cost_estimate(
                    "increase_safety_stock", component=comp, planned_volume=context.planned_volume
                ),
                category="supply",
                notes="Holding-cost assumption on 30-day demand.",
            )
        )
    optional = [t for t in model.tasks if t.optional and t.base_duration >= 2]
    for task in optional[:1]:
        add(
            InterventionSpec(
                id=f"scope-{task.id[:8]}",
                type="reduce_scope",
                label=f"Reduce scope: {task.name} (-50%)",
                target_type="task",
                target_id=task.id,
                params={"task_id": task.id, "reduction_pct": 0.5},
                cost=intervention_cost_estimate("reduce_scope"),
                category="scope",
                notes="Cost saving; may remove coverage — review engineering sign-off.",
            )
        )
    return catalog


def estimate_catalog(
    context: SimulationContext,
    catalog: list[InterventionSpec],
    base_options: SimulationOptions,
    iterations: int = 300,
    limit: int = 14,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[list[InterventionSpec], dict]:
    """Pilot simulation per candidate using common random numbers."""
    pilot = replace(base_options, iterations=iterations, label="catalog-baseline")
    base = run_monte_carlo(context, pilot)
    base_delay_cost = base.summary["deadline"]["expected_delay_cost"]
    base_ontime = base.summary["deadline"]["on_time_probability"]
    base_p90 = base.summary["makespan"]["p90"]
    estimated: list[InterventionSpec] = []
    rejected = 0
    for i, spec in enumerate(catalog[:limit]):
        if progress:
            progress(0.05 + 0.25 * i / max(1, min(len(catalog), limit)), f"Estimating {spec.label}")
        scenario_context, warnings = apply_interventions(context, [spec])
        if warnings and any("rejected" in w for w in warnings):
            rejected += 1
            continue
        result = run_monte_carlo(
            scenario_context, replace(base_options, iterations=iterations, label=f"estimate-{spec.id}")
        )
        delta = paired_delta(base.samples, result.samples)
        benefit_days = -float(delta.get("mean_delta", 0.0))
        ontime_gain = result.summary["deadline"]["on_time_probability"] - base_ontime
        p90_gain = base_p90 - result.summary["makespan"]["p90"]
        estimated.append(
            replace(
                spec,
                expected_benefit_days=round(benefit_days, 3),
                expected_on_time_gain=round(ontime_gain, 4),
                estimated=True,
                estimate_iterations=iterations,
                notes=(
                    spec.notes
                    + f" Pilot estimate: {benefit_days:+.2f} d (P90 {p90_gain:+.2f} d, on-time {ontime_gain:+.1%}); "
                    f"paired n={iterations}, cost {spec.cost:,.0f}."
                ).strip(),
            )
        )
        # attach p90 gain in params for objective use (kept explicit, not hidden)
        estimated[-1] = replace(
            estimated[-1], params={**estimated[-1].params, "_p90_gain_days": round(p90_gain, 3)}
        )
    meta = {
        "pilot_iterations": iterations,
        "baseline_mean": base.summary["makespan"]["mean"],
        "baseline_p90": base_p90,
        "baseline_on_time": base_ontime,
        "baseline_delay_cost": base_delay_cost,
        "rejected": rejected,
        "catalog_size": len(catalog),
        "estimated_count": len(estimated),
        "method": "Paired pilot Monte Carlo with common random numbers",
    }
    return estimated, meta


def select_portfolios(
    catalog: list[InterventionSpec],
    budget: float,
    objective: str = "max_probability",
    weights: dict | None = None,
    constraints: dict | None = None,
    delay_cost_per_day: float = 25000.0,
) -> dict:
    objective = objective if objective in OBJECTIVES else "max_probability"
    weights = weights or {"delay": 1.0, "probability": 1.0, "cost": 1.0}
    constraints = constraints or {}
    candidates = [c for c in catalog if c.expected_benefit_days is not None]
    if not candidates:
        return {
            "status": "NO_ESTIMATES",
            "selected": [],
            "selected_ids": [],
            "total_cost": 0.0,
            "estimated_benefit_days": 0.0,
            "pareto": [],
            "message": "No candidates could be estimated.",
        }

    min_benefit = float(constraints.get("min_benefit_days", 0.0))
    min_reliability = float(constraints.get("min_reliability", 0.0))
    max_selected = int(constraints.get("max_selected", 4))
    max_added_capacity = float(constraints.get("max_added_capacity", 4.0))

    def score(c: InterventionSpec) -> float:
        benefit = max(0.0, c.expected_benefit_days or 0.0)
        prob = max(0.0, c.expected_on_time_gain or 0.0)
        p90 = max(0.0, float(c.params.get("_p90_gain_days", 0.0)))
        if objective == "min_expected_delay":
            return benefit
        if objective == "max_probability":
            return prob * 1000 + benefit
        if objective == "min_cost":
            return -c.cost / 1000.0
        if objective == "min_downside_risk":
            return p90 * 1.2 + benefit * 0.4
        if objective == "min_combined_exposure":
            return (benefit * delay_cost_per_day - c.cost) / 1000.0
        # weighted
        return (
            benefit * float(weights.get("delay", 1.0))
            + prob * 1000 * float(weights.get("probability", 1.0))
            - c.cost / 1000.0 * float(weights.get("cost", 1.0))
        )

    def solve(cap: float) -> dict:
        model = cp_model.CpModel()
        xs = [model.NewBoolVar(f"x_{i}") for i in range(len(candidates))]
        costs = [int(round(max(-1e9, c.cost))) for c in candidates]
        model.Add(sum(xs[i] * costs[i] for i in range(len(candidates))) <= int(round(cap)))
        model.Add(sum(xs) <= max_selected)
        if min_benefit > 0:
            scaled = [int(round(max(0.0, c.expected_benefit_days or 0.0) * 100)) for c in candidates]
            model.Add(sum(xs[i] * scaled[i] for i in range(len(candidates))) >= int(round(min_benefit * 100)))
        if min_reliability > 0:
            # Conservative proxy: disqualify candidates carrying explicitly low reliability.
            for i, c in enumerate(candidates):
                if float(c.params.get("reliability", 1.0)) < min_reliability:
                    model.Add(xs[i] == 0)
        groups: dict[str, list[int]] = {}
        for i, c in enumerate(candidates):
            if c.exclusivity_group:
                groups.setdefault(c.exclusivity_group, []).append(i)
        for indices in groups.values():
            if len(indices) > 1:
                model.Add(sum(xs[i] for i in indices) <= 1)
        by_id = {c.id: i for i, c in enumerate(candidates)}
        for i, c in enumerate(candidates):
            for req in c.requires:
                if req in by_id:
                    model.Add(xs[i] <= xs[by_id[req]])
        capacity_terms = [
            xs[i] * int(round(float(c.params.get("capacity_delta", 0)) * 100))
            for i, c in enumerate(candidates)
            if c.type in ("add_capacity", "add_resource")
        ]
        if capacity_terms:
            model.Add(sum(capacity_terms) <= int(round(max_added_capacity * 100)))
        scale = 1000
        model.Maximize(sum(int(round(score(c) * scale)) * xs[i] for i, c in enumerate(candidates)))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5.0
        solver.parameters.num_search_workers = 8
        status = solver.Solve(model)
        picked = [candidates[i] for i in range(len(candidates)) if solver.Value(xs[i]) > 0.5] \
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else []
        return {
            "picked": picked,
            "cost": sum(c.cost for c in picked),
            "benefit": sum(max(0.0, c.expected_benefit_days or 0.0) for c in picked),
            "status": solver.StatusName(status),
            "optimal": status == cp_model.OPTIMAL,
        }

    best = solve(budget)

    # Pareto front over budget fractions (real CP-SAT solves, not interpolation).
    pareto = []
    points = []
    for fraction in (0.0, 0.15, 0.3, 0.45, 0.6, 0.8, 1.0):
        cap = budget * fraction
        result = solve(cap)
        points.append((round(result["cost"], 2), round(result["benefit"], 2), result["picked"]))
    points.sort(key=lambda p: (p[0], -p[1]))
    best_benefit = -math.inf
    for cost, benefit, picked in points:
        if benefit > best_benefit + 1e-9:
            pareto.append(
                {
                    "cost": cost,
                    "benefit_days": benefit,
                    "interventions": [c.id for c in picked],
                    "labels": [c.label for c in picked],
                }
            )
            best_benefit = benefit

    selected = best["picked"]
    return {
        "status": best["status"],
        "optimal": best["optimal"],
        "selected": [c.to_dict() for c in selected],
        "selected_ids": [c.id for c in selected],
        "selected_specs": selected,
        "total_cost": round(best["cost"], 2),
        "estimated_benefit_days": round(best["benefit"], 2),
        "budget": budget,
        "budget_utilization": round(best["cost"] / budget, 4) if budget > 0 else 0.0,
        "objective": objective,
        "pareto": pareto,
        "feasibility": {
            "budget_ok": best["cost"] <= budget + 1e-6,
            "exclusivity_ok": _check_exclusivity(selected),
            "prerequisites_ok": _check_prerequisites(selected),
            "max_selected_ok": len(selected) <= max_selected,
            "notes": [
                "Portfolio benefits are additive in the optimiser; the simulation verification stage measures the true combined effect.",
            ],
        },
    }


def _check_exclusivity(selected: list[InterventionSpec]) -> bool:
    groups = [c.exclusivity_group for c in selected if c.exclusivity_group]
    return len(groups) == len(set(groups))


def _check_prerequisites(selected: list[InterventionSpec]) -> bool:
    ids = {c.id for c in selected}
    return all(req in ids for c in selected for req in c.requires)


def verify_portfolios(
    context: SimulationContext,
    portfolios: list[list[InterventionSpec]],
    base_options: SimulationOptions,
    iterations: int = 800,
    progress: Callable[[float, str], None] | None = None,
    budget: float | None = None,
) -> dict:
    baseline = run_monte_carlo(
        context, replace(base_options, iterations=iterations, label="optimization-baseline")
    )
    base_delay_cost = baseline.summary["deadline"]["expected_delay_cost"]
    base_incremental = baseline.summary["cost"]["expected_incremental_cost"]
    details = []
    seen_signatures = set()
    for idx, portfolio in enumerate(portfolios):
        signature = tuple(sorted(c.id for c in portfolio))
        if not portfolio or signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        if progress:
            progress(0.4 + 0.4 * idx / max(1, len(portfolios)), f"Verifying portfolio {idx + 1}")
        scenario_context, warnings = apply_interventions(context, portfolio)
        result = run_monte_carlo(
            scenario_context,
            replace(base_options, iterations=iterations, label=f"verify-portfolio-{idx + 1}"),
        )
        delta = paired_delta(baseline.samples, result.samples)
        intervention_cost = sum(c.cost for c in portfolio)
        delay_cost_avoided = base_delay_cost - result.summary["deadline"]["expected_delay_cost"]
        incremental_avoided = base_incremental - result.summary["cost"]["expected_incremental_cost"]
        net_benefit = incremental_avoided - intervention_cost
        schedule_check = resource_constrained_schedule(
            scenario_context.model,
            scenario_context.calendar,
            CpsatOptions(time_limit_seconds=6, compute_float=False),
        )
        details.append(
            {
                "intervention_ids": [c.id for c in portfolio],
                "labels": [c.label for c in portfolio],
                "intervention_cost": round(intervention_cost, 2),
                "simulation": {
                    "mean_makespan": result.summary["makespan"]["mean"],
                    "p50": result.summary["makespan"]["p50"],
                    "p90": result.summary["makespan"]["p90"],
                    "on_time_probability": result.summary["deadline"]["on_time_probability"],
                    "expected_delay_days": result.summary["deadline"]["expected_delay_days"],
                    "expected_delay_cost": result.summary["deadline"]["expected_delay_cost"],
                    "expected_incremental_cost": result.summary["cost"]["expected_incremental_cost"],
                    "summary": result.summary,
                },
                "delta": delta,
                "delay_cost_avoided": round(delay_cost_avoided, 2),
                "incremental_cost_avoided": round(incremental_avoided, 2),
                "net_economic_benefit": round(net_benefit, 2),
                "roi": round(net_benefit / intervention_cost, 3) if intervention_cost > 0 else None,
                "budget_utilization": round(intervention_cost / budget, 4) if budget and budget > 0 else None,
                "new_bottlenecks": result.summary.get("deterministic", {}),
                "schedule_verification": {
                    "feasible": bool(schedule_check.get("feasible")),
                    "makespan": schedule_check.get("makespan"),
                    "status": schedule_check.get("status"),
                    "conflicts": schedule_check.get("conflicts", [])[:5],
                    "bottlenecks": schedule_check.get("bottlenecks", [])[:3],
                    "deadline": schedule_check.get("deadline"),
                },
                "warnings": warnings,
            }
        )
    details.sort(key=lambda d: -d["net_economic_benefit"])
    return {
        "baseline": {
            "mean_makespan": baseline.summary["makespan"]["mean"],
            "p90": baseline.summary["makespan"]["p90"],
            "on_time_probability": baseline.summary["deadline"]["on_time_probability"],
            "expected_delay_cost": base_delay_cost,
            "expected_incremental_cost": base_incremental,
            "iterations": iterations,
            "summary": baseline.summary,
        },
        "portfolios": details,
        "iterations": iterations,
        "selection_rule": "Highest verified net economic benefit (delay + disruption cost avoided minus intervention cost).",
    }


def pareto_alternative_portfolios(selection: dict, limit: int = 3) -> list[list[InterventionSpec]]:
    """Return the recommended portfolio first, then distinct Pareto alternatives."""
    by_id = {c.id: c for c in selection.get("selected_specs", [])}
    portfolios: list[list[InterventionSpec]] = [list(by_id.values())] if by_id else []
    catalog_by_id = {c.id: c for c in selection.get("_catalog", [])}
    for point in selection.get("pareto", []):
        portfolio = [catalog_by_id[i] for i in point["interventions"] if i in catalog_by_id]
        signature = tuple(sorted(c.id for c in portfolio))
        if portfolio and signature not in {tuple(sorted(c.id for c in p)) for p in portfolios}:
            portfolios.append(portfolio)
        if len(portfolios) >= limit:
            break
    return portfolios
