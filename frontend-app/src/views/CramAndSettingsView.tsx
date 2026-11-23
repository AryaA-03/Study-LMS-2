import React, { useEffect, useState } from 'react';
import { Download, Printer, Sparkles, Key, Database, CheckCircle2 } from 'lucide-react';
import { api, Course } from '../api/client';
import { MarkdownView } from '../components/MarkdownView';

interface CramSheetViewProps {
  course: Course;
  onToast: (msg: string) => void;
}

export const CramSheetView: React.FC<CramSheetViewProps> = ({ course, onToast }) => {
  const [markdown, setMarkdown] = useState('');
  const [loading, setLoading] = useState(false);
  const [jobStatus, setJobStatus] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api
      .getCramSheet(course.id)
      .then((res) => setMarkdown(res.content_markdown || ''))
      .catch(() => setMarkdown(''))
      .finally(() => setLoading(false));
  }, [course.id]);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const res = await api.generateCramSheet(course.id);
      setMarkdown(res.content_markdown || '');
      onToast('Cram Sheet generated');
    } catch (e: any) {
      onToast(e.message || 'Cram Sheet generation failed');
    } finally {
      setLoading(false);
    }
  };

  const handleFullAsync = async () => {
    try {
      const { job_id } = await api.generateCramSheetAsync(course.id);
      setJobStatus('Running full-syllabus synthesis in background...');
      const poll = window.setInterval(async () => {
        try {
          const j = await api.getJob(job_id);
          if (j.status === 'completed') {
            window.clearInterval(poll);
            setJobStatus(null);
            const res = await api.getCramSheet(course.id);
            setMarkdown(res.content_markdown || '');
            onToast('Full-Syllabus Cram Sheet ready!');
          } else if (j.status === 'failed' || j.status === 'cancelled') {
            window.clearInterval(poll);
            setJobStatus(null);
            onToast(`Background job ${j.status}`);
          }
        } catch {
          window.clearInterval(poll);
          setJobStatus(null);
        }
      }, 1500);
    } catch (e: any) {
      onToast(e.message || 'Could not start background job');
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 no-print">
        <div>
          <h1 className="text-xl font-bold text-fg-primary">Last-Night Cram Sheet</h1>
          <p className="text-sm text-fg-secondary">High-density printable revision guide for {course.title}.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={loading}
            onClick={handleGenerate}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-accent hover:bg-accent-hover text-white inline-flex items-center gap-1.5"
          >
            <Sparkles className="w-3.5 h-3.5" /> {loading ? 'Generating...' : 'Generate'}
          </button>
          <button
            type="button"
            onClick={handleFullAsync}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface border border-border-def hover:bg-subtle text-fg-primary"
          >
            Full Syllabus (Async)
          </button>
          <button
            type="button"
            onClick={() => window.print()}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface border border-border-def hover:bg-subtle text-fg-primary inline-flex items-center gap-1.5"
          >
            <Printer className="w-3.5 h-3.5" /> Print A4
          </button>
          <a
            href={`/api/courses/${course.id}/cram-sheet/download`}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface border border-border-def hover:bg-subtle text-fg-primary inline-flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" /> .md
          </a>
        </div>
      </div>

      {jobStatus && (
        <div className="p-3 rounded-lg bg-accent-soft text-accent-text text-xs font-medium no-print">{jobStatus}</div>
      )}

      <div id="cram-sheet-print-root" className="p-6 rounded-xl bg-surface border border-border-def">
        {markdown ? (
          <MarkdownView markdown={markdown} />
        ) : (
          <p className="text-sm text-fg-muted text-center py-10">
            Click <strong>Generate</strong> to build your printable last-night cram sheet.
          </p>
        )}
      </div>
    </div>
  );
};

interface SettingsViewProps {
  onToast: (msg: string) => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({ onToast }) => {
  const [geminiKey, setGeminiKey] = useState('');
  const [groqKey, setGroqKey] = useState('');
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434');
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.getSettings().then(setStatus).catch(() => setStatus(null));
  }, []);

  const handleSaveKeys = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload: Record<string, string> = {};
    if (geminiKey.trim()) payload.GEMINI_API_KEY = geminiKey.trim();
    if (groqKey.trim()) payload.GROQ_API_KEY = groqKey.trim();
    if (ollamaUrl.trim()) payload.OLLAMA_BASE_URL = ollamaUrl.trim();
    try {
      await api.saveKeys(payload);
      setGeminiKey('');
      setGroqKey('');
      onToast('API keys saved to .env (live immediately — no restart needed)');
      api.getSettings().then(setStatus).catch(() => {});
    } catch (err: any) {
      onToast(err.message || 'Could not save keys');
    }
  };

  const handleTest = async (provider: string) => {
    try {
      const res = await api.testConnection(provider, undefined, provider === 'ollama' ? ollamaUrl : undefined);
      onToast(res.message);
    } catch (err: any) {
      onToast(err.message || `${provider} test failed`);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-fg-primary">Settings & Backups</h1>
        <p className="text-sm text-fg-secondary">Manage BYOK AI providers, local Ollama, and verified SQLite backups.</p>
      </div>

      <form onSubmit={handleSaveKeys} className="p-5 rounded-xl bg-surface border border-border-def space-y-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-fg-primary">
          <Key className="w-4 h-4 text-accent-text" /> AI Providers (Stored in .env with 0600 permissions)
        </div>
        <div className="space-y-3">
          <div className="flex gap-2">
            <input
              type="password"
              value={geminiKey}
              onChange={(e) => setGeminiKey(e.target.value)}
              placeholder={status?.gemini_configured ? 'Gemini Key configured (paste to replace)' : 'GEMINI_API_KEY'}
              className="flex-1 px-3 py-2 text-xs rounded-lg bg-canvas border border-border-def text-fg-primary"
            />
            <button type="button" onClick={() => handleTest('gemini')} className="px-3 py-2 rounded-lg text-xs bg-subtle border border-border-def text-fg-primary">
              Test
            </button>
          </div>
          <div className="flex gap-2">
            <input
              type="password"
              value={groqKey}
              onChange={(e) => setGroqKey(e.target.value)}
              placeholder={status?.groq_configured ? 'Groq Key configured (paste to replace)' : 'GROQ_API_KEY'}
              className="flex-1 px-3 py-2 text-xs rounded-lg bg-canvas border border-border-def text-fg-primary"
            />
            <button type="button" onClick={() => handleTest('groq')} className="px-3 py-2 rounded-lg text-xs bg-subtle border border-border-def text-fg-primary">
              Test
            </button>
          </div>
          <div className="flex gap-2">
            <input
              type="url"
              value={ollamaUrl}
              onChange={(e) => setOllamaUrl(e.target.value)}
              placeholder="http://localhost:11434"
              className="flex-1 px-3 py-2 text-xs rounded-lg bg-canvas border border-border-def text-fg-primary"
            />
            <button type="button" onClick={() => handleTest('ollama')} className="px-3 py-2 rounded-lg text-xs bg-subtle border border-border-def text-fg-primary">
              Test Ollama
            </button>
          </div>
        </div>
        <button type="submit" className="px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-white text-xs font-semibold inline-flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5" /> Save Keys
        </button>
      </form>

      <div className="p-5 rounded-xl bg-surface border border-border-def space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-fg-primary">
          <Database className="w-4 h-4 text-emerald-600" /> Storage & Verified SQLite Backups
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            href="/api/settings/backup"
            target="_blank"
            rel="noopener noreferrer"
            className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-accent hover:bg-accent-hover text-white inline-flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" /> Download Verified SQLite Backup
          </a>
          <button
            type="button"
            onClick={() => api.cleanupCache().then((r) => onToast(r.message)).catch((e) => onToast(e.message))}
            className="px-3.5 py-2 rounded-lg text-xs font-medium bg-subtle border border-border-def text-fg-primary"
          >
            Clean Media & Expired Cache
          </button>
          <button
            type="button"
            onClick={() => api.vacuumDb().then((r) => onToast(r.message)).catch((e) => onToast(e.message))}
            className="px-3.5 py-2 rounded-lg text-xs font-medium bg-subtle border border-border-def text-fg-primary"
          >
            Vacuum SQLite DB
          </button>
        </div>
      </div>
    </div>
  );
};
