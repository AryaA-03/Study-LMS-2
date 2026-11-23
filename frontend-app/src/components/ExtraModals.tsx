import React, { useMemo, useState } from 'react';
import { CheckSquare, Command, Layers, Loader2, Search, Square, X } from 'lucide-react';
import { api, Lesson } from '../api/client';

/* ================= CURRICULUM DRAWER (INSPECT & FILTER ALL PLAYLIST VIDEOS) ================= */
export const CurriculumDrawerModal: React.FC<{
  courseId: string;
  lessons: Lesson[];
  onClose: () => void;
  onUpdated: () => void;
  onOpenSyllabus: () => void;
  onToast: (msg: string) => void;
}> = ({ courseId, lessons, onClose, onUpdated, onOpenSyllabus, onToast }) => {
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return lessons;
    return lessons.filter(
      (l) =>
        l.title.toLowerCase().includes(q) ||
        (l.chapter_title || '').toLowerCase().includes(q),
    );
  }, [lessons, search]);

  const includedCount = lessons.filter((l) => !l.is_excluded).length;

  const handleToggle = async (lessonId: string) => {
    setBusy(true);
    try {
      await api.toggleExcludeLesson(courseId, lessonId);
      onUpdated();
    } catch (e: any) {
      onToast(`Toggle error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleSkipAllExamples = async () => {
    setBusy(true);
    const exRe = /\b(example|examples|ex\s*\d|problem|problems|solved|numerical|exercise|practice|question|walkthrough|demo)\b/i;
    try {
      const toExclude = lessons.filter((l) => !l.is_excluded && exRe.test(l.title));
      for (const l of toExclude) {
        await api.toggleExcludeLesson(courseId, l.id);
      }
      await api.replanSchedule(courseId, 'normal').catch(() => {});
      onToast(`Excluded ${toExclude.length} example/practice videos & repacked schedule`);
      onUpdated();
    } catch (e: any) {
      onToast(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleIncludeAll = async () => {
    setBusy(true);
    try {
      const excluded = lessons.filter((l) => !!l.is_excluded);
      for (const l of excluded) {
        await api.toggleExcludeLesson(courseId, l.id);
      }
      await api.replanSchedule(courseId, 'normal').catch(() => {});
      onToast(`Included all ${lessons.length} lessons & repacked schedule`);
      onUpdated();
    } catch (e: any) {
      onToast(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="no-print fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-[2px]" onClick={onClose}>
      <div
        className="flex h-full w-full max-w-lg flex-col border-l border-[var(--border-strong)] bg-[var(--bg-card)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
          <div>
            <h2 className="text-sm font-bold text-[var(--fg-primary)]">Curriculum Inspector</h2>
            <p className="text-[11px] text-[var(--fg-secondary)]">
              {includedCount} of {lessons.length} lessons active in your schedule
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1.5 text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)]">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="border-b border-[var(--border-subtle)] px-4 py-2.5 space-y-2 text-xs">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-[var(--fg-muted)]" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter lessons or topics..."
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] py-1.5 pl-8 pr-3 text-xs text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleIncludeAll}
              disabled={busy}
              className="font-semibold text-[var(--accent)] hover:underline"
            >
              Select All
            </button>
            <button
              type="button"
              onClick={handleSkipAllExamples}
              disabled={busy}
              className="font-semibold text-amber-600 dark:text-amber-400 hover:underline"
            >
              Skip All Examples
            </button>
            <button
              type="button"
              onClick={() => {
                onClose();
                onOpenSyllabus();
              }}
              className="ml-auto inline-flex items-center gap-1 rounded-md bg-[var(--accent)] px-2.5 py-1 text-[11px] font-semibold text-white"
            >
              <Layers className="h-3 w-3" /> Match Syllabus
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-[var(--border-subtle)] px-2">
          {filtered.map((l) => (
            <div
              key={l.id}
              onClick={() => handleToggle(l.id)}
              className="flex cursor-pointer items-center gap-2.5 px-2.5 py-2 text-xs hover:bg-[var(--bg-hover)]/60"
            >
              {!l.is_excluded ? (
                <CheckSquare className="h-4 w-4 shrink-0 text-[var(--accent)]" />
              ) : (
                <Square className="h-4 w-4 shrink-0 text-[var(--fg-muted)]" />
              )}
              <div className="min-w-0 flex-1">
                <div className={`truncate font-medium ${l.is_excluded ? 'line-through opacity-50' : 'text-[var(--fg-primary)]'}`}>
                  {l.title}
                </div>
                {l.chapter_title && (
                  <div className="truncate text-[10px] text-[var(--fg-muted)]">{l.chapter_title}</div>
                )}
              </div>
              <span className="shrink-0 rounded bg-[var(--bg-elevated)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--fg-secondary)]">
                {Math.max(1, Math.round((l.raw_duration_sec || 600) / 60))}m
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

/* ================= EDIT LESSON MODAL ================= */
export const EditLessonModal: React.FC<{
  courseId: string;
  lesson: Lesson;
  onClose: () => void;
  onSaved: () => void;
  onToast: (msg: string) => void;
}> = ({ courseId, lesson, onClose, onSaved, onToast }) => {
  const [title, setTitle] = useState(lesson.title || '');
  const [chapter, setChapter] = useState(lesson.chapter_title || '');
  const [priority, setPriority] = useState(lesson.priority || 'core');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateLesson(courseId, lesson.id, {
        title: title.trim() || lesson.title,
        chapter_title: chapter.trim(),
        priority,
      });
      onToast('Lesson updated');
      onSaved();
      onClose();
    } catch (e: any) {
      onToast(`Update failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="no-print fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-[2px]" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-2xl border border-[var(--border-strong)] bg-[var(--bg-card)] p-5 shadow-2xl space-y-3 text-xs"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-[var(--fg-primary)]">Edit Lesson Details</h2>
          <button type="button" onClick={onClose} className="rounded p-1 text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)]">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div>
          <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Lesson Title</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
          />
        </div>
        <div>
          <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Topic Group (Chapter)</label>
          <input
            value={chapter}
            onChange={(e) => setChapter(e.target.value)}
            placeholder="e.g. Pushdown Automata (PDA)"
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
          />
        </div>
        <div>
          <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Priority</label>
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
          >
            <option value="core">Core (Always Kept)</option>
            <option value="deep_dive">Deep-Dive (Dropped in Emergency Cram)</option>
          </select>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-[var(--border-subtle)] px-3.5 py-1.5 font-semibold text-[var(--fg-secondary)]">
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded-lg bg-[var(--accent)] px-4 py-1.5 font-semibold text-white"
          >
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
          </button>
        </div>
      </div>
    </div>
  );
};

/* ================= ⌘K COMMAND PALETTE ================= */
export const CommandPaletteModal: React.FC<{
  lessons: Lesson[];
  onClose: () => void;
  onSelectLesson: (lesson: Lesson) => void;
  onAction: (action: string) => void;
}> = ({ lessons, onClose, onSelectLesson, onAction }) => {
  const [query, setQuery] = useState('');

  const actions = [
    { id: 'cram', label: 'Open Last-Night Cram Sheet' },
    { id: 'mock_exam', label: 'Start Timed Mock Exam' },
    { id: 'diagnostic', label: 'Start 2-Minute Diagnostic Pre-Test' },
    { id: 'edit-course', label: 'Edit Course, Exam Date & Study Timings' },
    { id: 'curriculum', label: 'Open Curriculum Inspector' },
    { id: 'syllabus', label: 'Match University Syllabus' },
    { id: 'add-source', label: 'Add Source (YouTube / PDF / Web / Transcript)' },
    { id: 'cluster', label: 'Auto-Group Playlist Videos into Topics' },
    { id: 'theme', label: 'Toggle Warm Paper Light / Deep Graphite Dark' },
    { id: 'settings', label: 'Open Settings & Data Portability' },
  ];

  const q = query.trim().toLowerCase();
  const matchedActions = actions.filter((a) => !q || a.label.toLowerCase().includes(q));
  const matchedLessons = lessons
    .filter((l) => !l.is_excluded && (!q || l.title.toLowerCase().includes(q) || (l.chapter_title || '').toLowerCase().includes(q)))
    .slice(0, 8);

  return (
    <div className="no-print fixed inset-0 z-50 flex items-start justify-center bg-black/50 pt-20 p-4 backdrop-blur-[2px]" onClick={onClose}>
      <div
        className="w-full max-w-lg overflow-hidden rounded-2xl border border-[var(--border-strong)] bg-[var(--bg-card)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3.5 py-2.5">
          <Command className="h-4 w-4 text-[var(--fg-muted)]" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Jump to lesson or run command..."
            className="flex-1 bg-transparent text-xs text-[var(--fg-primary)] outline-none"
          />
          <kbd className="rounded border border-[var(--border-subtle)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--fg-muted)]">ESC</kbd>
        </div>

        <div className="max-h-80 overflow-y-auto p-2 space-y-2 text-xs">
          {matchedActions.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-[var(--fg-muted)]">Commands</div>
              {matchedActions.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => {
                    onAction(a.id);
                    onClose();
                  }}
                  className="flex w-full items-center rounded-lg px-2.5 py-1.5 text-left text-[var(--fg-primary)] hover:bg-[var(--accent-soft)] hover:text-[var(--accent-text)]"
                >
                  {a.label}
                </button>
              ))}
            </div>
          )}

          {matchedLessons.length > 0 && (
            <div>
              <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-[var(--fg-muted)]">Lessons</div>
              {matchedLessons.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  onClick={() => {
                    onSelectLesson(l);
                    onClose();
                  }}
                  className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-[var(--fg-primary)] hover:bg-[var(--accent-soft)] hover:text-[var(--accent-text)]"
                >
                  <span className="truncate">{l.title}</span>
                  {l.chapter_title && <span className="ml-2 shrink-0 text-[10px] text-[var(--fg-muted)]">{l.chapter_title}</span>}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
