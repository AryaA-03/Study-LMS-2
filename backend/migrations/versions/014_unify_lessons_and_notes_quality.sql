-- 014_unify_lessons_and_notes_quality.sql
-- Unifies lessons as canonical Layer-1 table and tracks notes.generation_mode ('llm' vs 'deterministic')

-- 1. Reconcile any newer completion/priority state from concept_clips into lessons before dropping duplicate table
UPDATE lessons
SET
    status = COALESCE((SELECT cc.status FROM concept_clips cc WHERE cc.id = lessons.id), status),
    completed_at = COALESCE((SELECT cc.completed_at FROM concept_clips cc WHERE cc.id = lessons.id), completed_at),
    skipped_at = COALESCE((SELECT cc.skipped_at FROM concept_clips cc WHERE cc.id = lessons.id), skipped_at),
    priority_tag = COALESCE((SELECT cc.priority_tag FROM concept_clips cc WHERE cc.id = lessons.id), priority_tag)
WHERE EXISTS (SELECT 1 FROM concept_clips cc WHERE cc.id = lessons.id);

DROP TABLE IF EXISTS concept_clips;
DROP VIEW IF EXISTS schedule_assignments;

-- Provide a read-only compatibility view so any legacy SELECT against concept_clips works seamlessly
CREATE VIEW IF NOT EXISTS concept_clips AS
SELECT
    id,
    course_id,
    source_id,
    order_index,
    title,
    start_sec,
    end_sec,
    raw_duration_sec,
    COALESCE(priority_tag, priority, 'core') AS priority_tag,
    COALESCE(status, 'not_started') AS status,
    completed_at,
    skipped_at,
    created_at
FROM lessons;

-- 2. Track whether saved notes came from a real LLM or deterministic fallback so fallback notes auto-upgrade
ALTER TABLE notes ADD COLUMN generation_mode TEXT NOT NULL DEFAULT 'deterministic';

UPDATE notes
SET generation_mode = CASE
    WHEN COALESCE(is_generated, 0) = 1
         AND COALESCE(content_markdown, '') != ''
         AND content_markdown NOT LIKE '%Aspect 1 (%'
         AND content_markdown NOT LIKE '%Watch for empty strings%'
         AND content_markdown NOT LIKE '%- Sources: chk_%'
         AND content_markdown NOT LIKE '%No transcript or captions found%'
    THEN 'llm'
    ELSE 'deterministic'
END;
