# Architectural & Design Decisions

This document logs all pragmatic design and architecture decisions, their justifications, and the competitor feature matrix.

---

## 1. Stack Evaluation: Single-Process vs. Split Stack

### Comparison Matrix
| Dimension | Single-Process (FastAPI + Jinja2 + Vanilla JS / Alpine.js) | Split Stack (FastAPI + React / Vite / TypeScript / Tailwind) |
| :--- | :--- | :--- |
| **Setup Simplicity** | **Winner**: Pure Python launcher (`python run.py`), zero Node.js/npm dependencies on target host. | Requires Node 18+, npm install, Vite build step, dual process handling or reverse proxy in dev. |
| **Local Latency** | **Winner**: Direct static serving and lightweight DOM operations; zero client-side bundle hydration lag. | Virtual DOM reconciliation overhead, larger initial asset bundle transfer. |
| **YouTube IFrame API** | **Winner**: Direct binding to `window.YT.Player` without React lifecycle / synthetic event friction. | Susceptible to player re-mounts on React state updates causing audio/video reloads. |
| **Pyodide Ergonomics** | **Winner**: Pyodide web worker loads directly via standard Web Worker API from local static/CDN. | Requires special Vite worker bundling plugins and cross-origin isolation headers. |
| **Maintenance & Portability** | **Winner**: Fully self-contained in Python virtual environment; single executable command starts the LMS. | Dependency rot across both PyPI and npm ecosystems over time. |

### Justification & Stack Winner
**Winner: Single-Process Stack (FastAPI + Jinja2 Shell + Vanilla ES Modules / Alpine.js + Tailwind CDN/CSS)**
For a local-first, low-overhead personal LMS targeting rapid startup on Apple Silicon with strict single-command launching (`python run.py`), the single-process architecture decisively outperforms a split stack: it completely eliminates Node.js/npm toolchain dependencies and build steps, allows direct, glitch-free lifecycle control over the YouTube IFrame Player DOM instance, enables seamless in-browser Pyodide Web Worker execution without complex Vite bundling plugins, and serves sub-millisecond API and UI responses from a single unified server process.

---

## 2. Competitor Feature Matrix (Core Loop Filter)

| Competitor | Inspiring UX Pattern | Kept in Core Loop | Dropped / Excluded | Reason (1 Line) |
| :--- | :--- | :--- | :--- | :--- |
| **CourseIt** | Diagnostic pre-test & day-wise time-budgeted lessons | Day-wise schedule constrained by `minutes_per_day`, playback speed scaling, automatic lesson splitting across days, and 2-minute diagnostic pre-test marking topics "Tested Out" | Proprietary heavy video re-rendering and cloud AI synthesis | Deterministic chapter and time-slice chunking runs 100% locally with zero cloud rendering costs. |
| **BiliNote** | Timestamped Markdown notes & keyframe screenshots | Synchronized split-screen UI with Markdown notes, clickable `[MM:SS]` YouTube player jump links, and opt-in low-res keyframe screenshots via `ffmpeg` | Mandatory background video downloading and heavy OCR processing | YouTube IFrame embeds stream directly without saving multi-gigabyte video files to disk. |
| **NotebookLM** | Multi-source notebooks & citation-grounded Q&A | Multi-source study notebooks (YouTube transcripts, PDFs, single-page web articles) indexed into SQLite FTS5 chunks (300–600 tokens) with strict citation verification | Cloud vector databases and proprietary embedding models | SQLite FTS5 full-text search runs locally at zero marginal cost with deterministic token chunking. |
| **Anki / FSRS** | Target-retention spaced repetition scheduling | Modern FSRS algorithm (`fsrs` library) with `desired_retention` dynamically computed from remaining days to exam deadline, auto-populated from missed quiz items | Complex manual flashcard deck builders and manual sync servers | Automated generation directly from cited source chunks and quiz errors maximizes retention with zero manual deck authoring. |
| **Coursera** | Modular curriculum structure with core vs. deep-dive topics | Structured topic roadmaps with `core` vs. `deep-dive` classification; automatic schedule compression drops lowest-priority deep-dive topics to protect the 2-day revision buffer | Fixed calendar deadlines, peer review grading queues, and paywalled certificates | Personal exam prep requires dynamic schedule adaptation and instant reflow when life happens. |
| **Khan Academy** | Mastery progression & diagnostic testing out | Topic mastery loops: diagnostic pre-test or post-lesson quizzes scoring >=80% mark topics "Tested Out" and reflow schedule; scores <60% inject targeted review lessons | Gamified points, badges, avatar shops, and grade-school hierarchies | Focuses purely on rapid mastery and retention for high-stakes college exams without distraction. |

---

## 3. Architecture & Pragmatic Decisions Log

1. **Local-First SQLite Database**: SQLite with WAL mode and FTS5 enables zero-config, portable storage, instant text search, and zero background database server overhead.
2. **Deterministic Scheduler over LLM Scheduling**: Pure Python scheduling with an injectable clock ensures 100% reproducible, instant replanning, diffing, and undo with zero token cost.
3. **Multi-Day Lesson Splitting by Seconds**: Splitting videos exceeding the daily budget into `[start_sec, end_sec]` segments prevents study fatigue while maintaining lesson continuity.
4. **Captions-First Ingestion with JSON3 Deduplication**: Fetching `json3` subtitles via `yt-dlp` avoids video download, eliminates rolling-caption duplicate lines, and preserves millisecond timestamps.
5. **On-Demand Lazy Whisper Transcription**: Transcribing only the active lesson rather than entire playlists prevents Mac thermal throttling and disk bloat.
6. **Strict Citation Grounding Rule**: Answers and quizzes must cite valid `chunk_id`s in SQLite and verbatim quotes from the chunk; ungrounded items are discarded automatically.
7. **Single OpenAI-Compatible Async LLM Client**: Supporting Google Gemini, Groq, OpenRouter, and local Ollama through one client allows seamless zero-code switching between free providers.
8. **In-Browser Pyodide in Web Worker**: Executing Python code client-side inside a sandboxed Web Worker guarantees safety with zero server-side remote code execution risks.
9. **Separate Dev & Live Worktree Isolation**: Using `data-dev/app.db` for active development while pointing `../learn-app-live/` to tagged releases and `data/app.db` protects exam study from build breakages.
10. **Pre-Migration Automatic Database Backups**: Copying `<data_dir>/app.db` to `<data_dir>/backups/app_v<N>_<timestamp>.db` before any migration guarantees non-destructive rollbacks.
11. **Dual Scheduling Strategies (Paced vs Fixed Daily Sprint)**: Allowing the student to choose between pacing lessons evenly across all days until the exam buffer vs packing greedily into a fixed daily budget prevents unallocated time gaps before exams.
12. **Granular Video & Lesson Inclusion Filter**: Providing per-video toggles and smart keyword filters (e.g. Concept-only vs Examples) lets students adapt when study days are tight without losing the core curriculum.
13. **CourseIt + NotebookLM Aesthetic with Collapsible Panes**: Adding collapsible split-screen panes (focus player vs full notes vs schedule drawer) with modern elevated cards and subtle borders maximizes focus during high-intensity exam prep.
14. **Full-Spectrum Structured Logging (Terminal + Browser F12)**: Structured logging on both backend stdout and client browser console ensures instant observability and rapid debugging without manual code inspection.
15. **Captions-First JSON3 Timing**: Extracting word-level offsets from `json3` subtitles avoids full video/audio downloads, while providing millisecond precision for clickable `[MM:SS]` player seeking.
16. **Canonical Rolling VTT Deduplication**: Stripping prefix lines that repeat the previous cue blocks eliminates repeated phrases in auto-generated captions before FTS5 indexing.
17. **Per-Lesson Audio Slice Whisper Fallback with PATH-injected ffmpeg**: Prepending `.venv/bin` to `PATH` ensures `yt-dlp` partial downloading and `mlx-whisper` on Apple Silicon function seamlessly with zero host system dependencies.
18. **NotebookLM-Style Dual Notes Workspace**: Providing tabbed Grounded Notes (with citations and keyframes) alongside debounced auto-saving Personal Notes gives students focused study and exam-prep efficiency.
19. **Opt-in 480p Keyframe Screenshots via ffmpeg Stream Seeking**: Seeking low-res frames on fresh stream URLs keeps disk usage under ~40 KB per image with YouTube thumbnail fallback.
20. **Multi-Source SQLite FTS5 Unification**: Indexing YouTube captions, PDF text, and web articles into the same `chunks` and `chunks_fts` tables with `source_type` allows uniform BM25 retrieval without external vector DB dependencies.
21. **Polite Web Ingestion with robots.txt Compliance**: Checking `robots.txt` and using a descriptive personal-study User-Agent prevents IP blocks while guaranteeing no crawler runaway.
22. **Strict Verbatim Citation Grounding**: Rejecting ungrounded claims and requiring verbatim quotes with `[ref:chk_...]` chunk citations ensures exam prep is 100% faithful to authoritative course materials.
23. **Official FSRS v5 Integration via fsrs Python Package**: Using `fsrs.Scheduler` and `fsrs.Card` provides state-of-the-art spaced repetition math with pure Python portability and SQLite serialization.
24. **Dynamic Proximity-to-Exam Retention Scaling**: Automatically scaling FSRS target retention from 0.90 up to 0.96 as the exam date approaches ensures critical concepts are drilled with high frequency during crunch time.
25. **Extractive Deterministic Quiz Generation in No-Key Mode**: Parsing sentences and factual assertions directly from SQLite chunks with distractor generation ensures quizzes work 100% offline with zero LLM API key.
26. **Automated Quiz Mastery Loop & Schedule Reflow**: Scoring &ge;80% marks lesson `is_tested_out = 1` and triggers automatic schedule reflow to reclaim study time; scoring &lt;60% automatically generates targeted FSRS flashcards for missed concepts and queues them for spaced repetition.
27. **2-Minute Diagnostic Pre-Test for Rapid Topic Test-Out**: Diagnostic questions sampled across course topics allow students to test out of already-known concepts on Day One, instantly compressing their schedule.
28. **In-Browser Timed Mock Exam Simulator**: Simulating real exam conditions with a countdown timer and topic-level score breakdown provides true exam readiness assessment with one-click flashcard generation for all missed questions.
29. **Client-Side Pyodide in Web Worker for Zero Server RCE Risk**: Executing Python 3.12 inside a Web Worker via Pyodide isolates user scripts entirely in the browser sandbox, preventing server-side remote code execution risks.
30. **Raw SQLite Stream Download & JSON Bundle Export for Portability**: Providing both raw `.db` file downloads and structured JSON course exports ensures students retain 100% data ownership and cross-device portability.
31. **In-Place SQLite VACUUM for Zero-Downtime Disk Reclaim**: Exposing a one-click VACUUM endpoint reclaims unindexed pages and compacts storage without requiring database restarts.
32. **Dual-Theme Design System (Monochrome Foundation + Editorial Accents)**: Replaced generic dark violet gradients with a crisp monochrome foundation (Zinc/Slate) supporting both Dark and Light themes with WCAG AA compliance, intentional functional accent tokens (Amber for pacing/diagnostic, Blue for citations, Mint for mastery, Coral for errors), and zero AI-slop neon styling.
33. **Explicit Exam Date Alignment & 0-Day Buffer Support**: Added a prominent toggle between "Finish on Exam Date" (0-day or 2-day buffer) and "Fixed Daily Spend", ensuring that when 0-day buffer is selected, Projected Finish Date strictly matches Exam Date with automatic pacing and zero date spillover.
34. **Collapsible Multi-Pane Studio & Days**: Provided granular collapse toggles for the video player (theater/reader mode), schedule sidebar (100% full-width studio), day groups, and curriculum drawer to accommodate different study modes and screen sizes.
35. **Selective Video Inclusion with Quick Examples Filter**: Enabled one-click exclusion of question & practice example videos alongside individual video checkboxes in the Curriculum Drawer, recalculating remaining study time and reflowing schedules immediately.
36. **Rich Color-Coded F12 Console Logging & window.learnLMS Debugger**: Exposed structured logs for API calls, theme switches, schedule calculations, player states, and filter events, alongside `window.learnLMS` global object for rapid browser-based inspection and debugging.
