import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Database,
  Download,
  FileText,
  Globe,
  Loader2,
  Play,
  Printer,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
  Upload,
  X,
  Youtube,
  Zap,
} from 'lucide-react';
import { api, Course, CramSheet, JobStatus, Quiz, QuizSubmitResult, SystemSettings } from '../api/client';
import { formatSecToPill, MarkdownView } from './MarkdownView';

const ModalShell: React.FC<{
  title: string;
  subtitle?: string;
  onClose: () => void;
  wide?: boolean;
  children: React.ReactNode;
}> = ({ title, subtitle, onClose, wide, children }) => (
  <div
    className="no-print fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-[2px]"
    onClick={onClose}
  >
    <div
      className={`flex max-h-[90vh] w-full flex-col overflow-hidden rounded-2xl border border-[var(--border-strong)] bg-[var(--bg-card)] shadow-2xl ${
        wide ? 'max-w-4xl' : 'max-w-xl'
      }`}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-3.5">
        <div>
          <h2 className="text-sm font-bold text-[var(--fg-primary)]">{title}</h2>
          {subtitle && <p className="text-xs text-[var(--fg-secondary)]">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg p-1.5 text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-5">{children}</div>
    </div>
  </div>
);

const CREATOR_PRESETS = [
  {
    label: 'Neso Academy — Theory of Computation',
    title: 'Theory of Computation (Neso Academy)',
    url: 'https://www.youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev',
  },
  {
    label: 'Gate Smashers — DBMS Complete',
    title: 'DBMS Exam Prep (Gate Smashers)',
    url: 'https://www.youtube.com/playlist?list=PLxCzCOWd7aiFAN6I8CuViBuCdJgiOkT2Y',
  },
  {
    label: 'Abdul Bari — Algorithms',
    title: 'Design & Analysis of Algorithms',
    url: 'https://www.youtube.com/playlist?list=PLDN4rrl48XKpZkf03iYFl-O29szjTrs_O',
  },
  {
    label: 'Gate Smashers — Operating Systems',
    title: 'Operating Systems (Gate Smashers)',
    url: 'https://www.youtube.com/playlist?list=PLxCzCOWd7aiGz9donHRrE9I3Mwn6XdP8p',
  },
];

/* ================= 1. NEW GOAL / COURSE WIZARD ================= */
export const NewCourseModal: React.FC<{
  onClose: () => void;
  onCreated: (courseId: string) => void;
  onToast: (msg: string) => void;
}> = ({ onClose, onCreated, onToast }) => {
  const defaultDate = new Date(Date.now() + 21 * 86400000).toISOString().slice(0, 10);
  const [title, setTitle] = useState('');
  const [targetDate, setTargetDate] = useState(defaultDate);
  const [minutesPerDay, setMinutesPerDay] = useState(90);
  const [speed, setSpeed] = useState(1.25);
  const [strategy, setStrategy] = useState<'paced' | 'fixed'>('paced');
  const [sourceUrl, setSourceUrl] = useState('');
  const [discoverQuery, setDiscoverQuery] = useState('');
  const [candidates, setCandidates] = useState<any[]>([]);
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>({});
  const [createdCourseId, setCreatedCourseId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleDiscover = async () => {
    if (!title.trim() && !discoverQuery.trim()) return;
    setBusy(true);
    try {
      let cid = createdCourseId;
      if (!cid) {
        const c = await api.createCourse({
          title: title.trim() || discoverQuery.trim(),
          goal_query: discoverQuery.trim() || title.trim(),
          target_date: targetDate,
          minutes_per_day: minutesPerDay,
          playback_speed: speed,
          schedule_strategy: strategy,
          rest_days: [],
          revision_buffer_days: 2,
        });
        cid = c.id;
        setCreatedCourseId(cid);
      }
      const res = await api.discoverSources(cid, discoverQuery.trim() || title.trim());
      setCandidates(res.candidates || []);
      const init: Record<string, boolean> = {};
      (res.candidates || []).slice(0, 2).forEach((cand: any) => {
        if (cand.source_id) init[cand.source_id] = true;
      });
      setSelectedIds(init);
    } catch (e: any) {
      onToast(`Discovery error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleCreateAndImport = async () => {
    if (!title.trim()) {
      onToast('Enter a course title first');
      return;
    }
    setBusy(true);
    try {
      let cid = createdCourseId;
      if (!cid) {
        const c = await api.createCourse({
          title: title.trim(),
          goal_query: title.trim(),
          target_date: targetDate,
          minutes_per_day: minutesPerDay,
          playback_speed: speed,
          schedule_strategy: strategy,
          rest_days: [],
          revision_buffer_days: 2,
        });
        cid = c.id;
      }

      if (sourceUrl.trim()) {
        const src = await api.importSource(cid, sourceUrl.trim(), true);
        if (src?.id) {
          await api.approveSources(cid, [src.id], []);
        }
      } else if (candidates.length > 0) {
        const approve = Object.entries(selectedIds)
          .filter(([, v]) => v)
          .map(([k]) => k);
        const reject = candidates
          .map((c) => c.source_id)
          .filter((id) => id && !approve.includes(id));
        if (approve.length > 0) {
          await api.approveSources(cid, approve, reject);
        }
      }

      await api.clusterTopics(cid).catch(() => {});
      await api.generateSchedule(cid).catch(() => {});
      onToast('Course created & scheduled!');
      onCreated(cid);
      onClose();
    } catch (e: any) {
      onToast(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell
      title="Create New Study Goal"
      subtitle="Paste a YouTube playlist/video, pick a CS preset, or discover & approve sources."
      onClose={onClose}
      wide
    >
      <div className="space-y-4 text-xs">
        <div>
          <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Popular CS / Exam Presets</label>
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {CREATOR_PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => {
                  setTitle(p.title);
                  setSourceUrl(p.url);
                }}
                className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-left font-medium text-[var(--fg-primary)] hover:border-[var(--accent)]"
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Course / Exam Title</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Theory of Computation"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
            />
          </div>
          <div>
            <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Target Exam Date</label>
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Daily Study (min)</label>
            <input
              type="number"
              min={15}
              max={480}
              step={15}
              value={minutesPerDay}
              onChange={(e) => setMinutesPerDay(parseInt(e.target.value || '60', 10))}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
            />
          </div>
          <div>
            <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Playback Speed</label>
            <select
              value={speed}
              onChange={(e) => setSpeed(parseFloat(e.target.value))}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
            >
              {[1, 1.25, 1.5, 1.75, 2].map((s) => (
                <option key={s} value={s}>{s}x</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Scheduling Mode</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as 'paced' | 'fixed')}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
            >
              <option value="paced">Paced (Finish by Exam)</option>
              <option value="fixed">Fixed Daily Minutes</option>
            </select>
          </div>
        </div>

        <div>
          <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">
            Direct YouTube Playlist or Marathon Video URL
          </label>
          <input
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            placeholder="https://youtube.com/playlist?list=... or https://youtu.be/..."
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
          />
        </div>

        {/* Discovery Approval Gate */}
        <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3 space-y-2">
          <div className="flex items-center gap-2">
            <input
              value={discoverQuery}
              onChange={(e) => setDiscoverQuery(e.target.value)}
              placeholder="Or search YouTube playlists/lectures (Approval Gate)..."
              className="flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-1.5 text-[var(--fg-primary)] outline-none"
            />
            <button
              type="button"
              onClick={handleDiscover}
              disabled={busy}
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-card)] px-3 py-1.5 font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
            >
              <Search className="h-3.5 w-3.5" /> Discover
            </button>
          </div>

          {candidates.length > 0 && (
            <div className="max-h-40 space-y-1.5 overflow-y-auto pt-1">
              {candidates.map((cand: any) => (
                <label
                  key={cand.source_id || cand.id}
                  className="flex cursor-pointer items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2.5 py-1.5"
                >
                  <input
                    type="checkbox"
                    checked={!!selectedIds[cand.source_id]}
                    onChange={(e) =>
                      setSelectedIds((prev) => ({ ...prev, [cand.source_id]: e.target.checked }))
                    }
                  />
                  <span className="flex-1 truncate font-medium text-[var(--fg-primary)]">{cand.title}</span>
                  <span className="text-[10px] text-[var(--fg-muted)]">{cand.channel || cand.source_type}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-[var(--border-subtle)] px-4 py-2 font-semibold text-[var(--fg-secondary)]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleCreateAndImport}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--accent)] px-4 py-2 font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Create & Build Schedule
          </button>
        </div>
      </div>
    </ModalShell>
  );
};

/* ================= 2. EDIT COURSE & SCHEDULE TIMINGS ================= */
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

export const EditCourseModal: React.FC<{
  course: Course;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
  onToast: (msg: string) => void;
}> = ({ course, onClose, onSaved, onDeleted, onToast }) => {
  const [title, setTitle] = useState(course.title || '');
  const [targetDate, setTargetDate] = useState(course.target_date || '');
  const [minutesPerDay, setMinutesPerDay] = useState(course.minutes_per_day || 60);
  const [speed, setSpeed] = useState(course.playback_speed || 1.25);
  const [bufferDays, setBufferDays] = useState(course.revision_buffer_days ?? 2);
  const [strategy, setStrategy] = useState<'paced' | 'fixed'>(course.schedule_strategy || 'paced');
  const [restDays, setRestDays] = useState<string[]>(course.rest_days || []);
  const [saving, setSaving] = useState(false);

  const toggleRestDay = (day: string) =>
    setRestDays((prev) => (prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]));

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.updateCourse(course.id, {
        title: title.trim() || course.title,
        target_date: targetDate,
        minutes_per_day: minutesPerDay,
        playback_speed: speed,
        revision_buffer_days: bufferDays,
        schedule_strategy: strategy,
        rest_days: restDays,
      });
      await api.replanSchedule(course.id, 'normal').catch(() => {});
      onToast('Course timings updated & schedule repacked instantly!');
      onSaved();
      onClose();
    } catch (e: any) {
      onToast(`Update failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${course.title}" and all its lessons, notes, and flashcards?`)) return;
    setSaving(true);
    try {
      await api.deleteCourse(course.id);
      onToast('Course deleted');
      onDeleted();
      onClose();
    } catch (e: any) {
      onToast(`Delete failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalShell
      title="Edit Course & Study Timings"
      subtitle="Changes repack your calendar instantly with zero AI calls and 1-click Undo."
      onClose={onClose}
    >
      <div className="space-y-3.5 text-xs">
        <div>
          <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Course Title</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Exam Target Date</label>
            <input
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
            />
          </div>
          <div>
            <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Daily Study Budget (min)</label>
            <input
              type="number"
              min={15}
              max={480}
              step={15}
              value={minutesPerDay}
              onChange={(e) => setMinutesPerDay(parseInt(e.target.value || '60', 10))}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Playback Speed</label>
            <select
              value={speed}
              onChange={(e) => setSpeed(parseFloat(e.target.value))}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-2 text-[var(--fg-primary)]"
            >
              {[1, 1.25, 1.5, 1.75, 2].map((s) => (
                <option key={s} value={s}>{s}x</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Revision Buffer</label>
            <input
              type="number"
              min={0}
              max={14}
              value={bufferDays}
              onChange={(e) => setBufferDays(parseInt(e.target.value || '0', 10))}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-2 text-[var(--fg-primary)]"
            />
          </div>
          <div>
            <label className="mb-1 block font-semibold text-[var(--fg-secondary)]">Strategy</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as 'paced' | 'fixed')}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-2 text-[var(--fg-primary)]"
            >
              <option value="paced">Paced</option>
              <option value="fixed">Fixed</option>
            </select>
          </div>
        </div>

        <div>
          <label className="mb-1.5 block font-semibold text-[var(--fg-secondary)]">Rest Days (No Study Scheduled)</label>
          <div className="flex flex-wrap gap-1.5">
            {WEEKDAYS.map((day) => {
              const active = restDays.includes(day);
              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => toggleRestDay(day)}
                  className={`rounded-md border px-2.5 py-1 text-[11px] font-semibold transition ${
                    active
                      ? 'border-[var(--accent)] bg-[var(--accent)] text-white'
                      : 'border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-[var(--fg-secondary)]'
                  }`}
                >
                  {day.slice(0, 3)}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-[var(--border-subtle)] pt-3">
          <button
            type="button"
            onClick={handleDelete}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded-lg border border-[var(--danger)]/40 px-3 py-1.5 font-semibold text-[var(--danger)] hover:bg-[var(--danger)]/10"
          >
            <Trash2 className="h-3.5 w-3.5" /> Delete Course
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-[var(--border-subtle)] px-3.5 py-1.5 font-semibold text-[var(--fg-secondary)]"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--accent)] px-4 py-1.5 font-semibold text-white hover:opacity-90"
            >
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              Save & Repack Schedule
            </button>
          </div>
        </div>
      </div>
    </ModalShell>
  );
};

/* ================= 3. ADD SOURCE MODAL (YT / PDF / WEB / MANUAL TRANSCRIPT) ================= */
export const AddSourceModal: React.FC<{
  courseId: string;
  onClose: () => void;
  onAdded: () => void;
  onToast: (msg: string) => void;
}> = ({ courseId, onClose, onAdded, onToast }) => {
  const [tab, setTab] = useState<'youtube' | 'pdf' | 'web' | 'manual'>('youtube');
  const [ytUrl, setYtUrl] = useState('');
  const [webUrl, setWebUrl] = useState('');
  const [webTitle, setWebTitle] = useState('');
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [manualTitle, setManualTitle] = useState('');
  const [manualText, setManualText] = useState('');
  const [busy, setBusy] = useState(false);

  const handleSubmit = async () => {
    setBusy(true);
    try {
      if (tab === 'youtube') {
        if (!ytUrl.trim()) throw new Error('Enter a YouTube URL');
        const src = await api.importSource(courseId, ytUrl.trim(), true);
        if (src?.id) await api.approveSources(courseId, [src.id], []);
        await api.clusterTopics(courseId).catch(() => {});
        await api.generateSchedule(courseId).catch(() => {});
        onToast('YouTube source imported & topics grouped!');
      } else if (tab === 'pdf') {
        if (!pdfFile) throw new Error('Select a PDF file');
        await api.uploadPdfSource(courseId, pdfFile, pdfFile.name);
        onToast('PDF added to subject notebook!');
      } else if (tab === 'web') {
        if (!webUrl.trim()) throw new Error('Enter an article URL');
        await api.importWebSource(courseId, webUrl.trim(), webTitle.trim() || undefined);
        onToast('Web article added to notebook!');
      } else {
        if (!manualTitle.trim() || !manualText.trim()) throw new Error('Enter title and transcript text');
        await api.submitManualTranscript(courseId, manualTitle.trim(), manualText.trim());
        await api.generateSchedule(courseId).catch(() => {});
        onToast('Manual transcript imported!');
      }
      onAdded();
      onClose();
    } catch (e: any) {
      onToast(`Import failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell
      title="Add Study Source"
      subtitle="Attach YouTube playlists/videos, lecture PDFs, web articles, or manual transcripts."
      onClose={onClose}
    >
      <div className="space-y-4 text-xs">
        <div className="grid grid-cols-4 gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-1">
          {([
            { id: 'youtube', label: 'YouTube', icon: Youtube },
            { id: 'pdf', label: 'PDF', icon: FileText },
            { id: 'web', label: 'Web', icon: Globe },
            { id: 'manual', label: 'Transcript', icon: Upload },
          ] as const).map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`flex items-center justify-center gap-1 rounded-md py-1.5 font-semibold transition ${
                  tab === t.id ? 'bg-[var(--accent)] text-white' : 'text-[var(--fg-secondary)]'
                }`}
              >
                <Icon className="h-3.5 w-3.5" /> {t.label}
              </button>
            );
          })}
        </div>

        {tab === 'youtube' && (
          <input
            value={ytUrl}
            onChange={(e) => setYtUrl(e.target.value)}
            placeholder="Paste YouTube video or playlist URL..."
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
          />
        )}
        {tab === 'pdf' && (
          <input
            type="file"
            accept=".pdf"
            onChange={(e) => setPdfFile(e.target.files?.[0] || null)}
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-2 text-[var(--fg-primary)]"
          />
        )}
        {tab === 'web' && (
          <div className="space-y-2">
            <input
              value={webUrl}
              onChange={(e) => setWebUrl(e.target.value)}
              placeholder="https://geeksforgeeks.org/..."
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
            />
            <input
              value={webTitle}
              onChange={(e) => setWebTitle(e.target.value)}
              placeholder="Optional title"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
            />
          </div>
        )}
        {tab === 'manual' && (
          <div className="space-y-2">
            <input
              value={manualTitle}
              onChange={(e) => setManualTitle(e.target.value)}
              placeholder="Lesson Title (e.g. Lecture 5: Pumping Lemma)"
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
            />
            <textarea
              value={manualText}
              onChange={(e) => setManualText(e.target.value)}
              rows={6}
              placeholder="Paste raw lecture transcript or notes here (manual fallback when YouTube captions are unavailable)..."
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-2 text-[var(--fg-primary)]"
            />
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-[var(--border-subtle)] px-3.5 py-1.5 font-semibold text-[var(--fg-secondary)]"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--accent)] px-4 py-1.5 font-semibold text-white"
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Import Source
          </button>
        </div>
      </div>
    </ModalShell>
  );
};

/* ================= 4. LAST-NIGHT CRAM SHEET MODAL (PRINT-READY A4!) ================= */
export const CramSheetModal: React.FC<{
  courseId: string;
  onClose: () => void;
  onSeekTimestamp: (sec: number) => void;
  onToast: (msg: string) => void;
}> = ({ courseId, onClose, onSeekTimestamp, onToast }) => {
  const [sheet, setSheet] = useState<CramSheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [job, setJob] = useState<JobStatus | null>(null);

  const loadSheet = async (refresh = false) => {
    setLoading(true);
    try {
      const data = refresh ? await api.generateCramSheet(courseId, true) : await api.getCramSheet(courseId);
      setSheet(data);
    } catch {
      try {
        const data = await api.generateCramSheet(courseId, true);
        setSheet(data);
      } catch (e: any) {
        onToast(`Cram Sheet error: ${e.message}`);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSheet(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  const handleFullSyllabusAsync = async () => {
    try {
      const res = await api.generateFullCramSheetAsync(courseId);
      setJob({ id: res.job_id, job_type: 'cram_sheet_full', status: 'queued', progress_pct: 5, message: 'Starting full syllabus synthesis...' });
      const es = new EventSource(`/api/jobs/${res.job_id}/events`);
      es.onmessage = (ev) => {
        try {
          const j = JSON.parse(ev.data) as JobStatus;
          setJob(j);
          if (j.status === 'completed') {
            es.close();
            loadSheet(false);
            onToast('Full-syllabus Cram Sheet ready!');
          } else if (j.status === 'failed' || j.status === 'cancelled') {
            es.close();
            onToast(`Synthesis ${j.status}: ${j.error_text || ''}`);
          }
        } catch {
          // ignore
        }
      };
      es.onerror = () => es.close();
    } catch (e: any) {
      onToast(`Error: ${e.message}`);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-[2px] print-only-container"
      onClick={onClose}
    >
      <div
        className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-[var(--border-strong)] bg-[var(--bg-card)] shadow-2xl print-only-container"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="no-print flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] px-5 py-3">
          <div>
            <h2 className="text-sm font-bold text-[var(--fg-primary)]">Last-Night Exam Cram Sheet</h2>
            <p className="text-[11px] text-[var(--fg-secondary)]">
              High-yield formulas, comparison tables, PYQ focus & clickable [MM:SS] lecture links.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <button
              type="button"
              onClick={() => loadSheet(true)}
              disabled={loading}
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </button>
            <button
              type="button"
              onClick={handleFullSyllabusAsync}
              disabled={!!job && (job.status === 'queued' || job.status === 'running')}
              className="inline-flex items-center gap-1 rounded-lg bg-[var(--accent)] px-2.5 py-1.5 font-semibold text-white hover:opacity-90"
            >
              <Sparkles className="h-3.5 w-3.5" /> Synthesize Full Syllabus
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
            >
              <Printer className="h-3.5 w-3.5" /> Print A4 / PDF
            </button>
            <a
              href={api.downloadCramSheetUrl(courseId)}
              download
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
            >
              <Download className="h-3.5 w-3.5" /> .md
            </a>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)]"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {job && (job.status === 'queued' || job.status === 'running') && (
          <div className="no-print border-b border-[var(--border-subtle)] bg-[var(--accent-soft)] px-5 py-2 text-xs text-[var(--accent-text)]">
            <div className="flex items-center justify-between font-semibold">
              <span>{job.message || 'Synthesizing lessons across syllabus...'}</span>
              <span>{job.progress_pct}%</span>
            </div>
            <div className="mt-1 h-1.5 w-full rounded-full bg-[var(--bg-card)] overflow-hidden">
              <div className="h-full bg-[var(--accent)] transition-all" style={{ width: `${job.progress_pct}%` }} />
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-8 py-6 print-only-container">
          {loading ? (
            <div className="flex h-48 items-center justify-center gap-2 text-xs text-[var(--fg-secondary)]">
              <Loader2 className="h-5 w-5 animate-spin text-[var(--accent)]" />
              Compiling high-yield exam cram sheet...
            </div>
          ) : (
            <MarkdownView
              markdown={sheet?.content_markdown || 'No content yet.'}
              onSeekTimestamp={(sec) => {
                onSeekTimestamp(sec);
                onClose();
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
};

/* ================= 5. DIAGNOSTIC PRE-TEST & TIMED MOCK EXAM MODAL ================= */
export const ExamModal: React.FC<{
  courseId: string;
  mode: 'diagnostic' | 'mock_exam';
  onClose: () => void;
  onSeekTimestamp: (sec: number) => void;
  onScheduleChanged: () => void;
  onToast: (msg: string) => void;
}> = ({ courseId, mode, onClose, onSeekTimestamp, onScheduleChanged, onToast }) => {
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [result, setResult] = useState<QuizSubmitResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    setLoading(true);
    api
      .generateQuiz(courseId, {
        quiz_type: mode,
        question_count: mode === 'diagnostic' ? 6 : 12,
      })
      .then((q) => setQuiz(q))
      .catch((e: any) => onToast(`Failed to generate ${mode}: ${e.message}`))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, mode]);

  useEffect(() => {
    if (!quiz || result) return;
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [quiz, result]);

  const handleSubmit = async () => {
    if (!quiz) return;
    setLoading(true);
    try {
      const res = await api.submitQuiz(courseId, quiz.id, answers, {}, elapsed);
      setResult(res);
      if (res.schedule_updated) onScheduleChanged();
      onToast(
        mode === 'diagnostic'
          ? 'Diagnostic graded — mastered topics updated in your schedule!'
          : `Mock Exam graded: ${Math.round(res.score)}%`,
      );
    } catch (e: any) {
      onToast(`Submit error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalShell
      title={mode === 'diagnostic' ? '2-Minute Diagnostic Pre-Test' : 'Timed Subject Mock Exam'}
      subtitle={
        mode === 'diagnostic'
          ? 'Skip topics you already know — your schedule repacks automatically.'
          : `Elapsed: ${formatSecToPill(elapsed)} • Wrong answers link directly to video explanations.`
      }
      onClose={onClose}
      wide
    >
      {loading && !quiz ? (
        <div className="flex h-40 items-center justify-center gap-2 text-xs text-[var(--fg-secondary)]">
          <Loader2 className="h-5 w-5 animate-spin text-[var(--accent)]" />
          Preparing grounded exam questions...
        </div>
      ) : !quiz ? (
        <p className="text-xs text-[var(--fg-secondary)]">Could not load exam questions.</p>
      ) : (
        <div className="space-y-4">
          {result && (
            <div className="rounded-xl border border-[var(--accent)] bg-[var(--accent-soft)] p-3.5 text-xs text-[var(--accent-text)]">
              <div className="text-sm font-bold">
                Final Score: {Math.round(result.score)}% ({result.correct_count}/{result.total_questions})
              </div>
              {mode === 'diagnostic' && (
                <p className="mt-1">Mastered topics have been marked & schedule updated automatically.</p>
              )}
            </div>
          )}

          {quiz.questions.map((q, i) => {
            const resItem = result?.results?.find((r) => r.question_id === q.id);
            const ts = resItem?.source_timestamp_sec ?? q.source_timestamp_sec;
            return (
              <div
                key={q.id}
                className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3.5 space-y-2"
              >
                <div className="text-xs font-semibold text-[var(--fg-primary)]">
                  {i + 1}. {q.question_text}
                </div>
                <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                  {(q.options || []).map((opt, oi) => {
                    const chosen = answers[q.id] === oi;
                    const correctOpt = resItem && resItem.correct_index === oi;
                    return (
                      <button
                        key={oi}
                        type="button"
                        disabled={!!result}
                        onClick={() => setAnswers((p) => ({ ...p, [q.id]: oi }))}
                        className={`rounded-lg border px-3 py-2 text-left text-xs transition ${
                          correctOpt
                            ? 'border-[var(--success)] bg-[var(--success)]/15 font-semibold text-[var(--fg-primary)]'
                            : chosen
                            ? 'border-[var(--accent)] bg-[var(--accent-soft)] font-semibold text-[var(--accent-text)]'
                            : 'border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)]'
                        }`}
                      >
                        <span className="mr-1.5 font-mono font-bold opacity-70">{String.fromCharCode(65 + oi)}.</span>
                        {opt}
                      </button>
                    );
                  })}
                </div>
                {resItem && (
                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[11px] text-[var(--fg-secondary)]">
                    <span>{resItem.explanation || q.explanation}</span>
                    {ts !== undefined && ts !== null && (
                      <button
                        type="button"
                        onClick={() => {
                          onSeekTimestamp(ts);
                          onClose();
                        }}
                        className="inline-flex items-center gap-1 rounded bg-[var(--accent)] px-2 py-0.5 font-semibold text-white"
                      >
                        <Play className="h-3 w-3" /> Replay {formatSecToPill(ts)}
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {!result && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleSubmit}
                disabled={loading || Object.keys(answers).length === 0}
                className="rounded-lg bg-[var(--accent)] px-5 py-2 text-xs font-bold text-white"
              >
                Submit Exam
              </button>
            </div>
          )}
        </div>
      )}
    </ModalShell>
  );
};

/* ================= 6. SYLLABUS ALIGNMENT MODAL ================= */
export const SyllabusModal: React.FC<{
  courseId: string;
  onClose: () => void;
  onApplied: () => void;
  onToast: (msg: string) => void;
}> = ({ courseId, onClose, onApplied, onToast }) => {
  const [text, setText] = useState('');
  const [strictness, setStrictness] = useState<'strict' | 'balanced' | 'comprehensive'>('balanced');
  const [preview, setPreview] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const handlePreview = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const res = await api.matchSyllabus(courseId, text.trim(), strictness);
      setPreview(res);
    } catch (e: any) {
      onToast(`Match error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleApply = async () => {
    if (!preview) return;
    setBusy(true);
    try {
      const ids = preview.selected_lesson_ids || preview.matched_lessons?.map((m: any) => m.lesson_id) || [];
      await api.applySyllabus(courseId, text.trim(), ids);
      onToast(`Applied syllabus alignment (${ids.length} lessons kept)`);
      onApplied();
      onClose();
    } catch (e: any) {
      onToast(`Apply error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell
      title="University Syllabus Auto-Matcher"
      subtitle="Paste your official exam syllabus to automatically exclude out-of-syllabus videos."
      onClose={onClose}
      wide
    >
      <div className="space-y-3 text-xs">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          placeholder="Paste syllabus units here (e.g., Unit 1: DFA, NFA, Epsilon-NFA, Minimization...)"
          className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3 text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
        />
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            {(['strict', 'balanced', 'comprehensive'] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStrictness(s)}
                className={`rounded-md border px-2.5 py-1 font-semibold capitalize ${
                  strictness === s
                    ? 'border-[var(--accent)] bg-[var(--accent)] text-white'
                    : 'border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-[var(--fg-secondary)]'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={handlePreview}
            disabled={busy || !text.trim()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--accent)] px-4 py-1.5 font-semibold text-white"
          >
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Preview Match
          </button>
        </div>

        {preview && (
          <div className="rounded-xl border border-[var(--border-strong)] bg-[var(--bg-elevated)] p-3 space-y-2">
            <div className="flex items-center justify-between font-bold text-[var(--fg-primary)]">
              <span>
                Matched: {preview.selected_lesson_ids?.length ?? preview.matched_count ?? 0} lessons
              </span>
              <button
                type="button"
                onClick={handleApply}
                disabled={busy}
                className="rounded-lg bg-[var(--success)] px-3.5 py-1.5 text-xs font-semibold text-white"
              >
                Apply to Schedule
              </button>
            </div>
          </div>
        )}
      </div>
    </ModalShell>
  );
};

/* ================= 7. SETTINGS, DATA PORTABILITY & STORAGE CLEANUP ================= */
export const SettingsModal: React.FC<{
  courseId: string | null;
  onClose: () => void;
  onToast: (msg: string) => void;
}> = ({ courseId, onClose, onToast }) => {
  const [settings, setSettings] = useState<SystemSettings>({});
  const [geminiKey, setGeminiKey] = useState('');
  const [groqKey, setGroqKey] = useState('');
  const [openrouterKey, setOpenrouterKey] = useState('');
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434');
  const [ollamaModel, setOllamaModel] = useState('llama3.2');
  const [whisperModel, setWhisperModel] = useState('base');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .getSettings()
      .then((s) => {
        setSettings(s || {});
        if (s.ollama_base_url) setOllamaUrl(s.ollama_base_url);
        if (s.ollama_model) setOllamaModel(s.ollama_model);
        if (s.whisper_model) setWhisperModel(s.whisper_model);
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    setBusy(true);
    try {
      const payload: Record<string, any> = {
        ollama_base_url: ollamaUrl,
        ollama_model: ollamaModel,
        whisper_model: whisperModel,
      };
      if (geminiKey.trim()) payload.gemini_api_key = geminiKey.trim();
      if (groqKey.trim()) payload.groq_api_key = groqKey.trim();
      if (openrouterKey.trim()) payload.openrouter_api_key = openrouterKey.trim();
      await api.saveSettings(payload);
      onToast('Settings saved!');
      setGeminiKey('');
      setGroqKey('');
      setOpenrouterKey('');
    } catch (e: any) {
      onToast(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleTest = async () => {
    setBusy(true);
    try {
      const res = await api.testConnection();
      onToast(res.message || (res.success ? 'AI connection working!' : 'Connection failed'));
    } catch (e: any) {
      onToast(`Test failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell
      title="Settings, AI Keys & Data Portability"
      subtitle="Configure BYOK API keys, local Whisper/Ollama, exports, backups, and storage cleanup."
      onClose={onClose}
      wide
    >
      <div className="space-y-5 text-xs">
        <div className="space-y-2.5">
          <h3 className="font-bold text-[var(--fg-primary)]">AI Providers (BYOK — Stored Locally)</h3>
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-[var(--fg-secondary)]">
                Gemini API Key {settings.gemini_api_key_set && <CheckCircle2 className="inline h-3 w-3 text-[var(--success)]" />}
              </label>
              <input
                type="password"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder={settings.gemini_api_key_set ? '•••••••• (saved)' : 'AIza...'}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[var(--fg-secondary)]">
                Groq API Key {settings.groq_api_key_set && <CheckCircle2 className="inline h-3 w-3 text-[var(--success)]" />}
              </label>
              <input
                type="password"
                value={groqKey}
                onChange={(e) => setGroqKey(e.target.value)}
                placeholder={settings.groq_api_key_set ? '•••••••• (saved)' : 'gsk_...'}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[var(--fg-secondary)]">
                OpenRouter Key {settings.openrouter_api_key_set && <CheckCircle2 className="inline h-3 w-3 text-[var(--success)]" />}
              </label>
              <input
                type="password"
                value={openrouterKey}
                onChange={(e) => setOpenrouterKey(e.target.value)}
                placeholder={settings.openrouter_api_key_set ? '•••••••• (saved)' : 'sk-or-...'}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)]"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-[var(--fg-secondary)]">Ollama URL (Offline AI)</label>
              <input
                value={ollamaUrl}
                onChange={(e) => setOllamaUrl(e.target.value)}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[var(--fg-secondary)]">Ollama Model</label>
              <input
                value={ollamaModel}
                onChange={(e) => setOllamaModel(e.target.value)}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[var(--fg-secondary)]">Local Whisper Model</label>
              <select
                value={whisperModel}
                onChange={(e) => setWhisperModel(e.target.value)}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)]"
              >
                {['tiny', 'base', 'small', 'medium'].map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={busy}
              className="rounded-lg bg-[var(--accent)] px-4 py-1.5 font-semibold text-white"
            >
              Save Settings
            </button>
            <button
              type="button"
              onClick={handleTest}
              disabled={busy}
              className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3.5 py-1.5 font-semibold text-[var(--fg-primary)]"
            >
              <Zap className="h-3.5 w-3.5" /> Test AI Connection
            </button>
          </div>
        </div>

        {/* Data Portability & Storage Cleanup */}
        <div className="border-t border-[var(--border-subtle)] pt-4 space-y-2.5">
          <h3 className="font-bold text-[var(--fg-primary)]">Data Portability & Storage Cleanup</h3>
          <div className="flex flex-wrap gap-2">
            {courseId && (
              <>
                <a
                  href={api.exportCourseJsonUrl(courseId)}
                  download
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-1.5 font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
                >
                  <Download className="h-3.5 w-3.5" /> Export Course JSON
                </a>
                <a
                  href={api.exportCourseMarkdownUrl(courseId)}
                  download
                  className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-1.5 font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
                >
                  <Download className="h-3.5 w-3.5" /> Export Notes (.md)
                </a>
              </>
            )}
            <a
              href={api.backupDbUrl()}
              download
              className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-1.5 font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
            >
              <Database className="h-3.5 w-3.5" /> Backup SQLite DB
            </a>
            <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-1.5 font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]">
              <Upload className="h-3.5 w-3.5" /> Restore DB
              <input
                type="file"
                accept=".db,.sqlite"
                className="hidden"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  try {
                    await api.restoreDb(f);
                    onToast('Database restored! Reloading...');
                    window.location.reload();
                  } catch (err: any) {
                    onToast(`Restore failed: ${err.message}`);
                  }
                }}
              />
            </label>
            <button
              type="button"
              onClick={async () => {
                const r = await api.cleanupCache();
                onToast(r.message || 'Audio & temporary cache cleaned!');
              }}
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-1.5 font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
            >
              Clean Temp Cache
            </button>
            <button
              type="button"
              onClick={async () => {
                await api.vacuumDb();
                onToast('SQLite database compacted (VACUUM)!');
              }}
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-1.5 font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
            >
              Compact DB
            </button>
            <button
              type="button"
              onClick={async () => {
                const r = await api.updateYtdlp();
                onToast(r.message || 'yt-dlp updated!');
              }}
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3 py-1.5 font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
            >
              Update yt-dlp
            </button>
          </div>
        </div>
      </div>
    </ModalShell>
  );
};
