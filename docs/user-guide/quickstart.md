# Quick start — 15 minutes to a decision-grade forecast

This guide takes you from a clean checkout to a portfolio view with real forecasts,
on Linux/macOS or Windows PowerShell.

---

## 0. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.12+ | `python3 --version` / `py -3 --version` |
| Node.js | 20+ | `node --version` |
| npm | 10+ | `npm --version` |
| Docker (optional) | 24+ | `docker --version` |

OR-Tools, SciPy, NumPy and NetworkX are installed from `backend/requirements.txt`;
no compiler toolchain is required.

---

## 1. Start the API

### Linux / macOS

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
cd backend && uvicorn app.main:app --reload --port 8000
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item .env.example .env
Set-Location backend
uvicorn app.main:app --reload --port 8000
```

Check it: `curl http://127.0.0.1:8000/api/health` → `{"status":"ok", …}`.
OpenAPI explorer: <http://localhost:8000/docs>.

---

## 2. Seed the demo programs and run real forecasts

With the API running (or in a second terminal):

```bash
python scripts/bootstrap_demo.py
```

The script is idempotent. It seeds the four synthetic programs, creates the baseline
and catalog-derived scenarios, and then **actually runs** a 2,000-trial Monte Carlo
plus a budget-constrained optimisation for every program:

```
AURORA-X1 · Plan forecast: P50 225.5d, P90 273.8d, on-time 53.5%
AURORA-X1 · optimisation: 4 interventions, net 218,176 (ROI 5.45)
...
```

---

## 3. Start the UI

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```

Windows PowerShell: `Set-Location ..\frontend`, `npm install`, `npm run dev`.

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`; set
`VITE_PROXY_TARGET` to point somewhere else.

---

## 4. Your first forecast

1. **Command centre** — the portfolio table lists every program with its latest
   on-time probability, P50/P90 and expected delay cost. The chart orders programs by
   exposure.
2. **Open a program → Monte Carlo** — press **Run Monte Carlo**. 2,000 trials take
   under a second; the page then shows the distribution, the completion curve, the
   convergence check and the cost decomposition.
3. **Read the convergence badge.** If the relative standard error is above 1 %, the
   run is not decision-grade yet — raise the iteration count.
4. **Schedule & capacity** — compare the unconstrained CPM duration with the
   CP-SAT makespan. The difference is the delay caused by capacity and material
   constraints, and it is the number most often misread as "the project is late".
5. **Risk attribution** — see which inputs co-move with the makespan, and run the
   Sobol or leave-one-out analyses for a stricter view.
6. **Scenarios → Simulate paired comparison** — select a scenario and compare it
   against the approved plan with common random numbers. Read the paired delta and
   its confidence interval, not just the on-time probability.
7. **Optimiser** — set a budget and run. The recommendation is the portfolio with the
   best *verified* net economic benefit, and the run records what was verified.
8. **Risk copilot** — ask "What is the probability we hit the deadline, what drives
   it, and what should we do next?" Every answer cites the records it used.

---

## 5. Bring your own program

```bash
curl -X POST http://127.0.0.1:8000/api/projects/import \
     -F file=@data/samples/npi_demo_project.json
```

Or use **Programs → Import program** in the UI. The JSON contract is documented in
`data/samples/` and in the README; imports are transactional.

---

## 6. Next steps

* Turn on authentication and PostgreSQL before exposing the API — see
  [`docs/ops/troubleshooting.md`](../ops/troubleshooting.md).
* Configure a real AI provider in **Settings & AI providers** (keys are encrypted),
  or run Ollama locally: `ollama pull gemma3:1b`.
* Read [`docs/research/validation_report.md`](../research/validation_report.md) to
  understand what is and is not validated.
