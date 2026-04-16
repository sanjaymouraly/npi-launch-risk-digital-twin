"""Recommend milestone due dates for the synthetic demo programs.

Gate commitments are inputs as well.  This script picks a due date for every
milestone so that the gate confidence lands on a realistic spread (early
gates comfortable, late gates exposed) instead of an artefact of the
constrained plan.  It prints values for ``scripts/build_datasets.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.calendar import WorkingCalendar  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.models import Project, SimulationRun  # noqa: E402

# Target confidence per milestone, ordered as the milestones appear in the data.
TARGETS = {
    "AURORA-X1": [0.88, 0.78, 0.85, 0.66],
    "HELIOS-INV": [0.85, 0.80, 0.70, 0.75],
    "TITAN-PUMP": [0.86, 0.74, 0.40],
    "VECTOR-5G": [0.88, 0.80, 0.22],
}


def offset_for_target(row: dict, target: float) -> float:
    p10 = row.get("p50_offset", 0.0) - 30.0
    p50 = row.get("p50_offset", 0.0)
    p90 = row.get("p90_offset", 0.0)
    if target >= 0.5:
        share = (target - 0.5) / 0.4
        return p50 + share * (p90 - p50)
    share = (0.5 - target) / 0.4
    return p50 - share * (p50 - p10)


def main() -> int:
    with SessionLocal() as db:
        for key, targets in TARGETS.items():
            project = db.scalar(select(Project).where(Project.key == key))
            sim = db.scalar(
                select(SimulationRun)
                .where(SimulationRun.project_id == project.id, SimulationRun.status == "completed")
                .order_by(SimulationRun.created_at.desc())
                .limit(1)
            )
            summary = sim.summary or {}
            milestones = summary.get("milestones", [])
            calendar = WorkingCalendar(
                start_date=project.start_date,
                holidays=list(project.holidays or []),
                working_days_per_week=project.working_days_per_week or 5,
            )
            print(f"\n{key}")
            for row, target in zip(milestones, targets, strict=False):
                offset = offset_for_target(row, target)
                print(
                    f"  {row['name']:<32} due {calendar.to_date(offset)}  target {target:.0%}  "
                    f"(current {row['due_date']}, p50 {row['p50_date']}, p90 {row['p90_date']})"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
