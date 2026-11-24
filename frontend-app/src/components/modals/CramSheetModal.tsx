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

export const CramSheetModal: React.FC<{
  courseId: string;
  onClose: () => void;
  onSeekTimestamp: (sec: number) => void;
  onToast: (msg: string) => void;
  sources?: Array<{ id: string; title: string }>;
  chapters?: string[];
}> = ({ courseId, onClose, onSeekTimestamp, onToast , sources = [], chapters = []}) => {
  const [scopeType, setScopeType] = useState<'course' | 'video' | 'module'>('course');
  const [selectedSourceId, setSelectedSourceId] = useState<string>(sources[0]?.id || '');
  const [selectedChapter, setSelectedChapter] = useState<string>(chapters[0] || '');

  const [sheet, setSheet] = useState<CramSheet | null>(null);
  const [loading, setLoading] = useState(true);
  const [job, setJob] = useState<JobStatus | null>(null);

  const loadSheet = async (refresh = false) => {
    setLoading(true);
    try {
      const scope =
        scopeType === 'video' && selectedSourceId
          ? { source_id: selectedSourceId }
          : scopeType === 'module' && selectedChapter
          ? { chapter_title: selectedChapter }
          : undefined;
      const data = refresh ? await api.generateCramSheet(courseId, true, scope) : await api.getCramSheet(courseId, scope);
      setSheet(data);
    } catch {
      try {
        const scope =
          scopeType === 'video' && selectedSourceId
            ? { source_id: selectedSourceId }
            : scopeType === 'module' && selectedChapter
            ? { chapter_title: selectedChapter }
            : undefined;
        const data = await api.generateCramSheet(courseId, true, scope);
        setSheet(data);
      } catch (e: any) {
        onToast(`Cram Sheet error: ${e.message}`);
      }
    } finally {
      setLoading(false);
    }
  };

  const eventSourceRef = React.useRef<EventSource | null>(null);

  useEffect(() => {
    loadSheet(false);
    return () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, scopeType, selectedSourceId, selectedChapter]);

  const handleFullSyllabusAsync = async () => {
    try {
      eventSourceRef.current?.close();
      const res = await api.generateFullCramSheetAsync(courseId);
      setJob({ id: res.job_id, job_type: 'cram_sheet_full', status: 'queued', progress_pct: 5, message: 'Starting full syllabus synthesis...' });
      const es = new EventSource(`/api/jobs/${res.job_id}/events`);
      eventSourceRef.current = es;
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
            <p className="text-xs text-[var(--fg-secondary)]">
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
