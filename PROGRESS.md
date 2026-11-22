# Milestone Progress & Recovery Log

## Current Status
- **Current Milestone**: Completed Milestone 8 (`v0.7-concept-partition` — Decoupled Concept Partitioning, Instant Repacking, Per-Unit Study Bundles & Whole-Video Cheat Sheet)
- **Status**: ALL MILESTONES (M1 through M8) COMPLETED & 100% VERIFIED
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
  - [x] Live browser test suite: 8 Playwright tests in `tests/test_live_browser_ui.py` validating themes, date alignment, collapsing, filtering, and F12 logs
- [x] Milestone 6: Frictionless Flow, 3-Minute Merging, Drag-and-Drop & Diagnostic Engine (`v0.6-buttery-smooth`)
  - [x] Sub-3-Minute Chapter Merging Rule (180s threshold) in `backend/services/youtube.py` preventing micro-fragment lessons
  - [x] Interactive 3-Minute Diagnostic Pre-Test with live timer countdown, option card selection, mastery calculation, schedule reflow, and celebratory results screen
  - [x] Video Player Auto-Advance: automatically completes current allocation and seamlessly cues next lesson slice when reaching `allocated_end_sec`
  - [x] Two-Way Live Timestamp Highlighting in Grounded Notes: synchronized with active video playback
  - [x] Native Drag-and-Drop Schedule Reordering: drag lesson cards directly between calendar days with drop highlighting and optimistic API persistence
  - [x] Resilient Metal-Safe Whisper Device Probing: `mlx_whisper` device checking with seamless CPU/metadata fallback
  - [x] Global Keyboard Navigation (`Space` play/pause, `[`/`]` 10s jump, `M` complete, `Escape` close modal)
  - [x] Non-blocking gradient toast notifications replacing browser `alert()` dialogs across all flows
- [x] Milestone 7: Serene Minimalist Redesign & Metal Driver Hardening (`v0.7-calm-minimalist`)
  - [x] **Split-Screen Academic Redesign Matching Mockup (`media_1795275531110_95d9297b.jpg`)**:
    - Complete purge of casino/gamer neon accents, garish gradient cards, and cluttered multi-tier toolbars.
    - Warm Alabaster (`#F5F3EE` canvas, `#ECE8DF` cards/sidebars, `#DDD7CA` borders, `#1F2328` text) light mode.
    - Soft Matte Charcoal (`#141517` canvas, `#1C1D20` cards/sidebars, `#2A2C32` borders, `#E5E7EB` text) dark mode.
    - Calm blue (`#2563EB` / `#60A5FA`) active underlines and timestamp pills.
  - [x] **3-Zone Layout Architecture**:
    - **Left Column (~260px)**: Compact collapsible syllabus rail (`#pane-schedule`) with day headers, clean checkmarks/dots, lesson durations (`30m`, `45m`), drag handles, and bottom resources tray.
    - **Center Column (Primary Study Area)**: 16:9 video player at top with a thin quiet action bar, and an expansive independently scrollable grounded notes reading canvas (`#pane-grounded-notes`, `#notes-content`) at bottom with quiet calm blue timestamp pills (`[ ▶ 04:12 ]`), inline keyframe diagram cards, and a floating round scroll-down button (`#btn-scroll-notes-down`).
    - **Right Column (~380px Full-Height Studio Panel)**: Quiet text tabs (`Notes`, `Quiz`, `Flashcards`, `Q&A`, `Code`) with calm blue active underline; Quiz MCQ card matching mockup with choices `A`, `B`, `C`, `D`, verbatim source quotes, and citation pills; Personal Markdown notes editor; FSRS review cards; Q&A notebook; and dark Python code scratchpad.
  - [x] **Markdown Notes Rendering Fix**:
    - Replaced hardcoded `text-white` with dynamic theme tokens so text is never invisible in light mode.
    - Handled `[text](seek://seconds)` and `[text](url)` markdown links cleanly alongside timestamp pills.
  - [x] **Sandboxed Subprocess Metal Probing**:
    - Isolated `mlx.core` check in an ephemeral 3-second subprocess (`sys.executable -c ...`) preventing uncatchable C++ Metal GPU aborts (`SIGABRT` / exit code 134) in headless/sandboxed mode.
  - [x] **100% Test Verification**:
    - 32 core backend unit & integration tests passing (`pytest tests/test_*.py` in 0.69s).
    - 11 Playwright live browser UI tests passing (`pytest tests/test_live_browser_ui.py` in 28.46s).
    - Total: 43 passing tests across the entire test suite.

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

---

## Milestone 6.0: University PYQ Weightage Matcher & Last-Night Cram Sheet Generator
- [x] **PYQ Upload & Parsing**:
  - In the Subject Notebook sources panel, added **"Past Papers (PYQ)"** tab supporting exam PDF uploads and raw question text pasting.
  - Lightweight regex parser supporting diverse university styles: sub-questions (`Q1(a)`, `2(b)`), marks annotations (`[5M]`, `[10 Marks]`, `(6 marks)`), and question text clean extraction.
- [x] **FTS5 BM25 Syllabus Matching & Frequency Tagging**:
  - Matched extracted past exam questions against 300–600 token lesson chunks using **SQLite FTS5 BM25 search**.
  - Computed per-lesson aggregates `pyq_hit_count` and `pyq_total_marks`, updating `lessons` schema.
  - Left Lesson Rail displays subtle, non-intrusive badges on high-yield lessons (e.g. `PYQ ×3`).
  - Added **"🔥 PYQs"** toggle filter chip in syllabus view to instantly isolate high-yield exam topics.
  - Added dedicated **PYQ Tab** in Right Studio panel (`#tab-pyq-questions`) displaying exact past paper questions, marks tags, paper titles, and a 1-click `💬 Ask AI Solution` button.
- [x] **Last-Night Cram Sheet Generator (1-2 Page Revision Sheet)**:
  - Added **"⚡ Cram Sheet"** button in top header navbar and 2-day revision buffer views.
  - 1-click synthesis condensing lesson notes, exam weightage matrix, definitions, comparison tables, and top PYQ phrasings into a high-density Last-Night Cram Sheet.
  - Cached in SQLite `cram_sheets` table by SHA-256 hash of underlying notes and PYQs for sub-millisecond retrieval and zero extra token usage.
  - Deterministic no-key fallback extracting tables, key takeaways, and PYQs if no LLM key is configured.
- [x] **Clean Print-Ready View & Export**:
  - Distraction-free modal reader with `@media print` CSS for crisp A4 two-column or compact single-column printing with automatic navbar/sidebar hiding.
  - "🖨️ Print / Save PDF" and "📥 Download .md" buttons.
- [x] **Verification**:
  - Unit & integration tests in `tests/test_pyq_and_cram_sheet.py`: verified question splitting, FTS5 BM25 matching, and SHA-256 caching.
  - Playwright live browser UI test `test_ui_pyq_upload_and_cram_sheet_print` in `tests/test_live_browser_ui.py`: end-to-end PYQ upload -> syllabus badge display -> high-yield filter -> Right Studio PYQ questions -> Cram Sheet modal -> print layout rendering.
  - Visual verification artifact saved: `21_cram_sheet_and_pyq_verification.png`.
  - Non-destructive migration `006_pyq_and_cram_sheets.sql` applied with automatic backup.
  - Core test suites passing 100%.

---

## Milestone 6.1: Comprehensive System Audit, Bug Fixes & Optimization Pass
- [x] **Allocation Auto-Advance Completion Endpoint**:
  - Implemented missing backend route `POST /api/courses/{course_id}/schedule/allocations/{allocation_id}/complete` in `backend/routers/schedule.py`.
  - Fixed client-side video playback slice auto-advance which was previously failing with HTTP 404/405.
- [x] **FTS5 Virtual Table Deletion Trigger & Index Cleanup**:
  - Created migration `007_fts_cleanup_and_triggers.sql` adding trigger `trg_chunks_delete_fts` on `chunks` table.
  - Automatically cascades deletions from `chunks` to virtual table `chunks_fts`, preventing index bloating and orphaned records.
  - Added unit test `test_fts5_cleanup_trigger` in `tests/test_migrations.py`.
- [x] **FTS5 Reserved Keyword Quoting**:
  - Added quotation wrapping `f'"{kw}"'` across `backend/services/pyq_engine.py` and `backend/services/qa_engine.py`.
  - Added `"not"` to query stopwords list, eliminating SQLite FTS5 `syntax error near "NOT"` exceptions during natural language queries.
- [x] **Live Note Timestamp Highlighting Fix**:
  - Fixed element ID mismatch in `syncLiveNoteTimestamp` in `frontend/static/js/app.js` (`grounded-notes-container` -> `notes-content`).
  - Restored dynamic visual synchronization between active video playback and timestamp badges in lesson notes.
- [x] **Screenshots Capture Idempotency**:
  - Hardened `capture_lesson_keyframes` in `backend/services/screenshots.py` with an existence check before insertion.
  - Prevents duplicate rows and screenshot card accumulation when re-capturing keyframes for a lesson.
- [x] **Multi-Provider LLM Fallback Hardening**:
  - Replaced rigid `if-elif` chains with resilient fall-through try/catch blocks across `notes.py`, `qa_engine.py`, `cram_sheet_engine.py`, and `quiz_engine.py` (both for MCQ generation and 3-part subjective rubric evaluation).
  - In cases of Gemini free-tier rate limits or transient errors, requests automatically fall through to Groq or OpenRouter before falling back to deterministic synthesis.
  - Added whitespace-normalized citation quote verification in `quiz_engine.py`.
- [x] **Cram Sheet Markdown Formatting & Parser Hardening**:
  - Corrected unclosed `**` bold syntax in `cram_sheet_engine.py` when extracting definition lines, preventing unclosed `<strong>` tag leaks.
  - Cleaned redundant database `SELECT` statements prior to commit in `get_or_create_cram_sheet`.
  - Upgraded `renderMarkdownNotes` and `renderCramSheetMarkdown` in `frontend/static/js/app.js` to parse both `- ` and `* ` bullet items before inline italic replacements.
- [x] **LLM Cache Performance Optimization**:
  - Cached `llm_cache` column metadata in `backend/services/llm_cache.py` to eliminate redundant `PRAGMA table_info` I/O on every cache read/write.
- [x] **API Specification & Cache Busting**:
  - Synchronized FastAPI app version to `v0.6.0` in `backend/main.py` and regenerated locked `openapi.json`.
  - Updated `app.js?v=0.6.0` query parameter in `frontend/templates/index.html`.
- [x] **Comprehensive Test Verification**:
  - Full suite of 53 tests passing across unit, integration, and API tests (`pytest tests/` with 0 failures).
  - Verified balanced Markdown bold syntax in `test_cram_sheet_generation_and_sha256_cache`.

### Complete UI/UX Overhaul, Button Integrity Audit & Course Reschedule Fix (v0.6.1)
- **UI/UX & Design Architecture**:
  - Implemented dual draggable split-pane sliders with localStorage persistence: horizontal splitter between video and notes (with `Compact (25%)`, `Balanced (38%)`, and `Hide/Show` quick-snap controls), and vertical splitter between study canvas and studio panel (`300px` to `55vw`, double-click reset to `380px`).
  - Enforced strict calm color system with 100% elimination of purple/violet/indigo hex codes and classes across CSS, HTML templates, and JS console badges.
  - Implemented single 48px top-bar housing left rail toggle, course switcher, compact progress metrics, quick action modals (`+ New Goal`, `⚡ Cram Sheet`, `Mock Exam`), Settings modal, right studio collapse toggle, and day/night mode switcher.
  - Added collapsible left syllabus rail (`260px` -> `52px`) displaying slim Chrome-style vertical badges with completion rings, status checkmarks, and top expansion toggle.
- **Course Reschedule & API Fixes**:
  - Eliminated 405 Method Not Allowed error on `PATCH /api/courses/{course_id}` by ensuring dual `@router.patch` and `@router.put` endpoints in `backend/routers/courses.py` with explicit `db.commit()` on course and lesson updates.
  - Added graceful client-side fallback from `PATCH` to `PUT` in `frontend/static/js/app.js` with structured error extraction.
  - Fixed `Logger.layout` runtime error on sidebar toggle.
  - Terminated stale background process and restarted live app with auto-reloading (`run.py` on `http://127.0.0.1:8000`).
  - Bumped asset version to `v=0.6.1` for cache-busting.
- **Button & Feature Integrity Audit**:
  - Comprehensive audit in `tests/test_audit_all_buttons_and_features.py` verified that 100% of interactive elements, modals, drawers, tabs, and filters remain intact and fully functional with zero console errors.
  - 15/15 Playwright browser tests in `tests/test_live_browser_ui.py` passed with 0 failures.

### 3-Way Lesson Filter: All vs Concepts vs Examples / Applications
- **Backend Model & Endpoint**:
  - Added `filter_mode: Optional[str] = Field(None, description="'all', 'concepts', or 'examples'")` to `LessonFilterRequest` in `backend/models/schemas.py`.
  - Implemented comprehensive pattern matching in `backend/routers/courses.py` across: `%example%`, `%examples%`, `%problem%`, `%problems%`, `%question%`, `%questions%`, `%exercise%`, `%exercises%`, `%practice%`, `%project%`, `%projects%`, `%practical%`, `%practicals%`, `%application%`, `%applications%`, `%code%`, `%coding%`, `%implementation%`, `%lab%`, `%hands-on%`, `%walkthrough%`, `%solved%`, `%solution%`, `%solutions%`, `%numerical%`, `%numericals%`, `%pyq%`, `%gate%`, `%demo%`, `%assignment%`.
  - Three distinct modes:
    1. **`all`**: Un-excludes all lessons (`is_excluded = 0`) to show the complete syllabus (both theory/concepts and practical examples/applications).
    2. **`concepts`**: Includes pure theory, overviews, prerequisites, and foundational lectures (`is_excluded = 0`), while excluding all practical examples, problems, walkthroughs, and applications (`is_excluded = 1`).
    3. **`examples`**: Includes all practical applications, solved examples, problems, and hands-on walkthroughs (`is_excluded = 0`), while excluding pure conceptual theory lectures (`is_excluded = 1`).
  - Added friendly HTTP 400 validations if a playlist has zero examples or zero theory lessons to prevent empty schedules.
- **Frontend Reactive Pill Selection**:
  - Added dynamic active pill state toggling in `frontend/static/js/app.js` (`updateFilterButtonsUI(mode)`):
    - Selected filter receives active pill style: `bg-accent text-white shadow-sm font-semibold`.
    - Unselected filters receive inactive style: `text-text-secondary hover:text-text-primary hover:bg-bg-card font-medium`.
  - Automatically triggers schedule regeneration (`/api/courses/{id}/schedule/generate`), reloads schedule allocations, and updates curriculum drawer check states.
  - Displays instant toast feedback for the user explaining the filtered view.
- **Verification**:
  - `tests/test_filter_modes_api.py`: Verified API model and exclusion rules for `concepts`, `examples`, and `all` with schedule generation.
  - `tests/test_three_way_filter.py`: Playwright browser test verified active pill highlights and schedule reflow when clicking `[Concepts]`, `[Examples]`, and `[All]`.
  - 100% test suite passing.

### Copy-Paste Syllabus Matcher & Auto-Curator
- **Database & Architecture**:
  - Migration `008_syllabus_alignment.sql`: Added `syllabus_text` and `syllabus_metadata` columns to `courses` table.
  - Pydantic schemas in `backend/models/schemas.py`: `SyllabusMatchRequest`, `SyllabusTopicMatch`, `SyllabusLessonMatch`, `SyllabusMatchResponse`, `SyllabusApplyRequest`, `SyllabusApplyResponse`, `SyllabusInfoResponse`.
- **Parsing & Multi-Signal Matching Engine (`backend/services/syllabus_matcher.py`)**:
  - Supports unit/module/chapter blocks, roman numerals, bullet points, numbered lists, and comma/semicolon delimited topic lists.
  - Filters out common university noise (course codes, credit hours, textbook references, grading schemes).
  - Domain synonym & acronym expansion across Computer Science, Engineering, Math, and Science (DFA, NFA, PDA, CFG, TM, Normalization, SQL, Transactions, CPU Scheduling, IPC, BST, etc.).
  - Multi-signal scoring combining normalized title n-grams and token overlap with SQLite FTS5 BM25 search across lesson transcripts and chunks.
  - Adjustable strictness presets: `balanced` (default), `strict`, `comprehensive`.
- **Endpoints (`backend/routers/courses.py`)**:
  - `POST /api/courses/{course_id}/syllabus/match`: Analyzes pasted syllabus and returns structured topic mappings, matched lessons, saved study hours, and coverage percentage.
  - `POST /api/courses/{course_id}/syllabus/apply`: Automatically sets `is_excluded = 0` for matched/selected videos, `is_excluded = 1` for out-of-syllabus videos, persists syllabus metadata, and automatically regenerates the study schedule.
  - `GET /api/courses/{course_id}/syllabus`: Returns previously saved syllabus text and alignment metrics.
- **Frontend UI & Experience (`frontend/templates/index.html` & `frontend/static/js/app.js`)**:
  - Dedicated access points: `📑` icon in syllabus header, `📑 University Syllabus` banner in Curriculum Drawer, and `📑 Syllabus` button in Course Settings modal.
  - Modal `#modal-syllabus-match` with two-step workflow:
    - Step 1: Syllabus paste textarea, strictness selector pills, and `Analyze & Match Videos` button.
    - Step 2: Visual review dashboard showing 3 metrics cards (Videos Matched, Out-of-Syllabus Time Saved, Syllabus Coverage), `By Syllabus Topic` mapping view, and `All Videos Checklist` with manual override checkboxes.
    - `Apply & Auto-Reschedule Course` button immediately trims the course to the syllabus and reflows the study plan.
- **Verification**:
  - `tests/test_syllabus_matching.py`: Unit and API ASGI test verifying matching, exclusion toggling, syllabus retrieval, and schedule reflow.
  - `tests/test_syllabus_match_ui.py`: Playwright live browser test verifying modal opening, syllabus pasting, matching analysis (57/117 videos matched, 11h 3m saved), and schedule reflow with 0 JavaScript console errors.

---

## Milestone 8: Decoupled Concept-Clip Partitioning, Instant Deterministic Day Repacking, Per-Unit Study Bundles & Whole-Video Cheat Sheet (`v0.7-concept-partition`)
- **Layer 1 (Immutable Content Architecture)**:
  - Created Migration `009_concept_clips_and_decoupled_schedule.sql`:
    - Created `concept_clips` table (`id`, `source_id`, `course_id`, `order_index`, `title`, `start_sec`, `end_sec`, `raw_duration_sec`, `priority_tag`, `status`, `completed_at`, `skipped_at`).
    - Added `priority_tag`, `status`, `completed_at`, `skipped_at` to `lessons`.
    - Added `num_study_days`, `preferred_daily_minutes` to `courses`.
    - Added `clip_id` to `schedule_allocations` and created `schedule_assignments` view.
    - Automatic pre-migration backup saved to `data-dev/backups/app_v8_20261123_022153.db`.
  - Concept Partitioner Engine (`backend/services/concept_partitioner.py`):
    - Continuous partitioning from `00:00` to `video_end` with 0 gaps and 0 overlaps into ~10–15 min concept units (range 8–18 min).
    - Merges tiny micro-chapters (`< 180s`) with adjacent topics.
    - Splits long chapters (`> 18m`) at natural transcript sentence/silence gaps into sequential parts (`— Part 1: ...`, `— Part 2: ...`).
    - Two modes: Deterministic (zero-LLM, instant) and AI-Assisted Semantic (sliding 45–60 min windows, marathon-safe for 10–15h videos).
  - Permanent Content Attachment:
    - Notes, quizzes, flashcards, and completion states attach permanently to Concept Clips, never to calendar days.
- **Layer 2 (Mutable Schedule & Instant Deterministic Repacking)**:
  - Built pure Python scheduler `repack_schedule(clips, config, clock)` in `backend/scheduler/engine.py`:
    - Runs in `< 10ms` with **0 LLM calls**.
    - Supports Fit to Exam Date / Number of Days (calculates `required_daily_minutes = remaining_eff / days`, distributes concept clips evenly up to revision buffer, displays pace notice if exceeding preferred daily budget).
    - Supports Fixed Daily Budget mode (greedily packs sequential clips with soft `±15%` tolerance without splitting a concept mid-topic).
    - Generates concise diff (`Old finish -> New finish`, `Pace: 60m -> 75m/day`) and saves snapshots for 1-click **Undo**.
- **Progressive Per-Concept Study Bundles**:
  - Built `backend/services/study_bundle.py`: immediately generates Clips 1–3 upon source approval so learning begins in seconds; silent resumable background queue processes remaining clips, cached by SHA-256 hash in SQLite.
  - Structured Notes: 5-part GeeksforGeeks-style standalone notes strictly from transcript slices with clickable `[MM:SS]` timestamp pills.
  - Per-Concept Quiz: Citation-grounded MCQs linked to exact timestamps; missing a question reveals a "Replay Explanation [MM:SS]" button seeking the video.
  - Spaced Repetition Flashcards: 4–6 concise Q&A/formula cards generated per clip tagged with `[MM:SS]` timestamps and added to the FSRS queue.
- **Whole-Video Master Cheat Sheet / Cram Sheet**:
  - Synthesized whole-video cram sheets with 1-line formal definitions, master comparison/complexity tables, key formulas/algorithms, and clickable `[MM:SS]` jump links.
  - Cached by SHA-256 digest with dedicated `@media print` CSS for "Print / Save as PDF" and "Download Markdown".
- **Comprehensive Verification**:
  - `tests/test_concept_partitioner.py`: Verified deterministic & AI sliding window partitioning (continuity, zero gaps/overlaps, 8–18m sizing, sequential part splitting).
  - `tests/test_repack_schedule.py`: Verified pure math repacking < 10ms, pace notice, greedy packing ±15%, completed clip locking.
  - `tests/test_course_reschedule_flow.py`: Verified editing exam date (14d -> 7d -> 20d), minutes_per_day, and speed makes 0 LLM calls, preserves notes/quizzes/completed states, and supports 1-click Undo.
  - `tests/test_concept_partition_and_repack_ui.py`: Playwright live browser test verified day rail updates instantaneously without reloading notes, clicking `[MM:SS]` in notes, quiz replay, and Master Cheat Sheet seeks video with 0 browser console errors.
  - Full test suite: 47/47 tests passing (100% green).
