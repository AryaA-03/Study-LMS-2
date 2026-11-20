# User Feedback Log

## Milestone 1 Check-In Feedback (2026-11-20)

### 1. Test Playlist & Video Anchors
- **Primary Playlist for Testing All Features**: `https://youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev&si=rlyiJ9fIMBnIWFnj` (Neso Academy Theory of Computation / TOC)
- **Single Large Video Test Anchor**: `https://youtu.be/YRnjGeQbsHQ?si=sYZPsnBvslOzIXIF` (Large lecture video)

### 2. Logging & Debuggability
- Add comprehensive terminal logs and browser console (`F12`) logs across all user actions, player seeks, API requests/responses, reflow computations, and errors so issues are instantly traceable and editable.

### 3. UI/UX Redesign (CourseIt.xyz & NotebookLM Inspiration)
- Elevate design from basic boxes to modern CourseIt / NotebookLM aesthetic:
  - Clean, spacious modern typography and dark theme.
  - Collapsible panels (collapse video player to give notes full screen; collapse schedule days; collapsible curriculum tree).
  - NotebookLM-style source explorer & grounded note workspace.
  - CourseIt-style smooth day timeline with lesson cards, duration badges, and progress indicators.

### 4. Scheduling Mode: "Spread to Exam Date" vs. "Fixed Daily Budget"
- Currently, greedy scheduling with fixed 90 min/day finished on Nov 30 for an exam on Dec 22, leaving 22 empty days.
- Add user-selectable scheduling strategy:
  1. **"Spread to Exam Date" (Paced)**: Calculates required daily minutes (`total_effective_minutes / study_days_available`) so lessons pace evenly and finish right before the 2-day revision buffer.
  2. **"Fixed Daily Budget" (Sprint)**: Uses fixed minutes/day and finishes as early as possible.

### 5. Selective Video Inclusion / Quick Filter
- Allow selecting/unselecting which videos to study or skip (e.g. selectively include only concept videos and skip/defer example/exercise videos when short on time).
- One-click bulk filters (e.g. "Concepts Only", "Include Examples", "Select All", "Deselect All").
