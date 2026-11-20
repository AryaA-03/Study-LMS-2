-- 002_scheduling_strategy_and_lesson_filters.sql: Add Pacing Strategy and Lesson Exclusion

ALTER TABLE courses ADD COLUMN schedule_strategy TEXT NOT NULL DEFAULT 'paced';
ALTER TABLE lessons ADD COLUMN is_excluded INTEGER NOT NULL DEFAULT 0;
