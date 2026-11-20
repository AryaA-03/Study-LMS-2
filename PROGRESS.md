# Milestone Progress & Recovery Log

## Current Status
- **Current Milestone**: Completed M1 (`v0.1-m1` — Usable Day One)
- **Next Milestone**: M2 (`v0.2-m2` — Captions, Transcripts, Notes, Screenshots & Adaptive Replanning)
- **Active Data Directory**: `data-dev/`
- **Stable Live Directory**: `../learn-app-live/` (checked out at `v0.1-m1`, pointing to `data/app.db`)

## Milestone Roadmap
- [x] Step 0: Research, Stack Decision, Project Init & Launcher
- [x] M1: Usable Day One (`v0.1-m1`)
  - [x] Goal & YouTube URL input (video & playlist import)
  - [x] Zero-quota `yt-dlp` discovery (`ytsearch:` + YouTube playlist-filter URL)
  - [x] Source Approval Gate UI & API
  - [x] Deterministic lesson splitting (1 chapter = 1 lesson; 15-20 min fixed splitting for chapter-less)
  - [x] Deterministic pure-Python scheduler engine with injectable clock (IST / local)
  - [x] Playback speed scaling (`effective_minutes = raw_minutes / playback_speed`)
  - [x] Multi-day lesson splitting by `[start_sec, end_sec]`
  - [x] Configurable rest days & exam revision buffer
  - [x] Skip & reflow with schedule diff & one-click Undo
  - [x] Behind-schedule detection with Compress vs. Extend Deadline (and core deficit reporting)
  - [x] Clean dark-mode split-screen study UI with YouTube IFrame Player API integration
  - [x] Settings modal: yt-dlp version, one-click update, browser cookies, disk usage meter & cleanup
  - [x] 18 tests passed (unit, migration auto-backup, integration pipeline, live YouTube smoke, Playwright E2E)
- [ ] M2: Captions, Transcripts, Notes, Screenshots & Adaptive Replanning (`v0.2-m2`)
- [ ] M3: Multi-Source Notebooks (PDFs, Web, Videos) & Citation Q&A (`v0.3-m3`)
- [ ] M4: Citation Quizzes, FSRS Spaced Repetition & Mock Exams (`v0.4-m4`)
- [ ] M5: In-Browser Pyodide Scratchpad, Storage Guard, UI Polish & Ship (`v0.5-m5`)

## Verification Summary (M1)
- `tests/test_scheduler.py`: 8 passed
- `tests/test_yt_service.py`: 5 passed
- `tests/test_migrations.py`: 1 passed
- `tests/test_integration_pipeline.py`: 1 passed
- `tests/test_live_smoke.py`: 2 passed (live YouTube endpoints tested)
- `tests/test_e2e_m1.py`: 1 passed (Playwright headless Chromium verified)
- Total: 18 passed, 0 failed.
