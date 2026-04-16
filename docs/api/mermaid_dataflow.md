# API data flow

All routes are prefixed with `/api`. Requests carry an `X-Request-ID` header that is
echoed in the response and in the structured logs; errors use the uniform body
`{"code", "message", "details", "request_id"}`.

## Program lifecycle

```mermaid
sequenceDiagram
    participant UI as React UI
    participant API as FastAPI
    participant PS as project_service
    participant DB as Database

    UI->>API: POST /api/projects (JSON program)
    API->>PS: create_project(payload)
    PS->>PS: validate tasks, dependencies, resources, BOM
    PS->>DB: transactional insert (rollback on error)
    PS->>DB: audit_log("project.created")
    PS-->>UI: 201 {id, key, name}
```

## Schedule

```mermaid
sequenceDiagram
    participant UI as React UI
    participant API as FastAPI
    participant SS as scheduling_service
    participant CPM as cpm.compute_cpm
    participant CP as cpsat.resource_constrained_schedule

    UI->>API: GET /api/projects/{id}/schedule?mode=both
    API->>SS: project_schedule(mode, time_limit, objective)
    SS->>CPM: compute_cpm(model, calendar)
    CPM-->>SS: project_duration, critical path, float
    SS->>CP: resource_constrained_schedule(...)
    CP-->>SS: makespan, status, bottlenecks, deadline report
    SS-->>UI: {cpm, constrained, comparison, assumptions}
```

## Simulation and attribution

```mermaid
sequenceDiagram
    participant UI as React UI
    participant API as FastAPI
    participant JS as job_service
    participant SIM as simulation_service
    participant MC as run_monte_carlo
    participant ATT as attribution

    UI->>API: POST /api/projects/{id}/simulations
    API->>JS: submit(kind="simulation")
    API-->>UI: 202 {job_id}
    JS->>SIM: execute(request)
    SIM->>MC: run_monte_carlo(context, options)
    MC->>ATT: Spearman, tornado, supplier/risk attribution
    MC-->>SIM: samples + summary
    SIM->>SIM: persist run, snapshot, audit entry
    UI->>API: GET /api/jobs/{job_id}
    API-->>UI: {status, progress, result.simulation_id}
    UI->>API: GET /api/simulations/{id}
    API-->>UI: full summary (+samples on request)
    UI->>API: POST /api/projects/{id}/attribution/sobol
    API-->>UI: first-order indices with bootstrap CIs
```

## Scenario comparison (common random numbers)

```mermaid
sequenceDiagram
    participant UI as React UI
    participant API as FastAPI
    participant SC as scenario_service
    participant ENG as engines

    UI->>API: POST /api/projects/{id}/scenarios/compare
    API->>SC: compare(request)
    SC->>ENG: build baseline context + scenario context
    SC->>ENG: run_monte_carlo(baseline, seed)
    SC->>ENG: run_monte_carlo(scenario, same seed)
    ENG-->>SC: samples (paired by entity-keyed streams)
    SC->>SC: paired_delta, economics, ROI
    SC-->>UI: {baseline, scenario, paired_delta, economics}
```

## Optimisation

```mermaid
sequenceDiagram
    participant UI as React UI
    participant API as FastAPI
    participant OS as optimization_service
    participant OE as optimization.engine
    participant DB as Database

    UI->>API: POST /api/projects/{id}/optimizations
    API->>OS: submit_optimization(request)
    OS->>OE: generate_catalog(context)
    OE->>OE: estimate_catalog (paired pilots)
    OE->>OE: select_portfolios (CP-SAT, budget + constraints)
    OE->>OE: verify_portfolios (higher-fidelity simulation + CP-SAT)
    OE-->>OS: recommendation + alternatives + method
    OS->>DB: persist OptimizationRun + audit entry
    API-->>UI: 202 {job_id} or 200 {optimization_id}
```

## AI copilot

```mermaid
sequenceDiagram
    participant UI as React UI
    participant API as FastAPI
    participant AS as ai.assistant
    participant TL as ai.tools
    participant PV as ai.providers

    UI->>API: POST /api/projects/{id}/ai/chat
    API->>AS: answer(db, project, message, provider)
    AS->>AS: budget check (monthly cap)
    alt offline / provider unavailable
        AS->>TL: read-only tools
        TL-->>AS: data + citations
        AS-->>UI: deterministic answer (offline = true)
    else live provider
        AS->>TL: evidence pack
        TL-->>AS: data + citations
        AS->>PV: chat(messages, tools)
        PV-->>AS: content (+ tool calls)
        AS->>TL: execute requested tools
        TL-->>AS: data + citations
        AS-->>UI: answer + citations + usage
    end
    AS->>AS: persist conversation, message, audit entry
```
