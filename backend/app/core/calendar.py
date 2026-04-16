"""Working-day calendar arithmetic.

Everything in the scheduling layer is expressed in *working-day offsets* from
the project start (offset 0 == project start date).  A working day is a day the
organisation operates, determined by ``working_days_per_week`` and the holiday
list.  Converting offsets to calendar dates is exact — no 7/5 fudge factors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class WorkingCalendar:
    start_date: date
    working_days_per_week: int = 5
    holidays: frozenset[date] = field(default_factory=frozenset)
    max_scan_days: int = 365 * 15

    def __post_init__(self) -> None:
        """Normalise the holiday list so string input cannot silently be ignored."""
        normalized: set[date] = set()
        for raw in self.holidays or ():
            if isinstance(raw, date):
                normalized.add(raw)
                continue
            try:
                normalized.add(date.fromisoformat(str(raw)[:10]))
            except ValueError:
                continue
        object.__setattr__(self, "holidays", frozenset(normalized))
        object.__setattr__(
            self, "working_days_per_week", max(1, min(7, int(self.working_days_per_week)))
        )
        # Incremental conversion cache.  Without it, mapping N offsets costs
        # O(N * offset) day-steps, which dominates the critical path for large
        # programs.  The cache is derived state and is rebuilt on every copy.
        base = self.start_date
        while not self.is_working_day(base):
            base += timedelta(days=1)
        object.__setattr__(self, "_offset_cache", {0: base})
        object.__setattr__(self, "_high_water_offset", 0)
        object.__setattr__(self, "_high_water_date", base)

    @classmethod
    def from_project(cls, start_date: date, working_days_per_week: int = 5,
                     holidays: list[str] | None = None) -> "WorkingCalendar":
        parsed = set()
        for raw in holidays or []:
            try:
                parsed.add(date.fromisoformat(str(raw)[:10]))
            except ValueError:
                continue
        return cls(
            start_date=start_date,
            working_days_per_week=max(1, min(7, int(working_days_per_week))),
            holidays=frozenset(parsed),
        )

    def is_working_day(self, day: date) -> bool:
        if day in self.holidays:
            return False
        # Monday == 0
        return day.weekday() < self.working_days_per_week

    def to_date(self, offset: float) -> date:
        """Map a (possibly fractional) working-day offset to a calendar date.

        Fractional offsets are truncated to the working day containing the
        instant; durations are stored as whole working days by the solver.
        Conversions are incremental: the calendar remembers the furthest offset
        it has resolved and walks forward from there, so a program with many
        tasks costs O(total horizon) instead of O(tasks x horizon).
        """
        key = int(round(max(0.0, float(offset))))
        cache = self._offset_cache
        cached = cache.get(key)
        if cached is not None:
            return cached

        if key == 0:
            current = self.start_date
            while not self.is_working_day(current):
                current += timedelta(days=1)
            cache[0] = current
            if self._high_water_offset < 0:
                object.__setattr__(self, "_high_water_offset", 0)
                object.__setattr__(self, "_high_water_date", current)
            return current

        if key > self._high_water_offset:
            current = self._high_water_date
            remaining = key - self._high_water_offset
        else:
            current = self.start_date
            while not self.is_working_day(current):
                current += timedelta(days=1)
            remaining = key

        guard = 0
        while remaining > 0:
            current += timedelta(days=1)
            if self.is_working_day(current):
                remaining -= 1
            guard += 1
            if guard > self.max_scan_days:
                raise ValueError("Calendar horizon exceeded while converting working-day offset")
        cache[key] = current
        if key > self._high_water_offset:
            object.__setattr__(self, "_high_water_offset", key)
            object.__setattr__(self, "_high_water_date", current)
        return current

    def from_date(self, day: date) -> int:
        """Number of working days between project start and ``day`` (>= 0).

        Offset 0 is the first working day on or after the project start, so
        ``from_date(to_date(n)) == n`` holds even when a program starts on a
        non-working day.
        """
        if day <= self.start_date:
            return 0
        current = self.start_date
        while not self.is_working_day(current):
            current += timedelta(days=1)
        count = 0
        while current < day:
            current += timedelta(days=1)
            if self.is_working_day(current):
                count += 1
        return count

    def working_days_between(self, start: date, end: date) -> int:
        """Inclusive working days in [start, end]; 0 when end < start."""
        if end < start:
            return 0
        return max(0, self.from_date(end) - self.from_date(start) + (1 if self.is_working_day(end) else 0))

    def duration_to_dates(self, start_offset: float, duration_working_days: float) -> tuple[date, date]:
        """Return (start date, finish date) for a task occupying whole working days.

        A 5-working-day task starting Monday finishes Friday.  The finish date
        is the last working day worked, so the successor starting the next
        working day has ``start_offset = start + duration``.
        """
        duration = max(0, int(round(float(duration_working_days))))
        start = self.to_date(start_offset)
        if duration == 0:
            return start, start
        # Last worked day is offset start + duration - 1
        last = self.to_date(float(start_offset) + duration - 1)
        return start, last

    def add_working_days(self, day: date, days: int) -> date:
        return self.to_date(self.from_date(day) + max(0, int(days)))
