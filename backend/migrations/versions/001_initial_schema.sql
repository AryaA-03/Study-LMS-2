-- 001_initial_schema.sql: Initial Core Tables for LMS & Exam Prep

-- 1. Courses / Study Goals
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal_query TEXT NOT NULL,
    source_preferences TEXT DEFAULT '',
    target_date TEXT NOT NULL,                -- YYYY-MM-DD
    minutes_per_day INTEGER NOT NULL DEFAULT 90,
    playback_speed REAL NOT NULL DEFAULT 1.0, -- 1.0, 1.25, 1.5, 2.0
    rest_days TEXT NOT NULL DEFAULT '["Sunday"]', -- JSON array of weekday names
    revision_buffer_days INTEGER NOT NULL DEFAULT 2,
    status TEXT NOT NULL DEFAULT 'active',    -- active, completed, archived
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Sources (YouTube videos, playlists, PDFs, web pages)
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,                -- youtube_video, youtube_playlist, pdf, url
    title TEXT NOT NULL,
    url TEXT,
    external_id TEXT,                        -- e.g. YouTube video ID or playlist ID
    metadata_json TEXT DEFAULT '{}',
    is_approved INTEGER NOT NULL DEFAULT 0,   -- Approval Gate (0 = pending approval, 1 = approved)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sources_course ON sources(course_id);
CREATE INDEX IF NOT EXISTS idx_sources_approved ON sources(is_approved);

-- 3. Lessons (Atomic study units)
CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    summary TEXT DEFAULT '',
    video_id TEXT,                            -- YouTube video ID for IFrame embed
    video_url TEXT,
    start_sec INTEGER NOT NULL DEFAULT 0,
    end_sec INTEGER NOT NULL DEFAULT 0,
    raw_duration_sec INTEGER NOT NULL,        -- Duration in seconds
    priority TEXT NOT NULL DEFAULT 'core',    -- 'core' vs 'deep-dive'
    order_index INTEGER NOT NULL DEFAULT 0,
    chapter_title TEXT DEFAULT '',
    is_tested_out INTEGER NOT NULL DEFAULT 0, -- Marked 1 if diagnostic test or quiz passed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_lessons_course ON lessons(course_id);
CREATE INDEX IF NOT EXISTS idx_lessons_order ON lessons(course_id, order_index);

-- 4. Schedule Allocations (Day-wise lesson blocks with multi-day splitting)
CREATE TABLE IF NOT EXISTS schedule_allocations (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    scheduled_date TEXT NOT NULL,             -- YYYY-MM-DD
    split_index INTEGER NOT NULL DEFAULT 0,   -- 0-indexed part of a multi-day split
    split_count INTEGER NOT NULL DEFAULT 1,   -- Total number of splits for this lesson
    allocated_start_sec INTEGER NOT NULL,     -- Specific time slice start
    allocated_end_sec INTEGER NOT NULL,       -- Specific time slice end
    effective_minutes REAL NOT NULL,          -- (end - start) / (60 * playback_speed)
    is_completed INTEGER NOT NULL DEFAULT 0,
    completed_at TIMESTAMP,
    is_skipped INTEGER NOT NULL DEFAULT 0,
    skipped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_allocations_course_date ON schedule_allocations(course_id, scheduled_date);
CREATE INDEX IF NOT EXISTS idx_allocations_lesson ON schedule_allocations(lesson_id);

-- 5. Schedule Snapshots (For instant Undo & Diff of schedule replans)
CREATE TABLE IF NOT EXISTS schedule_snapshots (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,                     -- e.g. 'replan', 'compress', 'extend', 'skip', 'settings_change'
    diff_summary_json TEXT NOT NULL DEFAULT '{}',
    snapshot_state_json TEXT NOT NULL,        -- Full serialized state of allocations and parameters
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_snapshots_course ON schedule_snapshots(course_id, created_at);

-- 6. Content Chunks (For Notes, Transcripts, Retrieval, Citations)
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    source_id TEXT REFERENCES sources(id) ON DELETE CASCADE,
    lesson_id TEXT REFERENCES lessons(id) ON DELETE SET NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    token_count INTEGER NOT NULL DEFAULT 0,
    start_sec INTEGER,
    end_sec INTEGER,
    content TEXT NOT NULL,                    -- Exact text of the chunk (300-600 tokens)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chunks_lesson ON chunks(lesson_id);
CREATE INDEX IF NOT EXISTS idx_chunks_course ON chunks(course_id);

-- 7. Full Text Search FTS5 Table for Grounding & Retrieval
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    id UNINDEXED,
    course_id UNINDEXED,
    lesson_id UNINDEXED,
    content,
    tokenize = 'porter unicode61'
);

-- 8. Grounded Study Notes
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id TEXT REFERENCES lessons(id) ON DELETE CASCADE,
    content_markdown TEXT NOT NULL,
    personal_notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. Quizzes & Diagnostic Tests
CREATE TABLE IF NOT EXISTS quizzes (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id TEXT REFERENCES lessons(id) ON DELETE CASCADE,
    quiz_type TEXT NOT NULL DEFAULT 'lesson', -- 'lesson', 'diagnostic', 'mock_exam'
    title TEXT NOT NULL,
    questions_json TEXT NOT NULL,             -- Array of questions with cited chunk_id and verbatim quote
    score REAL,                               -- Percentage 0.0 - 100.0
    passed INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. FSRS Spaced Repetition Flashcards
CREATE TABLE IF NOT EXISTS flashcards (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id TEXT REFERENCES lessons(id) ON DELETE SET NULL,
    chunk_id TEXT REFERENCES chunks(id) ON DELETE SET NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    state INTEGER NOT NULL DEFAULT 0,         -- 0=New, 1=Learning, 2=Review, 3=Relearning
    due_date TIMESTAMP NOT NULL,
    stability REAL NOT NULL DEFAULT 0.0,
    difficulty REAL NOT NULL DEFAULT 0.0,
    elapsed_days INTEGER NOT NULL DEFAULT 0,
    scheduled_days INTEGER NOT NULL DEFAULT 0,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    last_review TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_flashcards_due ON flashcards(course_id, due_date);

-- 11. LLM Response Cache (Content Hash Deduplication)
CREATE TABLE IF NOT EXISTS llm_cache (
    prompt_hash TEXT PRIMARY KEY,             -- SHA-256 of normalized prompt + model
    model_name TEXT NOT NULL,
    response_text TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. Key-Value System Settings
CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
