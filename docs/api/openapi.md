# API reference

The full OpenAPI document is [`openapi.json`](openapi.json). It is generated from the
running application, so it cannot drift from the code:

```bash
cd backend && python -c "import json; from app.main import app; json.dump(app.openapi(), open('../docs/api/openapi.json','w'), indent=2)"
```

With the API running you can explore it interactively at <http://localhost:8000/docs>.

## Conventions

* All routes are prefixed with `/api`.
* Requests may carry `Authorization: Bearer <token>` when `AUTH_ENABLED=true`.
* Every response includes an `X-Request-ID` header; errors repeat it in the body.
* Error body: `{"code", "message", "details", "request_id"}`.
* Simulation and optimisation requests accept `async_job`: `false` runs inline and
  returns the result id, `true` returns a `job_id` to poll.

## Endpoint index

| Method | Path | Summary |
|---|---|---|
| `POST` | `/api/auth/login` | Login |
| `GET` | `/api/auth/me` | Me |
| `GET` | `/api/auth/users` | List Users |
| `POST` | `/api/auth/users` | Create User |
| `GET` | `/api/health` | Health |
| `GET` | `/api/jobs` | List Jobs |
| `GET` | `/api/jobs/{job_id}` | Get Job |
| `POST` | `/api/jobs/{job_id}/cancel` | Cancel Job |
| `GET` | `/api/meta` | Meta |
| `GET` | `/api/optimizations/{optimization_id}` | Get Optimization |
| `GET` | `/api/projects` | List Projects |
| `POST` | `/api/projects` | Create Project |
| `GET` | `/api/projects/csv-template` | Csv Template |
| `POST` | `/api/projects/import` | Import Projects |
| `GET` | `/api/projects/{project_id}` | Get Project |
| `PATCH` | `/api/projects/{project_id}` | Update Project |
| `DELETE` | `/api/projects/{project_id}` | Delete Project |
| `POST` | `/api/projects/{project_id}/ai/chat` | Chat |
| `GET` | `/api/projects/{project_id}/ai/conversations` | Conversations |
| `GET` | `/api/projects/{project_id}/ai/conversations/{conversation_id}` | Conversation |
| `DELETE` | `/api/projects/{project_id}/ai/conversations/{conversation_id}` | Delete Conversation |
| `GET` | `/api/projects/{project_id}/ai/status` | Ai Status |
| `GET` | `/api/projects/{project_id}/ai/suggestions` | Suggestions |
| `POST` | `/api/projects/{project_id}/archive` | Archive Project |
| `POST` | `/api/projects/{project_id}/attribution/leave-one-out` | Leave One Out |
| `POST` | `/api/projects/{project_id}/attribution/sobol` | Sobol |
| `GET` | `/api/projects/{project_id}/audit` | Audit Log |
| `GET` | `/api/projects/{project_id}/calibration` | Calibration |
| `POST` | `/api/projects/{project_id}/duplicate` | Duplicate Project |
| `GET` | `/api/projects/{project_id}/export` | Export Project |
| `GET` | `/api/projects/{project_id}/interventions` | Intervention Catalog |
| `GET` | `/api/projects/{project_id}/milestones` | Milestones |
| `GET` | `/api/projects/{project_id}/network` | Network |
| `POST` | `/api/projects/{project_id}/optimizations` | Run Optimization |
| `GET` | `/api/projects/{project_id}/optimizations` | List Optimizations |
| `GET` | `/api/projects/{project_id}/optimizations/latest` | Latest Optimization |
| `GET` | `/api/projects/{project_id}/risks` | Risks |
| `GET` | `/api/projects/{project_id}/scenarios` | Get Scenarios |
| `POST` | `/api/projects/{project_id}/scenarios` | Create Scenario |
| `POST` | `/api/projects/{project_id}/scenarios/compare` | Compare Scenarios |
| `POST` | `/api/projects/{project_id}/scenarios/{scenario_id}/preview` | Preview Scenario |
| `GET` | `/api/projects/{project_id}/schedule` | Schedule |
| `POST` | `/api/projects/{project_id}/simulations` | Run Simulation |
| `GET` | `/api/projects/{project_id}/simulations` | List Simulations |
| `GET` | `/api/projects/{project_id}/simulations/latest` | Latest |
| `GET` | `/api/projects/{project_id}/snapshots` | Snapshots |
| `GET` | `/api/projects/{project_id}/suppliers` | Suppliers |
| `GET` | `/api/projects/{project_id}/tasks` | Task Catalog |
| `POST` | `/api/projects/{project_id}/tasks/import` | Import Tasks |
| `GET` | `/api/projects/{project_id}/validation` | Validation |
| `GET` | `/api/ready` | Ready |
| `GET` | `/api/scenarios/{scenario_id}` | Get Scenario |
| `PATCH` | `/api/scenarios/{scenario_id}` | Update Scenario |
| `DELETE` | `/api/scenarios/{scenario_id}` | Delete Scenario |
| `POST` | `/api/scenarios/{scenario_id}/clone` | Clone Scenario |
| `GET` | `/api/settings/providers` | List Providers |
| `PATCH` | `/api/settings/providers/{provider}` | Update Provider |
| `GET` | `/api/settings/providers/{provider}/models` | Provider Models |
| `POST` | `/api/settings/providers/{provider}/test` | Test Provider |
| `GET` | `/api/simulations/{simulation_id}` | Get Simulation |
| `GET` | `/api/simulations/{simulation_id}/download` | Download Simulation |
| `GET` | `/api/stats` | Stats |

_52 paths, 17 schemas._
