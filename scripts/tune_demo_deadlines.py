"""Recommend launch deadlines for the synthetic demo programs.

The demo deadlines are inputs, not results.  This script picks, for each
program, the deadline that produces a target on-time probability under the
current risk model, so the portfolio view shows a realistic *spread* of
posture instead of four identical failures.  It prints the values that belong
in ``scripts/build_datasets.py``; it never edits the samples by itself.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sqlalchemy import select

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.calendar import WorkingCalendar  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.models import Project, SimulationRun  # noqa: E402

TARGETS = {
    "AURORA-X1": 0.55,
    "HELIOS-INV": 0.75,
    "TITAN-PUMP": 0.40,
    "VECTOR-5G": 0.22,
}


def main() -> int:
    with SessionLocal() as db:
        for key, target in TARGETS.items():
            project = db.scalar(select(Project).where(Project.key == key))
            if not project:
                print(f"{key}: project not found")
                continue
            sim = db.scalar(
                select(SimulationRun)
                .where(SimulationRun.project_id == project.id, SimulationRun.status == "completed")
                .order_by(SimulationRun.created_at.desc())
                .limit(1)
            )
            if not sim or not sim.samples:
                print(f"{key}: no simulation with samples — run scripts/bootstrap_demo.py first")
                continue
            samples = np.asarray(sim.samples, dtype=float)
            calendar = WorkingCalendar(
                start_date=project.start_date,
                holidays=list(project.holidays or []),
                working_days_per_week=project.working_days_per_week or 5,
            )
            current_offset = calendar.from_date(project.launch_deadline) if project.launch_deadline else None
            best = None
            for offset in range(int(np.min(samples)) - 5, int(np.max(samples)) + 5):
                probability = float(np.mean(samples <= offset))
                error = abs(probability - target)
                if best is None or error < best[0]:
                    best = (error, offset, probability)
            _, offset, probability = best
            print(
                f"{key}: deadline {calendar.to_date(offset)} (offset {offset}) → on-time {probability:.1%} "
                f"(target {target:.0%}); current {project.launch_deadline} → "
                f"{float(np.mean(samples <= current_offset)):.1%}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
