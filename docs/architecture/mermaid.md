# Architecture diagrams (Mermaid)

## System context

```mermaid
flowchart LR
    User[Program manager / engineer] --> UI[React + TypeScript UI]
    UI -->|REST| API[FastAPI API]
    API -->|SQL| DB[(SQLite or PostgreSQL)]
    API -->|HTTP| LLM[[LLM provider\nOpenAI-compatible / Anthropic / Ollama]]
    API -->|files| Store[(Program JSON / CSV)]

    style LLM stroke-dasharray: 4 3
```

## Layered architecture

```mermaid
flowchart TB
    subgraph presentation[Presentation]
        UI[React 18 + Vite + Plotly]
    end
    subgraph interface[Interface]
        REST[REST routers]
        JOB[Job service]
        AUDIT[Audit service]
        COPILOT[AI copilot]
    end
    subgraph application[Application services]
        PROJ[project_service]
        SCHED[scheduling_service]
        SIM[simulation_service]
        SCEN[scenario_service]
        OPT[optimization_service]
    end
    subgraph domain[Domain engines - pure]
        CPM[CPM]
        CPSAT[CP-SAT]
        SGS[SGS]
        MC[Monte Carlo]
        ATT[Attribution]
        OPTENG[Optimiser]
    end
    subgraph infrastructure[Infrastructure]
        ORM[SQLAlchemy ORM]
        MIG[Alembic]
        CAL[Working calendar]
        SEC[Security & secrets]
    end
    DB[(Database)]

    UI --> REST
    REST --> JOB & AUDIT & COPILOT
    REST --> PROJ & SCHED & SIM & SCEN & OPT
    JOB & COPILOT --> PROJ & SCHED & SIM & SCEN & OPT
    PROJ & SCHED & SIM & SCEN & OPT --> CPM & CPSAT & SGS & MC & ATT & OPTENG
    CPM & CPSAT & SGS & MC & ATT & OPTENG --> CAL
    PROJ & SCHED & SIM & SCEN & OPT & COPILOT & AUDIT --> ORM
    ORM --> DB
    MIG --> DB
    SEC -.-> REST
```

## Simulation data flow

```mermaid
sequenceDiagram
    participant U as UI
    participant A as API
    participant J as Job service
    participant S as simulation_service
    participant C as SimulationContext
    participant E as Monte Carlo engine
    participant SGS as SGS scheduler
    participant D as Database

    U->>A: POST /projects/{id}/simulations
    A->>J: submit(kind=simulation)
    A-->>U: 202 {job_id}
    J->>S: execute(request)
    S->>C: build_context(db, project)
    C-->>S: immutable context
    S->>E: run_monte_carlo(context, options)
    loop each trial
        E->>E: sample durations, disruptions, risks, ECOs
        E->>SGS: schedule_sgs(durations, material_ready)
        SGS-->>E: feasible schedule + makespan
    end
    E-->>S: samples + summary
    S->>D: SimulationRun + SimulationSnapshot + audit
    S-->>J: simulation_id
    J-->>U: GET /jobs/{id} → completed
```

## Paired scenario comparison (common random numbers)

```mermaid
flowchart LR
    Seed[seed + entity id] --> StreamA[Random stream per entity]
    Seed --> StreamB[Same streams]
    StreamA --> Base[Baseline arm]
    StreamB --> Scen[Scenario arm]
    Base --> D1[(makespan samples)]
    Scen --> D2[(makespan samples)]
    D1 --> Delta[Paired delta = scen - base]
    D2 --> Delta
    Delta --> Stats[mean, CI95, P(improve), P(harm)]
    Stats --> Econ[Net benefit and ROI]
```

## Optimisation loop

```mermaid
flowchart LR
    Ctx[Program context] --> Cat[Candidate catalog\n14 intervention types]
    Cat --> Pilot[Paired pilot estimates]
    Pilot --> Sel[CP-SAT selection\nbudget, exclusivity, prerequisites]
    Sel --> Ver[Higher-fidelity verification]
    Sel --> Par[Pareto front\n(real CP-SAT solves)]
    Par --> Ver
    Ver --> Rec[Recommendation\nverified net benefit]
    Ver -.->|interactions| Caution[Additive score caveat]
```

## Data model (excerpt)

```mermaid
erDiagram
    PROJECT ||--o{ TASK : contains
    PROJECT ||--o{ DEPENDENCY : links
    PROJECT ||--o{ RESOURCE : has
    PROJECT ||--o{ SUPPLIER : sources
    PROJECT ||--o{ COMPONENT : buys
    PROJECT ||--o{ RISK : tracks
    PROJECT ||--o{ MILESTONE : commits
    PROJECT ||--o{ SCENARIO : compares
    PROJECT ||--o{ SIMULATION_RUN : forecasts
    PROJECT ||--o{ OPTIMIZATION_RUN : recommends
    SCENARIO ||--o{ INTERVENTION : contains
    TASK ||--o{ TASK_COMPONENT : consumes
    COMPONENT ||--o{ TASK_COMPONENT : supplies
    TASK ||--o{ TASK_RESOURCE : needs
    RESOURCE ||--o{ TASK_RESOURCE : provides
    SIMULATION_RUN ||--o{ SIMULATION_SNAPSHOT : freezes
    PROJECT ||--o{ AUDIT_LOG : records
    AI_CONVERSATION ||--o{ AI_MESSAGE : contains
```
