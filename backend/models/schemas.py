"""Pydantic schemas for request validation and API responses."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# --- Course Schemas ---
class CourseCreateRequest(BaseModel):
    title: str = Field(..., description="Course or subject title")
    goal_query: str = Field(..., description="User's goal query or topic")
    source_preferences: Optional[str] = Field("", description="Optional preferences like 'freeCodeCamp, official docs'")
    target_date: str = Field(..., description="Target exam or completion date (YYYY-MM-DD)")
    minutes_per_day: int = Field(90, ge=10, le=720, description="Daily available study time in minutes")
    playback_speed: float = Field(1.0, ge=0.5, le=3.0, description="Playback speed scaling factor")
    rest_days: List[str] = Field(default_factory=lambda: ["Sunday"], description="Weekly rest days")
    revision_buffer_days: int = Field(2, ge=0, le=14, description="Days reserved before exam strictly for revision")

class CourseUpdateRequest(BaseModel):
    title: Optional[str] = None
    target_date: Optional[str] = None
    minutes_per_day: Optional[int] = Field(None, ge=10, le=720)
    playback_speed: Optional[float] = Field(None, ge=0.5, le=3.0)
    rest_days: Optional[List[str]] = None
    revision_buffer_days: Optional[int] = Field(None, ge=0, le=14)

class CourseResponse(BaseModel):
    id: str
    title: str
    goal_query: str
    source_preferences: str
    target_date: str
    minutes_per_day: int
    playback_speed: float
    rest_days: List[str]
    revision_buffer_days: int
    status: str
    total_effective_minutes: float = 0.0
    completed_effective_minutes: float = 0.0
    remaining_effective_minutes: float = 0.0
    completion_percentage: float = 0.0
    projected_finish_date: Optional[str] = None
    is_behind_schedule: bool = False
    created_at: str

# --- Source Schemas ---
class SourceImportRequest(BaseModel):
    url: str = Field(..., description="YouTube video or playlist URL")
    is_approved: bool = Field(True, description="Directly approve manual URL imports")

class CandidateDiscoveryResponse(BaseModel):
    candidate_videos: List[Dict[str, Any]]
    candidate_playlists: List[Dict[str, Any]]

class SourceApprovalRequest(BaseModel):
    source_ids_to_approve: List[str] = Field(..., description="List of source IDs to approve")
    source_ids_to_reject: Optional[List[str]] = Field(default_factory=list, description="List of source IDs to drop")

class SourceResponse(BaseModel):
    id: str
    course_id: str
    source_type: str
    title: str
    url: Optional[str] = None
    external_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_approved: bool
    created_at: str

# --- Lesson Schemas ---
class LessonResponse(BaseModel):
    id: str
    course_id: str
    source_id: Optional[str] = None
    title: str
    summary: str
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    start_sec: int
    end_sec: int
    raw_duration_sec: int
    priority: str  # 'core' vs 'deep-dive'
    order_index: int
    chapter_title: Optional[str] = None
    is_tested_out: bool = False

# --- Allocation & Schedule Schemas ---
class AllocationResponse(BaseModel):
    id: str
    course_id: str
    lesson_id: str
    lesson_title: str
    video_id: Optional[str]
    video_url: Optional[str]
    scheduled_date: str
    split_index: int
    split_count: int
    allocated_start_sec: int
    allocated_end_sec: int
    raw_minutes: float
    effective_minutes: float
    is_completed: bool
    is_skipped: bool
    priority: str

class DayScheduleResponse(BaseModel):
    date: str
    day_name: str
    is_rest_day: bool
    is_revision_day: bool
    total_effective_minutes: float
    allocations: List[AllocationResponse]

class ScheduleResponse(BaseModel):
    course_id: str
    days: List[DayScheduleResponse]
    total_effective_minutes: float
    completed_effective_minutes: float
    remaining_effective_minutes: float
    projected_finish_date: Optional[str]
    target_date: str
    is_behind_schedule: bool
    revision_buffer_days: int

# --- Replan, Diff & Undo Schemas ---
class ReplanRequest(BaseModel):
    mode: str = Field("normal", description="'normal', 'compress', or 'extend'")
    minutes_per_day: Optional[int] = Field(None, ge=10, le=720)
    playback_speed: Optional[float] = Field(None, ge=0.5, le=3.0)
    rest_days: Optional[List[str]] = None
    target_date: Optional[str] = None
    revision_buffer_days: Optional[int] = None

class DiffSummary(BaseModel):
    old_finish_date: Optional[str] = None
    new_finish_date: Optional[str] = None
    days_difference: int = 0
    lessons_moved_count: int = 0
    dropped_deep_dive_count: int = 0
    deficit_minutes: float = 0.0
    deficit_message: Optional[str] = None

class ReplanResponse(BaseModel):
    success: bool
    snapshot_id: str
    diff: DiffSummary
    schedule: ScheduleResponse

# --- Settings Schemas ---
class SystemSettingsResponse(BaseModel):
    ytdlp_version: str
    cookies_browser: Optional[str] = None
    timezone: str
    data_dir: str
    db_size_bytes: int
    transcripts_size_bytes: int
    screenshots_size_bytes: int
    has_gemini_key: bool
    has_groq_key: bool
    has_openrouter_key: bool

class UpdateSettingsRequest(BaseModel):
    cookies_browser: Optional[str] = Field(None, description="Browser name for --cookies-from-browser (e.g. 'chrome', 'firefox', 'safari', 'brave')")
