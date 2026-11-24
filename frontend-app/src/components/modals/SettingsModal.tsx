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
      await api.saveSettings({
        ollama_base_url: ollamaUrl,
        ollama_model: ollamaModel,
        whisper_model: whisperModel,
      });
      const keyUpdates: Record<string, string> = {};
      if (geminiKey.trim()) keyUpdates.GEMINI_API_KEY = geminiKey.trim();
      if (groqKey.trim()) keyUpdates.GROQ_API_KEY = groqKey.trim();
      if (openrouterKey.trim()) keyUpdates.OPENROUTER_API_KEY = openrouterKey.trim();
      if (Object.keys(keyUpdates).length > 0) {
        await api.saveApiKeys(keyUpdates);
      }
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
      const provider =
        geminiKey.trim() || settings.has_gemini_key
          ? 'gemini'
          : groqKey.trim() || settings.has_groq_key
          ? 'groq'
          : openrouterKey.trim() || settings.has_openrouter_key
          ? 'openrouter'
          : 'ollama';
      const res = await api.testConnection(provider);
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
                Gemini API Key {settings.has_gemini_key && <CheckCircle2 className="inline h-3 w-3 text-[var(--success)]" />}
              </label>
              <input
                type="password"
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder={settings.has_gemini_key ? '•••••••• (saved)' : 'AIza...'}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[var(--fg-secondary)]">
                Groq API Key {settings.has_groq_key && <CheckCircle2 className="inline h-3 w-3 text-[var(--success)]" />}
              </label>
              <input
                type="password"
                value={groqKey}
                onChange={(e) => setGroqKey(e.target.value)}
                placeholder={settings.has_groq_key ? '•••••••• (saved)' : 'gsk_...'}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)]"
              />
            </div>
            <div>
              <label className="mb-1 block text-[var(--fg-secondary)]">
                OpenRouter Key {settings.has_openrouter_key && <CheckCircle2 className="inline h-3 w-3 text-[var(--success)]" />}
              </label>
              <input
                type="password"
                value={openrouterKey}
                onChange={(e) => setOpenrouterKey(e.target.value)}
                placeholder={settings.has_openrouter_key ? '•••••••• (saved)' : 'sk-or-...'}
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
