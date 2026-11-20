-- Migration 005: Quizzes, Mock Exams, and FSRS Flashcard Enhancements

ALTER TABLE quizzes ADD COLUMN time_taken_seconds INTEGER;
ALTER TABLE quizzes ADD COLUMN completed_at TIMESTAMP;
ALTER TABLE quizzes ADD COLUMN user_answers_json TEXT;

ALTER TABLE flashcards ADD COLUMN fsrs_data_json TEXT;
ALTER TABLE flashcards ADD COLUMN source_quote TEXT;

CREATE INDEX IF NOT EXISTS idx_quizzes_course_type ON quizzes(course_id, quiz_type);
CREATE INDEX IF NOT EXISTS idx_flashcards_lesson ON flashcards(lesson_id);
