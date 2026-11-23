import React, { useEffect, useMemo, useState } from 'react';
import {
  BookOpen,
  Calendar,
  FileSpreadsheet,
  FolderOpen,
  GraduationCap,
  Moon,
  Search,
  Settings,
  Sun,
} from 'lucide-react';
import { Allocation, api, Course, ScheduleResponse } from './api/client';
import { CommandItem, CommandPalette } from './components/CommandPalette';
import { StudyView } from './views/StudyView';
import { ExamHubView } from './views/ExamHubView';
import { ScheduleView, SourcesView } from './views/SourcesAndScheduleView';
import { CramSheetView, SettingsView } from './views/CramAndSettingsView';

type NavMode = 'study' | 'schedule' | 'sources' | 'exams' | 'cram' | 'settings';

export const App: React.FC = () => {
  const [dark, setDark] = useState(() => localStorage.getItem('study-theme') === 'dark');
  const [mode, setMode] = useState<NavMode>('study');
  const [courses, setCourses] = useState<Course[]>([]);
  const [activeCourseId, setActiveCourseId] = useState<string>('');
  const [schedule, setSchedule] = useState<ScheduleResponse | null>(null);
  const [activeAlloc, setActiveAlloc] = useState<Allocation | null>(null);
  const [cmdOpen, setCmdOpen] = useState(false);
  const [toast, setToast] = useState<{ msg: string; withUndo?: boolean } | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('study-theme', dark ? 'dark' : 'light');
  }, [dark]);

  const showToast = (msg: string, withUndo = false) => {
    setToast({ msg, withUndo });
    window.setTimeout(() => setToast((cur) => (cur?.msg === msg ? null : cur)), 4500);
  };

  // Load courses + honor initial URL hash
  useEffect(() => {
    api
      .listCourses()
      .then((list) => {
        setCourses(list);
        const hashMatch = window.location.hash.match(/^#\/course\/([^/]+)/);
        const hashCid = hashMatch ? decodeURIComponent(hashMatch[1]) : null;
        if (hashCid && list.some((c) => c.id === hashCid)) {
          setActiveCourseId(hashCid);
        } else if (list.length > 0) {
          setActiveCourseId(list[0].id);
        } else {
          setMode('schedule');
        }
      })
      .catch(() => setCourses([]));
  }, []);

  // Load schedule whenever active course changes (clean reset + AbortController)
  const reloadSchedule = (cid: string, signal?: AbortSignal) => {
    if (!cid) return;
    api
      .getSchedule(cid, signal)
      .then((sched) => {
        setSchedule(sched);
        const allAllocs = sched.days.flatMap((d) => d.allocations);
        const hashLesson = window.location.hash.match(/\/lesson\/([^/]+)/)?.[1];
        const matched =
          (hashLesson && allAllocs.find((a) => a.lesson_id === decodeURIComponent(hashLesson))) ||
          allAllocs.find((a) => !a.is_completed && !a.is_skipped) ||
          allAllocs[0] ||
          null;
        setActiveAlloc(matched);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setSchedule(null);
      });
  };

  useEffect(() => {
    if (!activeCourseId) return;
    const ac = new AbortController();
    setActiveAlloc(null);
    setSchedule(null);
    reloadSchedule(activeCourseId, ac.signal);
    return () => ac.abort();
  }, [activeCourseId]);

  // Global Cmd+K / Ctrl+K shortcut
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCmdOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const activeCourse = courses.find((c) => c.id === activeCourseId) || null;

  const selectAlloc = (a: Allocation) => {
    setActiveAlloc(a);
    setMode('study');
    window.history.replaceState(null, '', `#/course/${encodeURIComponent(a.course_id)}/lesson/${encodeURIComponent(a.lesson_id)}`);
  };

  const commandItems: CommandItem[] = useMemo(() => {
    const items: CommandItem[] = [
      { id: 'act-study', label: 'Go to Study Workspace', category: 'View', onSelect: () => setMode('study') },
      { id: 'act-sched', label: 'Go to Day-Wise Schedule & New Course', category: 'View', onSelect: () => setMode('schedule') },
      { id: 'act-src', label: 'Go to Subject Notebook Sources', category: 'View', onSelect: () => setMode('sources') },
      { id: 'act-exam', label: 'Go to Exam Prep Hub (Flashcards / Mock)', category: 'View', onSelect: () => setMode('exams') },
      { id: 'act-cram', label: 'Open Last-Night Cram Sheet', category: 'View', onSelect: () => setMode('cram') },
      { id: 'act-set', label: 'Open Settings & Backups', category: 'View', onSelect: () => setMode('settings') },
      { id: 'act-theme', label: 'Toggle Light / Dark Theme', category: 'Action', onSelect: () => setDark((d) => !d) },
    ];
    courses.forEach((c) => {
      items.push({
        id: `course-${c.id}`,
        label: `Switch Course: ${c.title}`,
        category: 'Course',
        onSelect: () => setActiveCourseId(c.id),
      });
    });
    (schedule?.days || []).flatMap((d) => d.allocations).slice(0, 50).forEach((a) => {
      items.push({
        id: `alloc-${a.id}`,
        label: a.lesson_title,
        category: 'Lesson',
        onSelect: () => selectAlloc(a),
      });
    });
    return items;
  }, [courses, schedule]);

  const navItems: Array<{ id: NavMode; label: string; icon: React.ElementType }> = [
    { id: 'study', label: 'Study', icon: BookOpen },
    { id: 'schedule', label: 'Schedule', icon: Calendar },
    { id: 'sources', label: 'Sources', icon: FolderOpen },
    { id: 'exams', label: 'Exams', icon: GraduationCap },
    { id: 'cram', label: 'Cram', icon: FileSpreadsheet },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <div className="h-full flex flex-col bg-canvas text-fg-primary">
      {/* Calm 48px Top Bar */}
      <header className="h-12 shrink-0 border-b border-border-def bg-surface px-3 flex items-center justify-between gap-3 no-print">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="font-bold text-sm tracking-tight text-accent-text shrink-0">StudyLMS</span>
          <select
            aria-label="Select course"
            value={activeCourseId}
            onChange={(e) => setActiveCourseId(e.target.value)}
            className="max-w-[220px] sm:max-w-xs truncate text-xs font-medium px-2.5 py-1.5 rounded-lg bg-subtle border border-border-def text-fg-primary"
          >
            {courses.length === 0 && <option value="">No courses yet</option>}
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCmdOpen(true)}
            className="hidden sm:inline-flex items-center gap-2 px-2.5 py-1 rounded-lg bg-subtle border border-border-def text-xs text-fg-secondary hover:text-fg-primary"
          >
            <Search className="w-3.5 h-3.5" /> Search <kbd className="font-mono text-[11px]">⌘K</kbd>
          </button>
          <button
            type="button"
            aria-label="Toggle theme"
            onClick={() => setDark((d) => !d)}
            className="p-1.5 rounded-lg bg-subtle border border-border-def text-fg-primary hover:bg-border-def/40"
          >
            {dark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>
      </header>

      {/* Main Shell: Left Rail (desktop) + Active View */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        <nav
          aria-label="Primary navigation"
          className="hidden md:flex w-16 shrink-0 flex-col items-center py-3 gap-2 border-r border-border-def bg-surface no-print"
        >
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = mode === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setMode(item.id)}
                className={`w-12 py-2 rounded-xl flex flex-col items-center gap-1 text-[11px] font-medium transition-colors ${
                  active ? 'bg-accent text-white' : 'text-fg-secondary hover:bg-subtle hover:text-fg-primary'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <main className="flex-1 min-w-0 min-h-0 overflow-hidden">
          {mode === 'settings' ? (
            <SettingsView onToast={showToast} />
          ) : !activeCourse ? (
            <ScheduleView
              course={{
                id: '',
                title: 'Get Started',
                goal_query: '',
                target_date: new Date().toISOString().slice(0, 10),
                minutes_per_day: 90,
                playback_speed: 1.25,
                rest_days: ['Sunday'],
                revision_buffer_days: 2,
              }}
              schedule={null}
              onScheduleChanged={() => {}}
              onCourseCreated={(c) => {
                setCourses((prev) => [c, ...prev]);
                setActiveCourseId(c.id);
                setMode('study');
              }}
              onToast={showToast}
            />
          ) : mode === 'study' ? (
            <StudyView
              course={activeCourse}
              schedule={schedule}
              activeAlloc={activeAlloc}
              onSelectAlloc={selectAlloc}
              onScheduleChanged={(s) => setSchedule(s)}
              onToast={showToast}
            />
          ) : mode === 'schedule' ? (
            <ScheduleView
              course={activeCourse}
              schedule={schedule}
              onScheduleChanged={(s) => setSchedule(s)}
              onCourseCreated={(c) => {
                setCourses((prev) => [c, ...prev]);
                setActiveCourseId(c.id);
                setMode('study');
              }}
              onToast={showToast}
            />
          ) : mode === 'sources' ? (
            <SourcesView
              course={activeCourse}
              onRefreshSchedule={() => reloadSchedule(activeCourse.id)}
              onToast={showToast}
            />
          ) : mode === 'exams' ? (
            <ExamHubView course={activeCourse} onToast={showToast} />
          ) : (
            <CramSheetView course={activeCourse} onToast={showToast} />
          )}
        </main>
      </div>

      {/* Responsive Mobile Bottom Tab Bar (<768px) */}
      <nav
        aria-label="Mobile navigation"
        className="md:hidden shrink-0 grid grid-cols-6 border-t border-border-def bg-surface py-1.5 no-print"
      >
        {navItems.map((item) => {
          const Icon = item.icon;
          const active = mode === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => setMode(item.id)}
              className={`flex flex-col items-center gap-0.5 text-[11px] font-medium ${
                active ? 'text-accent-text' : 'text-fg-secondary'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Command Palette */}
      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} items={commandItems} />

      {/* Accessible Toast & Optional Undo */}
      {toast && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-16 md:bottom-5 right-5 z-50 flex items-center gap-3 px-4 py-2.5 rounded-xl bg-fg-primary text-canvas text-xs font-medium shadow-xl no-print"
        >
          <span>{toast.msg}</span>
          {toast.withUndo && activeCourse && (
            <button
              type="button"
              onClick={async () => {
                try {
                  const s = await api.undoReplan(activeCourse.id);
                  setSchedule(s);
                  setToast(null);
                } catch {
                  /* ignore */
                }
              }}
              className="underline font-bold"
            >
              Undo
            </button>
          )}
        </div>
      )}
    </div>
  );
};
