# Workflows

Four recurring situations and how the platform supports them. Each workflow ends
with a decision that can be defended, because every number points at a run.

---

## 1. Monthly launch-risk review (program manager)

1. **Command centre** — sort programs by on-time probability. Note the ones below
   the 50 % threshold and the aggregate expected delay exposure.
2. For each exposed program, open **Program overview** and read the three-lane
   schedule: CPM (logic), CP-SAT (feasible plan) and Monte Carlo P90 (risk). The
   first question is always *which* of the three moved.
3. Open **Risk attribution** — the top sensitivity rows tell you where the modelled
   date is being driven. Confirm the top driver is plausible before acting on it.
4. Open **Decisions & audit** — check whether a decision was already taken (and
   whether the forecast has moved since).

**Output**: a one-line posture per program (managed / contingent / critical) with the
simulation id, seed and iteration count attached.

---

## 2. Choosing an intervention (engineering lead)

1. **Optimiser** — set the realistic budget and the objective
   (`min_combined_exposure` is the default: delay cost avoided minus spend).
2. Read the *candidate catalog* before the recommendation. Each row states what the
   pilot measured, and the notes state what the intervention actually changes.
3. Check the *cost–benefit frontier*. A cheaper portfolio may be the better decision
   even when it buys fewer days.
4. Read the verification block: verified P90, verified on-time probability, net
   benefit, ROI, and whether a **new bottleneck** was created by the portfolio.
5. Materialise the decision as a **scenario** (Scenarios → New scenario, pick the
   same interventions) so it can be compared, approved and audited.

**Guardrails**: the optimiser's scores are additive; the verification stage measures
interactions. Treat the recommendation as a shortlist, and the scenario comparison
as the evidence.

---

## 3. Deadline negotiation with the customer (program director)

1. Run the simulation for the plan and read the **completion-date curve**: the
   probability of finishing by any date.
2. Open **Milestones** — gate confidence is often the sharper conversation than the
   launch date, because a late gate usually causes the late launch.
3. If the deadline cannot be met, the platform says so explicitly: CP-SAT returns
   `FEASIBLE_DEADLINE_MISSED` with the conflicting constraint, and the completion
   curve gives the earliest date with a defensible confidence (e.g. 80 %).
4. If a trade is needed, use **Scenarios → Simulate paired comparison** to quantify
   the customer-visible effect of a mitigation, with a confidence interval on the
   paired difference.

**Output**: a deadline with an explicit confidence, and a record of which scenarios
were considered.

---

## 4. Weekly programme cadence (PMO)

| When | What | Where |
|---|---|---|
| Monday | Refresh the plan forecast (same seed → comparable; new seed → re-baselined) | Monte Carlo page |
| Tuesday | Re-run the optimisation if the plan changed; compare verified portfolios | Optimiser |
| Wednesday | Risk review with the top three drivers and their owners | Risk attribution |
| Thursday | Gate review for milestones below target | Milestones |
| Friday | Decisions & audit: what was decided, by whom, on what evidence | Decisions & audit |

Keep the same seed across a series of runs if you want comparability; change it and
say so in the audit trail. Both are recorded in every run summary.

---

## 5. Using the copilot responsibly

* Ask about *evidence*, not for decisions: "Which validation failure contributes most
  to the P90?" rather than "Should we delay launch?"
* Check the citation chips — they point at the simulation, schedule or scenario that
  supports the statement.
* Expand **Evidence tools used** to see exactly which read-only tools ran.
* If the answer says the provider was unavailable or the budget was spent, the
  answer came from the offline deterministic router: still grounded, but less
  fluent. Treat it as a data summary, not an analysis.
* The copilot cannot write to the platform. Decisions are made in the optimiser and
  the scenario builder, and recorded in the audit trail.
