# Milestone Progress & Recovery Log

## Current Status
- **Current Milestone**: Completed M5 (`v0.5-m5` — In-Browser Pyodide Scratchpad, Storage Guard, UI Polish & Final Ship)
- **Status**: ALL MILESTONES (M1 through M5) COMPLETED & 100% VERIFIED
- **Active Data Directory**: `data-dev/`
- **Stable Live Directory**: `../learn-app-live/` (checked out at `v0.1-m1`, pointing to `data/app.db`)

## Milestone Roadmap
- [x] Step 0: Research, Stack Decision, Project Init & Launcher
- [x] M1: Usable Day One (`v0.1-m1`)
- [x] M2: Captions, Transcripts, Notes, Screenshots & Adaptive Replanning (`v0.2-m2`)
- [x] M3: Multi-Source Notebooks (PDFs, Web, Videos) & Citation Q&A (`v0.3-m3`)
- [x] M4: Citation Quizzes, FSRS Spaced Repetition, Diagnostic Pre-Test & Mock Exams (`v0.4-m4`)
- [x] M5: In-Browser Pyodide Scratchpad, Storage Guard, UI Polish & Final Ship (`v0.5-m5`)
  - [x] In-browser Python 3.12 scratchpad executing inside a client-side Web Worker via Pyodide
  - [x] Zero server-side code execution guarantee
  - [x] Scratchpad templates: DFA Automata simulator, formula calculator, and regex matcher
  - [x] Storage Guard with disk usage meters, media cache cleanup, and in-place SQLite VACUUM
  - [x] One-click raw SQLite `.db` backup download (`/api/settings/backup`)
  - [x] One-click JSON course study bundle export (`/api/courses/{course_id}/export`)
  - [x] Comprehensive `README.md` documentation
  - [x] 48 tests passed (100% pass across all unit, integration, live YouTube smoke, and Playwright E2E tests)

## Verification Summary (Full M1–M5 Suite)
- `tests/test_scheduler.py`: 10 passed
- `tests/test_yt_service.py`: 5 passed
- `tests/test_migrations.py`: 1 passed
- `tests/test_integration_pipeline.py`: 1 passed
- `tests/test_transcription.py`: 5 passed
- `tests/test_screenshots.py`: 1 passed
- `tests/test_multi_source.py`: 3 passed
- `tests/test_qa_engine.py`: 1 passed
- `tests/test_fsrs_engine.py`: 4 passed
- `tests/test_quiz_engine.py`: 4 passed
- `tests/test_storage_backup.py`: 3 passed
- `tests/test_live_smoke.py`: 3 passed (live TOC playlist 114 entries, large video, search)
- `tests/test_live_smoke_m2.py`: 2 passed (live TOC captions + DBMS Whisper audio slice)
- `tests/test_e2e_m1.py`: 1 passed (Playwright golden path)
- `tests/test_e2e_m2.py`: 1 passed (Playwright notes, tabs, seek buttons, personal notes)
- `tests/test_e2e_m3.py`: 1 passed (Playwright sources tray, add modal, Ask NotebookLM Q&A)
- `tests/test_e2e_m4.py`: 1 passed (Playwright quiz generation, mastery submission, FSRS card drill, diagnostic & mock exam)
- `tests/test_e2e_m5.py`: 1 passed (Playwright Pyodide scratchpad, Storage Guard vacuum, backup, bundle export)
- **Total**: 48 passed, 0 failed.
