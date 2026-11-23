-- Migration 011: Ensure llm_cache has response_json column consistently for all readers
ALTER TABLE llm_cache ADD COLUMN response_json TEXT;
