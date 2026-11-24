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
      const ids = (preview.lessons || []).filter((m: any) => m.is_matched || m.matched).map((m: any) => m.id || m.lesson_id);
      await api.applySyllabus(courseId, text.trim(), ids, strictness);
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
                Matched: {preview.matched_lessons_count ?? (preview.lessons || []).filter((m: any) => m.is_matched || m.matched).length} of {preview.total_lessons ?? 0} lessons
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
            {(preview.lessons || []).length > 0 && (
              <div className="max-h-44 overflow-y-auto space-y-1 border-t border-[var(--border-subtle)] pt-2">
                {(preview.lessons || []).map((m: any, idx: number) => {
                  const matched = Boolean(m.is_matched || m.matched);
                  return (
                    <div key={m.id || m.lesson_id || idx} className="flex items-center justify-between gap-2 text-xs">
                      <span className={matched ? 'text-[var(--fg-primary)] font-medium truncate' : 'text-[var(--fg-muted)] line-through truncate'}>
                        {matched ? '✓ ' : '✗ '}
                        {m.title || m.lesson_title || 'Lesson'}
                      </span>
                      {m.score !== undefined && (
                        <span className="shrink-0 font-mono text-xs text-[var(--fg-muted)]">
                          {Math.round((m.score || 0) * 100)}%
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </ModalShell>
  );
};

/* ================= 7. SETTINGS, DATA PORTABILITY & STORAGE CLEANUP ================= */
