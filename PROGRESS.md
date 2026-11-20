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
- [x] Post-M5: UI/UX Refresh & Rigorous Live Browser Testing (`v0.5.1-ui-refresh`)
  - [x] Replaced purple/indigo "AI slop" gradients with clean monochrome (black & white) and functional editorial accents (amber, blue, mint, coral)
  - [x] Dual themes (Dark and Light) with top navbar theme switcher (☀️/🌙) and `localStorage` persistence
  - [x] Declared `<meta name="color-scheme" content="light dark">` and `:root { color-scheme: light dark; }` per Modern Web Guidance
  - [x] Explicit Exam Date Alignment: added choice between "Finish on Exam Date" (0-day or 2-day buffer) and "Fixed Daily Spend"
  - [x] Fixed date spillover in `backend/scheduler/engine.py`: in paced mode with 0-day buffer, finish date strictly matches exam date
  - [x] Collapsible interface: theater player toggle, full-width studio sidebar toggle, day-card chevrons with global collapse/expand
  - [x] Selective video toggling: curriculum drawer with "Skip All Examples", search filter, and individual inclusion checkboxes
  - [x] Full-spectrum logging: color-coded terminal HTTP request logging and rich F12 browser console logger (`[LearnLMS:...]`)
  - [x] Interactive browser inspection: exposed `window.learnLMS` global object for debugging
  - [x] Live browser test suite: 5 Playwright tests in `tests/test_live_browser_ui.py` validating themes, date alignment, collapsing, filtering, and F12 logs
  - [x] 53 tests passed (100% pass rate across all 38 unit/integration, 5 live YouTube smoke, and 10 Playwright E2E tests)

## Verification Summary (Full 53-Test Suite)
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
- `tests/test_live_browser_ui.py`: 5 passed (Playwright live dual-theme, date alignment, buffer toggle, collapsible studio & days, selective video toggling, F12 console)
- **Total**: 53 passed, 0 failed (100% pass rate).

---

## Milestone 5.2: Complete Editability, Pacing Alignment & Colorful UI Redesign (CourseIt & NotebookLM Inspired)
- [x] **Full Course & Pacing Editability**: Added `PATCH /api/courses/{course_id}` allowing one-click updates to Course Title, Exam Target Date, Pacing Mode (Finish on Exam Date vs Fixed Daily Spend), Daily Study Minutes, Playback Speed, Revision Buffer Days, and Weekly Rest Days with automatic instant replan.
- [x] **Full Lesson & Allocation Editability**: Added `PATCH /api/courses/{course_id}/lessons/{lesson_id}` and `POST /allocations/{id}/reschedule` to rename lessons, toggle priority (Core vs Deep-Dive), move allocations to any calendar date, and edit lesson summaries.
- [x] **Interactive Personal Notes**: Built a dedicated Personal Notes studio tab with a rich Markdown formatting toolbar (`**B**`, `*I*`, `H2`, `</>`, `• List`, `> Quote`), live word counter, and manual `💾 Save Notes` button with toast confirmation.
- [x] **Flashcard Editor & Add Card**: Built interactive modal editor (`PUT /api/courses/{course_id}/flashcards/{card_id}`) to edit front prompts, back answers, and delete cards, plus a manual card creator.
- [x] **Selective Video Ingestion & Examples Filter**: Enhanced the Curriculum Drawer with a `⚡ Skip All Examples` one-click action that automatically excludes practice/question videos, saving hours of exam prep time.
- [x] **Vibrant Creative Layout**:
  - Replaced drab monochrome with an elevated visual hierarchy: electric violet brand icon, 4 vibrant Top KPI cards (Cyan Study Left, Emerald Projected Finish, Purple Exam Deadline, Amber Pace & Speed), rainbow progress bar, and signature color accents on each studio tab.
  - High-contrast dual theme support (Obsidian Slate Dark Mode + Porcelain Light Mode) with WCAG AA compliance.
- [x] **Test Verification**:
  - 12 unit and integration tests passing (`tests/test_scheduler.py`, `tests/test_migrations.py`, `tests/test_integration_pipeline.py`).
  - 8 Playwright live browser UI tests passing (`tests/test_live_browser_ui.py`) covering theme switching, date alignment, studio collapsing, selective video filtering, course editing, lesson editing, and personal notes.
