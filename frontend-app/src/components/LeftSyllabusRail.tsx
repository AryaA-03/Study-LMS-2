import React, { useMemo, useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  FileText,
  Film,
  Flame,
  FolderPlus,
  Globe,
  PanelLeftOpen,
  Settings,
  SkipForward,
  Trash2,
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
  onOpenAddSource,
  onDeleteSource,
  onOpenSettings,
}) => {
  const [viewMode, setViewMode] = useState<'days' | 'topics'>('days');
  const [filter, setFilter] = useState<RailFilter>('all');
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

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

  // Sleek Collapsed Chrome-style Rail (D1 / D2 / V1)
  if (collapsed) {
    return (
      <aside className="no-print flex h-full w-[56px] shrink-0 flex-col items-center justify-between border-r border-[var(--border-subtle)] bg-[var(--bg-sidebar)] py-3 select-none">
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
                const mins = Math.round(
                  d.total_effective_minutes ?? d.total_minutes ?? d.allocations.reduce((s, a) => s + (a.effective_minutes || 0), 0),
                );
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
                    title={`${d.day_label || `Day ${idx + 1}`} (${mins}m)`}
                    className={`flex h-9 w-9 items-center justify-center rounded-full border text-[11px] font-semibold transition ${
                      isActiveDay
                        ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent-text)] ring-2 ring-[var(--accent)]/25'
                        : allDone
                        ? 'border-[var(--success)]/40 bg-[var(--bg-card)] text-[var(--success)]'
                        : 'border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
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
      {/* Clean Minimal Header: Syllabus + By Day / By Topic */}
      <div className="px-3.5 pt-3.5 pb-2.5 space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--fg-muted)]">
            Syllabus
          </span>
          <div className="inline-flex rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] p-0.5 text-[11px]">
            <button
              type="button"
              onClick={() => setViewMode('days')}
              className={`rounded-md px-2 py-0.5 font-semibold transition ${
                viewMode === 'days'
                  ? 'bg-[var(--accent)] text-white shadow-sm'
                  : 'text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
              }`}
            >
              Days
            </button>
            <button
              type="button"
              onClick={() => setViewMode('topics')}
              className={`rounded-md px-2 py-0.5 font-semibold transition ${
                viewMode === 'topics'
                  ? 'bg-[var(--accent)] text-white shadow-sm'
                  : 'text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
              }`}
            >
              Topics
            </button>
          </div>
        </div>

        {/* Clean Single-Row Filter Pills */}
        <div className="flex items-center gap-1 rounded-lg bg-[var(--bg-hover)]/60 p-0.5">
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
              className={`flex-1 rounded-md py-1 text-[10.5px] font-semibold transition ${
                filter === f.id
                  ? 'bg-[var(--bg-card)] text-[var(--fg-primary)] shadow-sm'
                  : 'text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Breathable Scrollable Lesson List */}
      <div className="flex-1 overflow-y-auto px-2.5 pb-3 space-y-2.5">
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
              const dayMins = Math.round(
                day.total_effective_minutes ?? day.total_minutes ?? filteredAllocs.reduce((acc, a) => acc + (a.effective_minutes || 0), 0),
              );

              return (
                <div key={gKey} className="space-y-1">
                  <button
                    type="button"
                    onClick={() => toggleGroup(gKey)}
                    className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left hover:bg-[var(--bg-hover)]/70"
                  >
                    <div className="flex items-center gap-1.5 text-[11px] font-bold text-[var(--fg-secondary)]">
                      {isCollapsed ? (
                        <ChevronRight className="h-3.5 w-3.5 text-[var(--fg-muted)]" />
                      ) : (
                        <ChevronDown className="h-3.5 w-3.5 text-[var(--fg-muted)]" />
                      )}
                      <span>{day.day_label || `Day ${dIdx + 1}`}</span>
                      <span className="font-normal text-[var(--fg-muted)]">· {dayMins}m</span>
                    </div>
                    <span className="text-[10px] font-semibold text-[var(--fg-muted)]">
                      {doneCount}/{filteredAllocs.length}
                    </span>
                  </button>

                  {!isCollapsed && (
                    <div className="space-y-0.5 pl-1">
                      {filteredAllocs.map((alloc) => {
                        const les = lessonById.get(alloc.lesson_id);
                        const isActive = alloc.lesson_id === activeLessonId;
                        return (
                          <div
                            key={alloc.id}
                            onClick={() => les && onSelectLesson(les, alloc)}
                            className={`group flex items-start gap-2 rounded-lg px-2.5 py-2 text-[12px] transition cursor-pointer ${
                              isActive
                                ? 'bg-[var(--accent-soft)] text-[var(--accent-text)] font-semibold shadow-sm'
                                : 'text-[var(--fg-primary)] hover:bg-[var(--bg-card)]/80'
                            }`}
                          >
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onToggleComplete(alloc);
                              }}
                              className="mt-0.5 shrink-0 text-[var(--fg-muted)] hover:text-[var(--accent)]"
                              title={alloc.is_completed ? 'Completed' : 'Mark completed'}
                            >
                              {alloc.is_completed ? (
                                <CheckCircle2 className="h-3.5 w-3.5 text-[var(--success)]" />
                              ) : (
                                <Circle className="h-3.5 w-3.5" />
                              )}
                            </button>
                            <div className="min-w-0 flex-1">
                              <div className={`line-clamp-2 leading-snug ${alloc.is_completed ? 'line-through opacity-55' : ''}`}>
                                {alloc.lesson_title}
                              </div>
                            </div>
                            <div className="flex shrink-0 items-center gap-1 pt-0.5 text-[10px] text-[var(--fg-muted)]">
                              {(alloc.pyq_hit_count || 0) > 0 && <Flame className="h-3 w-3 text-[var(--warning)]" />}
                              <span className="font-mono">{Math.max(1, Math.round(alloc.effective_minutes))}m</span>
                              {!alloc.is_completed && (
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onSkipAllocation(alloc);
                                  }}
                                  className="hidden group-hover:inline-flex rounded p-0.5 hover:bg-[var(--bg-hover)] hover:text-[var(--warning)]"
                                  title="Skip to later day"
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
                  {pct > 0 && pct < 100 && !isCollapsed && (
                    <div className="mx-2.5 h-0.5 rounded-full bg-[var(--border-subtle)] overflow-hidden">
                      <div className="h-full bg-[var(--accent)]" style={{ width: `${pct}%` }} />
                    </div>
                  )}
                </div>
              );
            })
          ) : (
            <div className="rounded-xl border border-dashed border-[var(--border-strong)] p-4 text-center text-xs text-[var(--fg-secondary)]">
              Add a YouTube playlist, marathon lecture, or PDF below to build your syllabus.
            </div>
          )
        ) : (
          topicGroups.map((grp, gIdx) => {
            const gKey = `topic-${gIdx}-${grp.title}`;
            const isCollapsed = !!collapsedGroups[gKey];
            return (
              <div key={gKey} className="space-y-1">
                <button
                  type="button"
                  onClick={() => toggleGroup(gKey)}
                  className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left hover:bg-[var(--bg-hover)]/70"
                >
                  <div className="flex min-w-0 items-center gap-1.5 text-[11px] font-bold text-[var(--fg-secondary)]">
                    {isCollapsed ? (
                      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--fg-muted)]" />
                    ) : (
                      <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--fg-muted)]" />
                    )}
                    <span className="truncate">{grp.title}</span>
                  </div>
                  <span className="shrink-0 text-[10px] text-[var(--fg-muted)]">
                    {grp.items.length} · {grp.totalMin}m
                  </span>
                </button>
                {!isCollapsed && (
                  <div className="space-y-0.5 pl-1">
                    {grp.items.map((les) => {
                      const alloc = allocByLessonId.get(les.id);
                      const isActive = les.id === activeLessonId;
                      const done = alloc?.is_completed || les.status === 'completed';
                      return (
                        <div
                          key={les.id}
                          onClick={() => onSelectLesson(les, alloc)}
                          className={`flex items-start gap-2 rounded-lg px-2.5 py-2 text-[12px] cursor-pointer transition ${
                            isActive
                              ? 'bg-[var(--accent-soft)] text-[var(--accent-text)] font-semibold'
                              : 'text-[var(--fg-primary)] hover:bg-[var(--bg-card)]/80'
                          }`}
                        >
                          {done ? (
                            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--success)]" />
                          ) : (
                            <Circle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--fg-muted)]" />
                          )}
                          <span className={`min-w-0 flex-1 line-clamp-2 leading-snug ${done ? 'line-through opacity-55' : ''}`}>
                            {les.title}
                          </span>
                          {(les.pyq_hit_count || 0) > 0 && <Flame className="mt-0.5 h-3 w-3 shrink-0 text-[var(--warning)]" />}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Clean Compact Resources Dock */}
      <div className="border-t border-[var(--border-subtle)] px-3 py-2.5">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[10.5px] font-bold uppercase tracking-wider text-[var(--fg-muted)]">
            Resources
          </span>
          <button
            type="button"
            onClick={onOpenAddSource}
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold text-[var(--accent)] hover:bg-[var(--accent-soft)]"
          >
            <FolderPlus className="h-3 w-3" /> Add
          </button>
        </div>
        <div className="max-h-24 space-y-0.5 overflow-y-auto">
          {sources.length === 0 ? (
            <p className="text-[11px] text-[var(--fg-muted)]">No sources attached yet.</p>
          ) : (
            sources.map((src) => (
              <div
                key={src.id}
                className="group flex items-center justify-between gap-1.5 rounded-md px-1.5 py-1 text-[11.5px] text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)]"
              >
                <div className="flex min-w-0 items-center gap-1.5">
                  {src.source_type === 'pdf' ? (
                    <FileText className="h-3.5 w-3.5 shrink-0 text-[var(--danger)]" />
                  ) : src.source_type === 'url' || src.source_type === 'web_page' ? (
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
      </div>
    </aside>
  );
};
