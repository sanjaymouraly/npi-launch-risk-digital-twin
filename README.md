# NPI Launch Risk Digital Twin & Decision Intelligence

[![CI](https://github.com/sanjaymouraly/npi-launch-risk-digital-twin/actions/workflows/ci.yml/badge.svg)](https://github.com/sanjaymouraly/npi-launch-risk-digital-twin/actions/workflows/ci.yml)

An NPI launch-risk digital twin for scenario analysis and decision intelligence.

## Features

- Critical path: Exact activity-on-node CPM, FS/SS/FF/SF + lags, working-day calendar, holidays, 1–7 day weeks
- Resource-constrained plan: OR-Tools CP-SAT: cumulative capacity (capacity × availability), material release dates, all precedence types
- Launch-risk forecast: Monte Carlo over correlated durations, supplier disruption, risk events, validation failures, ECOs, absenteeism, transport and capacity loss
- Uncertainty reporting: Batch-means relative SE convergence check, 95 % CIs, documented percentile method
- Risk attribution: Spearman rank correlation, one-at-a-time tornado, Saltelli first-order Sobol with bootstrap CIs, leave-one-driver-out counterfactuals
- What-if: Paired Monte Carlo with common random numbers (entity-keyed RNG streams)
- Optimisation: Catalog generated from the real program → paired pilot estimates → CP-SAT selection under budget/exclusivity/prerequisites/capacity → higher-fidelity verification

## Stack

Python, Node.js, FastAPI, Uvicorn, HTTPX, SQLAlchemy, Pydantic, NumPy, SciPy, pandas

## Clone

```bash
git clone https://github.com/sanjaymouraly/npi-launch-risk-digital-twin.git
cd npi-launch-risk-digital-twin
```

## Setup

```bash
# The project ships a Docker Compose setup.
docker compose up --build
```

See `docs/` or the compose file for environment variables and ports.

## Run

```bash
docker compose up --build
```

## Tests

```bash
pytest -q
```

## Notes

- Sample data, when included, is synthetic.

## License

MIT © 2026 [Sanjay Mouraly](https://github.com/sanjaymouraly)
