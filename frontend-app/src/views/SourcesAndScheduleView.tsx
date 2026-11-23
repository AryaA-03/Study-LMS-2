import React, { useEffect, useState } from 'react';
import { Calendar, Globe, Plus, Trash2, Upload, Youtube, RotateCcw } from 'lucide-react';
import { api, Course, ScheduleResponse, SourceItem } from '../api/client';

interface SourcesViewProps {
  course: Course;
  onRefreshSchedule: () => void;
  onToast: (msg: string) => void;
}

export const SourcesView: React.FC<SourcesViewProps> = ({ course, onRefreshSchedule, onToast }) => {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [ytUrl, setYtUrl] = useState('');
  const [webUrl, setWebUrl] = useState('');
  const [busy, setBusy] = useState(false);

  const loadSources = () => {
    api.listSources(course.id).then(setSources).catch(() => setSources([]));
  };

  useEffect(() => {
    loadSources();
  }, [course.id]);

  const handleAddYoutube = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ytUrl.trim() || busy) return;
    setBusy(true);
    try {
      await api.importYoutubeSource(course.id, ytUrl.trim(), true);
      await api.generateSchedule(course.id);
      setYtUrl('');
      loadSources();
      onRefreshSchedule();
      onToast('YouTube source imported and scheduled');
    } catch (err: any) {
      onToast(err.message || 'YouTube import failed');
    } finally {
      setBusy(false);
    }
  };

  const handleAddWeb = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!webUrl.trim() || busy) return;
    setBusy(true);
    try {
      await api.importWebSource(course.id, webUrl.trim());
      setWebUrl('');
      loadSources();
      onToast('Web article added to Subject Notebook');
    } catch (err: any) {
      onToast(err.message || 'Web import failed');
    } finally {
      setBusy(false);
    }
  };

  const handlePdfUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      await api.uploadPdfSource(course.id, file, file.name);
      loadSources();
      onToast(`Uploaded ${file.name} to Subject Notebook`);
    } catch (err: any) {
      onToast(err.message || 'PDF upload failed');
    } finally {
      setBusy(false);
      e.target.value = '';
    }
  };

  const handleDeleteSource = async (sid: string) => {
    try {
      await api.deleteSource(course.id, sid);
      loadSources();
      onRefreshSchedule();
      onToast('Source removed');
    } catch (err: any) {
      onToast(err.message || 'Could not remove source');
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-fg-primary">Subject Notebook Sources</h1>
        <p className="text-sm text-fg-secondary">Combine YouTube lectures/playlists, PDFs, and web articles into one grounded notebook.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <form onSubmit={handleAddYoutube} className="p-4 rounded-xl bg-surface border border-border-def space-y-2.5">
          <div className="flex items-center gap-2 text-sm font-semibold text-fg-primary">
            <Youtube className="w-4 h-4 text-red-600" /> YouTube Video / Playlist
          </div>
          <input
            type="url"
            value={ytUrl}
            onChange={(e) => setYtUrl(e.target.value)}
            placeholder="https://youtube.com/..."
            className="w-full px-3 py-2 text-xs rounded-lg bg-canvas border border-border-def text-fg-primary"
          />
          <button
            type="submit"
            disabled={busy || !ytUrl.trim()}
            className="w-full py-2 rounded-lg bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-xs font-semibold"
          >
            {busy ? 'Importing...' : 'Import & Schedule'}
          </button>
        </form>

        <form onSubmit={handleAddWeb} className="p-4 rounded-xl bg-surface border border-border-def space-y-2.5">
          <div className="flex items-center gap-2 text-sm font-semibold text-fg-primary">
            <Globe className="w-4 h-4 text-accent-text" /> Web Article
          </div>
          <input
            type="url"
            value={webUrl}
            onChange={(e) => setWebUrl(e.target.value)}
            placeholder="https://geeksforgeeks.org/..."
            className="w-full px-3 py-2 text-xs rounded-lg bg-canvas border border-border-def text-fg-primary"
          />
          <button
            type="submit"
            disabled={busy || !webUrl.trim()}
            className="w-full py-2 rounded-lg bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-xs font-semibold"
          >
            Add Article
          </button>
        </form>

        <div className="p-4 rounded-xl bg-surface border border-border-def space-y-2.5 flex flex-col justify-between">
          <div className="flex items-center gap-2 text-sm font-semibold text-fg-primary">
            <Upload className="w-4 h-4 text-emerald-600" /> Upload PDF Notes / Slides
          </div>
          <p className="text-xs text-fg-muted">Max 25 MB. Indexed automatically into Ask AI.</p>
          <label className="w-full py-2 rounded-lg bg-subtle hover:bg-border-def/50 border border-border-def text-fg-primary text-xs font-semibold text-center cursor-pointer">
            Choose PDF File
            <input type="file" accept="application/pdf" className="hidden" onChange={handlePdfUpload} disabled={busy} />
          </label>
        </div>
      </div>

      <div className="rounded-xl bg-surface border border-border-def divide-y divide-border-def">
        {sources.length === 0 ? (
          <div className="p-8 text-center text-sm text-fg-muted">No sources added yet.</div>
        ) : (
          sources.map((s) => (
            <div key={s.id} className="p-4 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium text-fg-primary truncate">{s.title}</div>
                <div className="text-xs text-fg-muted font-mono">{s.source_type}</div>
              </div>
              <button
                type="button"
                onClick={() => handleDeleteSource(s.id)}
                className="p-1.5 rounded-lg text-fg-muted hover:text-red-600 hover:bg-subtle"
                aria-label="Delete source"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

interface ScheduleViewProps {
  course: Course;
  schedule: ScheduleResponse | null;
  onScheduleChanged: (s: ScheduleResponse) => void;
  onCourseCreated: (c: Course) => void;
  onToast: (msg: string, withUndo?: boolean) => void;
}

export const ScheduleView: React.FC<ScheduleViewProps> = ({
  course,
  schedule,
  onScheduleChanged,
  onCourseCreated,
  onToast,
}) => {
  const [showNew, setShowNew] = useState(false);
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [targetDate, setTargetDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 14);
    return d.toISOString().slice(0, 10);
  });
  const [minutesPerDay, setMinutesPerDay] = useState(90);
  const [speed, setSpeed] = useState(1.25);
  const [creating, setCreating] = useState(false);

  const handleReplan = async (mode: 'normal' | 'compress') => {
    try {
      const updated = await api.replanSchedule(course.id, { mode });
      onScheduleChanged(updated);
      onToast(mode === 'compress' ? 'Schedule compressed to exam date' : 'Schedule replanned', true);
    } catch (e: any) {
      onToast(e.message || 'Replan failed');
    }
  };

  const handleUndo = async () => {
    try {
      const updated = await api.undoReplan(course.id);
      onScheduleChanged(updated);
      onToast('Replan undone');
    } catch (e: any) {
      onToast(e.message || 'Nothing to undo');
    }
  };

  const handleCreateCourse = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || creating) return;
    setCreating(true);
    try {
      const created = await api.createCourse({
        title: title.trim(),
        goal_query: title.trim(),
        target_date: targetDate,
        minutes_per_day: minutesPerDay,
        playback_speed: speed,
        rest_days: ['Sunday'],
        revision_buffer_days: 2,
      });
      if (url.trim()) {
        await api.importYoutubeSource(created.id, url.trim(), true);
        await api.generateSchedule(created.id);
      }
      setShowNew(false);
      setTitle('');
      setUrl('');
      onCourseCreated(created);
      onToast(`Created "${created.title}"`);
    } catch (err: any) {
      onToast(err.message || 'Failed to create course');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-fg-primary flex items-center gap-2">
            <Calendar className="w-5 h-5 text-accent-text" /> Day-Wise Study Schedule
          </h1>
          <p className="text-sm text-fg-secondary">
            Target Exam: <span className="font-mono">{course.target_date}</span> · {course.minutes_per_day} min/day · {course.playback_speed}x
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => handleReplan('normal')}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface border border-border-def hover:bg-subtle text-fg-primary"
          >
            Replan Now
          </button>
          <button
            type="button"
            onClick={() => handleReplan('compress')}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface border border-border-def hover:bg-subtle text-fg-primary"
          >
            Compress to Exam Date
          </button>
          <button
            type="button"
            onClick={handleUndo}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface border border-border-def hover:bg-subtle text-fg-primary inline-flex items-center gap-1"
          >
            <RotateCcw className="w-3.5 h-3.5" /> Undo
          </button>
          <button
            type="button"
            onClick={() => setShowNew((s) => !s)}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent hover:bg-accent-hover text-white inline-flex items-center gap-1"
          >
            <Plus className="w-3.5 h-3.5" /> New Course
          </button>
        </div>
      </div>

      {showNew && (
        <form onSubmit={handleCreateCourse} className="p-5 rounded-xl bg-surface border border-border-def space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-fg-primary">Create Learning Goal</h2>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setTitle('Theory of Computation (End-Term)');
                  setUrl('https://youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev');
                }}
                className="px-2.5 py-1 rounded bg-accent-soft text-accent-text text-xs font-medium"
              >
                Preset: TOC Playlist
              </button>
              <button
                type="button"
                onClick={() => {
                  setTitle('DBMS Complete One-Shot');
                  setUrl('https://youtu.be/NlLM3sVF8wY');
                }}
                className="px-2.5 py-1 rounded bg-accent-soft text-accent-text text-xs font-medium"
              >
                Preset: Marathon Video
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Subject / Exam Title"
              className="px-3 py-2 text-sm rounded-lg bg-canvas border border-border-def text-fg-primary"
            />
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="YouTube Playlist or Video URL (optional)"
              className="px-3 py-2 text-sm rounded-lg bg-canvas border border-border-def text-fg-primary"
            />
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className="px-3 py-2 text-sm rounded-lg bg-canvas border border-border-def text-fg-primary"
            />
            <div className="flex gap-2">
              <input
                type="number"
                min={15}
                max={480}
                value={minutesPerDay}
                onChange={(e) => setMinutesPerDay(Number(e.target.value))}
                className="w-1/2 px-3 py-2 text-sm rounded-lg bg-canvas border border-border-def text-fg-primary"
              />
              <select
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
                className="w-1/2 px-3 py-2 text-sm rounded-lg bg-canvas border border-border-def text-fg-primary"
              >
                {[1, 1.25, 1.5, 1.75, 2].map((s) => (
                  <option key={s} value={s}>
                    {s}x speed
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button
            type="submit"
            disabled={creating}
            className="px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-semibold"
          >
            {creating ? 'Creating & Partitioning...' : 'Create Course'}
          </button>
        </form>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {(schedule?.days || []).map((day) => (
          <div key={day.date} className="p-4 rounded-xl bg-surface border border-border-def space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-fg-primary">
              <span>
                {day.day_name} · <span className="font-mono text-fg-muted">{day.date}</span>
              </span>
              <span className="font-mono text-fg-secondary">{Math.round(day.total_minutes)}m</span>
            </div>
            {day.is_rest_day ? (
              <p className="text-xs text-fg-muted italic">Rest Day</p>
            ) : day.is_revision_buffer ? (
              <p className="text-xs text-accent-text font-medium">Pre-Exam Revision Buffer</p>
            ) : day.allocations.length === 0 ? (
              <p className="text-xs text-fg-muted">Open study day</p>
            ) : (
              <ul className="space-y-1.5">
                {day.allocations.map((a) => (
                  <li key={a.id} className="text-xs text-fg-secondary flex justify-between gap-2">
                    <span className={`truncate ${a.is_completed ? 'line-through opacity-60' : ''}`}>{a.lesson_title}</span>
                    <span className="font-mono shrink-0">{Math.round(a.effective_minutes)}m</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
