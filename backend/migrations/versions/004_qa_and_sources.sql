-- Migration 004: Multi-Source Ingestion & Citation-Grounded Q&A

-- 1. Grounded Q&A Threads Table
CREATE TABLE IF NOT EXISTS qa_threads (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    answer_markdown TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]', -- Array of {chunk_id, source_id, excerpt, timestamp_sec}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_qa_course ON qa_threads(course_id, created_at);

-- 2. Enhance sources table
ALTER TABLE sources ADD COLUMN file_path TEXT DEFAULT '';
ALTER TABLE sources ADD COLUMN chunk_count INTEGER NOT NULL DEFAULT 0;

-- 3. Enhance chunks table
ALTER TABLE chunks ADD COLUMN source_type TEXT DEFAULT 'youtube_video';
