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
