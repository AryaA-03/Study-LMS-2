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
    schedule_strategy: str = Field("paced", description="'paced' (Spread to Exam Date) or 'fixed' (Fixed Daily Goal)")
    num_study_days: Optional[int] = Field(None, ge=1, le=365, description="Number of study days (alternative to target_date)")
    preferred_daily_minutes: Optional[int] = Field(60, ge=10, le=720, description="Preferred daily study budget in minutes")

class CourseUpdateRequest(BaseModel):
    title: Optional[str] = None
    target_date: Optional[str] = None
    minutes_per_day: Optional[int] = Field(None, ge=10, le=720)
    playback_speed: Optional[float] = Field(None, ge=0.5, le=3.0)
    rest_days: Optional[List[str]] = None
    revision_buffer_days: Optional[int] = Field(None, ge=0, le=14)
    schedule_strategy: Optional[str] = None
    num_study_days: Optional[int] = Field(None, ge=1, le=365)
    preferred_daily_minutes: Optional[int] = Field(None, ge=10, le=720)

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
    schedule_strategy: str = "paced"
    num_study_days: Optional[int] = None
    preferred_daily_minutes: Optional[int] = 60
    status: str
    total_effective_minutes: float = 0.0
    completed_effective_minutes: float = 0.0
    remaining_effective_minutes: float = 0.0
    completion_percentage: float = 0.0
    projected_finish_date: Optional[str] = None
    is_behind_schedule: bool = False
    effective_daily_target_minutes: float = 0.0
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
class LessonUpdateRequest(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    priority: Optional[str] = None  # 'core' vs 'deep-dive'
    chapter_title: Optional[str] = None

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
    is_excluded: bool = False
    pyq_hit_count: int = 0
    pyq_total_marks: int = 0
    priority_tag: Optional[str] = "core"
    status: Optional[str] = "pending"
    completed_at: Optional[str] = None
    skipped_at: Optional[str] = None

class LessonFilterRequest(BaseModel):
    filter_mode: Optional[str] = Field(None, description="'all', 'concepts', or 'examples'")
    include_examples: Optional[bool] = Field(None, description="Set True to include, False to exclude questions/examples videos")
    lesson_ids_to_include: Optional[List[str]] = None
    lesson_ids_to_exclude: Optional[List[str]] = None

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
    clip_id: Optional[str] = None
    pyq_hit_count: int = 0
    pyq_total_marks: int = 0

class AllocationRescheduleRequest(BaseModel):
    target_date: str = Field(..., description="Target date for this allocation (YYYY-MM-DD)")

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
    schedule_strategy: str = "paced"
    effective_daily_target_minutes: float = 0.0
    minutes_per_day: int = 90
    playback_speed: float = 1.25
    num_study_days: Optional[int] = None
    preferred_daily_minutes: Optional[float] = None
    required_daily_minutes: Optional[float] = None
    pace_notice: Optional[str] = None
    exceeds_budget: Optional[bool] = False

# --- Replan, Diff & Undo Schemas ---
class ReplanRequest(BaseModel):
    mode: str = Field("normal", description="'normal', 'compress', or 'extend'")
    schedule_strategy: Optional[str] = Field(None, description="'paced' or 'fixed'")
    minutes_per_day: Optional[int] = Field(None, ge=10, le=720)
    playback_speed: Optional[float] = Field(None, ge=0.5, le=3.0)
    rest_days: Optional[List[str]] = None
    target_date: Optional[str] = None
    revision_buffer_days: Optional[int] = None
    num_study_days: Optional[int] = Field(None, ge=1, le=365)
    preferred_daily_minutes: Optional[int] = Field(None, ge=10, le=720)

class DiffSummary(BaseModel):
    old_finish_date: Optional[str] = None
    new_finish_date: Optional[str] = None
    days_difference: int = 0
    lessons_moved_count: int = 0
    dropped_deep_dive_count: int = 0
    deficit_minutes: float = 0.0
    deficit_message: Optional[str] = None
    pace_change: Optional[str] = None
    pace_notice: Optional[str] = None

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
    has_ollama: bool = False
    gemini_model: str = "gemini-2.5-flash"
    groq_model: str = "llama-3.3-70b-versatile"
    openrouter_model: str = "google/gemini-2.5-flash"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    default_minutes_per_day: int = 90
    default_playback_speed: float = 1.25
    default_rest_days: List[str] = Field(default_factory=lambda: ["Sunday"])
    default_revision_buffer_days: int = 2

class UpdateSettingsRequest(BaseModel):
    cookies_browser: Optional[str] = Field(None, description="Browser name for --cookies-from-browser (e.g. 'chrome', 'firefox', 'safari', 'brave')")
    minutes_per_day: Optional[int] = Field(None, ge=10, le=720)
    playback_speed: Optional[float] = Field(None, ge=0.5, le=3.0)
    rest_days: Optional[List[str]] = None
    revision_buffer_days: Optional[int] = Field(None, ge=0, le=14)
    gemini_model: Optional[str] = None
    groq_model: Optional[str] = None
    openrouter_model: Optional[str] = None
    openrouter_base_url: Optional[str] = None
    ollama_base_url: Optional[str] = None
    ollama_model: Optional[str] = None

class TestConnectionRequest(BaseModel):
    provider: str = Field(..., description="'gemini', 'groq', 'openrouter', or 'ollama'")
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None

class TestConnectionResponse(BaseModel):
    success: bool
    provider: str
    message: str
    guide: Optional[str] = None

class ManualTranscriptRequest(BaseModel):
    title: str
    transcript_text: str
    raw_duration_sec: Optional[int] = 1200
    priority: str = "core"

# --- Notes & Screenshot Schemas ---
class PersonalNotesUpdate(BaseModel):
    personal_notes: str = Field(..., max_length=200000)

class NoteResponse(BaseModel):
    id: str
    course_id: Optional[str] = None
    lesson_id: str
    content_markdown: str
    personal_notes: str = ""
    is_generated: int = 1
    updated_at: Optional[str] = None

class ScreenshotResponse(BaseModel):
    id: str
    timestamp_sec: int
    formatted_time: str
    url: str
    caption: str

# --- Multi-Source & Q&A Schemas ---
class WebSourceImportRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    title: Optional[str] = None

class QARequest(BaseModel):
    query: str = Field(..., max_length=4000)
    lesson_id: Optional[str] = None

class CitationItem(BaseModel):
    chunk_id: str
    source_title: str
    source_type: str = "youtube_video"
    start_sec: Optional[int] = None
    excerpt: str

class QAResponse(BaseModel):
    id: str
    course_id: str
    query: str
    answer_markdown: str
    citations: List[CitationItem] = Field(default_factory=list)

# --- Quiz & Mock Exam Schemas ---
class QuizQuestion(BaseModel):
    id: str
    chunk_id: str
    lesson_id: Optional[str] = None
    quote: str
    question: str
    options: List[str] = Field(default_factory=list)
    correct_index: int = 0
    explanation: str
    question_type: str = "mcq"  # "mcq" or "short_answer"
    max_marks: float = 1.0
    rubric: Optional[List[str]] = None
    sample_solution: Optional[str] = None
    timestamp_sec: Optional[int] = None
    timestamp_str: Optional[str] = None
    replay_url: Optional[str] = None

class QuizGenerateRequest(BaseModel):
    lesson_id: Optional[str] = None
    quiz_type: str = Field("lesson", description="'lesson', 'diagnostic', or 'mock_exam'")
    question_count: int = Field(5, ge=1, le=30)
    title: Optional[str] = None

class QuizResponse(BaseModel):
    id: str
    course_id: str
    lesson_id: Optional[str] = None
    quiz_type: str
    title: str
    questions: List[QuizQuestion]
    score: Optional[float] = None
    passed: bool = False
    time_taken_seconds: Optional[int] = None
    created_at: Optional[str] = None

class QuizSubmitRequest(BaseModel):
    answers: Dict[str, int] = Field(default_factory=dict, description="Mapping of MCQ question ID to chosen option index")
    short_answers: Dict[str, str] = Field(default_factory=dict, description="Mapping of short-answer question ID to student answer text")
    time_taken_seconds: int = 0

class QuizSubmitResponse(BaseModel):
    quiz_id: str
    score: float
    passed: bool
    correct_count: int
    total_questions: int
    mastery_status: str
    tested_out_lessons: List[str] = Field(default_factory=list)
    flashcards_created: int = 0
    missed_count: int = 0
    schedule_updated: bool = False
    diff_summary: Optional[Dict[str, Any]] = None
    short_answer_evaluations: List[Dict[str, Any]] = Field(default_factory=list)
    total_marks_obtained: Optional[float] = None
    total_marks_possible: Optional[float] = None

# --- FSRS Flashcard Schemas ---
class FlashcardCreateRequest(BaseModel):
    front: str
    back: str
    lesson_id: Optional[str] = None
    chunk_id: Optional[str] = None
    source_quote: Optional[str] = None

class FlashcardUpdateRequest(BaseModel):
    front: Optional[str] = None
    back: Optional[str] = None

class FlashcardResponse(BaseModel):
    id: str
    course_id: str
    lesson_id: Optional[str] = None
    chunk_id: Optional[str] = None
    front: str
    back: str
    state: int
    state_name: str
    due_date: str
    stability: float
    difficulty: float
    reps: int
    source_quote: Optional[str] = None
    intervals: Dict[int, str] = Field(default_factory=dict)

class FlashcardReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=4, description="1=Again, 2=Hard, 3=Good, 4=Easy")

class FlashcardReviewResponse(BaseModel):
    card: FlashcardResponse
    next_interval_str: str

class FlashcardCountsResponse(BaseModel):
    total: int
    due: int
    new: int
    learning: int
    review: int

# --- PYQ (Past Papers) Schemas ---
class PYQUploadTextRequest(BaseModel):
    title: str = Field(..., max_length=256)
    raw_text: str = Field(..., min_length=10)

class PYQQuestionItem(BaseModel):
    id: str
    question_number: str
    question_text: str
    marks: Optional[int] = None
    matched_lesson_id: Optional[str] = None
    matched_chunk_id: Optional[str] = None
    snippet: Optional[str] = ""

class PYQUploadResponse(BaseModel):
    success: bool = True
    paper_id: str
    title: str
    filename: Optional[str] = ""
    questions_count: int
    matched_count: int
    questions: List[PYQQuestionItem] = Field(default_factory=list)

# --- Cram Sheet Schemas ---
class CramSheetGenerateRequest(BaseModel):
    force_refresh: bool = False
    full_syllabus: bool = False

class CramSheetResponse(BaseModel):
    id: str
    course_id: str
    content_markdown: str
    notes_hash: str
    is_generated_by_llm: bool = False
    cached: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# --- Syllabus Alignment Schemas ---
class SyllabusMatchRequest(BaseModel):
    syllabus_text: str = Field(..., min_length=5, max_length=500000)
    strictness: Optional[str] = Field("balanced", description="'strict', 'balanced', or 'comprehensive'")

class SyllabusTopicMatch(BaseModel):
    topic: str
    unit: Optional[str] = "General"
    matched_lesson_count: int = 0
    matched_lesson_ids: List[str] = Field(default_factory=list)

class SyllabusLessonMatch(BaseModel):
    id: str
    title: str
    raw_duration_sec: int
    order_index: int = 0
    is_matched: bool
    match_score: float
    matched_topics: List[str] = Field(default_factory=list)
    match_reason: str = ""

class SyllabusMatchResponse(BaseModel):
    course_id: str
    total_lessons: int
    matched_lessons_count: int
    matched_percentage: float
    saved_minutes: int
    topics: List[SyllabusTopicMatch] = Field(default_factory=list)
    lessons: List[SyllabusLessonMatch] = Field(default_factory=list)

class SyllabusApplyRequest(BaseModel):
    syllabus_text: str = Field(..., min_length=1)
    included_lesson_ids: List[str] = Field(default_factory=list)
    strictness: Optional[str] = "balanced"
    regenerate_schedule: bool = True

class SyllabusApplyResponse(BaseModel):
    course_id: str
    included_count: int
    excluded_count: int
    schedule_reflowed: bool = True
    message: str

class SyllabusInfoResponse(BaseModel):
    course_id: str
    syllabus_text: Optional[str] = None
    syllabus_metadata: Optional[Dict[str, Any]] = None



