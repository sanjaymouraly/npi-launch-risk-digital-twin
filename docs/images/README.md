# Screenshots

Every image in this folder is a **real screenshot of the running application**:
a live FastAPI backend, a real SQLite database seeded with the synthetic demo
programs, and real Monte Carlo / CP-SAT results. No mock-ups, no generated
illustrations.

They are produced by:

```bash
# 1. start the API
cd backend && uvicorn app.main:app --port 8000

# 2. start the UI
cd frontend && npm run dev

# 3. capture
python scripts/capture_screenshots.py
```

The script drives the UI with Playwright (Chromium), exercises the interactive
features — the paired scenario comparison, the live AI copilot and the local Ollama
model — and **fails** if any page logs a console error or returns a 4xx/5xx
response. The outcome of the last run is written to `docs/screenshot-report.json`.

| File | View |
|---|---|
| `01-dashboard.png` | Portfolio command centre |
| `02-programs.png` | Program portfolio table |
| `03-program-overview.png` | Program workspace overview (CPM vs CP-SAT vs P90) |
| `04-schedule-capacity.png` | Schedule gantt, utilisation, solver provenance |
| `05-risk-attribution.png` | Rank correlation, tornado, cost decomposition |
| `06-supply-exposure.png` | BOM and supplier exposure |
| `07-milestones.png` | Gate confidence |
| `08-monte-carlo.png` | Distribution, convergence, percentiles, run history |
| `09-scenario-comparison.png` | Paired scenario comparison with common random numbers |
| `10-optimiser-recommendation.png` | Verified portfolio, Pareto front, candidate catalog |
| `11-decisions-audit.png` | Audit trail, snapshots, calibration status, jobs |
| `12-methodology.png` | Methods and stated limitations |
| `13-settings-providers.png` | AI providers, security posture, runtime |
| `14-helios-program-overview.png` | Second program (Helios EV) for comparison |
| `15-assistant-welcome.png` | Copilot start screen with grounded suggestions |
| `16-assistant-grounded-answer.png` | Live provider answer with citations |
| `17-settings-ollama-active.png` | Local Ollama model activated in the settings screen |
| `18-assistant-ollama-answer.png` | Answer from the local `gemma3:1b` model |

Regenerating the images changes the numbers only if the demo data changes; the
layout is deterministic.
