# Implementation report

A map of what exists in the repository, layer by layer, with the file that
implements it. It is a companion to
[`docs/architecture/overview.md`](architecture/overview.md) (design rationale) and
[`docs/research/validation_report.md`](research/validation_report.md) (evidence).

---

## 1. Domain model (`backend/app/models/`)

| Module | Tables |
|---|---|
| `project.py` | `users`, `projects` |
| `task.py` | `tasks`, `dependencies`, `task_resources`, `task_components` |
| `resource.py` | `resources`, `suppliers`, `components` |
| `supply.py` | `quotes`, `purchase_orders`, `inventories` |
| `risk.py` | `risks`, `validation_tests`, `ecos` |
| `scenario.py` | `scenarios`, `interventions`, `milestones` |
| `simulation.py` | `simulation_runs`, `simulation_snapshots` |
| `audit.py` | `audit_logs`, `actual_events`, `calibration_records` |
| `base.py` | `jobs`, `ai_provider_configs`, `ai_conversations`, `ai_messages` |

31 tables in total; the Alembic revision `0001_initial` reproduces the schema from
scratch (verified in `backend/tests/test_migrations.py`).

## 2. Core services (`backend/app/core/`)

* `config.py` — pydantic-settings configuration; relative SQLite paths are anchored
  to `backend/` so the API, scripts and tests always share one file.
* `calendar.py` — exact working-day arithmetic with holidays, 1–7 day weeks,
  incremental (cached) offset→date conversion and a `from_date`/`to_date` round
  trip that holds even for a non-working program start.
* `logging.py` — structured JSON logging with credential redaction.
* `errors.py` — typed error hierarchy and uniform handlers (`code`, `message`,
  `details`, `request_id`).
* `security.py` — Argon2 hashing, JWT creation/verification, `Principal` with
  roles and project ACL.
* `secrets.py` — Fernet encryption and masking for provider credentials.

## 3. Scheduling (`backend/app/scheduling/`)

* `model.py` — frozen dataclasses (`TaskNode`, `Edge`, `ResourceNode`,
  `PlanningModel`), graph validation with cycle detection, ALAP float helpers.
* `cpm.py` — exact CPM: earliest/latest times for FS/SS/FF/SF with lags, critical
  path, total float, deadline margin, milestone forecast.
* `cpsat.py` — OR-Tools CP-SAT: cumulative capacity, material release constraints,
  milestone targets, deadline assumptions with an explanation core, float
  computation by an as-late-as-possible re-solve, utilisation and bottlenecks.
* `sgs.py` — serial schedule generation scheme (priority rule, capacity fitting,
  material release waiting) and resource utilisation reporting.

## 4. Simulation (`backend/app/simulation/`)

* `context.py` — DB → immutable `SimulationContext` (model, calendar, suppliers,
  components, task materials, risks, validations, ECOs, milestones, economics).
* `distributions.py` — sampling helpers and the inverse normal CDF.
* `engine.py` — the Monte Carlo engine: correlated duration sampling, supplier
  disruption, material release, validation failures, ECO rework, absenteeism,
  transport delay, capacity loss, per-trial SGS scheduling, percentile and
  convergence statistics, cost decomposition, supplier/risk/task attribution,
  completion curve, and optional CP-SAT validation of the heuristic gap.
* `attribution.py` — Sobol (Saltelli), leave-one-out, paired deltas, Spearman
  matrix, and the Ishigami benchmark used by the tests.

## 5. Optimisation (`backend/app/optimization/`)

* `interventions.py` — 14 intervention types as real model mutations, exclusivity
  groups, prerequisites, cost estimation, and the material-requirement sync that
  keeps re-sourced suppliers effective inside the simulation.
* `engine.py` — catalog generation from the live program, paired pilot estimation,
  CP-SAT portfolio selection with constraints, Pareto front, verification with
  higher-fidelity simulation plus a CP-SAT schedule re-check, and the method notes
  that ship with every result.

## 6. Services (`backend/app/services/`)

`project_service` (import/export, CSV tasks, validation, duplication, archival),
`scheduling_service` (schedule assembly, validation report, supplier exposure),
`simulation_service` (execution, history, downloads, calibration report),
`scenario_service` (CRUD, preview, paired comparison, economics),
`optimization_service` (run orchestration, persistence, list/detail),
`job_service` (thread pool, progress, cancellation, stale-job recovery) and
`audit` (append-only trail).

## 7. AI layer (`backend/app/ai/`)

* `providers.py` — OpenAI-compatible, Anthropic, Ollama and offline adapters with
  retries, timeouts, encrypted configuration, model discovery, cost estimation and
  a single active provider.
* `tools.py` — nine read-only tools returning compact data plus citation records.
* `assistant.py` — offline intent router, evidence-pack construction, live tool
  loop, budget enforcement, conversation persistence and citation decoration.

## 8. API (`backend/app/api/`)

Ten routers — `system`, `auth`, `projects`, `analysis`, `simulations`, `scenarios`,
`optimization`, `ai`, `settings`, `jobs` — mounted under `/api` in
`backend/app/main.py`, which also owns the lifespan (schema init, demo seeding,
stale-job recovery), the request-id middleware, CORS and the error handlers.

## 9. Frontend (`frontend/src/`)

| File | Contents |
|---|---|
| `App.tsx` | Routes for the 14 views |
| `components/Layout.tsx` | Shell, program navigation, portfolio switcher, project switcher |
| `components/ui.tsx` | Design system: cards, KPIs, badges, buttons, fields, callouts, icons |
| `components/Plot.tsx` | Plotly wrapper with the shared chart theme |
| `components/Markdown.tsx` | Dependency-free markdown renderer for copilot answers |
| `api.ts` | Typed API client |
| `hooks.ts` | `useApi` loader and the job poller |
| `styles.css` | The complete design system (no CSS framework) |
| `pages/*.tsx` | Dashboard, Programs, Program overview, Schedule, Risks, Suppliers, Milestones, Monte Carlo, Scenarios, Optimiser, Copilot, Decisions, Methodology, Settings |

## 10. Tooling and data

* `scripts/build_datasets.py` — generates the four synthetic programs.
* `scripts/bootstrap_demo.py` — idempotent seeding of programs, scenarios, real
  Monte Carlo forecasts and real optimisations.
* `scripts/benchmark.py` — performance benchmark → `docs/research/performance_benchmark.md`.
* `scripts/capture_screenshots.py` — Playwright capture with console-error and
  failed-request checks → `docs/images/`.
* `scripts/tune_demo_deadlines.py`, `scripts/tune_demo_milestones.py` — helpers that
  choose demo deadlines and gate dates for a realistic spread of posture.
* `backend/alembic/` — migration environment and the initial revision.
* `data/samples/` — the four synthetic programs.

## 11. Verification

* `backend/tests/` — 118 tests (see the validation report for the claim → method
  mapping).
* `frontend` — `npm run build` type-checks in strict mode before bundling.
* `scripts/capture_screenshots.py` — exercises the real UI and fails on any console
  error or failed request.
* `.github/workflows/ci.yml` — lint, tests, migration smoke test, frontend build and
  Docker image builds.

## 12. Deliberately not built

* Multi-program resource contention (a shared engineering pool across programs).
* Learning from historical outcomes — there are no real outcomes to learn from, so
  calibration is reported as insufficient rather than approximated.
* A solver-grade proof that the SGS schedule is optimal — the gap is measured and
  published instead.
* An AI copilot that can take actions. The copilot reads; humans decide.
