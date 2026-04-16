# Operations & troubleshooting

---

## Production checklist

Before exposing the API outside a trusted network:

| Item | Action | Why |
|---|---|---|
| `SECRET_KEY` | Set a long random value (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) | It signs JWTs **and** derives the Fernet key that encrypts provider credentials. Changing it invalidates stored provider keys. |
| `AUTH_ENABLED` | `true` | Enables JWT bearer tokens, roles (`admin`, `program_manager`, `viewer`) and per-project ACL. |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/npi` | SQLite is single-writer and unsuitable for concurrent users. |
| Migrations | `alembic -c backend/alembic.ini upgrade head` | Schema management in production instead of `create_all`. |
| CORS | Restrict `ALLOWED_ORIGINS` to the real UI host | The default allows only localhost. |
| Demo seeding | `SEED_DEMO_ON_STARTUP=false` | Never seed synthetic programs into a production database. |
| Demo user | Set `DEMO_ADMIN_PASSWORD` | In production the seeder refuses to invent a password. |
| TLS | Terminate TLS at a reverse proxy | Bearer tokens and credentials must not travel in clear text. |
| AI budget | Set `AI_MONTHLY_BUDGET_USD` | Bounds the monthly spend of the copilot. |
| Backups | Schedule `pg_dump` (see `backup_restore.md`) | Runs and audit entries are business records. |
| Logging | `ENVIRONMENT=production` | Switches the root logger to structured JSON with credential redaction. |

---

## Common failures

### `Cannot reach the API. Is the backend running on port 8000?`

The UI cannot reach the API. Check:

```bash
curl http://127.0.0.1:8000/api/health
```

If the API is on another host, set `VITE_PROXY_TARGET` before starting Vite, or
`VITE_API_URL` when building a static bundle.

### The database is empty after start-up

`SEED_DEMO_ON_STARTUP` only seeds when the `projects` table is empty. To load the
demo programs explicitly:

```bash
python scripts/bootstrap_demo.py
```

If you see `disk I/O error` from SQLite, a stale process still holds the deleted
database file. Stop the API, remove `backend/npi.db*` and start again.

### `No feasible intervention portfolio fits the budget`

The selected interventions all cost more than the budget allows, or the exclusivity
and prerequisite rules make the combination infeasible. Raise the budget, relax
`max_selected`, or exclude intervention types that do not fit
(`constraints.exclude_types`).

### The optimisation returns a portfolio with a *new* bottleneck

Adding capacity or compressing a task can shift contention elsewhere. The
verification stage lists the new bottlenecks; address them or pick a different
portfolio from the cost–benefit frontier.

### The copilot answers "offline"

Check **Settings & AI providers**:

* Is the provider *configured* (base URL, model, key)?
* Is the **monthly budget** exhausted? The status panel shows the spend; when the
  budget is reached the copilot answers from the offline router and says so.
* Did the provider time out? Live calls allow 120 s by default; a small local model
  over a large evidence pack can exceed that. Raise `timeout_seconds` in the
  provider configuration.

Test a provider directly:

```bash
curl -X POST http://127.0.0.1:8000/api/settings/providers/custom/test
```

### Ollama does not answer

```bash
curl http://localhost:11434/api/tags          # is the server running?
ollama list                                   # is the model pulled?
```

`gemma3:1b` needs roughly 1.5 GB of RAM. Tool calling is not available for local
models, so the evidence pack is injected into the prompt instead — expect slower
answers and lower fidelity than a hosted model.

### The schedule looks too long compared with the critical path

That difference is the point: CP-SAT adds capacity and material release constraints.
Open **Schedule & capacity → Resource utilisation** to see which resource binds.

### The deadline shows as missed

CP-SAT proves the deadline cannot be met under the current precedence, capacity and
materials (`status: FEASIBLE_DEADLINE_MISSED`, with the conflicting constraint in
`deadline.conflicting_constraints`). The platform never silently relaxes the
deadline.

## Docker

```bash
docker compose up --build          # API :8000, UI :5173, PostgreSQL :5432
docker compose logs -f backend     # seeding and request log
docker compose down -v             # stop and drop the database volume
```

Verified in this repository:

* The API image builds from the repository root (`docker build -f backend/Dockerfile .`)
  and seeds the four demo programs on an empty database, then answers
  `/api/health`, `/api/projects` and `/api/projects/{id}/schedule`.
* The UI image builds and serves the production bundle through nginx
  (`/` and `/assets/*` return 200); `/api` is proxied to the API service.
* The API runs against PostgreSQL through the `psycopg` (v3) driver.

*Environment note*: some sandboxes block container-to-container traffic on the
Docker bridge, so the `backend` service may not reach the `db` service by name
there. Running the API with host networking (or publishing the database port and
pointing `DATABASE_URL` at it) works around it.

---

## Diagnostics

| Check | Command |
|---|---|
| API health | `curl http://127.0.0.1:8000/api/health` |
| Database connectivity | `curl http://127.0.0.1:8000/api/ready` |
| Engine + capability inventory | `curl http://127.0.0.1:8000/api/meta` |
| Workspace counters | `curl http://127.0.0.1:8000/api/stats` |
| Background jobs | `curl http://127.0.0.1:8000/api/jobs` |
| Structured logs | `ENVIRONMENT=production` switches the root logger to JSON |

Every request carries an `X-Request-ID` header; the same id appears in the JSON logs
and in error payloads, which makes a single request traceable end to end.

---

## Job behaviour

* Simulations and optimisations can run inline (`async_job: false`) or as background
  jobs.
* Jobs are cancellable: `POST /api/jobs/{id}/cancel`. The engine checks the cancel
  flag between trials.
* Jobs left `running` by a crash are recovered at start-up and marked failed.
* Job payloads and results are stored, so the UI can show what was requested and
  what came back.
