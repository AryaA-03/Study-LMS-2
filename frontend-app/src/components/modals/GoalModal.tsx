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
import { api, Course, CramSheet, JobStatus, Quiz, QuizSubmitResult, SystemSettings } from '../../api/client';
import { formatSecToPill, MarkdownView } from '../MarkdownView';

import { ModalShell, CREATOR_PRESETS } from './ModalShell';

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
          preferred_daily_minutes: minutesPerDay,
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
          preferred_daily_minutes: minutesPerDay,
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
                  <span className="text-xs text-[var(--fg-muted)]">{cand.channel || cand.source_type}</span>
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

