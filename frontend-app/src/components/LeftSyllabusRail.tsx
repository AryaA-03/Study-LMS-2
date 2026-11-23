import React, { useMemo, useState } from 'react';
import {
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Clock,
  FileText,
  Film,
  Flame,
  FolderPlus,
  Globe,
  BookOpen,
  Layers,
  PanelLeftOpen,
  Pencil,
  RefreshCw,
  Settings,
  SkipForward,
  Sparkles,
  Square,
  Trash2,
  Zap,
} from 'lucide-react';
import { AllocationItem, Course, Lesson, ScheduleResponse, SourceItem } from '../api/client';

export type RailFilter = 'all' | 'concepts' | 'examples' | 'pyqs';

interface LeftSyllabusRailProps {
  course: Course | null;
  schedule: ScheduleResponse | null;
  lessons: Lesson[];
  sources: SourceItem[];
  activeLessonId: string | null;
  collapsed: boolean;
  width: number;
  onToggleCollapse: () => void;
  onSelectLesson: (lesson: Lesson, alloc?: AllocationItem) => void;
  onToggleComplete: (alloc: AllocationItem) => void;
  onSkipAllocation: (alloc: AllocationItem) => void;
  onQuickUpdateSchedule: (patch: Partial<Course>) => void;
  onReplan: () => void;
  onClusterTopics: () => void;
  onOpenEditCourse: () => void;
  onOpenCurriculum: () => void;
  onOpenSyllabusModal: () => void;
  onOpenDiagnostic: () => void;
  onOpenAddSource: () => void;
  onDeleteSource: (sourceId: string) => void;
  onOpenSettings: () => void;
}

const EXAMPLE_RE = /\b(example|examples|ex\s*\d|problem|problems|solved|numerical|exercise|practice|question|walkthrough|demo|worked|trace|construct|design\s+a|convert|pyq|gate\s+\d{4})\b/i;

function matchesFilter(title: string, pyqHits: number, filter: RailFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'pyqs') return pyqHits > 0;
  const isEx = EXAMPLE_RE.test(title || '');
  if (filter === 'examples') return isEx;
  return !isEx;
}

export const LeftSyllabusRail: React.FC<LeftSyllabusRailProps> = ({
  course,
  schedule,
  lessons,
  sources,
  activeLessonId,
  collapsed,
  width,
  onToggleCollapse,
  onSelectLesson,
  onToggleComplete,
  onSkipAllocation,
  onQuickUpdateSchedule,
  onReplan,
  onClusterTopics,
  onOpenEditCourse,
  onOpenCurriculum,
  onOpenSyllabusModal,
  onOpenDiagnostic,
  onOpenAddSource,
  onDeleteSource,
  onOpenSettings,
}) => {
  const [viewMode, setViewMode] = useState<'days' | 'topics'>('days');
  const [filter, setFilter] = useState<RailFilter>('all');
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [inlineSpeed, setInlineSpeed] = useState<number>(course?.playback_speed || 1.25);
  const [inlineMinutes, setInlineMinutes] = useState<number>(course?.minutes_per_day || 60);

  React.useEffect(() => {
    if (course?.playback_speed) setInlineSpeed(course.playback_speed);
    if (course?.minutes_per_day) setInlineMinutes(course.minutes_per_day);
  }, [course?.id, course?.playback_speed, course?.minutes_per_day]);

  const lessonById = useMemo(() => {
    const map = new Map<string, Lesson>();
    lessons.forEach((l) => map.set(l.id, l));
    return map;
  }, [lessons]);

  const allocByLessonId = useMemo(() => {
    const map = new Map<string, AllocationItem>();
    schedule?.days?.forEach((d) => {
      d.allocations.forEach((a) => {
        if (!map.has(a.lesson_id)) map.set(a.lesson_id, a);
      });
    });
    return map;
  }, [schedule]);

  const days = schedule?.days || [];

  // Group lessons by chapter_title for "By Topic" view (Playlist Topic Clustering!)
  const topicGroups = useMemo(() => {
    const groups: Array<{ title: string; items: Lesson[]; totalMin: number; completedCount: number }> = [];
    const byTitle = new Map<string, number>();
    lessons
      .filter((l) => !l.is_excluded)
      .forEach((l) => {
        if (!matchesFilter(l.title, l.pyq_hit_count || 0, filter)) return;
        const t = (l.chapter_title || '').trim() || 'Core Concepts';
        if (!byTitle.has(t)) {
          byTitle.set(t, groups.length);
          groups.push({ title: t, items: [], totalMin: 0, completedCount: 0 });
        }
        const g = groups[byTitle.get(t)!];
        g.items.push(l);
        const speed = course?.playback_speed || 1;
        g.totalMin += Math.max(1, Math.round(((l.raw_duration_sec || 600) / 60) / speed));
        const alloc = allocByLessonId.get(l.id);
        if (alloc?.is_completed || l.status === 'completed') g.completedCount += 1;
      });
    return groups;
  }, [lessons, filter, course?.playback_speed, allocByLessonId]);

  const toggleGroup = (key: string) =>
    setCollapsedGroups((prev) => ({ ...prev, [key]: !prev[key] }));

  // Collapsed Chrome-style Icon Rail (matches image_23084c.jpg!)
  if (collapsed) {
    return (
      <aside className="no-print flex h-full w-[54px] shrink-0 flex-col items-center justify-between border-r border-[var(--border-subtle)] bg-[var(--bg-sidebar)] py-2.5 select-none">
        <div className="flex flex-col items-center gap-2 overflow-y-auto px-1">
          <button
            type="button"
            onClick={onToggleCollapse}
            title="Expand Syllabus Rail"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
          >
            <PanelLeftOpen className="h-4 w-4" />
          </button>

          <div className="my-1 h-px w-6 bg-[var(--border-subtle)]" />

          {days.length > 0
            ? days.slice(0, 14).map((d, idx) => {
                const isActiveDay = d.allocations.some((a) => a.lesson_id === activeLessonId);
                const allDone = d.allocations.length > 0 && d.allocations.every((a) => a.is_completed);
                return (
                  <button
                    key={d.date || idx}
                    type="button"
                    onClick={() => {
                      const first = d.allocations[0];
                      if (first) {
                        const les = lessonById.get(first.lesson_id);
                        if (les) onSelectLesson(les, first);
                      }
                    }}
                    title={`${d.day_label || `Day ${idx + 1}`} (${Math.round(d.total_minutes ?? d.allocations.reduce((acc, a) => acc + (a.effective_minutes || 0), 0))}m)`}
                    className={`flex h-9 w-9 items-center justify-center rounded-full border text-[11px] font-semibold transition ${
                      isActiveDay
                        ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent-text)] ring-2 ring-[var(--accent)]/30'
                        : allDone
                        ? 'border-[var(--success)]/50 bg-[var(--bg-card)] text-[var(--success)]'
                        : 'border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--fg-primary)]'
                    }`}
                  >
                    D{idx + 1}
                  </button>
                );
              })
            : lessons.slice(0, 12).map((l, idx) => (
                <button
                  key={l.id}
                  type="button"
                  onClick={() => onSelectLesson(l)}
                  title={l.title}
                  className={`flex h-9 w-9 items-center justify-center rounded-full border text-[11px] font-semibold transition ${
                    l.id === activeLessonId
                      ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent-text)]'
                      : 'border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
                  }`}
                >
                  V{idx + 1}
                </button>
              ))}
        </div>

        <button
          type="button"
          onClick={onOpenSettings}
          title="Settings"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
        >
          <Settings className="h-4 w-4" />
        </button>
      </aside>
    );
  }

  return (
    <aside
      style={{ width }}
      className="no-print flex h-full shrink-0 flex-col overflow-hidden bg-[var(--bg-sidebar)] select-none"
    >
      {/* Header: Lesson Syllabus List + View Toggle */}
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-3 py-2.5">
        <span className="text-xs font-bold tracking-tight text-[var(--fg-primary)]">
          Lesson Syllabus List
        </span>
        <div className="flex items-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-card)] p-0.5 text-[10px]">
          <button
            type="button"
            onClick={() => setViewMode('days')}
            className={`rounded px-1.5 py-0.5 font-semibold transition ${
              viewMode === 'days'
                ? 'bg-[var(--accent)] text-white'
                : 'text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
            }`}
          >
            By Day
          </button>
          <button
            type="button"
            onClick={() => setViewMode('topics')}
            className={`rounded px-1.5 py-0.5 font-semibold transition ${
              viewMode === 'topics'
                ? 'bg-[var(--accent)] text-white'
                : 'text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
            }`}
            title="Group playlist videos into structured topics"
          >
            By Topic
          </button>
        </div>
      </div>

      {/* Scheduling Mode + Buffer + Quick Course Tools */}
      <div className="flex flex-wrap items-center justify-between gap-1.5 border-b border-[var(--border-subtle)] px-2.5 py-1.5 text-[10px]">
        <div className="flex items-center gap-1">
          <div className="flex rounded border border-[var(--border-subtle)] bg-[var(--bg-card)] p-0.5">
            {(['paced', 'fixed'] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => onQuickUpdateSchedule({ schedule_strategy: mode })}
                className={`rounded px-1.5 py-0.5 font-semibold capitalize transition ${
                  (course?.schedule_strategy || 'paced') === mode
                    ? 'bg-[var(--accent)] text-white'
                    : 'text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
                }`}
                title={mode === 'paced' ? 'Auto-pace to finish by exam date' : 'Fixed daily study minutes'}
              >
                {mode}
              </button>
            ))}
          </div>
          <div className="flex rounded border border-[var(--border-subtle)] bg-[var(--bg-card)] p-0.5">
            {[0, 2].map((buf) => (
              <button
                key={buf}
                type="button"
                onClick={() => onQuickUpdateSchedule({ revision_buffer_days: buf })}
                className={`rounded px-1.5 py-0.5 font-semibold transition ${
                  (course?.revision_buffer_days ?? 2) === buf
                    ? 'bg-[var(--accent)] text-white'
                    : 'text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
                }`}
                title={`${buf}-day revision buffer before exam`}
              >
                {buf}d
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-0.5">
          <button
            type="button"
            onClick={onOpenEditCourse}
            title="Edit Course, Exam Date & Timings"
            className="rounded p-1 text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onOpenCurriculum}
            title="Curriculum Inspector (Include/Exclude Videos & Skip Examples)"
            className="rounded p-1 text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
          >
            <BookOpen className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onOpenSyllabusModal}
            title="University Syllabus Auto-Matcher"
            className="rounded p-1 text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
          >
            <Layers className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onOpenDiagnostic}
            title="2-Min Diagnostic Pre-Test (Skip Known Topics)"
            className="rounded p-1 text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
          >
            <Zap className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onClusterTopics}
            title="Auto-Group Playlist Videos into Structured Topics"
            className="rounded p-1 text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
          >
            <Sparkles className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Lesson Rail Filters: All | Concepts | Examples | 🔥 PYQs */}
      <div className="flex items-center gap-1 border-b border-[var(--border-subtle)] px-2.5 py-1.5">
        {([
          { id: 'all', label: 'All' },
          { id: 'concepts', label: 'Concepts' },
          { id: 'examples', label: 'Examples' },
          { id: 'pyqs', label: '🔥 PYQs' },
        ] as const).map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className={`flex-1 rounded-md px-1.5 py-1 text-[10px] font-semibold transition ${
              filter === f.id
                ? 'bg-[var(--accent)] text-white shadow-sm'
                : 'text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Scrollable Days or Topics List */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-2">
        {viewMode === 'days' ? (
          days.length > 0 ? (
            days.map((day, dIdx) => {
              const filteredAllocs = day.allocations.filter((a) =>
                matchesFilter(a.lesson_title, a.pyq_hit_count || 0, filter),
              );
              if (filteredAllocs.length === 0) return null;

              const gKey = `day-${day.date || dIdx}`;
              const isCollapsed = !!collapsedGroups[gKey];
              const doneCount = filteredAllocs.filter((a) => a.is_completed).length;
              const pct = Math.round((doneCount / filteredAllocs.length) * 100);

              return (
                <div
                  key={gKey}
                  className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)]/70 overflow-hidden"
                >
                  <button
                    type="button"
                    onClick={() => toggleGroup(gKey)}
                    className="flex w-full items-center justify-between px-2.5 py-2 text-left hover:bg-[var(--bg-hover)]/60"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--fg-primary)]">
                        {isCollapsed ? (
                          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--fg-muted)]" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--fg-muted)]" />
                        )}
                        <span className="truncate">
                          {day.day_label || `Day ${dIdx + 1}`} • {Math.round(day.total_minutes ?? day.allocations.reduce((acc, a) => acc + (a.effective_minutes || 0), 0))}m
                        </span>
                      </div>
                      <div className="mt-1.5 h-1 w-full rounded-full bg-[var(--border-subtle)] overflow-hidden">
                        <div
                          className="h-full rounded-full bg-[var(--accent)] transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  </button>

                  {!isCollapsed && (
                    <div className="divide-y divide-[var(--border-subtle)]/60 border-t border-[var(--border-subtle)]/60">
                      {filteredAllocs.map((alloc) => {
                        const les = lessonById.get(alloc.lesson_id);
                        const isActive = alloc.lesson_id === activeLessonId;
                        return (
                          <div
                            key={alloc.id}
                            className={`group flex items-start gap-2 px-2.5 py-2 text-xs transition cursor-pointer ${
                              isActive
                                ? 'bg-[var(--accent-soft)] text-[var(--accent-text)] font-medium'
                                : 'text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]/70'
                            }`}
                            onClick={() => {
                              if (les) onSelectLesson(les, alloc);
                            }}
                          >
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onToggleComplete(alloc);
                              }}
                              className="mt-0.5 shrink-0 text-[var(--fg-secondary)] hover:text-[var(--accent)]"
                              title={alloc.is_completed ? 'Completed' : 'Mark completed'}
                            >
                              {alloc.is_completed ? (
                                <CheckSquare className="h-3.5 w-3.5 text-[var(--accent)]" />
                              ) : (
                                <Square className="h-3.5 w-3.5" />
                              )}
                            </button>
                            <div className="min-w-0 flex-1">
                              <div className={`truncate leading-snug ${alloc.is_completed ? 'line-through opacity-65' : ''}`}>
                                {alloc.lesson_title}
                              </div>
                              {alloc.chapter_title && (
                                <div className="mt-0.5 truncate text-[10px] text-[var(--fg-muted)]">
                                  {alloc.chapter_title}
                                </div>
                              )}
                            </div>
                            <div className="flex shrink-0 items-center gap-1 text-[10px] text-[var(--fg-muted)]">
                              {(alloc.pyq_hit_count || 0) > 0 && (
                                <span title={`${alloc.pyq_hit_count} Past Exam Questions`} className="text-[var(--warning)]">
                                  <Flame className="h-3 w-3" />
                                </span>
                              )}
                              <span className="font-mono">{Math.max(1, Math.round(alloc.effective_minutes))}m</span>
                              {!alloc.is_completed && (
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onSkipAllocation(alloc);
                                  }}
                                  className="hidden group-hover:inline-flex rounded p-0.5 text-[var(--fg-muted)] hover:bg-[var(--bg-card)] hover:text-[var(--warning)]"
                                  title="Skip & push to later day (Undo available)"
                                >
                                  <SkipForward className="h-3 w-3" />
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-3 text-center text-xs text-[var(--fg-secondary)]">
              No scheduled lessons yet. Add a YouTube playlist, video, or PDF below to build your plan.
            </div>
          )
        ) : (
          /* By Topic View (Structured Playlist Clusters!) */
          topicGroups.length > 0 ? (
            topicGroups.map((grp, gIdx) => {
              const gKey = `topic-${gIdx}-${grp.title}`;
              const isCollapsed = !!collapsedGroups[gKey];
              return (
                <div
                  key={gKey}
                  className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)]/70 overflow-hidden"
                >
                  <button
                    type="button"
                    onClick={() => toggleGroup(gKey)}
                    className="flex w-full items-center justify-between px-2.5 py-2 text-left hover:bg-[var(--bg-hover)]/60"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--fg-primary)]">
                        {isCollapsed ? (
                          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--fg-muted)]" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--fg-muted)]" />
                        )}
                        <span className="truncate">{grp.title}</span>
                      </div>
                      <div className="mt-0.5 pl-5 text-[10px] text-[var(--fg-muted)]">
                        {grp.items.length} {grp.items.length === 1 ? 'unit' : 'units'} • {grp.totalMin}m • {grp.completedCount}/{grp.items.length} done
                      </div>
                    </div>
                  </button>
                  {!isCollapsed && (
                    <div className="divide-y divide-[var(--border-subtle)]/60 border-t border-[var(--border-subtle)]/60">
                      {grp.items.map((les) => {
                        const alloc = allocByLessonId.get(les.id);
                        const isActive = les.id === activeLessonId;
                        const done = alloc?.is_completed || les.status === 'completed';
                        return (
                          <div
                            key={les.id}
                            onClick={() => onSelectLesson(les, alloc)}
                            className={`flex items-center gap-2 px-2.5 py-1.5 text-xs cursor-pointer transition ${
                              isActive
                                ? 'bg-[var(--accent-soft)] text-[var(--accent-text)] font-medium'
                                : 'text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]/70'
                            }`}
                          >
                            {done ? (
                              <CheckSquare className="h-3.5 w-3.5 shrink-0 text-[var(--accent)]" />
                            ) : (
                              <Square className="h-3.5 w-3.5 shrink-0 text-[var(--fg-muted)]" />
                            )}
                            <span className={`min-w-0 flex-1 truncate ${done ? 'line-through opacity-65' : ''}`}>
                              {les.title}
                            </span>
                            {(les.pyq_hit_count || 0) > 0 && <Flame className="h-3 w-3 shrink-0 text-[var(--warning)]" />}
                            <span className="shrink-0 font-mono text-[10px] text-[var(--fg-muted)]">
                              {Math.max(1, Math.round((les.raw_duration_sec || 600) / 60))}m
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <div className="p-3 text-center text-xs text-[var(--fg-secondary)]">No matching topics.</div>
          )
        )}
      </div>

      {/* Bottom Resources Dock (matches image_2308a9.jpg & image_235a7d.jpg!) */}
      <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-sidebar)] px-2.5 py-2">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[11px] font-bold text-[var(--fg-primary)]">Resources</span>
          <button
            type="button"
            onClick={onOpenAddSource}
            className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--accent)] hover:underline"
          >
            <FolderPlus className="h-3 w-3" /> Add Source
          </button>
        </div>
        <div className="max-h-24 space-y-1 overflow-y-auto">
          {sources.length === 0 ? (
            <p className="text-[10px] text-[var(--fg-muted)]">No sources attached yet.</p>
          ) : (
            sources.map((src) => (
              <div
                key={src.id}
                className="group flex items-center justify-between gap-1.5 rounded px-1.5 py-1 text-[11px] text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)]"
              >
                <div className="flex min-w-0 items-center gap-1.5">
                  {src.source_type === 'pdf' ? (
                    <FileText className="h-3.5 w-3.5 shrink-0 text-[var(--danger)]" />
                  ) : src.source_type === 'url' ? (
                    <Globe className="h-3.5 w-3.5 shrink-0 text-[var(--success)]" />
                  ) : (
                    <Film className="h-3.5 w-3.5 shrink-0 text-[var(--accent)]" />
                  )}
                  <span className="truncate text-[var(--fg-primary)]" title={src.title}>
                    {src.title}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => onDeleteSource(src.id)}
                  title="Remove source"
                  className="hidden group-hover:inline-flex text-[var(--fg-muted)] hover:text-[var(--danger)]"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Inline Quick-Repack Footer (Speed + Min/Day + Replan) */}
        <div className="mt-2 flex items-center gap-1.5 border-t border-[var(--border-subtle)] pt-2">
          <select
            value={inlineSpeed}
            onChange={(e) => {
              const spd = parseFloat(e.target.value);
              setInlineSpeed(spd);
              onQuickUpdateSchedule({ playback_speed: spd });
            }}
            title="Playback speed"
            className="rounded border border-[var(--border-subtle)] bg-[var(--bg-card)] px-1 py-0.5 font-mono text-[10px] text-[var(--fg-primary)]"
          >
            {[1, 1.25, 1.5, 1.75, 2].map((s) => (
              <option key={s} value={s}>
                {s}x
              </option>
            ))}
          </select>
          <div className="flex items-center gap-1 rounded border border-[var(--border-subtle)] bg-[var(--bg-card)] px-1.5 py-0.5 text-[10px]">
            <Clock className="h-3 w-3 text-[var(--fg-muted)]" />
            <input
              type="number"
              min={15}
              max={480}
              step={15}
              value={inlineMinutes}
              onChange={(e) => setInlineMinutes(parseInt(e.target.value || '60', 10))}
              onBlur={() => onQuickUpdateSchedule({ minutes_per_day: inlineMinutes })}
              className="w-9 bg-transparent text-center font-mono text-[var(--fg-primary)] outline-none"
            />
            <span className="text-[var(--fg-muted)]">m/d</span>
          </div>
          <button
            type="button"
            onClick={onReplan}
            className="ml-auto inline-flex items-center gap-1 rounded bg-[var(--accent)] px-2 py-1 text-[10px] font-semibold text-white hover:opacity-90"
            title="Instant deterministic schedule repack"
          >
            <RefreshCw className="h-3 w-3" /> Replan
          </button>
        </div>
      </div>
    </aside>
  );
};
