-- Migration 007: Automatic FTS5 cleanup triggers and index integrity

-- 1. Trigger to remove FTS5 entry when a chunk is deleted (via cascade or direct DELETE)
CREATE TRIGGER IF NOT EXISTS trg_chunks_delete_fts AFTER DELETE ON chunks
BEGIN
    DELETE FROM chunks_fts WHERE id = OLD.id;
END;

-- 2. Clean up any existing orphaned rows in chunks_fts that no longer have a parent chunk
DELETE FROM chunks_fts WHERE id NOT IN (SELECT id FROM chunks);
