"""Calendar arithmetic: exactness, holidays and non-5-day weeks."""
from __future__ import annotations

from datetime import date

import pytest
from app.core.calendar import WorkingCalendar
from hypothesis import given, settings
from hypothesis import strategies as st


def test_offset_zero_is_start_date():
    calendar = WorkingCalendar(start_date=date(2026, 1, 5))
    assert calendar.to_date(0) == date(2026, 1, 5)
    assert calendar.from_date(date(2026, 1, 5)) == 0


def test_five_day_week_skips_weekends():
    calendar = WorkingCalendar(start_date=date(2026, 1, 5))  # Monday
    assert calendar.to_date(4) == date(2026, 1, 9)  # Friday
    assert calendar.to_date(5) == date(2026, 1, 12)  # Monday
    assert calendar.to_date(10) == date(2026, 1, 19)


def test_holidays_are_skipped():
    calendar = WorkingCalendar(
        start_date=date(2026, 1, 5), holidays=["2026-01-06", "2026-01-07"]
    )
    assert calendar.to_date(1) == date(2026, 1, 8)
    assert not calendar.is_working_day(date(2026, 1, 6))


def test_six_day_week_includes_saturday():
    calendar = WorkingCalendar(start_date=date(2026, 1, 5), working_days_per_week=6)
    assert calendar.to_date(5) == date(2026, 1, 10)  # Saturday
    assert calendar.to_date(6) == date(2026, 1, 12)  # Monday


def test_duration_to_dates_uses_inclusive_finish():
    calendar = WorkingCalendar(start_date=date(2026, 1, 5))
    start, finish = calendar.duration_to_dates(0, 5)
    assert start == date(2026, 1, 5)
    assert finish == date(2026, 1, 9)


def test_roundtrip_is_exact():
    calendar = WorkingCalendar(
        start_date=date(2026, 1, 5), holidays=["2026-01-19", "2026-02-16"]
    )
    for offset in range(0, 250):
        assert calendar.from_date(calendar.to_date(offset)) == offset


@settings(max_examples=150, deadline=None)
@given(
    offset=st.integers(min_value=0, max_value=300),
    holidays=st.lists(
        st.dates(min_value=date(2026, 1, 1), max_value=date(2027, 12, 31)),
        max_size=12,
        unique=True,
    ),
    days_per_week=st.integers(min_value=2, max_value=7),
)
def test_offsets_are_monotonic_and_never_on_holidays(offset, holidays, days_per_week):
    calendar = WorkingCalendar(
        start_date=date(2026, 1, 5),
        working_days_per_week=days_per_week,
        holidays={holiday.isoformat() for holiday in holidays},
    )
    first = calendar.to_date(offset)
    second = calendar.to_date(offset + 1)
    assert second > first
    assert first not in calendar.holidays
    assert calendar.from_date(first) == offset


def test_non_working_start_snaps_forward():
    calendar = WorkingCalendar(start_date=date(2026, 1, 10))  # Saturday
    assert calendar.to_date(0) == date(2026, 1, 12)  # Monday


@pytest.mark.parametrize("value", [None, "not-a-date"])
def test_invalid_holidays_are_ignored(value):
    calendar = WorkingCalendar.from_project(date(2026, 1, 5), holidays=[value])
    assert calendar.to_date(3) == date(2026, 1, 8)
