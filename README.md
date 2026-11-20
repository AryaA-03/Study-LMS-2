# Learn LMS • Autonomous Personal LMS & Exam-Prep Web App

A lightweight, local-first personal LMS and exam-prep web application built for college students preparing for high-stakes exams. Designed for **macOS Apple Silicon (M-series, arm64)** with cross-platform Python compatibility, pure SQLite + FTS5 full-text search, and **zero video downloads** (streamed directly via YouTube IFrame Player API).

---

## 🌟 Key Capabilities

### 1. Adaptive Deterministic Scheduling (CourseIt-Inspired)
- **Dual Pacing Strategies**:
  - **"Paced to Exam Date"**: Spreads study load evenly across available calendar days (`total_effective_minutes / study_days_available`) so lessons finish right before your 2-day exam revision buffer.
  - **"Fixed Daily Budget"**: Packs lessons greedily into a fixed daily study budget (Sprint mode).
- **Playback Speed Scaling**: Per-course playback speed (`1.0x`, `1.25x`, `1.5x`, `2.0x`) scaling effective study time (`effective_minutes = raw_minutes / playback_speed`).
- **Granular Lesson Inclusion & Quick Filters**: One-click toggles to include/skip exercises or example videos when study time is short.
- **Dynamic Multi-Day Splitting**: Lessons exceeding daily study budgets split cleanly into `[start_sec, end_sec]` segment allocations.
- **Behind Schedule Protection**: Instant **Compress** (drops lowest-priority deep-dives while protecting revision buffers) vs. **Extend Deadline**, complete with diff summaries and one-click **Undo**.

### 2. Captions-First Ingestion & Lazy Local Whisper (Apple Silicon Optimized)
- **Zero Video Downloads**: Streams videos directly through the official YouTube IFrame Player API; clickable `[MM:SS]` links seek the player instantly.
- **Deduplicated Subtitles**: Fetches `json3` subtitles via `yt-dlp` and applies rolling-caption VTT prefix deduplication to eliminate repeated phrases.
- **On-Demand Lazy Whisper Fallback**:
  - Automatically runs only when captions are absent.
  - On macOS Apple Silicon: runs **`mlx-whisper`** (`whisper-small-mlx`, 100% GPU Metal acceleration, zero PyTorch).
  - On Linux/Windows/CPU: falls back to **`faster-whisper`** (`int8` CPU).
  - Fetches only that lesson's audio slice into temp storage, transcribes, and deletes the audio immediately.

### 3. Multi-Source Notebooks & Citation-Grounded Q&A (NotebookLM-Inspired)
- **Multi-Source Unified Indexing**: Ingests YouTube video transcripts, textbook PDFs (pure Python `pypdf` with page tracking), and web articles (polite `trafilatura` with `robots.txt` compliance).
- **SQLite FTS5 BM25 Retrieval**: All content chunked into 300–600 token segments and indexed in `chunks` and `chunks_fts`.
- **Strict Citation Grounding**: Q&A engine verifies every claim against retrieved chunks with verbatim quotes and `[ref:chk_...]` or `[MM:SS]` timestamp citations. Rejects ungrounded claims when evidence is insufficient.

### 4. Citation Quizzes & Mastery Loop
- **Citation-Grounded MCQs**: Generates 3–10 question quizzes where every question strictly cites a `chunk_id` and verbatim chunk excerpt. Operates deterministically in No-Key mode or enriches with Gemini 2.5 Flash when an API key is configured.
- **Mastery Loop Progression**:
  - **Score &ge; 80%**: Marks the topic **Tested Out**, freeing it from the remaining schedule and dynamically reflowing completion dates.
  - **Score &lt; 60%**: Marks **Needs Review** and automatically generates targeted FSRS spaced repetition flashcards for missed concepts.
- **2-Minute Diagnostic Pre-Test**: Allows testing out of known topics on Day One, shrinking study schedules before studying begins.
- **Timed Mock Exam Simulator**: 15/30-minute exam simulator with countdown timer, question palette, and topic-level score breakdown.

### 5. FSRS Spaced Repetition Flashcards
- **Official FSRS v5 Algorithm**: Integrated directly via the `fsrs` Python package.
- **Dynamic Retention Scaling**: Automatically scales target retention from `0.90` up to `0.96` as the exam deadline approaches to ensure high review frequency during crunch time.
- **Interactive 3D Card Flipping**: Flip with `Space`, rate with keyboard shortcuts:
  - `1` : Again (`1m`)
  - `2` : Hard (`5m`)
  - `3` : Good (`10m`)
  - `4` : Easy (`7d+`)

### 6. In-Browser Pyodide Web Worker Scratchpad
- **100% Client-Side Execution**: Runs Python 3.12 inside a client-side Web Worker via Pyodide. **Zero server-side code execution** ensures total security.
- **Study Presets**: Built-in templates for DFA Automata simulations, exam formula calculators, and regex matchers.

### 7. Storage Guard & Portability
- **Media Disk Usage Meter**: Real-time breakdown of SQLite DB, transcripts, and screenshots.
- **One-Click Maintenance**: Media cache cleanup, SQLite `VACUUM`, and raw `.db` file downloads.
- **Full Course Bundle Export**: One-click download of the complete study state (lessons, schedule, notes, flashcards, quizzes) as a portable JSON bundle.

---

## 🚀 Quickstart

### Prerequisites
- macOS Apple Silicon (M1/M2/M3/M4) or Linux/Windows with Python 3.10+
- Internet connection for initial dependency installation and YouTube streaming

### Single-Command Launch
```bash
python run.py
```
`python run.py` automatically:
1. Creates the virtual environment (`.venv`) if absent.
2. Installs pinned dependencies from `requirements.txt`.
3. Prepares bundled `ffmpeg` on `.venv/bin` and prepends to `PATH`.
4. Runs pending SQLite schema migrations with automated timestamped backups.
5. Launches the FastAPI server at `http://localhost:8000`.

Open your browser to `http://localhost:8000`.

---

## 🧪 Verified Test Anchors

All features and milestones have been validated against real course anchors:
1. **Full Playlist Test Anchor**: [Neso Academy Theory of Computation (114 videos)](https://youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev)
2. **Single Marathon Video Test Anchor**: [DBMS 5.5-Hour Lecture with 11 Chapters](https://youtu.be/YRnjGeQbsHQ)

---

## 🔬 Test Suite (48 Tests, 100% Pass)

Run the full automated test suite (unit, integration, live YouTube smoke, and Playwright E2E):
```bash
.venv/bin/pytest -v
```

### Test Coverage Overview
- `tests/test_scheduler.py`: 10 passed (playback speed scaling, rest days, revision buffers, multi-day splits, compress deficit, reflow diffs, paced strategy)
- `tests/test_yt_service.py`: 5 passed (metadata, chapter splitting, chapter-less fixed splitting, yt-dlp version)
- `tests/test_migrations.py`: 1 passed (non-destructive migrations & auto-backups)
- `tests/test_integration_pipeline.py`: 1 passed (M1 end-to-end golden flow)
- `tests/test_transcription.py`: 5 passed (json3 deduplication, rolling VTT prefix stripper, structured notes)
- `tests/test_screenshots.py`: 1 passed (ffmpeg keyframes & fallback)
- `tests/test_multi_source.py`: 3 passed (PDF extraction, polite web ingestion, robots.txt)
- `tests/test_qa_engine.py`: 1 passed (FTS5 BM25 retrieval, verbatim citations, negative rejection)
- `tests/test_fsrs_engine.py`: 4 passed (FSRS lifecycle, review intervals, target retention scaling)
- `tests/test_quiz_engine.py`: 4 passed (grounded MCQs, mastery test-out, low score review cards, diagnostic test-out)
- `tests/test_storage_backup.py`: 3 passed (raw SQLite backup, VACUUM, course bundle export)
- `tests/test_live_smoke.py`: 3 passed (live TOC playlist 114 entries, large video chapters, YouTube search)
- `tests/test_live_smoke_m2.py`: 2 passed (live TOC captions + DBMS Whisper audio slice)
- `tests/test_e2e_m1.py`: 1 passed (Playwright golden path)
- `tests/test_e2e_m2.py`: 1 passed (Playwright notes, tabs, seek buttons, personal notes)
- `tests/test_e2e_m3.py`: 1 passed (Playwright sources tray, add modal, Ask NotebookLM Q&A)
- `tests/test_e2e_m4.py`: 1 passed (Playwright quiz generation, mastery submission, FSRS card drill, diagnostic & mock exam)
- `tests/test_e2e_m5.py`: 1 passed (Playwright Pyodide scratchpad, Storage Guard vacuum, backup, bundle export)
- **Total**: 48 passed, 0 failed.

---

## 🔒 Security & Privacy Guarantees
- **Local-First**: All data, schedules, transcripts, notes, and flashcards stay in local SQLite storage.
- **Zero Server Code Execution**: Pyodide executes Python inside a client-side Web Worker sandboxed within the browser.
- **Safe Secrets Handling**: LLM API keys are stored solely in `.env` (never written to SQLite database tables).
