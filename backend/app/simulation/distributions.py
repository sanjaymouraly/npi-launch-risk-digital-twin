"""Validated probability distributions used by the Monte Carlo engine.

All samplers take a uniform draw ``u`` in (0, 1) so that correlated inputs can be
driven by a Gaussian copula while individual marginals stay intact.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

SUPPORTED = {"fixed", "triangular", "pert", "normal", "lognormal", "uniform", "gamma", "weibull"}


class InvalidDistribution(ValueError):
    pass


@dataclass(frozen=True)
class DurationParams:
    distribution: str
    base: float
    minimum: float | None = None
    mode: float | None = None
    maximum: float | None = None
    std_dev: float | None = None

    @property
    def mean(self) -> float:
        """Analytical mean where defined; used for deterministic baselines."""
        d = self.distribution
        if d in ("fixed", "uniform") and d == "fixed":
            return self.base
        if d == "uniform":
            return (self.minimum + self.maximum) / 2  # type: ignore[operator]
        if d in ("triangular", "pert"):
            return (self.minimum + self.mode + self.maximum) / 3  # type: ignore[operator]
        if d in ("normal", "lognormal"):
            return self.base
        return self.base


def make_params(
    distribution: str,
    base: float,
    minimum: float | None = None,
    mode: float | None = None,
    maximum: float | None = None,
    std_dev: float | None = None,
) -> DurationParams:
    dist = (distribution or "fixed").lower()
    if dist not in SUPPORTED:
        raise InvalidDistribution(f"Unsupported distribution '{distribution}'")
    if base is None or not math.isfinite(base) or base < 0:
        raise InvalidDistribution("Duration base must be a finite non-negative number")
    lo = base * 0.8 if minimum is None else float(minimum)
    mo = base if mode is None else float(mode)
    hi = base * 1.25 if maximum is None else float(maximum)
    if dist in ("triangular", "pert"):
        if not (0 <= lo <= mo <= hi) or hi <= lo:
            raise InvalidDistribution(
                f"Triangular/PERT parameters require 0 <= min <= mode <= max and min < max "
                f"(got min={lo}, mode={mo}, max={hi})"
            )
    if dist == "uniform":
        if hi <= lo:
            raise InvalidDistribution("Uniform distribution requires min < max")
    if dist in ("lognormal", "gamma", "weibull"):
        sd = std_dev if std_dev is not None else base * 0.25
        if sd <= 0:
            raise InvalidDistribution(f"{dist} requires a positive standard deviation")
    return DurationParams(
        distribution=dist,
        base=base,
        minimum=lo,
        mode=mo,
        maximum=hi,
        std_dev=std_dev,
    )


def duration_ppf(params: DurationParams, u: np.ndarray | float):
    """Inverse CDF for the task duration distribution."""
    u = np.clip(u, 1e-9, 1 - 1e-9)
    dist = params.distribution
    if dist == "fixed":
        return np.full_like(np.asarray(u, dtype=float), params.base)
    lo, mo, hi = float(params.minimum), float(params.mode), float(params.maximum)
    if dist == "triangular":
        c = (mo - lo) / (hi - lo) if hi > lo else 0.5
        return stats.triang.ppf(u, c=c, loc=lo, scale=hi - lo)
    if dist == "pert":
        lam = 4.0
        alpha = 1 + lam * (mo - lo) / (hi - lo)
        beta = 1 + lam * (hi - mo) / (hi - lo)
        return lo + stats.beta.ppf(u, alpha, beta) * (hi - lo)
    if dist == "uniform":
        return lo + u * (hi - lo)
    if dist == "normal":
        sd = params.std_dev if params.std_dev else max(1e-6, params.base * 0.2)
        return np.maximum(0.0, stats.norm.ppf(u, loc=params.base, scale=sd))
    if dist == "lognormal":
        sd = params.std_dev if params.std_dev else max(1e-6, params.base * 0.25)
        sigma = math.sqrt(math.log(1 + (sd / max(params.base, 1e-6)) ** 2))
        mu = math.log(max(params.base, 1e-6)) - 0.5 * sigma**2
        return stats.lognorm.ppf(u, s=sigma, scale=math.exp(mu))
    if dist == "gamma":
        sd = params.std_dev if params.std_dev else max(1e-6, params.base * 0.25)
        shape = max(1e-6, (params.base / sd) ** 2)
        scale = sd**2 / max(params.base, 1e-6)
        return stats.gamma.ppf(u, a=shape, scale=scale)
    if dist == "weibull":
        sd = params.std_dev if params.std_dev else max(1e-6, params.base * 0.25)
        cv = sd / max(params.base, 1e-6)
        # Method of moments shape approximation.
        shape = max(0.5, cv ** (-1.086)) if cv > 0 else 1.0
        scale = params.base / math.gamma(1 + 1 / shape)
        return stats.weibull_min.ppf(u, c=shape, scale=scale)
    raise InvalidDistribution(dist)


def sample_duration(params: DurationParams, rng: np.random.Generator, uniform_draw: float | None = None):
    u = rng.random() if uniform_draw is None else uniform_draw
    return float(duration_ppf(params, u))


def validate_distributions(items: list[tuple[str, DurationParams]]) -> list[str]:
    errors = []
    for name, params in items:
        try:
            make_params(
                params.distribution,
                params.base,
                params.minimum,
                params.mode,
                params.maximum,
                params.std_dev,
            )
            if params.distribution != "fixed" and params.base <= 0:
                errors.append(f"{name}: stochastic duration must be > 0 working days")
        except InvalidDistribution as exc:
            errors.append(f"{name}: {exc}")
    return errors


def normal_ppf(u):  # noqa: ANN001
    return stats.norm.ppf(np.clip(u, 1e-9, 1 - 1e-9))


def gaussian_copula_uniforms(
    rng: np.random.Generator,
    groups: dict[str, list[str]],
    rho: float = 0.6,
) -> dict[str, float]:
    """Return one correlated uniform per entity (keyed by entity id).

    Entities sharing a correlation group share a latent factor; ``rho`` controls
    how much of the variation is common.  Default 0.6 reflects the empirical
    tendency of qualification and supplier delays to cluster by programme phase.
    """
    rho = min(0.99, max(0.0, rho))
    uniforms: dict[str, float] = {}
    for _group, members in groups.items():
        shared = rng.standard_normal()
        for member in members:
            idio = rng.standard_normal()
            z = rho * shared + math.sqrt(1 - rho**2) * idio
            uniforms[member] = float(stats.norm.cdf(z))
    return uniforms
