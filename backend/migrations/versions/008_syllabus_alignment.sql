-- 008_syllabus_alignment.sql: Add syllabus storage to courses table

ALTER TABLE courses ADD COLUMN syllabus_text TEXT;
ALTER TABLE courses ADD COLUMN syllabus_metadata TEXT;
