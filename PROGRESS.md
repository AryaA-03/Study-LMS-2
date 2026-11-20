# Milestone Progress & Recovery Log

## Current Status
- **Current Milestone**: Completed M3 (`v0.3-m3` — Multi-Source Notebooks: PDFs, Web & Citation Q&A)
- **Next Milestone**: M4 (`v0.4-m4` — Citation Quizzes, FSRS Spaced Repetition & Mock Exams)
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
- [x] M2: Captions, Transcripts, Notes, Screenshots & Adaptive Replanning (`v0.2-m2`)
  - [x] Captions-first ingestion via `yt-dlp` with zero video download
  - [x] Millisecond-precise `json3` parser with deduplication and token chunking (300-600 tokens)
  - [x] WebVTT rolling-caption prefix deduplicator
  - [x] Resumable SQLite chunk storage + FTS5 full-text search indexing (`chunks_fts`)
  - [x] Lazy per-lesson Whisper fallback (`mlx-whisper` on Apple Silicon, `faster-whisper` on CPU)
  - [x] Audio slice extractor via `yt-dlp` + bundled `ffmpeg` on PATH with instant temp cleanup
  - [x] Opt-in 480p JPEG keyframe screenshot capture via ffmpeg with YouTube thumbnail fallback
  - [x] NotebookLM-style tabbed study studio: Grounded Notes vs. Personal Editable Notes
  - [x] Automatic note synthesis (Gemini 2.5 Flash with fallback to deterministic No-Key mode)
  - [x] Interactive clickable `[MM:SS]` timestamp seek links bound to `window.seekToSeconds`
  - [x] Keyframes visual gallery strip with duration badges and instant player jump
  - [x] Debounced auto-saving personal scratchpad persisted to SQLite `notes` table
  - [x] Adaptive replanning: Compress (drops deep-dives) vs. Extend Deadline with diff & Undo
  - [x] 31 tests passed across unit, integration, live TOC/DBMS smoke, and Playwright E2E
- [x] M3: Multi-Source Notebooks (PDFs, Web, Videos) & Citation Q&A (`v0.3-m3`)
  - [x] Pure-Python PDF text extraction via `pypdf` with page tracking (`[Page N]`)
  - [x] Polite single-page web article ingestion via `trafilatura` with `robots.txt` verification
  - [x] Multi-source chunk indexing (300-600 tokens) into unified SQLite FTS5 table (`chunks_fts`)
  - [x] Strict citation-grounded Q&A engine with SQLite FTS5 BM25 search ranking
  - [x] Verbatim quote enforcement and strict rejection when evidence is insufficient
  - [x] NotebookLM-style Sources Tray showing YouTube, PDF, and Web source badges
  - [x] NotebookLM-style "Ask Q&A" conversational studio pane with interactive citation pills
  - [x] Multi-source Add Source modal (PDF file drag-and-drop & Web article URL)
  - [x] Persistent Q&A thread history stored in `qa_threads` table
  - [x] 35 tests passed across unit, integration, and Playwright E2E
- [ ] M4: Citation Quizzes, FSRS Spaced Repetition & Mock Exams (`v0.4-m4`)
- [ ] M5: In-Browser Pyodide Scratchpad, Storage Guard, UI Polish & Ship (`v0.5-m5`)

## Verification Summary (M3)
- `tests/test_scheduler.py`: 10 passed
- `tests/test_yt_service.py`: 5 passed
- `tests/test_migrations.py`: 1 passed
- `tests/test_integration_pipeline.py`: 1 passed
- `tests/test_transcription.py`: 5 passed
- `tests/test_screenshots.py`: 1 passed
- `tests/test_multi_source.py`: 3 passed (PDF extraction, web chunking, robots.txt)
- `tests/test_qa_engine.py`: 1 passed (FTS5 BM25 search, citations, negative case, persistence)
- `tests/test_live_smoke.py`: 3 passed (live TOC playlist 114 entries, large video, search)
- `tests/test_live_smoke_m2.py`: 2 passed (live TOC captions + DBMS Whisper audio slice)
- `tests/test_e2e_m1.py`: 1 passed (Playwright golden path)
- `tests/test_e2e_m2.py`: 1 passed (Playwright notes, tabs, seek buttons, personal notes)
- `tests/test_e2e_m3.py`: 1 passed (Playwright sources tray, add modal, Ask NotebookLM Q&A)
- Total: 35 passed, 0 failed.
