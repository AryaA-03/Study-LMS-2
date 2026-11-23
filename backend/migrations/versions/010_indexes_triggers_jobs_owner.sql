-- Migration 010: Missing indexes, full FTS5 triggers, background jobs table, owner_id & idempotency hashes

-- 1. Multi-user readiness (non-breaking default 'local')
ALTER TABLE courses ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE llm_cache ADD COLUMN owner_id TEXT NOT NULL DEFAULT 'local';
ALTER TABLE llm_cache ADD COLUMN expires_at TIMESTAMP;

-- 2. Deduplicate any duplicate notes(lesson_id) rows before adding UNIQUE index
DELETE FROM notes
WHERE id NOT IN (
    SELECT id FROM (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY lesson_id ORDER BY updated_at DESC, id DESC) AS rn
        FROM notes
    ) WHERE rn = 1
);

-- 3. Missing performance & uniqueness indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_notes_lesson_unique ON notes(lesson_id);
CREATE INDEX IF NOT EXISTS idx_notes_course ON notes(course_id);
CREATE INDEX IF NOT EXISTS idx_quizzes_lesson ON quizzes(lesson_id);
CREATE INDEX IF NOT EXISTS idx_sources_course_ext ON sources(course_id, external_id);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_courses_owner ON courses(owner_id);
CREATE INDEX IF NOT EXISTS idx_llm_cache_expires ON llm_cache(expires_at);

-- 4. Complete FTS5 sync triggers (matching chunks_fts columns: id, course_id, lesson_id, content)
CREATE TRIGGER IF NOT EXISTS trg_chunks_update_fts AFTER UPDATE OF content ON chunks
BEGIN
    DELETE FROM chunks_fts WHERE id = OLD.id;
    INSERT INTO chunks_fts(id, course_id, lesson_id, content)
    VALUES (NEW.id, NEW.course_id, NEW.lesson_id, NEW.content);
END;

-- 5. Idempotency & flashcard deduplication columns
ALTER TABLE sources ADD COLUMN content_hash TEXT;
ALTER TABLE pyq_papers ADD COLUMN content_hash TEXT;
ALTER TABLE flashcards ADD COLUMN source_question_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_sources_content_hash ON sources(course_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_pyq_papers_hash ON pyq_papers(course_id, content_hash);
CREATE UNIQUE INDEX IF NOT EXISTS idx_flashcards_question_hash
    ON flashcards(course_id, source_question_hash)
    WHERE source_question_hash IS NOT NULL;

-- 6. Persistent background jobs table
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT 'local',
    course_id TEXT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    progress_pct INTEGER NOT NULL DEFAULT 0,
    message TEXT DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    cursor_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT,
    error_text TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_course ON jobs(course_id);
