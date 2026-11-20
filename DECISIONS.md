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
