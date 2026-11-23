-- Migration 013: FTS5 INSERT sync trigger + qa_threads lesson_id/scope columns

-- 1. Automatic FTS5 sync trigger on chunk inserts
CREATE TRIGGER IF NOT EXISTS trg_chunks_insert_fts
AFTER INSERT ON chunks
BEGIN
    INSERT INTO chunks_fts(id, course_id, lesson_id, content)
    VALUES (NEW.id, NEW.course_id, NEW.lesson_id, NEW.content);
END;

-- 2. Add lesson_id and scope columns to qa_threads so Lesson vs Notebook history stays cleanly separated
ALTER TABLE qa_threads ADD COLUMN lesson_id TEXT REFERENCES lessons(id) ON DELETE SET NULL;
ALTER TABLE qa_threads ADD COLUMN scope TEXT NOT NULL DEFAULT 'course';

CREATE INDEX IF NOT EXISTS idx_qa_course_lesson ON qa_threads(course_id, lesson_id);
