import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  ChevronDown,
  Layers,
  MoreHorizontal,
  Zap,
  Camera,
  CheckCircle2,
  Copy,
  Download,
  FileAudio,
  SkipForward,
  Eye,
  EyeOff,
  FileSpreadsheet,
  GraduationCap,
  Loader2,
  Menu,
  Moon,
  PanelRightClose,
  PanelRightOpen,
  Pencil,
  Plus,
  Printer,
  RefreshCw,
  Settings,
  Sparkles,
  Sun,
  Undo2,
} from 'lucide-react';
import { AllocationItem, api, Course, Lesson, LessonNotes, ScheduleResponse, SourceItem, JobStatus
} from './api/client';
import { LeftSyllabusRail } from './components/LeftSyllabusRail';
import { RightStudioPanel, StudioTab } from './components/RightStudioPanel';
import { YouTubePlayer } from './components/YouTubePlayer';
import { MarkdownView, extractMarkdownHeadings } from './components/MarkdownView';
import {
  AddSourceModal,
  CramSheetModal,
  EditCourseModal,
  ExamModal,
  NewCourseModal,
  SettingsModal,
  SyllabusModal,
} from './components/modals';
import { CommandPaletteModal, CurriculumDrawerModal, EditLessonModal } from './components/ExtraModals';


function safeStorageGet(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}
function safeStorageSet(key: string, val: string): void {
  try { window.localStorage.setItem(key, val); } catch { /* ignore */ }
}

function formatHoursMin(minutes?: number): string {
  const m = Math.max(0, Math.round(minutes || 0));
  const h = Math.floor(m / 60);
  const r = m % 60;
  return h > 0 ? `${h}h ${String(r).padStart(2, '0')}m` : `${r}m`;
}

export const App: React.FC = () => {
  // Theme (Warm Paper Light vs Deep Graphite Dark)
  const [dark, setDark] = useState<boolean>(() => {
    const saved = safeStorageGet('study-lms-theme');
    return saved ? saved === 'dark' : false;
  });

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    safeStorageSet('study-lms-theme', dark ? 'dark' : 'light');
  }, [dark]);

  // 3-Zone Resizable Layout State (persisted in localStorage)
  const [leftCollapsed, setLeftCollapsed] = useState<boolean>(() => typeof window !== 'undefined' && window.innerWidth < 1024);
  const [leftWidth, setLeftWidth] = useState<number>(() => Number(safeStorageGet('lms-left-w')) || 280);
  const [rightOpen, setRightOpen] = useState<boolean>(() => typeof window === 'undefined' || window.innerWidth >= 1200);
  const [rightWidth, setRightWidth] = useState<number>(() => Number(safeStorageGet('lms-right-w')) || 370);
  const [videoHeightPct, setVideoHeightPct] = useState<number>(() => Number(safeStorageGet('lms-vid-h')) || 38);
  const [videoHidden, setVideoHidden] = useState(false);
  const [studioTab, setStudioTab] = useState<StudioTab>('ask');
  const [studioExpanded, setStudioExpanded] = useState(false);
  const [focusReader, setFocusReader] = useState(false);
  const [activeVideoSec, setActiveVideoSec] = useState(0);
  const [activeJob, setActiveJob] = useState<JobStatus | null>(null);

  // Core Data State
  const [courses, setCourses] = useState<Course[]>([]);
  const [coursesLoading, setCoursesLoading] = useState(true);
  const [activeCourseId, setActiveCourseId] = useState<string | null>(null);
  const [schedule, setSchedule] = useState<ScheduleResponse | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [activeLesson, setActiveLesson] = useState<Lesson | null>(null);
  const [activeAlloc, setActiveAlloc] = useState<AllocationItem | null>(null);
  const [notes, setNotes] = useState<LessonNotes | null>(null);
  const [notesLoading, setNotesLoading] = useState(false);
  const [seekRequest, setSeekRequest] = useState<{ sec: number; ts: number } | null>(null);
  const [externalAskPrompt, setExternalAskPrompt] = useState<{ text: string; ts: number } | null>(null);

  // Banners & Toasts
  const [undoBanner, setUndoBanner] = useState<string | null>(null);
  const [preparingMsg, setPreparingMsg] = useState<string | null>(null);
  const [planMenuOpen, setPlanMenuOpen] = useState(false);
  const [lessonMenuOpen, setLessonMenuOpen] = useState(false);
  const autoPreparedRef = useRef<Set<string>>(new Set());
  const [toast, setToast] = useState<string | null>(null);

  // Modals
  const [modal, setModal] = useState<
    null | 'new-course' | 'edit-course' | 'edit-lesson' | 'curriculum' | 'cmdk' | 'add-source' | 'cram' | 'diagnostic' | 'mock_exam' | 'syllabus' | 'settings'
  >(null);


  // Global ⌘K / Ctrl+K Command Palette shortcut
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setModal((m) => (m === 'cmdk' ? null : 'cmdk'));
      } else if (e.key === 'Escape') {
        setModal(null);
      } else if (
        (e.key === 'f' || e.key === 'F') &&
        !e.metaKey && !e.ctrlKey && !e.altKey &&
        !['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName || '')
      ) {
        e.preventDefault();
        setFocusReader((prev) => {
          const next = !prev;
          setLeftCollapsed(next);
          setVideoHidden(next);
          return next;
        });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Drag Resizer Refs
  const centerRef = useRef<HTMLDivElement>(null);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast((cur) => (cur === msg ? null : cur)), 3400);
  }, []);

  const activeCourse = useMemo(
    () => courses.find((c) => c.id === activeCourseId) || null,
    [courses, activeCourseId],
  );

  // Load courses
  const loadCourses = useCallback(async (selectId?: string) => {
    try {
      const list = await api.listCourses();
      setCourses(list || []);
      if (selectId) {
        setActiveCourseId(selectId);
      } else if (list.length > 0) {
        setActiveCourseId((prev) => (prev && list.some((c) => c.id === prev) ? prev : list[0].id));
      } else {
        setActiveCourseId(null);
      }
    } catch (e: any) {
      showToast(`Failed to load courses: ${e.message}`);
    } finally {
      setCoursesLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    loadCourses();
  }, [loadCourses]);

  // Load course details (schedule + lessons + sources)
  const loadCourseData = useCallback(async (courseId: string) => {
    try {
      const [sched, lesList, srcList] = await Promise.all([
        api.getSchedule(courseId).catch(() => null),
        api.listLessons(courseId).catch(() => []),
        api.listSources(courseId).catch(() => []),
      ]);
      setSchedule(sched);
      setLessons(lesList || []);
      setSources(srcList || []);

      // Auto-upgrade long fixed-slice [MM:SS - MM:SS] videos using subtitles + enqueue background notes/quizzes/cards
      const fixedSliceCount = (lesList || []).filter((l) =>
        /\[\d{1,2}:\d{2}(?::\d{2})?\s*[-–—]\s*\d{1,2}:\d{2}(?::\d{2})?\]\s*$/.test(l.title || ''),
      ).length;
      if (fixedSliceCount >= 2 && !autoPreparedRef.current.has(courseId)) {
        autoPreparedRef.current.add(courseId);
        setPreparingMsg('Splitting marathon video into subtitle-based topics & building notes, quizzes, and flashcards in background...');
        api
          .smartPrepareCourse(courseId, false)
          .then((res) => {
            if ((res.repartitioned_sources || 0) > 0) {
              showToast(`Split video into ${res.new_semantic_clips} subtitle-based topics!`);
              loadCourseData(courseId);
            }
          })
          .catch(() => {})
          .finally(() => setPreparingMsg(null));
      }

      // Auto-select first incomplete scheduled lesson or first lesson
      setActiveLesson((prev) => {
        if (prev && lesList.some((l) => l.id === prev.id)) {
          return lesList.find((l) => l.id === prev.id) || prev;
        }
        const firstPending = sched?.days?.flatMap((d) => d.allocations).find((a) => !a.is_completed);
        if (firstPending) {
          const matched = lesList.find((l) => l.id === firstPending.lesson_id);
          if (matched) {
            setActiveAlloc(firstPending);
            return matched;
          }
        }
        return lesList[0] || null;
      });
    } catch (e: any) {
      showToast(`Load error: ${e.message}`);
    }
  }, [showToast]);

  useEffect(() => {
    if (activeCourseId) {
      loadCourseData(activeCourseId);
    }
  }, [activeCourseId, loadCourseData]);


  // Live SSE Background Job Pill tracker
  useEffect(() => {
    if (!activeCourseId) return;
    let es: EventSource | null = null;
    let cancelled = false;
    api.listJobs(activeCourseId).then((res) => {
      if (cancelled) return;
      const running = (res?.jobs || []).find((j) => j.status === 'queued' || j.status === 'running');
      if (!running) {
        setActiveJob(null);
        return;
      }
      setActiveJob(running);
      es = new EventSource(`/api/jobs/${running.id}/events`);
      es.onmessage = (ev) => {
        try {
          const j = JSON.parse(ev.data) as JobStatus;
          setActiveJob(j);
          if (j.status === 'completed') {
            es?.close();
            setActiveJob(null);
            loadCourseData(activeCourseId);
            showToast(j.message || 'Background study task completed!');
          } else if (j.status === 'failed' || j.status === 'cancelled') {
            es?.close();
            setActiveJob(null);
          }
        } catch {
          // ignore
        }
      };
      es.onerror = () => {
        es?.close();
      };
    }).catch(() => {});
    return () => {
      cancelled = true;
      es?.close();
    };
  }, [activeCourseId, loadCourseData, showToast]);

  // Load pre-made standalone structured notes when activeLesson changes
  useEffect(() => {
    if (!activeLesson?.id) {
      setNotes(null);
      return;
    }
    const ctrl = new AbortController();
    setNotesLoading(true);
    api
      .getLessonNotes(activeLesson.id, ctrl.signal)
      .then((n) => {
        setNotes(n);
        if (n?.lesson_title && activeLesson && n.lesson_title !== activeLesson.title) {
          setActiveLesson((prev) => (prev && prev.id === activeLesson.id ? { ...prev, title: n.lesson_title! } : prev));
          setLessons((prev) => prev.map((l) => (l.id === activeLesson.id ? { ...l, title: n.lesson_title! } : l)));
        }
      })
      .catch(() => {})
      .finally(() => setNotesLoading(false));
    return () => ctrl.abort();
  }, [activeLesson?.id]);

  // Smooth Drag Resizers (Left width, Right width, Center Video/Notes height) with iframe drag shield
  const startDragLeft = (e: React.MouseEvent) => {
    e.preventDefault();
    document.body.classList.add('is-resizing');
    const startX = e.clientX;
    const startW = leftWidth;
    const onMove = (ev: MouseEvent) => {
      const next = Math.min(420, Math.max(210, startW + (ev.clientX - startX)));
      setLeftWidth(next);
      safeStorageSet('lms-left-w', String(next));
    };
    const onUp = () => {
      document.body.classList.remove('is-resizing');
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const startDragRight = (e: React.MouseEvent) => {
    e.preventDefault();
    document.body.classList.add('is-resizing');
    const startX = e.clientX;
    const startW = rightWidth;
    const onMove = (ev: MouseEvent) => {
      const next = Math.min(560, Math.max(290, startW - (ev.clientX - startX)));
      setRightWidth(next);
      safeStorageSet('lms-right-w', String(next));
    };
    const onUp = () => {
      document.body.classList.remove('is-resizing');
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const startDragVideo = (e: React.MouseEvent) => {
    e.preventDefault();
    if (!centerRef.current) return;
    document.body.classList.add('is-resizing');
    const rect = centerRef.current.getBoundingClientRect();
    const onMove = (ev: MouseEvent) => {
      const pct = Math.round(((ev.clientY - rect.top) / rect.height) * 100);
      const clamped = Math.min(62, Math.max(18, pct));
      setVideoHeightPct(clamped);
      setVideoHidden(false);
      safeStorageSet('lms-vid-h', String(clamped));
    };
    const onUp = () => {
      document.body.classList.remove('is-resizing');
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  // Actions
  const handleSeekTimestamp = (sec: number) => {
    if (videoHidden) setVideoHidden(false);
    setSeekRequest({ sec, ts: Date.now() });
  };

  const handleToggleComplete = async (alloc: AllocationItem) => {
    if (!activeCourseId) return;
    try {
      await api.toggleAllocation(activeCourseId, alloc.id);
      await loadCourseData(activeCourseId);
    } catch (e: any) {
      showToast(`Error: ${e.message}`);
    }
  };

  const handleSkipAllocation = async (alloc: AllocationItem) => {
    if (!activeCourseId) return;
    try {
      await api.skipAllocation(activeCourseId, alloc.id);
      setUndoBanner(`Skipped "${alloc.lesson_title}" and repacked remaining days.`);
      await loadCourseData(activeCourseId);
    } catch (e: any) {
      showToast(`Skip error: ${e.message}`);
    }
  };

  const handleUndoSchedule = async () => {
    if (!activeCourseId) return;
    try {
      await api.undoSchedule(activeCourseId);
      setUndoBanner(null);
      showToast('Schedule restored to previous state!');
      await loadCourseData(activeCourseId);
    } catch (e: any) {
      showToast(`Undo error: ${e.message}`);
    }
  };

  const handleQuickUpdateSchedule = async (patch: Partial<Course>) => {
    if (!activeCourseId) return;
    try {
      await api.updateCourse(activeCourseId, patch);
      await api.replanSchedule(activeCourseId, 'normal').catch(() => {});
      await loadCourses(activeCourseId);
      await loadCourseData(activeCourseId);
      setUndoBanner('Schedule repacked with updated study preferences.');
    } catch (e: any) {
      showToast(`Update error: ${e.message}`);
    }
  };

  const handleReplan = async (mode: 'normal' | 'compress' = 'normal') => {
    if (!activeCourseId) return;
    try {
      await api.replanSchedule(activeCourseId, mode);
      await loadCourseData(activeCourseId);
      setUndoBanner(
        mode === 'compress'
          ? 'Compressed schedule by dropping deep-dive units.'
          : 'Schedule repacked deterministically.',
      );
    } catch (e: any) {
      showToast(`Replan error: ${e.message}`);
    }
  };

  const handleClusterTopics = async () => {
    if (!activeCourseId) return;
    try {
      const res = await api.clusterTopics(activeCourseId);
      showToast(`Grouped ${res.lessons_updated} videos into ${res.topics_created} structured topics!`);
      await loadCourseData(activeCourseId);
    } catch (e: any) {
      showToast(`Topic grouping error: ${e.message}`);
    }
  };

  const handleRegenerateNotes = async () => {
    if (!activeLesson) return;
    setNotesLoading(true);
    try {
      const updated = await api.regenerateLessonNotes(activeLesson.id);
      setNotes(updated);
      showToast('Structured notes regenerated!');
    } catch (e: any) {
      showToast(`Notes error: ${e.message}`);
    } finally {
      setNotesLoading(false);
    }
  };

  const handleSavePersonalNotes = async (text: string) => {
    if (!activeLesson) return;
    await api.savePersonalNotes(activeLesson.id, text);
    setNotes((prev) => (prev ? { ...prev, personal_notes: text } : prev));
  };

  const handleAppendToPersonalNotes = async (snippet: string) => {
    if (!activeLesson) return;
    const updated = `${notes?.personal_notes || ''}${snippet}`;
    await handleSavePersonalNotes(updated);
  };

  const allAllocs = useMemo(() => schedule?.days?.flatMap((d) => d.allocations) || [], [schedule]);
  const computedPct = allAllocs.length > 0
    ? Math.round((allAllocs.filter((a) => a.is_completed).length / allAllocs.length) * 100)
    : 0;
  const progressPct = schedule?.progress_pct ? Math.round(schedule.progress_pct) : computedPct;
  const remainingMin = schedule?.remaining_effective_minutes
    ?? Math.round(allAllocs.filter((a) => !a.is_completed).reduce((s, a) => s + (a.effective_minutes || 0), 0));

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[var(--bg-canvas)] text-[var(--fg-primary)]">
      {/* TOP COMMAND BAR (matches all 4 mockups + Live Schedule Telemetry!) */}
      <header className="no-print flex h-12 shrink-0 items-center justify-between gap-3 border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)] px-3">
        {/* Left: Collapse Rail + Course Selector + Progress + Live Telemetry */}
        <div className="flex min-w-0 items-center gap-2.5">
          <button
            type="button"
            onClick={() => setLeftCollapsed((c) => !c)}
            title="Toggle Lesson Syllabus Rail"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
          >
            <Menu className="h-4 w-4" />
          </button>

          <select
            value={activeCourseId || ''}
            onChange={(e) => setActiveCourseId(e.target.value)}
            className="max-w-[190px] truncate rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2.5 py-1.5 text-xs font-bold text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
          >
            {courses.length === 0 ? (
              <option value="">No courses yet</option>
            ) : (
              courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))
            )}
          </select>

          {activeCourse && (
            <div className="hidden items-center gap-3 md:flex">
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-24 overflow-hidden rounded-full bg-[var(--border-subtle)]">
                  <div
                    className="h-full rounded-full bg-[var(--accent)] transition-all"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <span className="whitespace-nowrap text-xs font-semibold text-[var(--fg-secondary)]">
                  {progressPct}% Completed
                </span>
              </div>

              {/* Live Schedule Telemetry */}
              <div
                onClick={() => setModal('edit-course')}
                title="Click to edit Exam Date, Pace & Rest Days"
                className="hidden cursor-pointer items-center gap-2.5 whitespace-nowrap rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2.5 py-1 text-xs text-[var(--fg-secondary)] hover:border-[var(--accent)] lg:flex"
              >
                <span>
                  Study Left: <strong className="text-[var(--fg-primary)]">{formatHoursMin(remainingMin)}</strong>
                </span>
                {schedule?.projected_finish_date && (
                  <span>
                    • Finish: <strong className="text-[var(--success)]">{schedule.projected_finish_date}</strong>
                  </span>
                )}
                {activeCourse.target_date && (
                  <span>
                    • Exam: <strong className="text-[var(--accent)]">{activeCourse.target_date}</strong>
                  </span>
                )}
                <span className="hidden xl:inline">
                  • Pace: <strong className="text-[var(--fg-primary)]">{activeCourse.minutes_per_day || 60}m@{activeCourse.playback_speed || 1}x</strong>
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Right: + New Goal, Cram Sheet, Mock Exam, Edit Course, Settings, Toggle Studio, Theme */}
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={() => setModal('new-course')}
            className="inline-flex items-center gap-1 rounded-lg bg-[var(--accent)] px-2.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:opacity-90"
          >
            <Plus className="h-3.5 w-3.5" /> New Goal
          </button>

          {activeCourse && (
            <>
              <button
                type="button"
                onClick={() => setModal('cram')}
                className="inline-flex items-center gap-1 rounded-lg border border-amber-500/35 bg-amber-500/10 px-2.5 py-1.5 text-xs font-semibold text-amber-700 dark:text-amber-300 hover:bg-amber-500/20"
              >
                <FileSpreadsheet className="h-3.5 w-3.5" /> Cram Sheet
              </button>
              <button
                type="button"
                onClick={() => setModal('mock_exam')}
                className="hidden sm:inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2.5 py-1.5 text-xs font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
              >
                <GraduationCap className="h-3.5 w-3.5" /> Mock Exam
              </button>
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setPlanMenuOpen((o) => !o)}
                  className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2.5 py-1.5 text-xs font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
                >
                  Plan <ChevronDown className="h-3.5 w-3.5 text-[var(--fg-muted)]" />
                </button>
                {planMenuOpen && (
                  <div
                    className="absolute right-0 top-10 z-40 w-60 rounded-xl border border-[var(--border-strong)] bg-[var(--bg-card)] p-1.5 shadow-xl text-xs"
                    onMouseLeave={() => setPlanMenuOpen(false)}
                  >
                    <button
                      type="button"
                      onClick={() => { setPlanMenuOpen(false); setModal('edit-course'); }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-[var(--bg-hover)]"
                    >
                      <Pencil className="h-3.5 w-3.5 text-[var(--accent)]" /> Edit Course & Timings
                    </button>
                    <button
                      type="button"
                      onClick={() => { setPlanMenuOpen(false); setModal('diagnostic'); }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-[var(--bg-hover)]"
                    >
                      <Zap className="h-3.5 w-3.5 text-[var(--warning)]" /> 2-Min Diagnostic Pre-Test
                    </button>
                    <button
                      type="button"
                      onClick={() => { setPlanMenuOpen(false); setModal('syllabus'); }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-[var(--bg-hover)]"
                    >
                      <Layers className="h-3.5 w-3.5 text-[var(--accent)]" /> University Syllabus Matcher
                    </button>
                    <button
                      type="button"
                      onClick={() => { setPlanMenuOpen(false); setModal('curriculum'); }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-[var(--bg-hover)]"
                    >
                      <BookOpen className="h-3.5 w-3.5 text-[var(--fg-secondary)]" /> Curriculum Inspector
                    </button>
                    <div className="my-1 h-px bg-[var(--border-subtle)]" />
                    <button
                      type="button"
                      onClick={async () => {
                        setPlanMenuOpen(false);
                        setPreparingMsg('Splitting videos into subtitle-based topics & preparing study bundles...');
                        try {
                          const res = await api.smartPrepareCourse(activeCourse.id, true);
                          showToast(`Prepared ${res.new_semantic_clips || res.topics_clustered} topics — notes & quizzes building in background`);
                          await loadCourseData(activeCourse.id);
                        } catch (e: any) {
                          showToast(`Smart Prepare error: ${e.message}`);
                        } finally {
                          setPreparingMsg(null);
                        }
                      }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-[var(--bg-hover)]"
                    >
                      <Sparkles className="h-3.5 w-3.5 text-[var(--accent)]" /> Smart Topic Split (Subtitles)
                    </button>
                    <button
                      type="button"
                      onClick={() => { setPlanMenuOpen(false); handleReplan('normal'); }}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left hover:bg-[var(--bg-hover)]"
                    >
                      <RefreshCw className="h-3.5 w-3.5 text-[var(--success)]" /> Instant Repack Schedule
                    </button>
                  </div>
                )}
              </div>
            </>
          )}

          {activeJob && (
            <div className="hidden lg:inline-flex items-center gap-1.5 rounded-full border border-[var(--accent)]/40 bg-[var(--accent-soft)] px-2.5 py-1 text-xs font-semibold text-[var(--accent-text)]">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span className="max-w-[140px] truncate">{activeJob.message || activeJob.job_type}</span>
              <span>{activeJob.progress_pct ?? 0}%</span>
              <button
                type="button"
                onClick={async () => {
                  await api.cancelJob(activeJob.id).catch(() => {});
                  setActiveJob(null);
                  showToast('Background job cancelled');
                }}
                title="Cancel background job"
                className="ml-0.5 rounded px-1 hover:bg-[var(--bg-card)]"
              >
                ×
              </button>
            </div>
          )}

          <button
            type="button"
            onClick={() => {
              setFocusReader((prev) => {
                const next = !prev;
                setLeftCollapsed(next);
                setVideoHidden(next);
                return next;
              });
            }}
            title="Toggle Focus Reader Mode (F)"
            className={`hidden md:inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition ${
              focusReader
                ? 'border-[var(--accent)] bg-[var(--accent)] text-white'
                : 'border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]'
            }`}
          >
            Focus
          </button>

          <button
            type="button"
            onClick={() => setModal('settings')}
            title="Settings, AI Keys & Data Portability"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
          >
            <Settings className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={() => setRightOpen((o) => !o)}
            title={rightOpen ? 'Collapse Studio Panel' : 'Open Studio Panel'}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
          >
            {rightOpen ? <PanelRightClose className="h-3.5 w-3.5" /> : <PanelRightOpen className="h-3.5 w-3.5" />}
          </button>

          <button
            type="button"
            onClick={() => setDark((d) => !d)}
            title="Toggle Warm Paper Light / Deep Graphite Dark"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
          >
            {dark ? <Sun className="h-3.5 w-3.5 text-amber-400" /> : <Moon className="h-3.5 w-3.5 text-[var(--accent)]" />}
          </button>
        </div>
      </header>

      {/* UNDO REPLAN BANNER */}
      {undoBanner && (
        <div className="no-print flex items-center justify-between border-b border-[var(--accent)]/30 bg-[var(--accent-soft)] px-4 py-1.5 text-xs text-[var(--accent-text)]">
          <span className="font-medium">{undoBanner}</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleUndoSchedule}
              className="inline-flex items-center gap-1 rounded bg-[var(--accent)] px-2.5 py-0.5 font-semibold text-white"
            >
              <Undo2 className="h-3 w-3" /> Undo Change
            </button>
            <button type="button" onClick={() => setUndoBanner(null)} className="px-1 font-bold">
              ✕
            </button>
          </div>
        </div>
      )}

      {preparingMsg && (
        <div className="no-print flex items-center gap-2 border-b border-[var(--accent)]/25 bg-[var(--accent-soft)] px-4 py-1.5 text-xs font-medium text-[var(--accent-text)]">
          <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
          <span>{preparingMsg}</span>
        </div>
      )}

      {/* BEHIND SCHEDULE WARNING BANNER */}
      {schedule?.is_behind_schedule && (
        <div className="no-print flex flex-wrap items-center justify-between gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-xs text-amber-800 dark:text-amber-200">
          <span className="inline-flex items-center gap-1.5 font-medium">
            <AlertTriangle className="h-3.5 w-3.5" />
            {(schedule as any).pace_notice || schedule.behind_message || 'Projected finish date encroaches on your exam revision buffer.'}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handleReplan('compress')}
              className="rounded bg-amber-600 px-2.5 py-0.5 font-semibold text-white hover:bg-amber-700"
            >
              Compress (Drop Deep-Dives)
            </button>
            <button
              type="button"
              onClick={() => setModal('edit-course')}
              className="rounded border border-amber-600/40 px-2.5 py-0.5 font-semibold"
            >
              Adjust Timings
            </button>
          </div>
        </div>
      )}

      {/* MAIN 3-ZONE RESIZABLE WORKSPACE */}
      {coursesLoading ? (<div className="flex flex-1 items-center justify-center text-sm text-[var(--fg-muted)]">Loading your study workspace...</div>) : !activeCourse ? (
        <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
          <h1 className="text-xl font-bold text-[var(--fg-primary)]">Welcome to your Calm Exam & Study Workspace</h1>
          <p className="mt-2 max-w-md text-sm text-[var(--fg-secondary)]">
            Create your first study goal with any YouTube playlist, marathon lecture, PDF, or syllabus to generate structured topic notes, instant day-wise schedules, FSRS flashcards, and printable Cram Sheets.
          </p>
          <button
            type="button"
            onClick={() => setModal('new-course')}
            className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[var(--accent)] px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90"
          >
            <Plus className="h-4 w-4" /> Create Your First Study Goal
          </button>
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* ZONE 1: LEFT SYLLABUS RAIL */}
          <LeftSyllabusRail
            course={activeCourse}
            schedule={schedule}
            lessons={lessons}
            sources={sources}
            activeLessonId={activeLesson?.id || null}
            collapsed={leftCollapsed}
            width={leftWidth}
            onToggleCollapse={() => setLeftCollapsed((c) => !c)}
            onSelectLesson={(les, alloc) => {
              setActiveLesson(les);
              setActiveAlloc(alloc || null);
            }}
            onToggleComplete={handleToggleComplete}
            onSkipAllocation={handleSkipAllocation}
            onOpenAddSource={() => setModal('add-source')}
            onDeleteSource={async (sid) => {
              await api.deleteSource(activeCourse.id, sid);
              showToast('Source removed');
              loadCourseData(activeCourse.id);
            }}
            onOpenSettings={() => setModal('settings')}
          />

          {/* VERTICAL DRAG SLIDER (Left <-> Center) */}
          {!leftCollapsed && <div className="no-print resizer-v" onMouseDown={startDragLeft} onDoubleClick={() => { setLeftWidth(280); safeStorageSet('lms-left-w', '280'); }} title="Drag to resize, double-click to reset" />}

          {/* ZONE 2: CENTER STUDY STAGE (Top Video + Draggable Horizontal Divider + Bottom Pre-Made Notes!) */}
          <main ref={centerRef} className="flex min-w-0 flex-1 flex-col overflow-hidden bg-[var(--bg-canvas)]">
            {/* Top Video Pane */}
            {!videoHidden && (
              <div
                style={{ height: `${videoHeightPct}%` }}
                className="no-print min-h-[180px] max-h-[55vh] shrink-0 bg-[var(--bg-sidebar)]/50 p-2.5"
              >
                <div className="mx-auto h-full max-w-4xl">
                  <YouTubePlayer
                    videoId={activeLesson?.video_id}
                    videoUrl={activeLesson?.video_url}
                    startSec={activeAlloc?.allocated_start_sec ?? activeLesson?.start_sec ?? 0}
                    endSec={activeAlloc?.allocated_end_sec ?? activeLesson?.end_sec}
                    playbackSpeed={activeCourse.playback_speed || 1.25}
                    seekRequest={seekRequest}
                    lessonTitle={activeLesson?.title}
                    onTimeUpdate={setActiveVideoSec}
                  />
                </div>
              </div>
            )}

            {/* HORIZONTAL DRAG SLIDER + Hide Video / Snap Pills (matches image_23084c.jpg!) */}
            <div
              className="no-print resizer-h group"
              onMouseDown={startDragVideo}
              onDoubleClick={() => {
                setVideoHidden(false);
                setVideoHeightPct(38);
                safeStorageSet('lms-vid-h', '38');
              }}
              title="Drag vertically to resize Video vs Notes (double-click to reset)"
            >
              <div
                className="flex items-center gap-1 rounded-full border border-[var(--border-strong)] bg-[var(--bg-card)] px-2 py-0.5 text-xs font-semibold text-[var(--fg-secondary)] shadow-sm"
                onMouseDown={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={() => {
                    setVideoHidden(false);
                    setVideoHeightPct(25);
                    safeStorageSet('lms-vid-h', '25');
                  }}
                  className="rounded px-1.5 py-0.5 hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
                >
                  25%
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setVideoHidden(false);
                    setVideoHeightPct(38);
                    safeStorageSet('lms-vid-h', '38');
                  }}
                  className="rounded px-1.5 py-0.5 hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
                >
                  38%
                </button>
                <span className="mx-0.5 text-[var(--border-strong)]">|</span>
                {[1, 1.25, 1.5, 2].map((spd) => (
                  <button
                    key={spd}
                    type="button"
                    onClick={() => handleQuickUpdateSchedule({ playback_speed: spd })}
                    className={`rounded px-1.5 py-0.5 text-xs ${
                      (activeCourse.playback_speed || 1.25) === spd
                        ? 'bg-[var(--accent-soft)] font-bold text-[var(--accent-text)]'
                        : 'hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]'
                    }`}
                  >
                    {spd}x
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setVideoHidden((h) => !h)}
                  className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[var(--accent)] hover:bg-[var(--bg-hover)]"
                >
                  {videoHidden ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
                  {videoHidden ? 'Show Video' : 'Hide Video'}
                </button>
              </div>
            </div>

            {/* Bottom Pre-Made Standalone Structured Notes Pane */}
            <div className="flex-1 overflow-y-auto px-6 py-5 sm:px-10">
              <div className="mx-auto max-w-3xl">
                {activeLesson ? (
                  <>
                    {/* Lesson Notes Toolbar */}
                    <div className="no-print mb-5 flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] pb-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={async () => {
                              const next = (activeLesson.priority === 'deep-dive' || activeLesson.priority === 'deep_dive') ? 'core' : 'deep-dive';
                              await api.updateLesson(activeCourse.id, activeLesson.id, { priority: next });
                              showToast(`Priority set to ${next === 'core' ? 'Core' : 'Deep-Dive'}`);
                              loadCourseData(activeCourse.id);
                            }}
                            title="Click to toggle Core / Deep-Dive priority"
                            className="rounded-full border border-[var(--border-subtle)] bg-[var(--accent-soft)] px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-[var(--accent-text)]"
                          >
                            {(activeLesson.priority === 'deep-dive' || activeLesson.priority === 'deep_dive') ? 'Deep-Dive' : 'Core'}
                          </button>
                          {activeLesson.chapter_title && activeLesson.chapter_title.trim().toLowerCase() !== activeLesson.title.trim().toLowerCase() && (
                            <span className="truncate text-xs font-semibold uppercase tracking-wider text-[var(--fg-muted)]">
                              {activeLesson.chapter_title} ›
                            </span>
                          )}
                          <span className="text-xs font-medium text-[var(--fg-muted)]">
                            Clip {Math.max(1, lessons.findIndex((l) => l.id === activeLesson.id) + 1)} of {lessons.length}
                          </span>
                          {notes?.generation_mode && (
                            <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                              notes.generation_mode === 'llm'
                                ? 'bg-[var(--success)]/15 text-[var(--success)]'
                                : 'bg-[var(--bg-elevated)] text-[var(--fg-secondary)] border border-[var(--border-subtle)]'
                            }`}>
                              {notes.generation_mode === 'llm' ? 'AI Notes' : 'Transcript Outline'}
                            </span>
                          )}
                        </div>
                        <div className="mt-1 flex items-center gap-1.5">
                          <h1
                            onClick={() => setModal('edit-lesson')}
                            className="cursor-pointer truncate text-lg font-bold text-[var(--fg-primary)] hover:text-[var(--accent)]"
                            title="Click to edit lesson details"
                          >
                            {activeLesson.title}
                          </h1>
                          <button
                            type="button"
                            onClick={() => setModal('edit-lesson')}
                            title="Edit Lesson Details"
                            className="rounded p-1 text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 text-xs">
                        {activeAlloc && (
                          <button
                            type="button"
                            onClick={() => handleToggleComplete(activeAlloc)}
                            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 font-semibold transition ${
                              activeAlloc.is_completed
                                ? 'bg-emerald-600 text-white'
                                : 'bg-[var(--accent)] text-white hover:opacity-90'
                            }`}
                          >
                            <CheckCircle2 className="h-3.5 w-3.5" /> {activeAlloc.is_completed ? 'Completed' : 'Mark Complete'}
                          </button>
                        )}
                        <div className="relative">
                          <button
                            type="button"
                            onClick={() => setLessonMenuOpen((o) => !o)}
                            title="More lesson actions"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </button>
                          {lessonMenuOpen && (
                            <div
                              className="absolute right-0 top-9 z-40 w-52 rounded-xl border border-[var(--border-strong)] bg-[var(--bg-card)] p-1.5 shadow-xl text-xs"
                              onMouseLeave={() => setLessonMenuOpen(false)}
                            >
                              {activeAlloc && !activeAlloc.is_completed && (
                                <button
                                  type="button"
                                  onClick={() => { setLessonMenuOpen(false); handleSkipAllocation(activeAlloc); }}
                                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left hover:bg-[var(--bg-hover)]"
                                >
                                  <SkipForward className="h-3.5 w-3.5" /> Skip to Later Day
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={async () => {
                                  setLessonMenuOpen(false);
                                  showToast('Fetching subtitles / transcribing...');
                                  try {
                                    const r = await api.transcribeLesson(activeLesson.id);
                                    showToast(`Transcribed (${r.chunk_count} chunks)`);
                                    await handleRegenerateNotes();
                                  } catch (e: any) {
                                    showToast(`Transcribe failed: ${e.message}`);
                                  }
                                }}
                                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left hover:bg-[var(--bg-hover)]"
                              >
                                <FileAudio className="h-3.5 w-3.5" /> Re-Transcribe Captions
                              </button>
                              <button
                                type="button"
                                onClick={async () => {
                                  setLessonMenuOpen(false);
                                  showToast('Capturing slide keyframes...');
                                  try {
                                    const frames = await api.captureScreenshots(activeLesson.id);
                                    showToast(`Captured ${frames.length} slide keyframes`);
                                    await handleRegenerateNotes();
                                  } catch (e: any) {
                                    showToast(`Slide capture failed: ${e.message}`);
                                  }
                                }}
                                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left hover:bg-[var(--bg-hover)]"
                              >
                                <Camera className="h-3.5 w-3.5" /> Capture Slide Keyframes
                              </button>
                              <button
                                type="button"
                                onClick={() => { setLessonMenuOpen(false); handleRegenerateNotes(); }}
                                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left hover:bg-[var(--bg-hover)]"
                              >
                                <RefreshCw className="h-3.5 w-3.5" /> Regenerate Notes
                              </button>
                              <button
                                type="button"
                                onClick={async () => {
                                  setLessonMenuOpen(false);
                                  if (notes?.content_markdown) {
                                    await handleAppendToPersonalNotes(`\n\n${notes.content_markdown}`);
                                    setStudioTab('notes');
                                    setRightOpen(true);
                                    showToast('Copied to My Notes');
                                  }
                                }}
                                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left hover:bg-[var(--bg-hover)]"
                              >
                                <Copy className="h-3.5 w-3.5" /> Copy to My Notes
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setLessonMenuOpen(false);
                                  if (!notes?.content_markdown) return;
                                  const blob = new Blob([notes.content_markdown], { type: 'text/markdown' });
                                  const url = URL.createObjectURL(blob);
                                  const a = document.createElement('a');
                                  a.href = url;
                                  a.download = `${activeLesson.title.replace(/[^a-z0-9]+/gi, '_')}.md`;
                                  a.click();
                                  URL.revokeObjectURL(url);
                                }}
                                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left hover:bg-[var(--bg-hover)]"
                              >
                                <Download className="h-3.5 w-3.5" /> Download Notes (.md)
                              </button>
                              <button
                                type="button"
                                onClick={() => { setLessonMenuOpen(false); window.print(); }}
                                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left hover:bg-[var(--bg-hover)]"
                              >
                                <Printer className="h-3.5 w-3.5" /> Print Notes
                              </button>
                            </div>
                          )}
                        </div>                      </div>
                    </div>

                    {/* Structured Notes Content with Highlight-to-Explain */}
                    {notesLoading ? (
                      <div className="flex h-44 items-center justify-center gap-2 text-xs text-[var(--fg-secondary)]">
                        <Loader2 className="h-5 w-5 animate-spin text-[var(--accent)]" />
                        Synthesizing standalone structured tutorial notes...
                      </div>
                    ) : (
                      <MarkdownView
                        markdown={
                          (notes?.content_markdown || '').replace(/^#\s+[^\n]+\n+/, '') ||
                          `Synthesizing standalone structured notes from this lecture's subtitles...`
                        }
                        onSeekTimestamp={handleSeekTimestamp}
                        onExplainSelection={(selText) => {
                          setRightOpen(true);
                          setExternalAskPrompt({ text: selText, ts: Date.now() });
                        }}
                        onSaveSelectionToNotes={async (selText) => {
                          await handleAppendToPersonalNotes(`\n- ${selText}\n`);
                          showToast('Saved highlight to My Notes');
                        }}
                      />
                    )}
                  </>
                ) : (
                  <div className="py-16 text-center text-sm text-[var(--fg-secondary)]">
                    Select a lesson from the left syllabus rail to start studying.
                  </div>
                )}
              </div>
            </div>
          </main>

          {/* VERTICAL DRAG SLIDER (Center <-> Right Studio) */}
          {rightOpen && <div className="no-print resizer-v" onMouseDown={startDragRight} onDoubleClick={() => { setRightWidth(370); safeStorageSet('lms-right-w', '370'); }} title="Drag to resize, double-click to reset" />}

          {/* ZONE 3: RIGHT FULL-HEIGHT TABBED STUDIO PANEL */}
          {rightOpen && (
            <RightStudioPanel
              courseId={activeCourse.id}
              activeLesson={activeLesson}
              activeTab={studioTab}
              onTabChange={setStudioTab}
              width={studioExpanded ? Math.round(window.innerWidth * 0.5) : rightWidth}
              personalNotes={notes?.personal_notes || ''}
              onSavePersonalNotes={handleSavePersonalNotes}
              onAppendToPersonalNotes={handleAppendToPersonalNotes}
              onSeekTimestamp={handleSeekTimestamp}
              externalAskPrompt={externalAskPrompt}
              onScheduleChanged={() => loadCourseData(activeCourse.id)}
              onToast={showToast}
            />
          )}
        </div>
      )}

      {/* MODALS */}
      {modal === 'new-course' && (
        <NewCourseModal
          onClose={() => setModal(null)}
          onCreated={(cid) => loadCourses(cid)}
          onToast={showToast}
        />
      )}
      {modal === 'edit-course' && activeCourse && (
        <EditCourseModal
          course={activeCourse}
          onClose={() => setModal(null)}
          onSaved={() => {
            loadCourses(activeCourse.id);
            loadCourseData(activeCourse.id);
          }}
          onDeleted={() => loadCourses()}
          onToast={showToast}
        />
      )}
      {modal === 'add-source' && activeCourse && (
        <AddSourceModal
          courseId={activeCourse.id}
          onClose={() => setModal(null)}
          onAdded={() => loadCourseData(activeCourse.id)}
          onToast={showToast}
        />
      )}
      {modal === 'cram' && activeCourse && (
        <CramSheetModal
          courseId={activeCourse.id}
          onClose={() => setModal(null)}
          onSeekTimestamp={handleSeekTimestamp}
          onToast={showToast}
        />
      )}
      {(modal === 'diagnostic' || modal === 'mock_exam') && activeCourse && (
        <ExamModal
          courseId={activeCourse.id}
          mode={modal}
          onClose={() => setModal(null)}
          onSeekTimestamp={handleSeekTimestamp}
          onScheduleChanged={() => loadCourseData(activeCourse.id)}
          onToast={showToast}
        />
      )}
      {modal === 'syllabus' && activeCourse && (
        <SyllabusModal
          courseId={activeCourse.id}
          onClose={() => setModal(null)}
          onApplied={() => loadCourseData(activeCourse.id)}
          onToast={showToast}
        />
      )}
      {modal === 'settings' && (
        <SettingsModal
          courseId={activeCourseId}
          onClose={() => setModal(null)}
          onToast={showToast}
        />
      )}


      {modal === 'curriculum' && activeCourse && (
        <CurriculumDrawerModal
          courseId={activeCourse.id}
          lessons={lessons}
          onClose={() => setModal(null)}
          onUpdated={() => loadCourseData(activeCourse.id)}
          onOpenSyllabus={() => setModal('syllabus')}
          onToast={showToast}
        />
      )}
      {modal === 'edit-lesson' && activeCourse && activeLesson && (
        <EditLessonModal
          courseId={activeCourse.id}
          lesson={activeLesson}
          onClose={() => setModal(null)}
          onSaved={() => loadCourseData(activeCourse.id)}
          onToast={showToast}
        />
      )}
      {modal === 'cmdk' && (
        <CommandPaletteModal
          lessons={lessons}
          onClose={() => setModal(null)}
          onSelectLesson={(les) => {
            setActiveLesson(les);
            const matchedAlloc = schedule?.days?.flatMap((d) => d.allocations).find((a) => a.lesson_id === les.id) || null;
            setActiveAlloc(matchedAlloc);
          }}
          onAction={(act) => {
            if (act === 'theme') {
              setDark((d) => !d);
              setModal(null);
            } else if (act === 'cluster') {
              setModal(null);
              handleClusterTopics();
            } else {
              setModal(act as any);
            }
          }}
        />
      )}

      {/* SUBTLE TOAST */}
      {toast && (
        <div className="no-print fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-xl border border-[var(--border-strong)] bg-[var(--bg-card)] px-4 py-2 text-xs font-semibold text-[var(--fg-primary)] shadow-xl">
          {toast}
        </div>
      )}
    </div>
  );
};

export default App;
