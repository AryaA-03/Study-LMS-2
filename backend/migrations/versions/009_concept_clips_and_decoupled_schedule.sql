-- 009_concept_clips_and_decoupled_schedule.sql: Decoupled Concept Clips and Immutable Content Layer

-- 1. Extend lessons table with priority_tag and permanent status tracking
ALTER TABLE lessons ADD COLUMN priority_tag TEXT NOT NULL DEFAULT 'core';
ALTER TABLE lessons ADD COLUMN status TEXT NOT NULL DEFAULT 'not_started';
ALTER TABLE lessons ADD COLUMN completed_at TIMESTAMP;
ALTER TABLE lessons ADD COLUMN skipped_at TIMESTAMP;

-- 2. Extend courses table with flexible schedule budget controls
ALTER TABLE courses ADD COLUMN preferred_daily_minutes INTEGER DEFAULT 60;
ALTER TABLE courses ADD COLUMN num_study_days INTEGER DEFAULT NULL;

-- 3. Extend schedule_allocations with clip_id reference
ALTER TABLE schedule_allocations ADD COLUMN clip_id TEXT DEFAULT NULL;

-- 4. Create permanent concept_clips table for Layer 1 immutable content
CREATE TABLE IF NOT EXISTS concept_clips (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    source_id TEXT REFERENCES sources(id) ON DELETE SET NULL,
    order_index INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    start_sec INTEGER NOT NULL DEFAULT 0,
    end_sec INTEGER NOT NULL DEFAULT 0,
    raw_duration_sec INTEGER NOT NULL,
    priority_tag TEXT NOT NULL DEFAULT 'core',
    status TEXT NOT NULL DEFAULT 'not_started', -- not_started, in_progress, completed, tested_out, skipped
    completed_at TIMESTAMP,
    skipped_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_concept_clips_course ON concept_clips(course_id, order_index);
CREATE INDEX IF NOT EXISTS idx_concept_clips_source ON concept_clips(source_id);
CREATE INDEX IF NOT EXISTS idx_concept_clips_status ON concept_clips(status);

-- 5. Backfill existing lessons into concept_clips
INSERT OR IGNORE INTO concept_clips (
    id, course_id, source_id, order_index, title, start_sec, end_sec, raw_duration_sec, priority_tag, status, created_at
)
SELECT
    id, course_id, source_id, order_index, title, start_sec, end_sec, raw_duration_sec,
    COALESCE(priority, 'core'),
    CASE WHEN is_tested_out = 1 THEN 'tested_out' ELSE 'not_started' END,
    created_at
FROM lessons;

-- Synchronize lessons priority_tag with priority
UPDATE lessons SET priority_tag = COALESCE(priority, 'core') WHERE priority_tag IS NULL OR priority_tag = '';

-- 6. Create schedule_assignments view aliasing schedule_allocations for Layer 2
CREATE VIEW IF NOT EXISTS schedule_assignments AS
SELECT
    id,
    course_id,
    lesson_id,
    COALESCE(clip_id, lesson_id) AS clip_id,
    scheduled_date,
    split_index,
    split_count,
    allocated_start_sec,
    allocated_end_sec,
    effective_minutes,
    is_completed,
    completed_at,
    is_skipped,
    skipped_at,
    created_at
FROM schedule_allocations;
