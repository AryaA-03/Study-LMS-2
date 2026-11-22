"""Deterministic Adaptive Schedule Engine.

Pure Python, zero LLM calls, fully unit-tested with an injectable clock.
Handles:
- Injectable clock (local calendar dates, default Asia/Kolkata)
- Dual Scheduling Strategies:
  * "paced": Spreads lessons evenly across available study days until the exam revision buffer.
  * "fixed": Packs lessons greedily into user's fixed daily budget.
- Playback speed scaling (effective_minutes = raw_minutes / playback_speed)
- Granular lesson exclusion / filtering (skip questions/examples or custom selection)
- Multi-day lesson splitting by [start_sec, end_sec]
- Weekly rest days & exam revision buffer
- Dynamic reflow of overdue/skipped lessons
- One-click Compress (drop deep-dive topics with deficit calculation) vs Extend Deadline
- Diff generation & snapshot-based Undo
"""

from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional, Tuple, Callable
import json
import math
import uuid
import logging
from zoneinfo import ZoneInfo

from backend.config import LOCAL_TZ

logger = logging.getLogger("learn_lms.scheduler")

def default_clock() -> date:
    """Default clock returning today's date in local timezone."""
    return datetime.now(LOCAL_TZ).date()

class ScheduleAllocation:
    def __init__(
        self,
        id: str,
        course_id: str,
        lesson_id: str,
        lesson_title: str,
        scheduled_date: str,  # YYYY-MM-DD
        allocated_start_sec: int,
        allocated_end_sec: int,
        effective_minutes: float,
        split_index: int = 0,
        split_count: int = 1,
        is_completed: bool = False,
        is_skipped: bool = False,
        priority: str = "core",
        video_id: Optional[str] = None,
        video_url: Optional[str] = None,
        clip_id: Optional[str] = None,
    ):
        self.id = id
        self.course_id = course_id
        self.lesson_id = lesson_id
        self.lesson_title = lesson_title
        self.scheduled_date = scheduled_date
        self.allocated_start_sec = allocated_start_sec
        self.allocated_end_sec = allocated_end_sec
        self.effective_minutes = round(effective_minutes, 2)
        self.split_index = split_index
        self.split_count = split_count
        self.is_completed = is_completed
        self.is_skipped = is_skipped
        self.priority = priority
        self.video_id = video_id
        self.video_url = video_url
        self.clip_id = clip_id or lesson_id

    @property
    def raw_minutes(self) -> float:
        return round((self.allocated_end_sec - self.allocated_start_sec) / 60.0, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "course_id": self.course_id,
            "lesson_id": self.lesson_id,
            "clip_id": self.clip_id,
            "lesson_title": self.lesson_title,
            "scheduled_date": self.scheduled_date,
            "allocated_start_sec": self.allocated_start_sec,
            "allocated_end_sec": self.allocated_end_sec,
            "raw_minutes": self.raw_minutes,
            "effective_minutes": self.effective_minutes,
            "split_index": self.split_index,
            "split_count": self.split_count,
            "is_completed": self.is_completed,
            "is_skipped": self.is_skipped,
            "priority": self.priority,
            "video_id": self.video_id,
            "video_url": self.video_url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleAllocation":
        return cls(
            id=data["id"],
            course_id=data["course_id"],
            lesson_id=data["lesson_id"],
            clip_id=data.get("clip_id") or data["lesson_id"],
            lesson_title=data.get("lesson_title", "Lesson"),
            scheduled_date=data["scheduled_date"],
            allocated_start_sec=data["allocated_start_sec"],
            allocated_end_sec=data["allocated_end_sec"],
            effective_minutes=data["effective_minutes"],
            split_index=data.get("split_index", 0),
            split_count=data.get("split_count", 1),
            is_completed=data.get("is_completed", False),
            is_skipped=data.get("is_skipped", False),
            priority=data.get("priority", "core"),
            video_id=data.get("video_id"),
            video_url=data.get("video_url"),
        )

def calculate_effective_minutes(raw_seconds: int, playback_speed: float) -> float:
    """Scales raw seconds by playback speed into effective minutes."""
    speed = max(0.5, playback_speed)
    raw_minutes = raw_seconds / 60.0
    return raw_minutes / speed

def is_rest_day(target_date: date, rest_days: List[str]) -> bool:
    """Checks if target_date falls on a configured rest day."""
    weekday_name = target_date.strftime("%A")
    return weekday_name in rest_days

def get_study_dates(
    start_date: date,
    end_date: date,
    rest_days: List[str],
    revision_buffer_days: int = 0,
) -> Tuple[List[date], List[date], List[date]]:
    """Returns (study_dates, rest_dates, revision_dates) between start_date and end_date."""
    all_dates = []
    curr = start_date
    while curr <= end_date:
        all_dates.append(curr)
        curr += timedelta(days=1)

    # Revision days are the last N days immediately before or on end_date
    revision_dates = []
    if revision_buffer_days > 0 and len(all_dates) >= revision_buffer_days:
        revision_dates = all_dates[-revision_buffer_days:]
        study_candidate_dates = all_dates[:-revision_buffer_days]
    else:
        study_candidate_dates = all_dates

    study_dates = []
    rest_dates = []
    for d in study_candidate_dates:
        if is_rest_day(d, rest_days):
            rest_dates.append(d)
        else:
            study_dates.append(d)

    return study_dates, rest_dates, revision_dates

def generate_schedule(
    course_id: str,
    lessons: List[Dict[str, Any]],
    start_date: date,
    target_date: date,
    minutes_per_day: int,
    playback_speed: float,
    rest_days: List[str],
    revision_buffer_days: int = 2,
    schedule_strategy: str = "paced",
    completed_lesson_ids: Optional[set] = None,
    skipped_lesson_ids: Optional[set] = None,
    clock: Optional[Callable[[], date]] = None,
) -> Dict[str, Any]:
    """Generates day-wise lesson allocations with multi-day splitting and rest/buffer days.

    Args:
        course_id: Course ID
        lessons: List of lesson dicts (id, title, raw_duration_sec, start_sec, end_sec, priority, is_excluded, etc.)
        start_date: Start date for scheduling
        target_date: Exam target date
        minutes_per_day: Fixed daily study budget in effective minutes (used if strategy='fixed')
        playback_speed: Speed factor (e.g. 1.25, 1.5)
        rest_days: e.g. ["Sunday"]
        revision_buffer_days: e.g. 2 days reserved strictly for revision
        schedule_strategy: 'paced' (Spread to Exam Date) or 'fixed' (Fixed Daily Goal)
        completed_lesson_ids: Lessons already completed
        skipped_lesson_ids: Lessons skipped
        clock: Injectable clock function returning date
    """
    if clock is None:
        clock = default_clock
    today = clock()

    if completed_lesson_ids is None:
        completed_lesson_ids = set()
    if skipped_lesson_ids is None:
        skipped_lesson_ids = set()

    # Filter lessons to schedule (exclude tested out or explicitly excluded)
    active_lessons = [
        l for l in lessons
        if not l.get("is_tested_out", False) and not l.get("is_excluded", False)
    ]

    # Calculate total remaining effective minutes to pace
    remaining_lessons = [
        l for l in active_lessons
        if l["id"] not in completed_lesson_ids and l["id"] not in skipped_lesson_ids
    ]
    total_remaining_eff_min = sum(
        calculate_effective_minutes(l.get("raw_duration_sec", 0), playback_speed)
        for l in remaining_lessons
    )

    # Determine daily study budget based on strategy
    deadline_effective = target_date - timedelta(days=revision_buffer_days)
    study_dates, _, _ = get_study_dates(start_date, deadline_effective, rest_days, revision_buffer_days=0)
    effective_cutoff = study_dates[-1] if study_dates else deadline_effective
    
    allocated_daily_budget = float(minutes_per_day)
    if schedule_strategy == "paced":
        if len(study_dates) > 0 and total_remaining_eff_min > 0:
            # Spread evenly across all available study days
            paced_budget = total_remaining_eff_min / len(study_dates)
            allocated_daily_budget = max(5.0, paced_budget)
            logger.info(
                f"[Scheduler] Strategy: PACED | Remaining: {round(total_remaining_eff_min, 1)}m | "
                f"Study Days: {len(study_dates)} | Daily Target: {round(allocated_daily_budget, 1)}m/day"
            )
        else:
            allocated_daily_budget = float(minutes_per_day)
    else:
        logger.info(
            f"[Scheduler] Strategy: FIXED | Daily Budget: {allocated_daily_budget}m/day"
        )

    allocations: List[ScheduleAllocation] = []
    curr_date = start_date
    curr_day_remaining_min = allocated_daily_budget

    def advance_to_next_study_day(d: date) -> date:
        next_d = d + timedelta(days=1)
        while is_rest_day(next_d, rest_days):
            next_d += timedelta(days=1)
        return next_d

    # Ensure start date is not a rest day
    if is_rest_day(curr_date, rest_days):
        curr_date = advance_to_next_study_day(curr_date)

    import uuid

    for lesson in active_lessons:
        lid = lesson["id"]
        ltitle = lesson.get("title", f"Lesson {lid}")
        lstart = int(lesson.get("start_sec", 0))
        lend = int(lesson.get("end_sec", lesson.get("raw_duration_sec", 0)))
        raw_duration = lend - lstart
        if raw_duration <= 0:
            raw_duration = int(lesson.get("raw_duration_sec", 600))
            lend = lstart + raw_duration

        priority = lesson.get("priority", "core")
        video_id = lesson.get("video_id")
        video_url = lesson.get("video_url")
        is_comp = lid in completed_lesson_ids
        is_skip = lid in skipped_lesson_ids

        total_effective = calculate_effective_minutes(raw_duration, playback_speed)

        # Multi-day splitting loop
        remaining_raw_sec = raw_duration
        current_split_start = lstart
        split_segments = []

        while remaining_raw_sec > 0:
            # In paced mode, cap at effective_cutoff to prevent spillover into rest days or revision buffer
            if schedule_strategy == "paced" and curr_date >= effective_cutoff:
                sec_allocated = remaining_raw_sec
                eff_min = calculate_effective_minutes(sec_allocated, playback_speed)
                split_segments.append((
                    curr_date,
                    current_split_start,
                    current_split_start + sec_allocated,
                    eff_min,
                ))
                curr_day_remaining_min = max(0.0, curr_day_remaining_min - eff_min)
                remaining_raw_sec = 0
                break

            if curr_day_remaining_min <= 0.05:  # Less than 3 seconds remaining
                curr_date = advance_to_next_study_day(curr_date)
                curr_day_remaining_min = allocated_daily_budget

            # Available raw seconds today based on remaining effective minutes
            max_raw_sec_today = int(curr_day_remaining_min * 60.0 * playback_speed)
            if max_raw_sec_today >= remaining_raw_sec:
                # Whole remaining lesson fits in today
                sec_allocated = remaining_raw_sec
                eff_min = calculate_effective_minutes(sec_allocated, playback_speed)
                split_segments.append((
                    curr_date,
                    current_split_start,
                    current_split_start + sec_allocated,
                    eff_min,
                ))
                curr_day_remaining_min -= eff_min
                remaining_raw_sec = 0
            else:
                # Lesson must split across consecutive study days
                sec_allocated = max_raw_sec_today
                if sec_allocated > 0:
                    eff_min = calculate_effective_minutes(sec_allocated, playback_speed)
                    split_segments.append((
                        curr_date,
                        current_split_start,
                        current_split_start + sec_allocated,
                        eff_min,
                    ))
                    current_split_start += sec_allocated
                    remaining_raw_sec -= sec_allocated

                # Advance to next study day for remaining slice
                curr_date = advance_to_next_study_day(curr_date)
                curr_day_remaining_min = allocated_daily_budget

        total_splits = len(split_segments)
        for idx, (alloc_date, s_start, s_end, s_eff) in enumerate(split_segments):
            alloc_id = str(uuid.uuid4())
            allocations.append(
                ScheduleAllocation(
                    id=alloc_id,
                    course_id=course_id,
                    lesson_id=lid,
                    lesson_title=ltitle,
                    scheduled_date=alloc_date.strftime("%Y-%m-%d"),
                    allocated_start_sec=s_start,
                    allocated_end_sec=s_end,
                    effective_minutes=s_eff,
                    split_index=idx,
                    split_count=total_splits,
                    is_completed=is_comp,
                    is_skipped=is_skip,
                    priority=priority,
                    video_id=video_id,
                    video_url=video_url,
                )
            )

    # Compute projected finish date
    projected_finish_date = None
    if allocations:
        dates_used = [datetime.strptime(a.scheduled_date, "%Y-%m-%d").date() for a in allocations if not a.is_skipped]
        if dates_used:
            projected_finish_date = max(dates_used)

    # Check if behind schedule (finish date encroaches on revision buffer or exceeds target_date)
    is_behind = False
    if projected_finish_date and projected_finish_date > deadline_effective:
        is_behind = True

    return {
        "allocations": allocations,
        "projected_finish_date": projected_finish_date.strftime("%Y-%m-%d") if projected_finish_date else None,
        "is_behind_schedule": is_behind,
        "target_date": target_date.strftime("%Y-%m-%d"),
        "minutes_per_day": minutes_per_day,
        "playback_speed": playback_speed,
        "rest_days": rest_days,
        "revision_buffer_days": revision_buffer_days,
        "schedule_strategy": schedule_strategy,
        "effective_daily_target_minutes": allocated_daily_budget,
    }

def reflow_overdue_and_remaining(
    course_id: str,
    allocations: List[ScheduleAllocation],
    lessons: List[Dict[str, Any]],
    target_date: date,
    minutes_per_day: int,
    playback_speed: float,
    rest_days: List[str],
    revision_buffer_days: int = 2,
    schedule_strategy: str = "paced",
    clock: Optional[Callable[[], date]] = None,
) -> Dict[str, Any]:
    """Reflows uncompleted or overdue allocations starting from today forward."""
    if clock is None:
        clock = default_clock
    today = clock()

    # Retain completed allocations in the past
    completed_allocs = [a for a in allocations if a.is_completed]
    completed_lesson_ids = {a.lesson_id for a in completed_allocs}
    skipped_lesson_ids = {a.lesson_id for a in allocations if a.is_skipped}

    # Lessons that still need scheduling
    uncompleted_lessons = [
        l for l in lessons
        if l["id"] not in completed_lesson_ids and l["id"] not in skipped_lesson_ids and not l.get("is_tested_out", False) and not l.get("is_excluded", False)
    ]

    reflow_result = generate_schedule(
        course_id=course_id,
        lessons=uncompleted_lessons,
        start_date=today,
        target_date=target_date,
        minutes_per_day=minutes_per_day,
        playback_speed=playback_speed,
        rest_days=rest_days,
        revision_buffer_days=revision_buffer_days,
        schedule_strategy=schedule_strategy,
        clock=clock,
    )

    all_allocs = completed_allocs + reflow_result["allocations"]
    reflow_result["allocations"] = all_allocs

    # Re-evaluate finish date
    dates_used = [datetime.strptime(a.scheduled_date, "%Y-%m-%d").date() for a in all_allocs if not a.is_skipped]
    projected = max(dates_used) if dates_used else today
    deadline_effective = target_date - timedelta(days=revision_buffer_days)
    reflow_result["projected_finish_date"] = projected.strftime("%Y-%m-%d")
    reflow_result["is_behind_schedule"] = projected > deadline_effective

    return reflow_result

def compress_schedule(
    course_id: str,
    lessons: List[Dict[str, Any]],
    start_date: date,
    target_date: date,
    minutes_per_day: int,
    playback_speed: float,
    rest_days: List[str],
    revision_buffer_days: int = 2,
    clock: Optional[Callable[[], date]] = None,
) -> Tuple[Dict[str, Any], int, float, Optional[str]]:
    """Compresses schedule by progressively dropping deep-dive topics."""
    if clock is None:
        clock = default_clock
    today = clock()
    deadline_effective = target_date - timedelta(days=revision_buffer_days)

    study_dates, _, _ = get_study_dates(today, deadline_effective, rest_days, revision_buffer_days=0)
    available_study_minutes = len(study_dates) * minutes_per_day

    # Exclude already excluded lessons
    active_lessons = [l for l in lessons if not l.get("is_excluded", False)]
    core_lessons = [l for l in active_lessons if l.get("priority", "core") == "core"]
    deep_dive_lessons = [l for l in active_lessons if l.get("priority", "core") == "deep-dive"]

    core_raw_sec = sum(l.get("raw_duration_sec", 0) for l in core_lessons)
    core_effective_min = calculate_effective_minutes(core_raw_sec, playback_speed)

    dropped_count = 0
    candidate_lessons = list(core_lessons)

    remaining_budget_for_deep_dive = available_study_minutes - core_effective_min
    included_deep_dive = []
    dropped_deep_dive = []

    for dd in deep_dive_lessons:
        dd_eff = calculate_effective_minutes(dd.get("raw_duration_sec", 0), playback_speed)
        if dd_eff <= remaining_budget_for_deep_dive:
            included_deep_dive.append(dd)
            remaining_budget_for_deep_dive -= dd_eff
        else:
            dropped_deep_dive.append(dd)

    dropped_count = len(dropped_deep_dive)
    all_included = candidate_lessons + included_deep_dive

    deficit_minutes = 0.0
    deficit_message = None
    if core_effective_min > available_study_minutes:
        deficit_minutes = round(core_effective_min - available_study_minutes, 1)
        needed_days = math.ceil(deficit_minutes / minutes_per_day)
        deficit_message = (
            f"Cannot fit all {len(core_lessons)} core topics before the revision buffer. "
            f"Deficit: {deficit_minutes} effective minutes. "
            f"Recommendation: Extend deadline by at least {needed_days} day(s) or increase daily study by {math.ceil(deficit_minutes / max(1, len(study_dates)))} min/day."
        )

    sched = generate_schedule(
        course_id=course_id,
        lessons=all_included,
        start_date=today,
        target_date=target_date,
        minutes_per_day=minutes_per_day,
        playback_speed=playback_speed,
        rest_days=rest_days,
        revision_buffer_days=revision_buffer_days,
        schedule_strategy="fixed",
        clock=clock,
    )

    return sched, dropped_count, deficit_minutes, deficit_message

def compute_schedule_diff(
    old_allocations: List[ScheduleAllocation],
    new_allocations: List[ScheduleAllocation],
    old_target_date: str,
    new_target_date: str,
    old_projected: Optional[str],
    new_projected: Optional[str],
    dropped_count: int = 0,
    deficit_minutes: float = 0.0,
    deficit_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculates diff between old and new schedule states."""
    old_date_map = {a.lesson_id: a.scheduled_date for a in old_allocations}
    moved_count = 0
    for a in new_allocations:
        if a.lesson_id in old_date_map and old_date_map[a.lesson_id] != a.scheduled_date:
            moved_count += 1

    days_diff = 0
    if old_projected and new_projected:
        d1 = datetime.strptime(old_projected, "%Y-%m-%d").date()
        d2 = datetime.strptime(new_projected, "%Y-%m-%d").date()
        days_diff = (d2 - d1).days

    return {
        "old_finish_date": old_projected,
        "new_finish_date": new_projected,
        "days_difference": days_diff,
        "lessons_moved_count": moved_count,
        "dropped_deep_dive_count": dropped_count,
        "deficit_minutes": deficit_minutes,
        "deficit_message": deficit_message,
    }


def repack_schedule(
    clips: List[Dict[str, Any]],
    config: Dict[str, Any],
    clock: Optional[Callable[[], date]] = None,
) -> Dict[str, Any]:
    """Pure, unit-tested deterministic day-wise repacker (Layer 2: Mutable Schedule).

    Maps incomplete Concept Clips onto calendar days (Asia/Kolkata) in < 10ms.
    Zero LLM calls. Never splits a ~10–15 min Concept Clip mid-topic.

    Supports two clean scheduling modes:
    1. Fit to Exam Date / Number of Days ('paced'):
       Calculates required_daily_minutes = remaining_effective_minutes / available_study_days
       and distributes Concept Clips evenly up to the revision buffer (surfaces pace notice
       if required pace exceeds preferred daily budget).
    2. Fixed Daily Budget ('fixed'):
       Packs sequential Concept Clips greedily into each study day (soft ±15% tolerance)
       and recalculates the projected finish date.
    """
    if clock is None:
        clock = default_clock
    today = clock()

    course_id = config.get("course_id", "")
    playback_speed = max(0.5, float(config.get("playback_speed", 1.25)))
    rest_days = list(config.get("rest_days", ["Sunday"]))
    revision_buffer_days = max(0, int(config.get("revision_buffer_days", 2)))
    strategy = config.get("schedule_strategy") or config.get("mode") or "paced"
    if strategy in ("fit_to_date", "fit"):
        strategy = "paced"
    elif strategy in ("fixed_budget", "budget"):
        strategy = "fixed"

    minutes_per_day = int(config.get("minutes_per_day", 90))
    preferred_daily_minutes = float(config.get("preferred_daily_minutes") or minutes_per_day)

    # 1. Determine target date and study days
    num_study_days = config.get("num_study_days") or config.get("study_days")
    if num_study_days is not None and int(num_study_days) > 0:
        num_days = int(num_study_days)
        study_dates = []
        d = today
        while len(study_dates) < num_days:
            if not is_rest_day(d, rest_days):
                study_dates.append(d)
            d += timedelta(days=1)
        target_date = (study_dates[-1] + timedelta(days=revision_buffer_days)) if study_dates else today
        deadline_effective = study_dates[-1] if study_dates else today
    else:
        raw_target = config.get("target_date") or config.get("exam_date")
        if isinstance(raw_target, str):
            target_date = datetime.strptime(raw_target, "%Y-%m-%d").date()
        elif isinstance(raw_target, date):
            target_date = raw_target
        else:
            target_date = today + timedelta(days=14)

        deadline_effective = target_date - timedelta(days=revision_buffer_days)
        study_dates, _, _ = get_study_dates(today, deadline_effective, rest_days, revision_buffer_days=0)

    # 2. Filter clips: active, completed, and incomplete
    active_clips = [c for c in clips if not c.get("is_excluded", False)]

    completed_clips = []
    incomplete_clips = []

    for c in active_clips:
        status = c.get("status", "not_started")
        is_comp = c.get("is_completed", False) or status == "completed"
        is_tested = c.get("is_tested_out", False) or status == "tested_out"
        is_skip = c.get("is_skipped", False) or status == "skipped"

        if is_comp:
            completed_clips.append(c)
        elif not is_tested and not is_skip:
            incomplete_clips.append(c)

    dropped_count = 0
    if config.get("mode") == "compress":
        kept_incomplete = []
        for c in incomplete_clips:
            prio = c.get("priority_tag") or c.get("priority", "core")
            if prio == "deep-dive":
                dropped_count += 1
            else:
                kept_incomplete.append(c)
        incomplete_clips = kept_incomplete

    # 3. Calculate remaining and completed effective minutes
    total_remaining_eff_min = sum(
        calculate_effective_minutes(c.get("raw_duration_sec") or (c.get("end_sec", 0) - c.get("start_sec", 0)), playback_speed)
        for c in incomplete_clips
    )
    total_completed_eff_min = sum(
        calculate_effective_minutes(c.get("raw_duration_sec") or (c.get("end_sec", 0) - c.get("start_sec", 0)), playback_speed)
        for c in completed_clips
    )

    if config.get("mode") == "extend" and strategy == "paced":
        eff_budget = max(10.0, preferred_daily_minutes)
        needed_days = max(1, int(math.ceil(total_remaining_eff_min / eff_budget))) if total_remaining_eff_min > 0 else len(study_dates)
        if needed_days > len(study_dates):
            study_dates = []
            d = today
            while len(study_dates) < needed_days:
                if not is_rest_day(d, rest_days):
                    study_dates.append(d)
                d += timedelta(days=1)
            target_date = study_dates[-1] + timedelta(days=revision_buffer_days)
            deadline_effective = study_dates[-1]

    allocations: List[ScheduleAllocation] = []
    pace_notice: Optional[str] = None
    exceeds_budget: bool = False

    def advance_to_study_day(curr: date) -> date:
        while is_rest_day(curr, rest_days):
            curr += timedelta(days=1)
        return curr

    # 4. Schedule incomplete clips onto study days without splitting any ~10-15 min clip
    if strategy == "paced":
        avail_days = max(1, len(study_dates))
        required_daily_minutes = round(total_remaining_eff_min / avail_days, 1) if (total_remaining_eff_min > 0 and avail_days > 0) else 0.0
        allocated_daily_target = required_daily_minutes

        if preferred_daily_minutes > 0 and required_daily_minutes > preferred_daily_minutes:
            exceeds_budget = True
            pace_notice = (
                f"Required pace ({required_daily_minutes}m/day) exceeds your preferred daily budget "
                f"({round(preferred_daily_minutes, 1)}m/day). Use 1-click Compress to drop deep-dive topics or Extend deadline."
            )

        # Distribute clips sequentially across available study dates
        if study_dates and incomplete_clips:
            day_idx = 0
            day_accum_min = 0.0

            for clip_idx, clip in enumerate(incomplete_clips):
                raw_sec = clip.get("raw_duration_sec") or (clip.get("end_sec", 0) - clip.get("start_sec", 0))
                eff_min = calculate_effective_minutes(raw_sec, playback_speed)

                # Advance to next day if adding this clip exceeds day's share (unless on last study day)
                is_last_day = (day_idx >= len(study_dates) - 1)
                # If current day already has at least one clip and adding this one exceeds target pace by > 15%
                if not is_last_day and day_accum_min > 0 and (day_accum_min + eff_min) > (required_daily_minutes * 1.15):
                    day_idx += 1
                    day_accum_min = 0.0

                alloc_date = study_dates[min(day_idx, len(study_dates) - 1)]
                lid = clip.get("id") or str(uuid.uuid4())
                allocations.append(
                    ScheduleAllocation(
                        id=str(uuid.uuid4()),
                        course_id=course_id,
                        lesson_id=lid,
                        clip_id=lid,
                        lesson_title=clip.get("title", f"Clip {lid}"),
                        scheduled_date=alloc_date.strftime("%Y-%m-%d"),
                        allocated_start_sec=clip.get("start_sec", 0),
                        allocated_end_sec=clip.get("end_sec", raw_sec),
                        effective_minutes=eff_min,
                        split_index=0,
                        split_count=1,
                        is_completed=False,
                        is_skipped=False,
                        priority=clip.get("priority_tag") or clip.get("priority", "core"),
                        video_id=clip.get("video_id"),
                        video_url=clip.get("video_url"),
                    )
                )
                day_accum_min += eff_min
    else:
        # Fixed Daily Budget mode: pack greedily with soft ±15% tolerance
        budget = float(minutes_per_day)
        allocated_daily_target = budget
        max_daily_budget = budget * 1.15

        required_daily_minutes = budget
        curr_d = advance_to_study_day(today)
        day_accum_min = 0.0

        for clip in incomplete_clips:
            raw_sec = clip.get("raw_duration_sec") or (clip.get("end_sec", 0) - clip.get("start_sec", 0))
            eff_min = calculate_effective_minutes(raw_sec, playback_speed)

            # Check if this clip fits into current day
            if day_accum_min > 0 and (day_accum_min + eff_min) > max_daily_budget:
                # Advance to next non-rest study day
                curr_d = advance_to_study_day(curr_d + timedelta(days=1))
                day_accum_min = 0.0

            lid = clip.get("id") or str(uuid.uuid4())
            allocations.append(
                ScheduleAllocation(
                    id=str(uuid.uuid4()),
                    course_id=course_id,
                    lesson_id=lid,
                    clip_id=lid,
                    lesson_title=clip.get("title", f"Clip {lid}"),
                    scheduled_date=curr_d.strftime("%Y-%m-%d"),
                    allocated_start_sec=clip.get("start_sec", 0),
                    allocated_end_sec=clip.get("end_sec", raw_sec),
                    effective_minutes=eff_min,
                    split_index=0,
                    split_count=1,
                    is_completed=False,
                    is_skipped=False,
                    priority=clip.get("priority_tag") or clip.get("priority", "core"),
                    video_id=clip.get("video_id"),
                    video_url=clip.get("video_url"),
                )
            )
            day_accum_min += eff_min

    # 5. Projected finish date calculation
    projected_finish_date = None
    if allocations:
        dates_used = [datetime.strptime(a.scheduled_date, "%Y-%m-%d").date() for a in allocations]
        projected_finish_date = max(dates_used)
    else:
        projected_finish_date = today

    is_behind = projected_finish_date > deadline_effective

    # 6. Build day-wise responses matching DayScheduleResponse schema
    calendar_end = max(target_date, projected_finish_date)
    day_map: Dict[str, List[ScheduleAllocation]] = {}
    for a in allocations:
        day_map.setdefault(a.scheduled_date, []).append(a)

    days_list = []
    curr = today
    while curr <= calendar_end:
        d_str = curr.strftime("%Y-%m-%d")
        d_name = curr.strftime("%A")
        is_rest = is_rest_day(curr, rest_days)
        is_rev = (curr > deadline_effective and curr <= target_date)
        day_allocs = day_map.get(d_str, [])
        day_eff_total = round(sum(a.effective_minutes for a in day_allocs), 2)

        days_list.append({
            "date": d_str,
            "day_name": d_name,
            "is_rest_day": is_rest,
            "is_revision_day": is_rev,
            "total_effective_minutes": day_eff_total,
            "allocations": [a.to_dict() for a in day_allocs],
        })
        curr += timedelta(days=1)

    # 7. Diff calculation if previous schedule provided
    diff = None
    prev = config.get("previous_schedule")
    if prev and isinstance(prev, dict):
        old_finish = prev.get("projected_finish_date")
        new_finish = projected_finish_date.strftime("%Y-%m-%d") if projected_finish_date else None
        days_diff = 0
        if old_finish and new_finish:
            try:
                days_diff = (datetime.strptime(new_finish, "%Y-%m-%d").date() - datetime.strptime(old_finish, "%Y-%m-%d").date()).days
            except Exception:
                days_diff = 0

        old_pace = prev.get("effective_daily_target_minutes") or prev.get("minutes_per_day", 0)
        new_pace = allocated_daily_target
        pace_change_str = f"Pace: {round(float(old_pace))}m -> {round(float(new_pace))}m/day" if old_pace else None

        diff = {
            "old_finish_date": old_finish,
            "new_finish_date": new_finish,
            "days_difference": days_diff,
            "pace_change": pace_change_str,
            "lessons_moved_count": len(allocations),
            "dropped_deep_dive_count": dropped_count,
            "deficit_minutes": 0.0,
            "deficit_message": pace_notice,
        }

    return {
        "allocations": allocations,
        "days": days_list,
        "projected_finish_date": projected_finish_date.strftime("%Y-%m-%d") if projected_finish_date else None,
        "is_behind_schedule": is_behind,
        "target_date": target_date.strftime("%Y-%m-%d"),
        "minutes_per_day": minutes_per_day,
        "preferred_daily_minutes": preferred_daily_minutes,
        "playback_speed": playback_speed,
        "rest_days": rest_days,
        "revision_buffer_days": revision_buffer_days,
        "schedule_strategy": strategy,
        "effective_daily_target_minutes": allocated_daily_target,
        "required_daily_minutes": required_daily_minutes,
        "total_effective_minutes": round(total_completed_eff_min + total_remaining_eff_min, 2),
        "completed_effective_minutes": round(total_completed_eff_min, 2),
        "remaining_effective_minutes": round(total_remaining_eff_min, 2),
        "pace_notice": pace_notice,
        "exceeds_budget": exceeds_budget,
        "diff": diff,
    }



# NOTE: trigger_course_reflow and replan_course_schedule are intentionally NOT
# re-exported here. Callers should import directly from backend.routers.schedule
# to avoid circular imports (routers.schedule already imports from this module).

