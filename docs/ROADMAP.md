# Roadmap

The roadmap is ordered by how much it would change the *decisions* the platform
supports, not by implementation convenience. Items marked **done** are in the
repository today; everything else is a proposal, not a commitment.

## Done (1.0.0)

* [x] Exact CPM (FS/SS/FF/SF, lags, calendars) with a separate resource-constrained
      CP-SAT plan.
* [x] Resource-feasible Monte Carlo with correlated inputs, convergence reporting
      and an explicit heuristic-gap measurement.
* [x] Risk attribution: Spearman, tornado, Sobol with bootstrap intervals and
      leave-one-driver-out counterfactuals.
* [x] Paired scenario comparison with common random numbers and net-benefit
      economics.
* [x] Budget-constrained intervention optimisation with pilot estimation, CP-SAT
      selection, a Pareto front and higher-fidelity verification.
* [x] Grounded AI copilot with read-only tools, citations, offline mode, multiple
      providers and a monthly budget cap.
* [x] Governance: JWT auth, roles, project ACL, encrypted credentials, redacted
      logs, audit trail, background jobs.
* [x] Import/export, Alembic migrations, Docker Compose, CI, 118 backend tests and
      real Playwright screenshots.

## Next (1.1 — evidence quality)

* [ ] **Observed-outcome capture.** Record actual gate and launch dates against the
      forecast that existed at the time, so calibration (Brier score, reliability
      curves) can be computed instead of reported as insufficient.
* [ ] **Supplier reliability history.** Replace the static disruption probability
      with a fitted model when a supplier has enough history.
* [ ] **Schedule-risk hybrid.** A stochastic CP-SAT variant (e.g. chance-constrained
      or scenario-based optimisation) so the solver, not only the SGS, reasons about
      risk.
* [ ] **SGS gap certification.** A benchmark suite that reports the SGS-to-CP-SAT
      gap distribution across many generated programs, not just the demo set.

## Later (1.2 — scale and integration)

* [ ] **Portfolio resource contention.** Model shared pools (engineering, labs)
      across programs, so a decision in one program is visible in another.
* [ ] **PLM/ERP connectors.** Import programs from Windchill or Teamcenter, and
      export approved plans back.
* [ ] **Continuous re-forecast.** Watch the plan graph and re-run the forecast when
      a task date, supplier or risk changes, with a diff against the previous run.
* [ ] **Decision log.** Promote approved scenarios into a first-class decision
      register with owners, deadlines and outcomes.
* [ ] **Multi-tenancy and SSO.** OIDC/SAML, per-organisation isolation and audit
      separation.
* [ ] **Rate limiting and quotas** on the public API.

## Explicitly out of scope

* Replacing the judgement of a program manager. The platform quantifies options and
  shows the evidence; it does not decide.
* Learning causal effects from observational data with the synthetic demo set. Until
  real outcomes exist, causal claims would be unfounded.
