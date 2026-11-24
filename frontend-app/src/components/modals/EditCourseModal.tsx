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

import { ModalShell } from './ModalShell';
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
        preferred_daily_minutes: minutesPerDay,
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
                  className={`rounded-md border px-2.5 py-1 text-xs font-semibold transition ${
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
