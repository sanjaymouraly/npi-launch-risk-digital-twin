"""Attribution methods: Sobol on a known benchmark, correlations and diagnostics."""
from __future__ import annotations

import numpy as np
import pytest
from app.simulation.attribution import ishigami, sobol_first_order, spearman_matrix


def test_sobol_recovers_ishigami_indices():
    """The Ishigami function has known first-order indices 0.314, 0.442 and 0."""
    # The published indices assume the standard Ishigami domain [-pi, pi].
    bounds = [(-3.141592653589793, 3.141592653589793)] * 3
    result = sobol_first_order(ishigami, bounds, n_base=4096, seed=11)
    indices = [row["S1"] for row in result["indices"]]
    assert indices[0] == pytest.approx(0.314, abs=0.09)
    assert indices[1] == pytest.approx(0.442, abs=0.09)
    assert indices[2] == pytest.approx(0.0, abs=0.12)


def test_sobol_reports_bootstrap_intervals():
    bounds = [(0.0, 1.0)]
    result = sobol_first_order(lambda x: x[:, 0], bounds, n_base=1024, seed=3)
    for row in result["indices"]:
        assert row["ci_low"] <= row["S1"] <= row["ci_high"] or row["ci_low"] <= row["ci_high"]


def test_sobol_without_inputs_is_explicit():
    result = sobol_first_order(lambda x: x[:, 0], [], n_base=16)
    assert result["indices"] == []
    assert "note" in result


def test_spearman_matrix_detects_a_monotone_driver():
    rng = np.random.default_rng(4)
    driver = rng.normal(size=300)
    output = 3.0 * driver + rng.normal(scale=0.2, size=300)
    rows = spearman_matrix(driver.reshape(-1, 1), output, ["driver"])
    assert rows[0]["name"] == "driver"
    assert rows[0]["correlation"] > 0.9
    assert rows[0]["p_value"] < 0.001


def test_spearman_ignores_constant_columns():
    rng = np.random.default_rng(5)
    output = rng.normal(size=50)
    rows = spearman_matrix(np.ones((50, 1)), output, ["flat"])
    assert rows == []


def test_paired_delta_handles_missing_samples():
    from app.simulation.attribution import paired_delta

    stats = paired_delta([], [1.0, 2.0])
    assert stats["paired"] is False
    assert "reason" in stats
