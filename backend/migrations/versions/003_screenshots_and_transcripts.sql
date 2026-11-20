-- Migration 003: Screenshots, Lesson Transcription Status, and Notes Enhancements

-- 1. Screenshots Table (Opt-in Keyframe captures stored locally)
CREATE TABLE IF NOT EXISTS screenshots (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    timestamp_sec INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    caption TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_screenshots_lesson ON screenshots(lesson_id);
CREATE INDEX IF NOT EXISTS idx_screenshots_course ON screenshots(course_id);

-- 2. Add transcript tracking columns to lessons
ALTER TABLE lessons ADD COLUMN has_transcript INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lessons ADD COLUMN transcript_type TEXT DEFAULT '';
ALTER TABLE lessons ADD COLUMN transcription_status TEXT DEFAULT 'pending';

-- 3. Enhance notes table if needed
-- is_generated distinguishes AI/auto-synthesized notes from personal user notes
ALTER TABLE notes ADD COLUMN is_generated INTEGER NOT NULL DEFAULT 1;
