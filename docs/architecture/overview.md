# Architecture

The platform is deliberately layered so that the **engines are pure** and the
**database is the only mutable state**. Every engine takes an immutable in-memory
model and returns a result; nothing in `scheduling/`, `simulation/` or
`optimization/` touches SQLAlchemy.

```
┌───────────────────────────────────────────────────────────────────────────┐
│ Frontend (React 18 + TypeScript + Vite + Plotly)                         │
│  Command centre · Programs · Overview · Schedule · Risks · Suppliers      │
│  Milestones · Monte Carlo · Scenarios · Optimiser · Copilot · Decisions    │
│  Methodology · Settings                                                   │
└───────────────────────────────┬───────────────────────────────────────────┘
                                │ REST (JSON) + X-Request-ID
┌───────────────────────────────▼───────────────────────────────────────────┐
│ API layer (FastAPI routers)                                               │
│  system · auth · projects · analysis · simulations · scenarios             │
│  optimization · ai · settings · jobs                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  ┌─────────────┐   │
│  │ job service  │  │ audit trail  │  │ AI copilot    │  │ error layer │   │
│  │ thread pool  │  │ append only  │  │ tools+evidence│  │ typed errors│   │
│  │ cancel/stale │  │              │  │ budget cap    │  │ request ids │   │
│  └──────────────┘  └──────────────┘  └───────────────┘  └─────────────┘   │
└───────────────────────────────┬───────────────────────────────────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────────────────┐
│ Service layer                                                             │
│  project_service · scheduling_service · simulation_service                │
│  scenario_service · optimization_service · job_service · audit            │
└───────────────────────────────┬───────────────────────────────────────────┘
                                │  immutable domain objects
┌───────────────────────────────▼───────────────────────────────────────────┐
│ Engine layer (pure, deterministic given a seed)                           │
│                                                                          │
│  scheduling/  cpm.py     exact CPM, FS/SS/FF/SF, lags, float             │
│               cpsat.py   OR-Tools CP-SAT: cumulative capacity, materials  │
│               sgs.py     serial schedule generation (feasibility engine)  │
│  simulation/  context.py DB → immutable SimulationContext                │
│               engine.py  Monte Carlo, percentile/convergence reporting    │
│               attribution.py  Spearman, tornado, Saltelli Sobol, LOO     │
│  optimization/ interventions.py  14 intervention types as real mutations │
│                engine.py  catalog → pilot → CP-SAT → verification         │
│  core/        calendar.py exact working-day arithmetic                   │
└───────────────────────────────┬───────────────────────────────────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────────────────┐
│ Persistence (SQLAlchemy 2 · Alembic · SQLite or PostgreSQL)              │
│  projects, tasks, dependencies, resources, suppliers, components,         │
│  risks, validations, ecos, milestones, scenarios, interventions,          │
│  simulation_runs, optimization_runs, snapshots, jobs, audit_logs,         │
│  ai_conversations, ai_messages, ai_provider_configs, users                │
└───────────────────────────────────────────────────────────────────────────┘
```

## Layer contracts

### 1. Calendar (`core/calendar.py`)

The single source of truth for time. Everything is expressed in **working-day
offsets** from the program start; conversion to dates is exact (no 7/5 fudge
factors). The calendar supports 1–7 day working weeks, holiday lists, and snaps a
non-working program start forward to the next working day. Conversions are
incremental and cached, which keeps a 500-task critical path in the millisecond
range.

### 2. Scheduling engines (`scheduling/`)

| Module | Contract | Guarantee |
|---|---|---|
| `cpm.py` | `compute_cpm(model, calendar) -> CpmResult` | Exact earliest/latest times for FS/SS/FF/SF with lags; cycle detection; total float |
| `cpsat.py` | `resource_constrained_schedule(model, calendar, options) -> dict` | Feasible schedule; cumulative capacity on `capacity × availability`; material release constraints; deadline feasibility with an assumption core when it fails |
| `sgs.py` | `schedule_sgs(model, durations, calendar, cpm, priorities, material_ready)` | Always feasible for a valid graph; serial SGS priority rule; the engine used inside every Monte Carlo trial |

`TaskNode`, `Edge`, `ResourceNode` and `PlanningModel` are frozen dataclasses, so a
scenario intervention produces a *new* model and the baseline is never mutated.

### 3. Simulation (`simulation/`)

`build_context(db, project)` converts the database into an immutable
`SimulationContext`; `run_monte_carlo(context, options)` runs the trials.

* Inputs are sampled with **entity-keyed random streams** (`seed`, entity id,
  purpose), which is what makes scenario comparisons paired and reproducible.
* Durations use the task's own distribution (fixed / triangular / PERT / normal /
  lognormal / uniform / gamma / Weibull) with a latent correlation factor.
* Every trial is scheduled with SGS under the sampled durations, material release
  dates and disruptions — so a reported makespan is always a feasible schedule.
* The summary records the engine version, iteration count, seed, percentile method,
  convergence diagnostics, cost decomposition, milestone probabilities, supplier and
  risk attribution, and the deterministic comparison (CPM vs SGS vs P50 vs P90).

### 4. Attribution (`simulation/attribution.py`)

* **Spearman** rank correlation between each sampled input and the makespan.
* **Tornado** — deterministic reruns with ±20 % durations (logic and capacity effect
  only, no probability).
* **Sobol** — Saltelli first-order estimator with bootstrap intervals, evaluated on the
  deterministic scheduler. Validated against the Ishigami benchmark in the test suite.
* **Leave-one-out** — neutralise one driver, re-simulate with common random numbers,
  measure the change. Explicitly labelled a model-internal counterfactual.

### 5. Optimisation (`optimization/`)

1. `generate_catalog(context)` builds candidates **from the real program**: critical
   tasks, exposed suppliers, capacity bottlenecks, critical dependencies.
2. `estimate_catalog(...)` scores every candidate with a paired pilot.
3. `select_portfolios(...)` solves a CP-SAT model under budget, exclusivity groups,
   prerequisites, headcount and added-capacity limits, and returns a Pareto front
   computed from real CP-SAT solves at budget fractions.
4. `verify_portfolios(...)` re-simulates the selected and Pareto-near portfolios at
   higher fidelity, re-checks them with CP-SAT scheduling, and ranks them by verified
   net economic benefit.

Intervention types: `replace_supplier`, `split_procurement`, `expedite_supplier`,
`expedite_task`, `tooling_readiness`, `delay_design_freeze`, `reduce_scope`,
`add_capacity`, `add_resource`, `add_overtime`, `parallelize`,
`increase_safety_stock`, `move_qualification_date`, `introduce_eco`.

Each one is a **real mutation** of the planning model — there is no hard-coded
benefit anywhere in the code.

### 6. AI copilot (`ai/`)

* `providers.py` — adapters for OpenAI-compatible, Anthropic, Ollama and offline
  modes, with retries, timeouts, encrypted credentials and cost estimation.
* `tools.py` — nine read-only tools; each returns compact data plus citation
  records (`kind`, `id`, `detail`).
* `assistant.py` — offline intent router, evidence-pack construction, the live tool
  loop, budget enforcement, conversation persistence and citation decoration.

### 7. Persistence

SQLAlchemy 2 with explicit `select()` statements, Alembic migrations, and an
idempotent demo seeder. The API, the maintenance scripts and the tests all resolve
the same SQLite file regardless of the working directory.

## Request lifecycle (simulation)

```
POST /api/projects/{id}/simulations
  → simulation_service.submit_simulation
     → job_service.submit (background thread) or inline execution
        → build_context(db, project)            # DB → immutable context
        → run_monte_carlo(context, options)     # pure engine
        → persist SimulationRun + SimulationSnapshot + audit entry
  → 202 Accepted {job_id}
GET /api/jobs/{job_id}   → progress, result ids, cancellation
GET /api/simulations/{id} → full summary (samples on request)
```

## Failure handling

| Failure | Behaviour |
|---|---|
| Provider outage or timeout | Copilot falls back to offline analytics, labels the answer, records the reason |
| Monthly budget exhausted | Same fallback, with the budget stated in the message |
| Infeasible launch deadline | CP-SAT returns `FEASIBLE_DEADLINE_MISSED` with the assumption core and a relaxed optimum — never a silent pass |
| Invalid input | Typed error with a stable code, a human message and the request id |
| Background job crash | Job marked `failed` with the error text; stale jobs are recovered at startup |
| Missing evidence for a question | The copilot says the data is missing and names the next action |
