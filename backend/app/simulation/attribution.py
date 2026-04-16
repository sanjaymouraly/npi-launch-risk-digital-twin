"""Risk attribution methods: variance-based Sobol indices and leave-one-out causal probing.

Correlation, one-at-a-time sensitivity and model-based causal attribution are
deliberately kept distinct.  None of these methods establishes real-world
causality; they quantify influence *inside the model*.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable

import numpy as np
from scipy import stats

from app.simulation.context import SimulationContext
from app.simulation.engine import SimulationOptions, run_monte_carlo


def sobol_first_order(
    evaluator: Callable[[np.ndarray], np.ndarray],
    bounds: list[tuple[float, float]],
    n_base: int = 512,
    seed: int = 7,
) -> dict:
    """Saltelli first-order Sobol indices with bootstrap confidence intervals.

    ``evaluator`` receives an (m, k) matrix of inputs and returns m outputs.
    Bounds are in the natural units of each input.
    """
    rng = np.random.default_rng(seed)
    k = len(bounds)
    if k == 0:
        return {"indices": [], "note": "No inputs supplied"}
    low = np.array([b[0] for b in bounds], dtype=float)
    high = np.array([b[1] for b in bounds], dtype=float)
    A = low + rng.random((n_base, k)) * (high - low)
    B = low + rng.random((n_base, k)) * (high - low)
    y_a = np.asarray(evaluator(A), dtype=float)
    y_b = np.asarray(evaluator(B), dtype=float)
    var_y = float(np.var(np.concatenate([y_a, y_b]), ddof=1))
    indices = []
    for i in range(k):
        ab = A.copy()
        ab[:, i] = B[:, i]
        y_ab = np.asarray(evaluator(ab), dtype=float)
        if var_y <= 1e-12:
            s1 = 0.0
            ci = (0.0, 0.0)
        else:
            # Saltelli (2010) first-order estimator.
            s1 = float(np.mean(y_b * (y_ab - y_a)) / var_y)
            boot = []
            for _ in range(200):
                idx = rng.integers(0, n_base, n_base)
                v = float(np.var(np.concatenate([y_a[idx], y_b[idx]]), ddof=1))
                if v > 1e-12:
                    boot.append(float(np.mean(y_b[idx] * (y_ab[idx] - y_a[idx])) / v))
            ci = (float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))) if boot else (s1, s1)
        indices.append(
            {"index": i, "S1": round(s1, 4), "ci_low": round(ci[0], 4), "ci_high": round(ci[1], 4)}
        )
    return {
        "indices": indices,
        "n_base": n_base,
        "evaluations": n_base * (k + 2),
        "seed": seed,
        "variance": round(var_y, 6),
        "method": "Saltelli first-order Sobol estimator",
        "note": "First-order indices neglect interactions; values are model-internal sensitivity measures.",
    }


def ishigami(x: np.ndarray) -> np.ndarray:
    """Standard Sobol benchmark with known first-order indices (0.314, 0.442, 0.0)."""
    return (
        np.sin(x[:, 0])
        + 7 * np.sin(x[:, 1]) ** 2
        + 0.1 * x[:, 2] ** 4 * np.sin(x[:, 0])
    )


def leave_one_out_attribution(
    context: SimulationContext,
    base_options: SimulationOptions,
    drivers: list[dict],
    iterations: int = 600,
    limit: int = 6,
) -> dict:
    """Re-run the simulation with each driver neutralised (common random numbers).

    This is a model-based counterfactual: it answers "how much of the modelled
    launch risk disappears if this driver were removed?", not "what would
    happen in the factory".
    """
    base = run_monte_carlo(
        context,
        replace(base_options, iterations=iterations, progress_callback=None, label="attribution-base"),
    )
    base_makespan = base.summary["makespan"]["mean"]
    base_ontime = base.summary["deadline"]["on_time_probability"]
    rows = []
    for driver in drivers[:limit]:
        kind = driver.get("kind")
        target_id = driver.get("id")
        if not target_id:
            continue
        if kind == "supplier":
            suppliers = dict(context.suppliers)
            if target_id in suppliers:
                suppliers[target_id] = replace(suppliers[target_id], disruption_prob=0.0)
            mutated = context.copy(suppliers=suppliers)
        elif kind == "risk":
            risks = tuple(r for r in context.risks if r.id != target_id)
            mutated = context.copy(risks=risks)
        elif kind == "task":
            tasks = [
                t.with_changes(
                    distribution="fixed", duration=t.duration, risk_factor=0.0, buffer=t.buffer
                )
                if t.id == target_id
                else t
                for t in context.model.tasks
            ]
            mutated = context.copy(model=context.model.copy(tasks=tasks))
        else:
            continue
        result = run_monte_carlo(
            mutated,
            replace(base_options, iterations=iterations, progress_callback=None, label="attribution-loo"),
        )
        rows.append(
            {
                "driver": driver.get("name", target_id),
                "driver_id": target_id,
                "kind": kind,
                "expected_delay_reduction_days": round(
                    base_makespan - result.summary["makespan"]["mean"], 2
                ),
                "on_time_probability_gain": round(
                    result.summary["deadline"]["on_time_probability"] - base_ontime, 4
                ),
                "p90_reduction_days": round(
                    base.summary["makespan"]["p90"] - result.summary["makespan"]["p90"], 2
                ),
            }
        )
    rows.sort(key=lambda r: -r["expected_delay_reduction_days"])
    return {
        "baseline": {
            "mean_makespan": base_makespan,
            "on_time_probability": base_ontime,
            "p90": base.summary["makespan"]["p90"],
            "iterations": iterations,
        },
        "drivers": rows,
        "method": "Leave-one-driver-out simulation with common random numbers",
        "caveat": "Model-internal counterfactual; not evidence of real-world causal effect.",
    }


def paired_delta(
    baseline_samples: list[float], scenario_samples: list[float]
) -> dict:
    """Paired difference statistics for common-random-number comparisons."""
    if not baseline_samples or not scenario_samples:
        return {"paired": False, "reason": "missing samples"}
    if len(baseline_samples) != len(scenario_samples):
        b = np.array(baseline_samples)
        s = np.array(scenario_samples)
        return {
            "paired": False,
            "mean_delta": float(np.mean(s) - np.mean(b)),
            "note": "Samples differ in length; unpaired comparison.",
        }
    delta = np.array(scenario_samples) - np.array(baseline_samples)
    n = len(delta)
    mean = float(np.mean(delta))
    sem = float(np.std(delta, ddof=1) / np.sqrt(n)) if n > 1 else 0.0
    return {
        "paired": True,
        "mean_delta": round(mean, 3),
        "median_delta": round(float(np.median(delta)), 3),
        "p10_delta": round(float(np.percentile(delta, 10)), 3),
        "p90_delta": round(float(np.percentile(delta, 90)), 3),
        "ci95_delta": [round(mean - 1.96 * sem, 3), round(mean + 1.96 * sem, 3)],
        "std_delta": round(float(np.std(delta, ddof=1)), 3),
        "sem_delta": round(sem, 4),
        "probability_improvement": round(float(np.mean(delta < 0)), 4),
        "probability_of_harm": round(float(np.mean(delta > 0)), 4),
        "iterations": n,
        "note": "Negative delta means the scenario finishes earlier than the baseline.",
    }


def spearman_matrix(inputs: np.ndarray, output: np.ndarray, names: list[str]) -> list[dict]:
    rows = []
    for i, name in enumerate(names):
        col = inputs[:, i]
        if np.std(col) < 1e-12:
            continue
        result = stats.spearmanr(col, output)
        rows.append(
            {
                "name": name,
                "correlation": round(float(result.statistic), 4),
                "p_value": float(result.pvalue),
            }
        )
    rows.sort(key=lambda r: -abs(r["correlation"]))
    return rows
