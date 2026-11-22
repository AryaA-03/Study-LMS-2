-- Migration 006: University PYQ (Previous Year Questions) and Last-Night Cram Sheets

-- 1. Add PYQ frequency tracking columns to lessons
ALTER TABLE lessons ADD COLUMN pyq_hit_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE lessons ADD COLUMN pyq_total_marks INTEGER NOT NULL DEFAULT 0;

-- 2. PYQ Exam Papers Table
CREATE TABLE IF NOT EXISTS pyq_papers (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    filename TEXT DEFAULT '',
    raw_text TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pyq_papers_course ON pyq_papers(course_id);

-- 3. PYQ Extracted Questions Table
CREATE TABLE IF NOT EXISTS pyq_questions (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    paper_id TEXT REFERENCES pyq_papers(id) ON DELETE CASCADE,
    question_number TEXT DEFAULT '',
    question_text TEXT NOT NULL,
    marks INTEGER DEFAULT NULL,
    matched_lesson_id TEXT REFERENCES lessons(id) ON DELETE SET NULL,
    matched_chunk_id TEXT REFERENCES chunks(id) ON DELETE SET NULL,
    bm25_score REAL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pyq_questions_course ON pyq_questions(course_id);
CREATE INDEX IF NOT EXISTS idx_pyq_questions_lesson ON pyq_questions(matched_lesson_id);
CREATE INDEX IF NOT EXISTS idx_pyq_questions_paper ON pyq_questions(paper_id);

-- 4. Cram Sheets Table
CREATE TABLE IF NOT EXISTS cram_sheets (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    content_markdown TEXT NOT NULL,
    notes_hash TEXT NOT NULL,
    is_generated_by_llm INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cram_sheets_course ON cram_sheets(course_id);
