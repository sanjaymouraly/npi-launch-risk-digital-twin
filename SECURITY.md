# Security policy

## What this platform protects

* **Program data** — schedules, BOMs, supplier information, risk registers, forecast
  runs, optimisation results and the audit trail.
* **Credentials** — provider API keys and the JWT signing secret.
* **Integrity of decisions** — a decision must be traceable to the run that
  supported it, and the run must be immutable.

## Controls in place

| Area | Control |
|---|---|
| Authentication | JWT bearer tokens (HS256), Argon2id password hashing, token expiry, per-project access control, roles `admin` / `program_manager` / `viewer` |
| Authorisation | Every project-scoped route calls `principal.require_project(...)`; write routes require a write-capable role |
| Credential storage | Provider keys are encrypted with a Fernet key derived from `SECRET_KEY`; the API never returns them, only a masked hint |
| Credential hygiene | Structured logging redacts `sk-…`, `Bearer …`, `"api_key": …` and `"authorization": …` in both message and exception text |
| Input validation | Pydantic schemas on every write endpoint; uploads are size-limited and schema-validated; JSON and CSV imports are transactional and roll back completely |
| Injection | SQLAlchemy ORM with bound parameters throughout; no string-built SQL |
| Transport | CORS restricted to `ALLOWED_ORIGINS`; TLS expected to be terminated at a reverse proxy |
| Auditability | Append-only audit log for project creation, imports, runs, scenario changes, approvals and AI answers |
| Availability | Background jobs are cancellable, time-bounded, and stale jobs are recovered at start-up |

## Deployment requirements

1. Set a strong, unique `SECRET_KEY`. It signs tokens **and** encrypts stored
   provider credentials; changing it invalidates them.
2. Set `AUTH_ENABLED=true` and `ENVIRONMENT=production`.
3. Use PostgreSQL; SQLite is single-writer.
4. Set `SEED_DEMO_ON_STARTUP=false`.
5. Set `ALLOWED_ORIGINS` to the real UI origin.
6. Terminate TLS in front of the API and the UI.
7. Keep `.env` out of version control and out of images.

## Reporting a vulnerability

Please report vulnerabilities privately through the repository's **Security
Advisories** page rather than in a public issue. Include the affected component,
the reproduction steps and the impact. You can expect an acknowledgement within
three working days and a status update at least every two weeks until a fix is
released.

Do not include real customer data, credentials or personal data in a report — a
synthetic reproduction is sufficient.

## Out of scope

* The demo programs are synthetic; no customer data is present in this repository.
* The platform does not implement multi-tenancy beyond project-level access
  control, rate limiting, or SSO — these are planned, not present.
