# Validation report

Everything below was measured by the code in this repository — by the test suite,
by `scripts/bootstrap_demo.py`, and by `scripts/benchmark.py`. Where a claim cannot
be measured, the report says so.

*Reference machine*: single container, Python 3.14, OR-Tools 9.15, 8 solver workers.
*Demo data*: the four synthetic programs in `data/samples/` (2,000 Monte Carlo
trials, seed 42, 150,000 USD intervention budget).

---

## 1. What is verified, and how

| Claim | Method | Where |
|---|---|---|
| Working-day arithmetic is exact | Property test: 150 random calendars (offsets, holidays, 2–7 day weeks) — `from_date(to_date(n)) == n`, monotonicity, never on a holiday | `backend/tests/test_calendar.py` |
| All four precedence types are supported | Unit tests for FS/SS/FF/SF with lags, plus cycle detection | `backend/tests/test_scheduling.py` |
| The engines agree on hand-checked schedules | Golden cases (serial chain, parallel fork, single-resource bottleneck) verified against CPM, SGS **and** CP-SAT | `backend/tests/test_golden_cases.py` |
| The simulation scheduler is resource-feasible | Property test: random task sets and capacities — the number of simultaneously running tasks never exceeds the capacity | `backend/tests/test_simulation.py` |
| The Monte Carlo is reproducible | Same seed → identical sample vector; different seed → different vector | `backend/tests/test_simulation.py` |
| A rebuild reproduces the forecast | Two throw-away databases, same program JSON, same seed → identical entity ids and identical sample digest | `backend/tests/test_reproducibility.py` |
| Percentiles are monotone and correctly ordered | Assertion on P10 ≤ P50 ≤ P80 ≤ P90 ≤ P95 ≤ max for every run | `backend/tests/test_simulation.py` |
| Sobol indices are correctly estimated | Ishigami benchmark with published first-order indices (0.3139, 0.4424, 0) | `backend/tests/test_attribution.py` |
| Interventions change the model | Every intervention type is applied to a real program and asserted to mutate the planning model (durations, capacity, suppliers, material needs, logic) | `backend/tests/test_optimization.py` |
| Budgets and constraints hold | The selected portfolio never exceeds the budget, the headcount limit, exclusivity groups or prerequisites | `backend/tests/test_optimization.py` |
| The optimiser's recommendation is verified | Selected portfolios are re-simulated and re-scheduled with CP-SAT before they are recommended | `backend/tests/test_optimization.py`, `backend/app/optimization/engine.py` |
| The API contract holds | Status codes, error shape (`code`/`message`/`request_id`), job lifecycle, import/export round-trips | `backend/tests/test_api.py`, `test_import_export.py` |
| The schema is reproducible from migrations | `alembic upgrade head` on an empty database creates every ORM table; `downgrade base` removes them | `backend/tests/test_migrations.py` |
| The copilot is grounded | Offline answers must cite records; provider failure degrades to offline with a reason; budget exhaustion degrades to offline | `backend/tests/test_ai.py` |
| Secrets never leak | Provider keys are encrypted, masked in responses, and redacted in logs (including the JSON-formatter path) | `backend/tests/test_security.py` |
| The UI has no runtime errors | Playwright drives every page, exercises the paired comparison and both AI providers, and fails on any console error or 4xx/5xx response | `scripts/capture_screenshots.py`, `docs/screenshot-report.json` |

**118 backend tests pass** (`pytest`), plus a strict TypeScript build
(`tsc --noEmit && vite build`) for the frontend.

---

## 2. Solver gap: how far is the simulation scheduler from optimal?

The Monte Carlo uses a serial schedule generation scheme (SGS): it is exact for
*feasibility* but heuristic for *optimality*. The platform measures the gap against
the CP-SAT optimum instead of assuming it is zero.

| Program | CPM (logic only) | CP-SAT optimum | SGS base schedule | Gap (SGS − optimum) | Gap % |
|---|---:|---:|---:|---:|---:|
| Aurora X1 | 168 d | 178 d (OPTIMAL) | 184.0 d | **+6.0 d** | 3.37 % |
| Helios EV | 202 d | 205 d (OPTIMAL) | 205.0 d | 0.0 d | 0.00 % |
| Titan H7 | 153 d | 181 d (OPTIMAL) | 181.0 d | 0.0 d | 0.00 % |
| Vector 5G | 178 d | 225 d (OPTIMAL) | 225.0 d | 0.0 d | 0.00 % |

*Consequence*: simulated P50 values carry an optimism of up to 6 working days for
Aurora. Users who need a tighter bound can enable `validate_iterations` on a run,
which re-solves CP-SAT per trial and reports the gap explicitly in
`summary.solver_validation`.

*Also visible in the same table*: the capacity/material delay (CP-SAT − CPM) is
10 d (Aurora), 3 d (Helios), 28 d (Titan) and 47 d (Vector). This is why the platform
never presents the critical path as a delivery date.

---

## 3. Monte Carlo convergence

All four demo programs were run with 2,000 trials, seed 42.

| Program | Trials/s | Relative SE (batch means) | Converged (<1 %)? | P50 | P90 | Infeasible trials |
|---|---:|---:|---|---:|---:|---:|
| Aurora X1 | 5,980 | 0.25 % | yes | 227.2 d | 273.4 d | 0 |
| Helios EV | 12,703 | 0.21 % | yes | 242.9 d | 282.6 d | 0 |
| Titan H7 | 10,930 | 0.15 % | yes | 207.1 d | 230.9 d | 0 |
| Vector 5G | 10,223 | 0.36 % | yes | 272.9 d | 329.0 d | 0 |

*Method*: batch-means relative standard error over 100 batches of 20 trials;
percentiles use linear interpolation between order statistics (NumPy
`method="linear"`). Both facts are recorded in every run summary, so a reader can
recompute them.

*Reproducibility*: entity ids are derived from the program key (`uuid5`), so the
random streams — which are keyed by entity id — are stable across database rebuilds.
Importing the same program JSON into a fresh database and running the same seed
produces a byte-identical sample vector; the test
`backend/tests/test_reproducibility.py` proves it with two throw-away databases.

---

## 4. Sobol index recovery (Ishigami benchmark)

The Ishigami function `f(x) = sin(x₁) + 7·sin²(x₂) + 0.1·x₃⁴·sin(x₁)` on
`[−π, π]³` has published first-order indices `S₁ = (0.3139, 0.4424, 0)`.

| n_base | S₁ (x₁) | S₁ (x₂) | S₁ (x₃) | 95 % bootstrap CI (x₁) |
|---:|---:|---:|---:|---|
| 1,024 | 0.309 | 0.461 | 0.018 | 0.220 – 0.398 |
| 4,096 | 0.334 | 0.432 | −0.007 | 0.289 – 0.377 |
| 16,384 | 0.299 | 0.441 | 0.014 | 0.282 – 0.320 |

The estimator converges to the published values as the sample size grows, and the
third index (which is analytically zero) stays within its interval of zero. The
regression test asserts the 4,096-sample result within ±0.09.

---

## 5. Paired comparison power

Scenario comparisons use entity-keyed random streams, so both arms see the same
randomness and the difference is paired.

| Comparison | Trials | Paired mean Δ | 95 % CI | P(improve) | P(harm) | On-time plan → scenario |
|---|---:|---:|---|---:|---:|---|
| Aurora — "Schedule acceleration" vs plan | 600 | −11.31 d | −11.41 … −11.20 d | 99.8 % | 0.0 % | 52.3 % → 67.5 % |
| Titan — "Schedule acceleration" vs plan | 600 | −12.39 d | −12.54 … −12.24 d | 100 % | 0.0 % | 27.2 % → 63.3 % |

The interval excludes zero whenever an intervention has a real effect, and the
probability of harm is reported explicitly, so a portfolio that helps on average but
hurts in some trials cannot hide.

---

## 6. Intervention effectiveness (verified, not asserted)

Every portfolio below was produced by the optimiser and then re-simulated at higher
fidelity by the verification stage, with the CP-SAT schedule re-checked.

| Program | Interventions | Cost | Verified P90 | Verified on-time | Net benefit | ROI |
|---|---:|---:|---:|---:|---:|---:|
| Aurora X1 | 4 | $40,056 | 248.4 d | 74.6 % | $227,922 | 5.69 |
| Helios EV | 3 | $43,860 | 247.3 d | 95.2 % | $184,210 | 4.20 |
| Titan H7 | 4 | $59,400 | 210.4 d | 75.2 % | $124,238 | 2.09 |
| Vector 5G | 4 | $65,364 | 283.4 d | 61.4 % | $979,191 | 14.98 |

*Net benefit = avoided incremental cost (delay + ramp-yield + rework) − intervention
cost.* It is a model quantity: it inherits every assumption in the simulation, and
the components are itemised in the run summary (`cost.breakdown`).

---

## 7. What is **not** validated

1. **Calibration against reality.** No observed launch outcomes exist for synthetic
   programs, so no Brier score, reliability curve or sharpness measure is reported.
   The API returns `{"status": "insufficient_data", …}` rather than a fabricated
   statistic.
2. **Real-world causality.** Rank correlation, tornado reruns, Sobol indices and
   leave-one-out counterfactuals are all *model-internal*. They identify where to
   investigate; they do not prove that changing an input moves a real launch.
3. **Supplier behaviour.** Disruption probabilities, lead-time variability and
   reliability are program inputs. Nothing is learned from history.
4. **Yield economics.** The ramp-yield cost uses a logistic curve with program-level
   parameters — a placeholder for a real PPAP dataset.
5. **Multi-project resource contention.** Resources are modelled per program; a
   shared engineering pool across programs is out of scope.
6. **Solver optimality under long horizons.** CP-SAT is run with a 20 s limit; the
   status (`OPTIMAL` / `FEASIBLE`) is always surfaced, and a `FEASIBLE` status means
   the makespan is an upper bound.

---

## 8. Reproducing this report

```bash
python scripts/bootstrap_demo.py      # seed + real forecasts + optimisations
python scripts/benchmark.py            # performance table
python scripts/capture_screenshots.py  # UI screenshots + error report
pytest                                 # 118 backend tests
```

Every number above is reproducible from the seeds recorded in the run summaries
(`summary.engine.seed`, `summary.engine.iterations`).
