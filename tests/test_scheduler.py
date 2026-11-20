"""Unit tests for deterministic adaptive scheduler engine."""

import pytest
from datetime import date, timedelta
from backend.scheduler.engine import (
    calculate_effective_minutes,
    is_rest_day,
    get_study_dates,
    generate_schedule,
    reflow_overdue_and_remaining,
    compress_schedule,
    compute_schedule_diff,
    ScheduleAllocation,
)

# Deterministic fake clock fixed at Monday, 2026-11-23 (IST)
FAKE_TODAY = date(2026, 11, 23)

def fake_clock():
    return FAKE_TODAY

def test_playback_speed_scaling():
    # 60 raw minutes at 1.0x = 60.0 effective minutes
    assert calculate_effective_minutes(3600, 1.0) == 60.0
    # 60 raw minutes at 1.5x = 40.0 effective minutes
    assert calculate_effective_minutes(3600, 1.5) == 40.0
    # 60 raw minutes at 2.0x = 30.0 effective minutes
    assert calculate_effective_minutes(3600, 2.0) == 30.0
    # 60 raw minutes at 1.25x = 48.0 effective minutes
    assert calculate_effective_minutes(3600, 1.25) == 48.0

def test_rest_days_and_revision_buffer():
    # Sunday is rest day
    sunday = date(2026, 11, 29)
    monday = date(2026, 11, 30)
    assert is_rest_day(sunday, ["Sunday"]) is True
    assert is_rest_day(monday, ["Sunday"]) is False

    # Check date partition between Monday Nov 23 and Wednesday Dec 2 (10 days total)
    start = date(2026, 11, 23)
    target = date(2026, 12, 2)
    # 2 revision days: Dec 1 and Dec 2
    study_dates, rest_dates, rev_dates = get_study_dates(start, target, ["Sunday"], revision_buffer_days=2)
    assert len(rev_dates) == 2
    assert rev_dates == [date(2026, 12, 1), date(2026, 12, 2)]
    # Sunday Nov 29 is in rest_dates
    assert sunday in rest_dates
    # No rest day or revision day in study_dates
    for d in study_dates:
        assert d not in rest_dates
        assert d not in rev_dates

def test_multi_day_lesson_splitting():
    # Single marathon lesson of 180 raw minutes (10,800 sec)
    # minutes_per_day = 60, speed = 1.0 -> requires exactly 3 days (60 min each)
    lessons = [
        {
            "id": "les-1",
            "title": "DBMS Marathon Lecture",
            "start_sec": 0,
            "end_sec": 10800,
            "raw_duration_sec": 10800,
            "priority": "core",
        }
    ]
    target_date = date(2026, 12, 10)

    sched = generate_schedule(
        course_id="c1",
        lessons=lessons,
        start_date=FAKE_TODAY, # Monday Nov 23
        target_date=target_date,
        minutes_per_day=60,
        playback_speed=1.0,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        schedule_strategy="fixed",
        clock=fake_clock,
    )

    allocs = sched["allocations"]
    assert len(allocs) == 3
    # Check splits
    assert allocs[0].scheduled_date == "2026-11-23" # Monday
    assert allocs[0].allocated_start_sec == 0
    assert allocs[0].allocated_end_sec == 3600
    assert allocs[0].effective_minutes == 60.0
    assert allocs[0].split_index == 0
    assert allocs[0].split_count == 3

    assert allocs[1].scheduled_date == "2026-11-24" # Tuesday
    assert allocs[1].allocated_start_sec == 3600
    assert allocs[1].allocated_end_sec == 7200
    assert allocs[1].effective_minutes == 60.0
    assert allocs[1].split_index == 1
    assert allocs[1].split_count == 3

    assert allocs[2].scheduled_date == "2026-11-25" # Wednesday
    assert allocs[2].allocated_start_sec == 7200
    assert allocs[2].allocated_end_sec == 10800
    assert allocs[2].effective_minutes == 60.0
    assert allocs[2].split_index == 2
    assert allocs[2].split_count == 3

def test_playback_speed_affects_allocations():
    # 120 raw minutes at 1.5x = 80 effective minutes
    # With minutes_per_day = 80, it should fit in 1 day!
    lessons = [
        {
            "id": "les-1",
            "title": "Fast Lecture",
            "start_sec": 0,
            "end_sec": 7200,
            "raw_duration_sec": 7200,
            "priority": "core",
        }
    ]
    sched = generate_schedule(
        course_id="c1",
        lessons=lessons,
        start_date=FAKE_TODAY,
        target_date=date(2026, 12, 5),
        minutes_per_day=80,
        playback_speed=1.5,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        schedule_strategy="fixed",
        clock=fake_clock,
    )
    allocs = sched["allocations"]
    assert len(allocs) == 1
    assert allocs[0].effective_minutes == 80.0
    assert allocs[0].raw_minutes == 120.0

def test_behind_schedule_detection():
    # Target date = Friday Nov 27, buffer = 2 days -> deadline_effective = Wednesday Nov 25.
    # 4 lessons (60 min each) -> finishes Nov 26 > Nov 25 -> behind schedule!
    lessons = [
        {"id": f"l-{i}", "title": f"Lesson {i}", "start_sec": 0, "end_sec": 3600, "raw_duration_sec": 3600, "priority": "core"}
        for i in range(4)
    ]
    sched = generate_schedule(
        course_id="c1",
        lessons=lessons,
        start_date=FAKE_TODAY,
        target_date=date(2026, 11, 27),
        minutes_per_day=60,
        playback_speed=1.0,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        schedule_strategy="fixed",
        clock=fake_clock,
    )
    assert sched["is_behind_schedule"] is True
    assert sched["projected_finish_date"] == "2026-11-26"

def test_compress_schedule_drops_deep_dive():
    lessons = [
        {"id": "c1", "title": "Core 1", "start_sec": 0, "end_sec": 3600, "raw_duration_sec": 3600, "priority": "core"},
        {"id": "c2", "title": "Core 2", "start_sec": 0, "end_sec": 3600, "raw_duration_sec": 3600, "priority": "core"},
        {"id": "dd1", "title": "Deep Dive 1", "start_sec": 0, "end_sec": 3600, "raw_duration_sec": 3600, "priority": "deep-dive"},
        {"id": "dd2", "title": "Deep Dive 2", "start_sec": 0, "end_sec": 3600, "raw_duration_sec": 3600, "priority": "deep-dive"},
    ]

    sched, dropped_count, deficit_min, deficit_msg = compress_schedule(
        course_id="c1",
        lessons=lessons,
        start_date=FAKE_TODAY,
        target_date=date(2026, 11, 26),
        minutes_per_day=60,
        playback_speed=1.0,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        clock=fake_clock,
    )

    assert dropped_count == 2
    assert deficit_min == 0.0
    assert deficit_msg is None
    lesson_ids = {a.lesson_id for a in sched["allocations"]}
    assert lesson_ids == {"c1", "c2"}
    assert sched["is_behind_schedule"] is False

def test_compress_schedule_reports_core_deficit():
    lessons = [
        {"id": "c1", "title": "Core 1", "start_sec": 0, "end_sec": 3600, "raw_duration_sec": 3600, "priority": "core"},
        {"id": "c2", "title": "Core 2", "start_sec": 0, "end_sec": 3600, "raw_duration_sec": 3600, "priority": "core"},
    ]

    sched, dropped_count, deficit_min, deficit_msg = compress_schedule(
        course_id="c1",
        lessons=lessons,
        start_date=FAKE_TODAY,
        target_date=date(2026, 11, 25),
        minutes_per_day=60,
        playback_speed=1.0,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        clock=fake_clock,
    )

    assert deficit_min == 60.0
    assert deficit_msg is not None
    assert "Deficit: 60.0 effective minutes" in deficit_msg

def test_reflow_skips_and_completed():
    lessons = [
        {"id": "l1", "title": "Lesson 1", "start_sec": 0, "end_sec": 3600, "raw_duration_sec": 3600, "priority": "core"},
        {"id": "l2", "title": "Lesson 2", "start_sec": 0, "end_sec": 3600, "raw_duration_sec": 3600, "priority": "core"},
        {"id": "l3", "title": "Lesson 3", "start_sec": 0, "end_sec": 3600, "raw_duration_sec": 3600, "priority": "core"},
    ]
    sched = generate_schedule(
        course_id="c1",
        lessons=lessons,
        start_date=FAKE_TODAY,
        target_date=date(2026, 12, 10),
        minutes_per_day=60,
        playback_speed=1.0,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        schedule_strategy="fixed",
        clock=fake_clock,
    )
    allocs = sched["allocations"]
    allocs[0].is_completed = True
    allocs[1].is_skipped = True

    reflowed = reflow_overdue_and_remaining(
        course_id="c1",
        allocations=allocs,
        lessons=lessons,
        target_date=date(2026, 12, 10),
        minutes_per_day=60,
        playback_speed=1.0,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        schedule_strategy="fixed",
        clock=fake_clock,
    )

    active_lids = [a.lesson_id for a in reflowed["allocations"] if not a.is_skipped]
    assert "l1" in active_lids
    assert "l3" in active_lids
    assert "l2" not in active_lids

def test_paced_vs_fixed_strategy_spread_to_exam_date():
    """Verify that 'paced' strategy spreads lessons evenly up to exam deadline (minus buffer),

    while 'fixed' strategy finishes early in a greedy sprint.
    """
    # Start: Mon Nov 23. Exam: Tue Dec 22 (29 calendar days).
    # Revision buffer: 2 days (Dec 21 & Dec 22). Study deadline: Sun Dec 20.
    # Total available study days (excluding Sundays): Mon-Sat = ~24 study days.
    # 20 lessons of 30 min each = 600 min.
    lessons = [
        {
            "id": f"toc-{i}",
            "title": f"TOC Lesson {i}",
            "start_sec": 0,
            "end_sec": 1800,
            "raw_duration_sec": 1800,
            "priority": "core",
        }
        for i in range(20)
    ]
    target_exam = date(2026, 12, 22)

    # Strategy 1: FIXED (90 min/day) -> 600 / 90 = ~7 study days -> finishes around Dec 1
    sched_fixed = generate_schedule(
        course_id="c1",
        lessons=lessons,
        start_date=FAKE_TODAY,
        target_date=target_exam,
        minutes_per_day=90,
        playback_speed=1.0,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        schedule_strategy="fixed",
        clock=fake_clock,
    )
    finish_fixed = sched_fixed["projected_finish_date"]
    assert finish_fixed < "2026-12-10"  # Finishes very early!

    # Strategy 2: PACED (Spread to Exam Date)
    # Available study days to Dec 20 = 24 days.
    # 600 / 24 = 25 min/day.
    # The lessons should spread across study days up to Dec 15-20!
    sched_paced = generate_schedule(
        course_id="c1",
        lessons=lessons,
        start_date=FAKE_TODAY,
        target_date=target_exam,
        minutes_per_day=90,  # Ignored by paced mode in favor of calculated pace
        playback_speed=1.0,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        schedule_strategy="paced",
        clock=fake_clock,
    )
    finish_paced = sched_paced["projected_finish_date"]
    # Paced finish lands on or right near Dec 20!
    assert finish_paced >= "2026-12-15"
    assert finish_paced <= "2026-12-20"
    assert sched_paced["is_behind_schedule"] is False
    assert sched_paced["effective_daily_target_minutes"] < 50.0  # ~25 min/day

def test_lesson_exclusion_omits_from_schedule():
    """Verify that lessons marked is_excluded=True are completely omitted from schedule allocations."""
    lessons = [
        {"id": "l-concept-1", "title": "DFA Definition", "start_sec": 0, "end_sec": 1800, "raw_duration_sec": 1800, "is_excluded": False},
        {"id": "l-example-1", "title": "DFA Example 1", "start_sec": 0, "end_sec": 1800, "raw_duration_sec": 1800, "is_excluded": True},
        {"id": "l-concept-2", "title": "NFA Definition", "start_sec": 0, "end_sec": 1800, "raw_duration_sec": 1800, "is_excluded": False},
    ]

    sched = generate_schedule(
        course_id="c1",
        lessons=lessons,
        start_date=FAKE_TODAY,
        target_date=date(2026, 12, 10),
        minutes_per_day=60,
        playback_speed=1.0,
        rest_days=["Sunday"],
        revision_buffer_days=2,
        clock=fake_clock,
    )

    scheduled_ids = {a.lesson_id for a in sched["allocations"]}
    assert "l-concept-1" in scheduled_ids
    assert "l-concept-2" in scheduled_ids
    assert "l-example-1" not in scheduled_ids  # Excluded lesson must NOT be scheduled!
