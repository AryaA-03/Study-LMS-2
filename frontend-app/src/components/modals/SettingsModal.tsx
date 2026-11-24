import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Database,
  Download,
  FileText,
  Globe,
  Key,
  Layers,
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
import { ModalShell } from './ModalShell';

const OPENROUTER_PRESETS = [
  { label: 'Auto Free Router', id: 'openrouter/free', badge: 'Free' },
  { label: 'Gemma 4 31B', id: 'google/gemma-4-31b-it:free', badge: 'Free' },
  { label: 'DeepSeek V3', id: 'deepseek/deepseek-chat', badge: 'Low Cost' },
  { label: 'Claude 3.5 Sonnet', id: 'anthropic/claude-3.5-sonnet', badge: 'High Quota' },
  { label: 'GPT-4o', id: 'openai/gpt-4o', badge: 'Flagship' },
  { label: 'Llama 3.3 70B', id: 'meta-llama/llama-3.3-70b-instruct', badge: 'Open' },
];

const GEMINI_PRESETS = [
  { label: 'Gemini 2.5 Flash', id: 'gemini-2.5-flash', badge: 'Recommended' },
  { label: 'Gemini 1.5 Flash', id: 'gemini-1.5-flash', badge: 'Fast' },
  { label: 'Gemini 1.5 Pro', id: 'gemini-1.5-pro', badge: 'Reasoning' },
  { label: 'Gemini 2.0 Flash Exp', id: 'gemini-2.0-flash-exp', badge: 'Preview' },
];

const GROQ_PRESETS = [
  { label: 'Llama 3.3 70B', id: 'llama-3.3-70b-versatile', badge: 'Ultra-fast' },
  { label: 'Llama 3.1 8B', id: 'llama-3.1-8b-instant', badge: 'Instant' },
  { label: 'Mixtral 8x7B', id: 'mixtral-8x7b-32768', badge: 'MoE' },
];

const OLLAMA_PRESETS = [
  { label: 'Llama 3.2', id: 'llama3.2', badge: 'Local 3B' },
  { label: 'Mistral 7B', id: 'mistral', badge: 'Local 7B' },
  { label: 'DeepSeek R1 8B', id: 'deepseek-r1:8b', badge: 'Reasoning' },
  { label: 'Qwen 2.5 7B', id: 'qwen2.5:7b', badge: 'Local 7B' },
];

export const SettingsModal: React.FC<{
  courseId: string | null;
  onClose: () => void;
  onToast: (msg: string) => void;
}> = ({ courseId, onClose, onToast }) => {
  const [settings, setSettings] = useState<SystemSettings>({});
  const [activeProvider, setActiveProvider] = useState('openrouter');
  const [geminiModel, setGeminiModel] = useState('gemini-2.5-flash');
  const [openrouterModel, setOpenrouterModel] = useState('openrouter/free');
  const [groqModel, setGroqModel] = useState('llama-3.3-70b-versatile');
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434');
  const [ollamaModel, setOllamaModel] = useState('llama3.2');
  const [whisperModel, setWhisperModel] = useState('base');
  const [geminiKey, setGeminiKey] = useState('');
  const [groqKey, setGroqKey] = useState('');
  const [openrouterKey, setOpenrouterKey] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .getSettings()
      .then((s) => {
        setSettings(s || {});
        if (s.active_llm_provider) setActiveProvider(s.active_llm_provider);
        if (s.gemini_model) setGeminiModel(s.gemini_model);
        if (s.openrouter_model) setOpenrouterModel(s.openrouter_model);
        if (s.groq_model) setGroqModel(s.groq_model);
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
        active_llm_provider: activeProvider,
        gemini_model: geminiModel.trim(),
        groq_model: groqModel.trim(),
        openrouter_model: openrouterModel.trim(),
        ollama_base_url: ollamaUrl,
        ollama_model: ollamaModel,
        whisper_model: whisperModel,
      });
      const keyUpdates: Record<string, string> = {
        ACTIVE_LLM_PROVIDER: activeProvider,
        GEMINI_MODEL: geminiModel.trim(),
        GROQ_MODEL: groqModel.trim(),
        OPENROUTER_MODEL: openrouterModel.trim(),
        OLLAMA_MODEL: ollamaModel.trim(),
      };
      if (geminiKey.trim()) keyUpdates.GEMINI_API_KEY = geminiKey.trim();
      if (groqKey.trim()) keyUpdates.GROQ_API_KEY = groqKey.trim();
      if (openrouterKey.trim()) keyUpdates.OPENROUTER_API_KEY = openrouterKey.trim();
      await api.saveApiKeys(keyUpdates);

      const activeModelName =
        activeProvider === 'openrouter'
          ? openrouterModel
          : activeProvider === 'gemini'
          ? geminiModel
          : activeProvider === 'groq'
          ? groqModel
          : ollamaModel;

      onToast(`Saved! Active provider: ${activeProvider.toUpperCase()} (${activeModelName})`);
      setGeminiKey('');
      setGroqKey('');
      setOpenrouterKey('');
      const updated = await api.getSettings();
      setSettings(updated || {});
    } catch (e: any) {
      onToast(`Error: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleTestProvider = async (provider: string, modelOverride?: string) => {
    setBusy(true);
    try {
      const model =
        modelOverride ||
        (provider === 'openrouter'
          ? openrouterModel.trim()
          : provider === 'gemini'
          ? geminiModel.trim()
          : provider === 'groq'
          ? groqModel.trim()
          : ollamaModel.trim());
      const key =
        provider === 'openrouter'
          ? openrouterKey.trim() || undefined
          : provider === 'gemini'
          ? geminiKey.trim() || undefined
          : provider === 'groq'
          ? groqKey.trim() || undefined
          : undefined;
      const res = await api.testConnection(provider, key, model);
      onToast(res.message || (res.success ? `${provider.toUpperCase()} connection verified!` : 'Connection test failed'));
    } catch (e: any) {
      onToast(`Test failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  // Determine current active model name for header
  const currentActiveModel =
    activeProvider === 'openrouter'
      ? openrouterModel
      : activeProvider === 'gemini'
      ? geminiModel
      : activeProvider === 'groq'
      ? groqModel
      : ollamaModel;

  return (
    <ModalShell
      title="Settings, AI Keys & Models"
      subtitle="Select active AI provider, switch models, manage API keys, and configure offline Whisper & Ollama."
      onClose={onClose}
      wide
    >
      <div className="space-y-5 text-xs">
        {/* Section 1: Active Provider & Model Chooser */}
        <div className="rounded-xl border-2 border-[var(--accent)] bg-[var(--bg-card)] p-4 space-y-3.5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] pb-2.5">
            <div>
              <span className="text-[11px] font-bold uppercase tracking-wider text-[var(--accent)]">
                Active AI Engine
              </span>
              <h3 className="text-sm font-semibold text-[var(--fg-primary)] flex items-center gap-1.5 mt-0.5">
                <Sparkles className="h-4 w-4 text-[var(--accent)]" />
                Using: <span className="font-mono text-xs px-2 py-0.5 rounded bg-[var(--accent-subtle)] text-[var(--accent)]">{activeProvider.toUpperCase()}</span>
                <span className="text-xs text-[var(--fg-muted)] font-mono">({currentActiveModel})</span>
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleTestProvider(activeProvider !== 'auto' ? activeProvider : 'openrouter')}
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] px-3 py-1.5 font-semibold text-[var(--fg-primary)] hover:border-[var(--accent)] transition"
              >
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Zap className="h-3.5 w-3.5 text-[var(--accent)]" />}
                Test Active Engine
              </button>
            </div>
          </div>

          {/* Provider Selection Tabs */}
          <div>
            <label className="mb-1.5 block font-semibold text-[var(--fg-secondary)]">
              Choose Active Provider:
            </label>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {[
                { id: 'openrouter', label: 'OpenRouter', badge: settings.has_openrouter_key ? '✓ Key' : 'No Key' },
                { id: 'gemini', label: 'Google Gemini', badge: settings.has_gemini_key ? '✓ Key' : 'No Key' },
                { id: 'groq', label: 'Groq', badge: settings.has_groq_key ? '✓ Key' : 'No Key' },
                { id: 'ollama', label: 'Ollama', badge: 'Local' },
                { id: 'auto', label: 'Auto (Fallback)', badge: 'Chain' },
              ].map((p) => {
                const isSelected = activeProvider === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setActiveProvider(p.id)}
                    className={`flex flex-col items-start rounded-lg border p-2 text-left transition ${
                      isSelected
                        ? 'border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)] font-bold ring-1 ring-[var(--accent)]'
                        : 'border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-[var(--fg-primary)] hover:border-[var(--border-strong)]'
                    }`}
                  >
                    <span className="text-xs">{p.label}</span>
                    <span className={`text-[10px] mt-0.5 ${isSelected ? 'text-[var(--accent)]' : 'text-[var(--fg-muted)]'}`}>
                      {p.badge}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Active Model Selector for the selected Provider */}
          <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3 space-y-2">
            <div className="flex items-center justify-between">
              <label className="font-semibold text-[var(--fg-primary)]">
                Active Model for {activeProvider.toUpperCase()}:
              </label>
              <span className="text-[10px] text-[var(--fg-muted)]">
                Click a preset below or type any custom model
              </span>
            </div>

            {activeProvider === 'openrouter' && (
              <div className="space-y-2">
                <input
                  type="text"
                  value={openrouterModel}
                  onChange={(e) => setOpenrouterModel(e.target.value)}
                  placeholder="e.g. openrouter/free or google/gemma-4-31b-it:free"
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                />
                <div className="flex flex-wrap gap-1.5">
                  {OPENROUTER_PRESETS.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => setOpenrouterModel(m.id)}
                      className={`rounded-md px-2 py-1 text-[11px] border transition ${
                        openrouterModel === m.id
                          ? 'border-[var(--accent)] bg-[var(--accent)] text-white font-semibold'
                          : 'border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)] hover:border-[var(--border-strong)]'
                      }`}
                    >
                      {m.label} <span className="opacity-75 text-[9px]">({m.badge})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {activeProvider === 'gemini' && (
              <div className="space-y-2">
                <input
                  type="text"
                  value={geminiModel}
                  onChange={(e) => setGeminiModel(e.target.value)}
                  placeholder="e.g. gemini-2.5-flash"
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                />
                <div className="flex flex-wrap gap-1.5">
                  {GEMINI_PRESETS.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => setGeminiModel(m.id)}
                      className={`rounded-md px-2 py-1 text-[11px] border transition ${
                        geminiModel === m.id
                          ? 'border-[var(--accent)] bg-[var(--accent)] text-white font-semibold'
                          : 'border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)] hover:border-[var(--border-strong)]'
                      }`}
                    >
                      {m.label} <span className="opacity-75 text-[9px]">({m.badge})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {activeProvider === 'groq' && (
              <div className="space-y-2">
                <input
                  type="text"
                  value={groqModel}
                  onChange={(e) => setGroqModel(e.target.value)}
                  placeholder="e.g. llama-3.3-70b-versatile"
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                />
                <div className="flex flex-wrap gap-1.5">
                  {GROQ_PRESETS.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => setGroqModel(m.id)}
                      className={`rounded-md px-2 py-1 text-[11px] border transition ${
                        groqModel === m.id
                          ? 'border-[var(--accent)] bg-[var(--accent)] text-white font-semibold'
                          : 'border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)] hover:border-[var(--border-strong)]'
                      }`}
                    >
                      {m.label} <span className="opacity-75 text-[9px]">({m.badge})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {activeProvider === 'ollama' && (
              <div className="space-y-2">
                <input
                  type="text"
                  value={ollamaModel}
                  onChange={(e) => setOllamaModel(e.target.value)}
                  placeholder="e.g. llama3.2"
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                />
                <div className="flex flex-wrap gap-1.5">
                  {OLLAMA_PRESETS.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => setOllamaModel(m.id)}
                      className={`rounded-md px-2 py-1 text-[11px] border transition ${
                        ollamaModel === m.id
                          ? 'border-[var(--accent)] bg-[var(--accent)] text-white font-semibold'
                          : 'border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)] hover:border-[var(--border-strong)]'
                      }`}
                    >
                      {m.label} <span className="opacity-75 text-[9px]">({m.badge})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {activeProvider === 'auto' && (
              <div className="text-[11px] text-[var(--fg-muted)] py-1">
                Auto mode dynamically routes calls: Gemini ({geminiModel}) → Groq ({groqModel}) → OpenRouter ({openrouterModel}) → Ollama ({ollamaModel}).
              </div>
            )}
          </div>
        </div>

        {/* Section 2: Configured Providers & Keys (Cards) */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-[var(--fg-primary)] flex items-center gap-1.5">
              <Key className="h-3.5 w-3.5 text-[var(--accent)]" />
              Provider Credentials & Saved Models (.env)
            </h3>
            <span className="text-[10px] text-[var(--fg-muted)]">
              All keys stay saved locally. Leaving a key field blank keeps your existing key intact.
            </span>
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {/* OpenRouter Card */}
            <div className={`rounded-xl border p-3.5 space-y-2.5 transition ${
              activeProvider === 'openrouter' ? 'border-[var(--accent)] bg-[var(--bg-card)] ring-1 ring-[var(--accent)]' : 'border-[var(--border-subtle)] bg-[var(--bg-card)]'
            }`}>
              <div className="flex items-center justify-between">
                <span className="font-bold text-[var(--fg-primary)] flex items-center gap-1">
                  OpenRouter
                  {settings.has_openrouter_key && (
                    <span className="inline-flex items-center gap-0.5 text-[10px] text-[var(--success)] font-medium">
                      <CheckCircle2 className="h-3 w-3" /> Key Saved
                    </span>
                  )}
                </span>
                <div className="flex items-center gap-1.5">
                  {activeProvider !== 'openrouter' ? (
                    <button
                      type="button"
                      onClick={() => setActiveProvider('openrouter')}
                      className="text-[10px] px-2 py-0.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[var(--fg-primary)]"
                    >
                      Set Active
                    </button>
                  ) : (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-[var(--accent-subtle)] text-[var(--accent)] font-bold">
                      ACTIVE
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => handleTestProvider('openrouter')}
                    disabled={busy}
                    className="text-[10px] px-2 py-0.5 rounded border border-[var(--border-strong)] bg-[var(--bg-elevated)] hover:border-[var(--accent)] text-[var(--fg-primary)]"
                  >
                    Test
                  </button>
                </div>
              </div>

              <div>
                <label className="mb-1 block text-[11px] text-[var(--fg-secondary)]">
                  API Key:
                </label>
                <input
                  type="password"
                  value={openrouterKey}
                  onChange={(e) => setOpenrouterKey(e.target.value)}
                  placeholder={settings.has_openrouter_key ? '•••••••••••••••• (saved in .env)' : 'sk-or-v1-...'}
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                />
              </div>

              <div>
                <label className="mb-1 block text-[11px] text-[var(--fg-secondary)]">
                  Model Slug:
                </label>
                <input
                  type="text"
                  value={openrouterModel}
                  onChange={(e) => setOpenrouterModel(e.target.value)}
                  placeholder="e.g. openrouter/free"
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                />
              </div>
            </div>

            {/* Google Gemini Card */}
            <div className={`rounded-xl border p-3.5 space-y-2.5 transition ${
              activeProvider === 'gemini' ? 'border-[var(--accent)] bg-[var(--bg-card)] ring-1 ring-[var(--accent)]' : 'border-[var(--border-subtle)] bg-[var(--bg-card)]'
            }`}>
              <div className="flex items-center justify-between">
                <span className="font-bold text-[var(--fg-primary)] flex items-center gap-1">
                  Google Gemini
                  {settings.has_gemini_key && (
                    <span className="inline-flex items-center gap-0.5 text-[10px] text-[var(--success)] font-medium">
                      <CheckCircle2 className="h-3 w-3" /> Key Saved
                    </span>
                  )}
                </span>
                <div className="flex items-center gap-1.5">
                  {activeProvider !== 'gemini' ? (
                    <button
                      type="button"
                      onClick={() => setActiveProvider('gemini')}
                      className="text-[10px] px-2 py-0.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[var(--fg-primary)]"
                    >
                      Set Active
                    </button>
                  ) : (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-[var(--accent-subtle)] text-[var(--accent)] font-bold">
                      ACTIVE
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => handleTestProvider('gemini')}
                    disabled={busy}
                    className="text-[10px] px-2 py-0.5 rounded border border-[var(--border-strong)] bg-[var(--bg-elevated)] hover:border-[var(--accent)] text-[var(--fg-primary)]"
                  >
                    Test
                  </button>
                </div>
              </div>

              <div>
                <label className="mb-1 block text-[11px] text-[var(--fg-secondary)]">
                  API Key:
                </label>
                <input
                  type="password"
                  value={geminiKey}
                  onChange={(e) => setGeminiKey(e.target.value)}
                  placeholder={settings.has_gemini_key ? '•••••••••••••••• (saved in .env)' : 'AIzaSy...'}
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                />
              </div>

              <div>
                <label className="mb-1 block text-[11px] text-[var(--fg-secondary)]">
                  Model Slug:
                </label>
                <input
                  type="text"
                  value={geminiModel}
                  onChange={(e) => setGeminiModel(e.target.value)}
                  placeholder="e.g. gemini-2.5-flash"
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                />
              </div>
            </div>

            {/* Groq Card */}
            <div className={`rounded-xl border p-3.5 space-y-2.5 transition ${
              activeProvider === 'groq' ? 'border-[var(--accent)] bg-[var(--bg-card)] ring-1 ring-[var(--accent)]' : 'border-[var(--border-subtle)] bg-[var(--bg-card)]'
            }`}>
              <div className="flex items-center justify-between">
                <span className="font-bold text-[var(--fg-primary)] flex items-center gap-1">
                  Groq
                  {settings.has_groq_key && (
                    <span className="inline-flex items-center gap-0.5 text-[10px] text-[var(--success)] font-medium">
                      <CheckCircle2 className="h-3 w-3" /> Key Saved
                    </span>
                  )}
                </span>
                <div className="flex items-center gap-1.5">
                  {activeProvider !== 'groq' ? (
                    <button
                      type="button"
                      onClick={() => setActiveProvider('groq')}
                      className="text-[10px] px-2 py-0.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[var(--fg-primary)]"
                    >
                      Set Active
                    </button>
                  ) : (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-[var(--accent-subtle)] text-[var(--accent)] font-bold">
                      ACTIVE
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => handleTestProvider('groq')}
                    disabled={busy}
                    className="text-[10px] px-2 py-0.5 rounded border border-[var(--border-strong)] bg-[var(--bg-elevated)] hover:border-[var(--accent)] text-[var(--fg-primary)]"
                  >
                    Test
                  </button>
                </div>
              </div>

              <div>
                <label className="mb-1 block text-[11px] text-[var(--fg-secondary)]">
                  API Key:
                </label>
                <input
                  type="password"
                  value={groqKey}
                  onChange={(e) => setGroqKey(e.target.value)}
                  placeholder={settings.has_groq_key ? '•••••••••••••••• (saved in .env)' : 'gsk_...'}
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                />
              </div>

              <div>
                <label className="mb-1 block text-[11px] text-[var(--fg-secondary)]">
                  Model Slug:
                </label>
                <input
                  type="text"
                  value={groqModel}
                  onChange={(e) => setGroqModel(e.target.value)}
                  placeholder="e.g. llama-3.3-70b-versatile"
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                />
              </div>
            </div>

            {/* Ollama & Local Whisper Card */}
            <div className={`rounded-xl border p-3.5 space-y-2.5 transition ${
              activeProvider === 'ollama' ? 'border-[var(--accent)] bg-[var(--bg-card)] ring-1 ring-[var(--accent)]' : 'border-[var(--border-subtle)] bg-[var(--bg-card)]'
            }`}>
              <div className="flex items-center justify-between">
                <span className="font-bold text-[var(--fg-primary)] flex items-center gap-1">
                  Ollama & Local Whisper
                </span>
                <div className="flex items-center gap-1.5">
                  {activeProvider !== 'ollama' ? (
                    <button
                      type="button"
                      onClick={() => setActiveProvider('ollama')}
                      className="text-[10px] px-2 py-0.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-elevated)] hover:bg-[var(--bg-hover)] text-[var(--fg-primary)]"
                    >
                      Set Active
                    </button>
                  ) : (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-[var(--accent-subtle)] text-[var(--accent)] font-bold">
                      ACTIVE
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => handleTestProvider('ollama')}
                    disabled={busy}
                    className="text-[10px] px-2 py-0.5 rounded border border-[var(--border-strong)] bg-[var(--bg-elevated)] hover:border-[var(--accent)] text-[var(--fg-primary)]"
                  >
                    Test
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-[11px] text-[var(--fg-secondary)]">Ollama Base URL:</label>
                  <input
                    value={ollamaUrl}
                    onChange={(e) => setOllamaUrl(e.target.value)}
                    className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-[11px] text-[var(--fg-secondary)]">Ollama Model:</label>
                  <input
                    value={ollamaModel}
                    onChange={(e) => setOllamaModel(e.target.value)}
                    className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)] font-mono text-xs"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-[11px] text-[var(--fg-secondary)]">Local Whisper Speech Model:</label>
                <select
                  value={whisperModel}
                  onChange={(e) => setWhisperModel(e.target.value)}
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-[var(--fg-primary)] font-medium"
                >
                  {['tiny', 'base', 'small', 'medium'].map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Action Row */}
          <div className="flex items-center gap-3 pt-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--accent)] px-5 py-2 font-semibold text-white shadow-sm hover:opacity-90 transition disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Save All Settings & Models
            </button>
          </div>
        </div>

        {/* Section 3: Data Portability & Storage Cleanup */}
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
