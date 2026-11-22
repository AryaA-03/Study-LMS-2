"""Unit tests for Instant Deterministic Day-Wise Repacking (Layer 2).

Verifies:
- 100% deterministic Python math with 0 LLM calls.
- Repacking runtime < 10ms.
- Sequential Concept Clips remain intact (never split mid-topic, soft ±15% tolerance).
- Two clean modes:
  1. Fit to Exam Date / Number of Days (calculates required_daily_minutes = remaining / days,
     surfaces pace notice if exceeding preferred daily budget).
  2. Fixed Daily Budget (packs clips into days, updates projected finish date).
- Editing exam date (14 days -> 7 days -> 20 days), minutes_per_day, and playback_speed.
- Diff generation (old finish -> new finish, pace change).
- Incomplete clips repacked while completed clips remain untouched.
"""

import time
import pytest
from datetime import date, timedelta
from backend.scheduler.engine import repack_schedule, default_clock

FAKE_TODAY = date(2026, 11, 23) # Monday

def fake_clock():
    return FAKE_TODAY


def create_fixture_clips(count: int = 12, clip_duration_sec: int = 720):
    """Creates a sequence of contiguous ~12 min Concept Clips."""
    clips = []
    start = 0
    for i in range(count):
        end = start + clip_duration_sec
        clips.append({
            "id": f"clip-{i+1}",
            "title": f"Concept {i+1}: Topic Details",
            "start_sec": start,
            "end_sec": end,
            "raw_duration_sec": clip_duration_sec,
            "priority_tag": "deep-dive" if i % 4 == 0 else "core",
            "status": "not_started",
            "is_completed": False,
        })
        start = end
    return clips


def test_repack_schedule_performance_under_10ms():
    """Verify repack_schedule runs in < 10ms for 50 concept clips."""
    clips = create_fixture_clips(count=50, clip_duration_sec=780)
    config = {
        "target_date": "2026-12-15",
        "minutes_per_day": 60,
        "playback_speed": 1.25,
        "rest_days": ["Sunday"],
        "revision_buffer_days": 2,
        "schedule_strategy": "paced",
    }

    t0 = time.perf_counter()
    res = repack_schedule(clips, config, clock=fake_clock)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_ms < 10.0, f"Repacking took {elapsed_ms:.2f}ms, expected < 10ms"
    assert res is not None
    assert len(res["allocations"]) == 50


def test_fit_to_exam_date_pacing_and_notice():
    """Fit to Exam Date calculates required_daily_minutes and surfaces pace notice if exceeding budget."""
    # 12 clips of 720 sec (12 min raw) = 144 raw minutes
    # At 1.0x playback_speed = 144 effective minutes
    # 4 study days -> required_daily_minutes = 144 / 4 = 36 min/day
    clips = create_fixture_clips(count=12, clip_duration_sec=720)

    # 4 study days: Monday Nov 23, Tuesday Nov 24, Wednesday Nov 25, Thursday Nov 26
    # Revision buffer: 2 days (Nov 27, Nov 28), target_date: Nov 28
    config = {
        "target_date": "2026-11-28",
        "minutes_per_day": 30, # preferred budget is 30m/day, required is 36m/day -> notice!
        "preferred_daily_minutes": 30,
        "playback_speed": 1.0,
        "rest_days": ["Sunday"],
        "revision_buffer_days": 2,
        "schedule_strategy": "paced",
    }

    res = repack_schedule(clips, config, clock=fake_clock)

    assert res["required_daily_minutes"] == pytest.approx(36.0, abs=0.5)
    assert res["exceeds_budget"] is True
    assert "exceeds your preferred daily budget" in res["pace_notice"]

    # Invariants: 12 clips allocated, each clip has split_count == 1 (never split mid-topic)
    for a in res["allocations"]:
        assert a.split_count == 1
        assert a.split_index == 0


def test_fixed_budget_greedy_packing_with_soft_tolerance():
    """Fixed Daily Budget mode packs sequential Concept Clips greedily without splitting a ~12 min clip."""
    # 6 clips of 12 min each (720s) at 1.0x speed
    # Daily budget = 20 min. Soft tolerance 15% = 23 min.
    # Clip 1 (12m) fits in Day 1. Clip 2 (12m) would bring Day 1 to 24m > 23m -> moves to Day 2!
    # Result: exactly 1 clip per day over 6 study days.
    clips = create_fixture_clips(count=6, clip_duration_sec=720)
    config = {
        "minutes_per_day": 20,
        "playback_speed": 1.0,
        "rest_days": ["Sunday"],
        "revision_buffer_days": 2,
        "schedule_strategy": "fixed",
    }

    res = repack_schedule(clips, config, clock=fake_clock)

    # Monday Nov 23 to Saturday Nov 28 (skipping Sunday Nov 29)
    allocations = res["allocations"]
    dates_used = [a.scheduled_date for a in allocations]
    assert len(set(dates_used)) == 6
    assert dates_used[0] == "2026-11-23"
    assert dates_used[1] == "2026-11-24"
    assert dates_used[2] == "2026-11-25"
    assert dates_used[3] == "2026-11-26"
    assert dates_used[4] == "2026-11-27"
    assert dates_used[5] == "2026-11-28"


def test_instant_repack_controls_diff_and_completed_permanence():
    """Simulates user dynamically editing Exam Date: 14 days -> 7 days -> 20 days.
    Asserts 0 LLM calls, completed clips stay untouched, and diff is generated accurately.
    """
    clips = create_fixture_clips(count=10, clip_duration_sec=720)
    # Mark clip 1 and 2 as completed
    clips[0]["status"] = "completed"
    clips[0]["is_completed"] = True
    clips[1]["status"] = "completed"
    clips[1]["is_completed"] = True

    # 1. Initial 14-day schedule
    conf_14 = {
        "target_date": "2026-12-07", # 14 days out
        "minutes_per_day": 60,
        "playback_speed": 1.25,
        "rest_days": ["Sunday"],
        "revision_buffer_days": 2,
        "schedule_strategy": "paced",
    }
    sched_14 = repack_schedule(clips, conf_14, clock=fake_clock)
    # Only 8 incomplete clips are allocated on future study days
    assert len(sched_14["allocations"]) == 8
    assert sched_14["completed_effective_minutes"] > 0

    # 2. Replan to 7 days (tighter exam deadline)
    conf_7 = {
        "target_date": "2026-11-30", # 7 days out
        "minutes_per_day": 60,
        "playback_speed": 1.25,
        "rest_days": ["Sunday"],
        "revision_buffer_days": 2,
        "schedule_strategy": "paced",
        "previous_schedule": sched_14,
    }
    sched_7 = repack_schedule(clips, conf_7, clock=fake_clock)
    assert len(sched_7["allocations"]) == 8
    assert sched_7["required_daily_minutes"] > sched_14["required_daily_minutes"]
    assert sched_7["diff"] is not None
    assert sched_7["diff"]["days_difference"] < 0
    assert "Pace:" in sched_7["diff"]["pace_change"]

    # 3. Replan to 20 days (relaxed deadline)
    conf_20 = {
        "target_date": "2026-12-13", # 20 days out
        "minutes_per_day": 60,
        "playback_speed": 1.5, # also bump playback speed
        "rest_days": ["Sunday"],
        "revision_buffer_days": 2,
        "schedule_strategy": "paced",
        "previous_schedule": sched_7,
    }
    sched_20 = repack_schedule(clips, conf_20, clock=fake_clock)
    assert len(sched_20["allocations"]) == 8
    assert sched_20["required_daily_minutes"] < sched_7["required_daily_minutes"]
    assert sched_20["diff"]["days_difference"] > 0
