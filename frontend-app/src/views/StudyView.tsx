import React, { useEffect, useRef, useState } from 'react';
import {
  Camera,
  CheckCircle2,
  Circle,
  Flame,
  MessageSquare,
  MoreHorizontal,
  Play,
  RefreshCw,
  Send,
  Sparkles,
  BookOpen,
  HelpCircle,
  FileText,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Allocation, api, Course, PYQItem, QAItem, QuizResponse, ScheduleResponse } from '../api/client';
import { MarkdownView } from '../components/MarkdownView';
import { YouTubePlayer } from '../components/YouTubePlayer';

interface StudyViewProps {
  course: Course;
  schedule: ScheduleResponse | null;
  activeAlloc: Allocation | null;
  onSelectAlloc: (alloc: Allocation) => void;
  onScheduleChanged: (sched: ScheduleResponse) => void;
  onToast: (msg: string, withUndo?: boolean) => void;
}

export const StudyView: React.FC<StudyViewProps> = ({
  course,
  schedule,
  activeAlloc,
  onSelectAlloc,
  onScheduleChanged,
  onToast,
}) => {
  const [notesTab, setNotesTab] = useState<'guide' | 'personal' | 'split'>('guide');
  const [rightTab, setRightTab] = useState<'qa' | 'practice' | 'pyq'>('qa');
  const [videoCollapsed, setVideoCollapsed] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const [guideMarkdown, setGuideMarkdown] = useState('');
  const [personalNotes, setPersonalNotes] = useState('');
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [loadingNotes, setLoadingNotes] = useState(false);

  const [seekReq, setSeekReq] = useState<{ sec: number; nonce: number } | null>(null);

  // Ask AI state
  const [qaScope, setQaScope] = useState<'lesson' | 'course'>('lesson');
  const [qaHistory, setQaHistory] = useState<QAItem[]>([]);
  const [qaInput, setQaInput] = useState('');
  const [qaLoading, setQaLoading] = useState(false);

  // Practice Quiz state
  const [quiz, setQuiz] = useState<QuizResponse | null>(null);
  const [quizAnswers, setQuizAnswers] = useState<Record<string, number>>({});
  const [quizResult, setQuizResult] = useState<Record<string, unknown> | null>(null);
  const [quizLoading, setQuizLoading] = useState(false);

  // PYQs state
  const [pyqs, setPyqs] = useState<PYQItem[]>([]);

  const saveTimerRef = useRef<number | null>(null);
  const pendingSaveRef = useRef<{ lessonId: string; text: string } | null>(null);

  // Flush any pending personal notes save cleanly on lesson switch or unmount
  const flushPersonalNotes = async () => {
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const pending = pendingSaveRef.current;
    if (pending) {
      pendingSaveRef.current = null;
      try {
        await api.savePersonalNotes(pending.lessonId, pending.text);
      } catch {
        /* ignore */
      }
    }
  };

  useEffect(() => {
    const ac = new AbortController();
    setMenuOpen(false);
    setQuiz(null);
    setQuizAnswers({});
    setQuizResult(null);

    if (!activeAlloc) {
      setGuideMarkdown('');
      setPersonalNotes('');
      setPyqs([]);
      return;
    }

    setLoadingNotes(true);
    api
      .getLessonNotes(activeAlloc.lesson_id, ac.signal)
      .then((n) => {
        setGuideMarkdown(n.content_markdown || '');
        setPersonalNotes(n.personal_notes || '');
        setSaveStatus('idle');
      })
      .catch((err) => {
        if (err.name !== 'AbortError') setGuideMarkdown('_No structured notes yet. Click **••• → Regenerate Guide** to generate._');
      })
      .finally(() => setLoadingNotes(false));

    api
      .listPYQs(course.id, activeAlloc.lesson_id)
      .then(setPyqs)
      .catch(() => setPyqs([]));

    return () => {
      ac.abort();
      void flushPersonalNotes();
    };
  }, [activeAlloc?.lesson_id, course.id]);

  useEffect(() => {
    const ac = new AbortController();
    api
      .getQAHistory(course.id, ac.signal)
      .then(setQaHistory)
      .catch(() => setQaHistory([]));
    return () => ac.abort();
  }, [course.id]);

  const handlePersonalNotesChange = (val: string) => {
    setPersonalNotes(val);
    if (!activeAlloc) return;
    const capturedLessonId = activeAlloc.lesson_id;
    pendingSaveRef.current = { lessonId: capturedLessonId, text: val };
    setSaveStatus('saving');
    if (saveTimerRef.current) window.clearTimeout(saveTimerRef.current);
    saveTimerRef.current = window.setTimeout(async () => {
      const p = pendingSaveRef.current;
      if (!p) return;
      pendingSaveRef.current = null;
      try {
        await api.savePersonalNotes(p.lessonId, p.text);
        setSaveStatus('saved');
      } catch {
        setSaveStatus('idle');
        onToast('Failed to save personal notes.');
      }
    }, 700);
  };

  const handleSeek = (sec: number) => {
    setVideoCollapsed(false);
    setSeekReq({ sec, nonce: Date.now() });
  };

  const handleToggleComplete = async () => {
    if (!activeAlloc) return;
    try {
      const updated = await api.toggleAllocation(course.id, activeAlloc.id);
      onScheduleChanged(updated);
      onToast(activeAlloc.is_completed ? 'Marked incomplete' : 'Lesson marked complete');
    } catch (e: any) {
      onToast(e.message || 'Could not update completion');
    }
  };

  const handleSnapFrame = async () => {
    if (!activeAlloc) return;
    try {
      onToast('Capturing keyframes...');
      await api.captureScreenshots(activeAlloc.lesson_id);
      const n = await api.regenerateLessonNotes(activeAlloc.lesson_id);
      setGuideMarkdown(n.content_markdown || '');
      onToast('Keyframes captured and embedded in notes');
    } catch (e: any) {
      onToast(e.message || 'Keyframe capture failed');
    }
  };

  const handleRegenerateGuide = async () => {
    if (!activeAlloc) return;
    setMenuOpen(false);
    setLoadingNotes(true);
    try {
      const n = await api.regenerateLessonNotes(activeAlloc.lesson_id);
      setGuideMarkdown(n.content_markdown || '');
      onToast('AI Study Guide regenerated');
    } catch (e: any) {
      onToast(e.message || 'Could not regenerate notes');
    } finally {
      setLoadingNotes(false);
    }
  };

  const handleTranscribe = async () => {
    if (!activeAlloc) return;
    setMenuOpen(false);
    try {
      onToast('Fetching lecture transcript...');
      await api.transcribeLesson(activeAlloc.lesson_id);
      const n = await api.regenerateLessonNotes(activeAlloc.lesson_id);
      setGuideMarkdown(n.content_markdown || '');
      onToast('Transcript ingested and notes refreshed');
    } catch (e: any) {
      onToast(e.message || 'Transcription failed');
    }
  };

  const handleSkip = async () => {
    if (!activeAlloc) return;
    setMenuOpen(false);
    try {
      const updated = await api.skipAllocation(course.id, activeAlloc.id);
      onScheduleChanged(updated);
      onToast('Lesson skipped and schedule reflowed', true);
    } catch (e: any) {
      onToast(e.message || 'Could not skip lesson');
    }
  };

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = qaInput.trim();
    if (!q || qaLoading) return;
    setQaLoading(true);
    setQaInput('');
    try {
      const ans = await api.askQuestion(course.id, q, qaScope === 'lesson' ? activeAlloc?.lesson_id : null);
      setQaHistory((prev) => [...prev, ans]);
    } catch (err: any) {
      onToast(err.message || 'Ask AI failed');
    } finally {
      setQaLoading(false);
    }
  };

  const handleSaveReplyToNotes = (markdownText: string) => {
    const next = (personalNotes ? personalNotes + '\n\n' : '') + `> **AI Note:**\n${markdownText}`;
    handlePersonalNotesChange(next);
    setNotesTab('personal');
    onToast('Saved AI reply to My Notes');
  };

  const handleGenerateQuiz = async () => {
    if (!activeAlloc) return;
    setQuizLoading(true);
    setQuizResult(null);
    setQuizAnswers({});
    try {
      const q = await api.generateQuiz(course.id, 'lesson', activeAlloc.lesson_id, 5);
      setQuiz(q);
    } catch (e: any) {
      onToast(e.message || 'Quiz generation failed');
    } finally {
      setQuizLoading(false);
    }
  };

  const handleSubmitQuiz = async () => {
    if (!quiz) return;
    setQuizLoading(true);
    try {
      const res = await api.submitQuiz(course.id, quiz.id, quizAnswers, 60);
      setQuizResult(res);
      onToast(`Quiz scored ${Math.round(Number(res.score || 0))}%`);
    } catch (e: any) {
      onToast(e.message || 'Quiz submission failed');
    } finally {
      setQuizLoading(false);
    }
  };

  const formatTime = (sec: number) => {
    const m = Math.floor((sec || 0) / 60);
    const s = Math.floor((sec || 0) % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  return (
    <div className="flex flex-col lg:flex-row h-full min-h-0 overflow-y-auto lg:overflow-hidden">
      {/* Left Queue Drawer */}
      <aside className="w-full lg:w-64 shrink-0 border-b lg:border-b-0 lg:border-r border-border-def bg-subtle/60 overflow-y-auto p-3">
        <div className="flex items-center justify-between mb-2 px-1">
          <span className="text-xs font-semibold uppercase tracking-wider text-fg-secondary">Study Queue</span>
          <span className="text-xs font-mono text-fg-muted">{course.playback_speed}x</span>
        </div>
        {!schedule || schedule.days.length === 0 ? (
          <p className="text-xs text-fg-muted p-2">No scheduled lessons yet. Add a source in Sources.</p>
        ) : (
          <div className="space-y-3">
            {schedule.days
              .filter((d) => d.allocations.length > 0)
              .map((day) => (
                <div key={day.date}>
                  <div className="text-xs font-medium text-fg-secondary px-1.5 mb-1 flex justify-between">
                    <span>
                      {day.day_name.slice(0, 3)}, {day.date.slice(5)}
                    </span>
                    <span className="font-mono text-fg-muted">{Math.round(day.total_minutes)}m</span>
                  </div>
                  <div className="space-y-1">
                    {day.allocations.map((alloc) => {
                      const isActive = activeAlloc?.id === alloc.id;
                      return (
                        <button
                          key={alloc.id}
                          type="button"
                          onClick={() => onSelectAlloc(alloc)}
                          className={`w-full text-left px-2.5 py-2 rounded-lg text-xs transition-colors flex items-start gap-2 border ${
                            isActive
                              ? 'bg-surface border-accent text-fg-primary shadow-xs font-medium'
                              : 'bg-transparent border-transparent hover:bg-surface/70 text-fg-secondary'
                          }`}
                        >
                          {alloc.is_completed ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                          ) : (
                            <Circle className="w-3.5 h-3.5 text-fg-muted shrink-0 mt-0.5" />
                          )}
                          <div className="min-w-0 flex-1">
                            <div className={`truncate ${alloc.is_completed ? 'line-through opacity-70' : ''}`}>
                              {alloc.lesson_title}
                            </div>
                            <div className="flex items-center gap-2 mt-0.5 text-[12px] text-fg-muted font-mono">
                              <span>{Math.round(alloc.effective_minutes)}m</span>
                              {(alloc.pyq_hit_count || 0) > 0 && (
                                <span className="inline-flex items-center gap-0.5 text-amber-600 dark:text-amber-400 font-sans">
                                  <Flame className="w-3 h-3" /> {alloc.pyq_hit_count} PYQ
                                </span>
                              )}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
          </div>
        )}
      </aside>

      {/* Center Study Canvas */}
      <section className="flex-1 flex flex-col min-w-0 lg:overflow-hidden bg-canvas">
        {/* Video Player */}
        <div className={`px-4 pt-3 shrink-0 transition-all ${videoCollapsed ? 'h-10' : 'h-60 sm:h-72'}`}>
          {videoCollapsed ? (
            <button
              type="button"
              onClick={() => setVideoCollapsed(false)}
              className="w-full h-full flex items-center justify-center gap-2 text-xs font-medium text-fg-secondary bg-subtle rounded-lg border border-border-def hover:bg-surface"
            >
              <ChevronDown className="w-4 h-4" /> Show Video Player
            </button>
          ) : (
            <div className="relative w-full h-full">
              <YouTubePlayer
                videoId={activeAlloc?.video_id}
                startSec={activeAlloc?.allocated_start_sec || 0}
                playbackSpeed={course.playback_speed}
                seekRequest={seekReq}
              />
              <button
                type="button"
                aria-label="Collapse video player"
                onClick={() => setVideoCollapsed(true)}
                className="absolute top-2 right-2 px-2 py-1 rounded bg-black/70 text-white text-xs inline-flex items-center gap-1 hover:bg-black"
              >
                <ChevronUp className="w-3.5 h-3.5" /> Hide
              </button>
            </div>
          )}
        </div>

        {/* Clean 3-Action Lesson Header */}
        <div className="px-4 py-3 border-b border-border-def flex items-center justify-between gap-3 shrink-0">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-fg-primary truncate">
              {activeAlloc?.lesson_title || 'Select a lesson'}
            </h2>
            {activeAlloc && (
              <span className="text-xs font-mono text-fg-muted">
                {formatTime(activeAlloc.allocated_start_sec)} – {formatTime(activeAlloc.allocated_end_sec)}
              </span>
            )}
          </div>
          {activeAlloc && (
            <div className="flex items-center gap-2 shrink-0 relative">
              <button
                type="button"
                onClick={handleToggleComplete}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-accent hover:bg-accent-hover text-white inline-flex items-center gap-1.5"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                {activeAlloc.is_completed ? 'Completed' : 'Complete'}
              </button>
              <button
                type="button"
                onClick={handleSnapFrame}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface border border-border-def hover:bg-subtle text-fg-primary inline-flex items-center gap-1.5"
              >
                <Camera className="w-3.5 h-3.5" /> Snap Frame
              </button>
              <button
                type="button"
                aria-label="More lesson actions"
                onClick={() => setMenuOpen((o) => !o)}
                className="p-1.5 rounded-lg bg-surface border border-border-def hover:bg-subtle text-fg-primary"
              >
                <MoreHorizontal className="w-4 h-4" />
              </button>
              {menuOpen && (
                <div className="absolute right-0 top-10 z-30 w-48 rounded-lg bg-surface border border-border-def shadow-lg py-1 text-xs">
                  <button
                    type="button"
                    onClick={handleRegenerateGuide}
                    className="w-full text-left px-3 py-2 hover:bg-subtle text-fg-primary flex items-center gap-2"
                  >
                    <RefreshCw className="w-3.5 h-3.5" /> Regenerate AI Guide
                  </button>
                  <button
                    type="button"
                    onClick={handleTranscribe}
                    className="w-full text-left px-3 py-2 hover:bg-subtle text-fg-primary flex items-center gap-2"
                  >
                    <FileText className="w-3.5 h-3.5" /> Re-Transcribe Lesson
                  </button>
                  <button
                    type="button"
                    onClick={handleSkip}
                    className="w-full text-left px-3 py-2 hover:bg-subtle text-red-600 dark:text-red-400 flex items-center gap-2"
                  >
                    Skip & Reflow Schedule
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Unified Notes Canvas: [AI Study Guide | My Notes | Split] */}
        <div className="px-4 py-2 border-b border-border-def flex items-center justify-between bg-subtle/40 shrink-0">
          <div role="tablist" className="inline-flex rounded-lg bg-subtle p-0.5 border border-border-def">
            {(['guide', 'personal', 'split'] as const).map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={notesTab === t}
                type="button"
                onClick={() => setNotesTab(t)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                  notesTab === t ? 'bg-surface text-fg-primary shadow-xs' : 'text-fg-secondary hover:text-fg-primary'
                }`}
              >
                {t === 'guide' ? 'AI Study Guide' : t === 'personal' ? 'My Notes' : 'Split View'}
              </button>
            ))}
          </div>
          {saveStatus !== 'idle' && (
            <span className="text-xs text-fg-muted">
              {saveStatus === 'saving' ? 'Saving...' : 'Saved ✓'}
            </span>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {loadingNotes ? (
            <div className="text-sm text-fg-muted animate-pulse">Loading structured study notes...</div>
          ) : notesTab === 'guide' ? (
            <MarkdownView markdown={guideMarkdown} onSeekTimestamp={handleSeek} />
          ) : notesTab === 'personal' ? (
            <textarea
              value={personalNotes}
              onChange={(e) => handlePersonalNotesChange(e.target.value)}
              placeholder="Write your personal exam notes, formulas, or mnemonics here (auto-saved)..."
              className="w-full h-full min-h-[280px] bg-surface border border-border-def rounded-lg p-4 text-sm text-fg-primary leading-relaxed focus:outline-none focus:border-accent resize-none"
            />
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 h-full">
              <div className="overflow-y-auto pr-2">
                <MarkdownView markdown={guideMarkdown} onSeekTimestamp={handleSeek} />
              </div>
              <textarea
                value={personalNotes}
                onChange={(e) => handlePersonalNotesChange(e.target.value)}
                placeholder="Personal notes..."
                className="w-full min-h-[260px] bg-surface border border-border-def rounded-lg p-3.5 text-sm text-fg-primary focus:outline-none focus:border-accent resize-none"
              />
            </div>
          )}
        </div>
      </section>

      {/* Right Companion Panel (3 Focused Tabs: Ask AI, Practice, PYQs) */}
      <aside className="w-full lg:w-96 shrink-0 border-t lg:border-t-0 lg:border-l border-border-def bg-surface flex flex-col min-h-[420px] lg:min-h-0">
        <div role="tablist" className="grid grid-cols-3 border-b border-border-def p-1.5 gap-1 bg-subtle/40 shrink-0">
          {[
            { id: 'qa' as const, label: 'Ask AI', icon: MessageSquare },
            { id: 'practice' as const, label: 'Practice', icon: HelpCircle },
            { id: 'pyq' as const, label: `PYQs (${pyqs.length})`, icon: Flame },
          ].map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={rightTab === tab.id}
                type="button"
                onClick={() => setRightTab(tab.id)}
                className={`py-1.5 px-2 rounded-md text-xs font-medium inline-flex items-center justify-center gap-1.5 transition-colors ${
                  rightTab === tab.id ? 'bg-surface text-fg-primary shadow-xs border border-border-def' : 'text-fg-secondary hover:text-fg-primary'
                }`}
              >
                <Icon className="w-3.5 h-3.5" /> {tab.label}
              </button>
            );
          })}
        </div>

        {/* Tab 1: Ask AI */}
        {rightTab === 'qa' && (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="px-3 py-2 border-b border-border-def flex items-center justify-between text-xs">
              <span className="text-fg-secondary">Scope:</span>
              <div className="inline-flex rounded-md bg-subtle p-0.5 border border-border-def">
                {(['lesson', 'course'] as const).map((sc) => (
                  <button
                    key={sc}
                    type="button"
                    onClick={() => setQaScope(sc)}
                    className={`px-2.5 py-0.5 rounded text-xs font-medium ${
                      qaScope === sc ? 'bg-accent text-white' : 'text-fg-secondary'
                    }`}
                  >
                    {sc === 'lesson' ? 'This Lesson' : 'Whole Subject'}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {qaHistory.length === 0 ? (
                <div className="text-xs text-fg-muted text-center py-8 px-4">
                  <Sparkles className="w-5 h-5 mx-auto mb-2 text-accent-text" />
                  Ask anything about this lecture or your uploaded PDFs & articles. Citations link straight to video timestamps.
                </div>
              ) : (
                qaHistory.map((item) => (
                  <div key={item.id} className="space-y-2">
                    <div className="ml-6 rounded-lg bg-accent text-white px-3 py-2 text-xs">{item.query}</div>
                    <div className="mr-2 rounded-lg bg-subtle border border-border-def p-3 text-xs space-y-2">
                      <MarkdownView markdown={item.answer_markdown} onSeekTimestamp={handleSeek} className="!text-xs" />
                      <div className="flex items-center justify-between pt-1 border-t border-border-def/60">
                        <div className="flex flex-wrap gap-1">
                          {(item.citations || []).slice(0, 3).map((c, idx) => (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => c.start_sec != null && handleSeek(c.start_sec)}
                              className="px-1.5 py-0.5 rounded bg-accent-soft text-accent-text font-mono text-[12px]"
                            >
                              {c.timestamp_str || c.source_title?.slice(0, 18) || 'Source'}
                            </button>
                          ))}
                        </div>
                        <button
                          type="button"
                          onClick={() => handleSaveReplyToNotes(item.answer_markdown)}
                          className="text-accent-text hover:underline font-medium shrink-0 ml-2"
                        >
                          + Save to Notes
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
            <form onSubmit={handleAsk} className="p-3 border-t border-border-def flex gap-2">
              <input
                type="text"
                value={qaInput}
                onChange={(e) => setQaInput(e.target.value)}
                placeholder="Ask a question..."
                className="flex-1 px-3 py-2 text-xs rounded-lg bg-canvas border border-border-def text-fg-primary focus:outline-none focus:border-accent"
              />
              <button
                type="submit"
                disabled={qaLoading || !qaInput.trim()}
                aria-label="Send question"
                className="px-3 py-2 rounded-lg bg-accent hover:bg-accent-hover disabled:opacity-50 text-white"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </form>
          </div>
        )}

        {/* Tab 2: Practice Quiz */}
        {rightTab === 'practice' && (
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-fg-primary">Lesson Practice Quiz</span>
              <button
                type="button"
                disabled={!activeAlloc || quizLoading}
                onClick={handleGenerateQuiz}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-accent hover:bg-accent-hover disabled:opacity-50 text-white"
              >
                {quizLoading ? 'Generating...' : quiz ? 'New Quiz' : 'Generate Quiz'}
              </button>
            </div>
            {!quiz ? (
              <p className="text-xs text-fg-muted py-6 text-center">
                Generate a 5-question quiz grounded in this lesson. Missed answers link straight back to the video timestamp and create FSRS flashcards.
              </p>
            ) : (
              <div className="space-y-3">
                {quiz.questions.map((q, idx) => {
                  const chosen = quizAnswers[q.id];
                  const isSubmitted = quizResult !== null;
                  const isCorrect = isSubmitted && chosen === q.correct_index;
                  return (
                    <div key={q.id} className="p-3 rounded-lg bg-canvas border border-border-def space-y-2">
                      <div className="text-xs font-medium text-fg-primary">
                        {idx + 1}. {q.question}
                      </div>
                      <div className="space-y-1.5">
                        {q.options.map((opt, oi) => {
                          const selected = chosen === oi;
                          let cls = 'bg-surface border-border-def text-fg-primary hover:bg-subtle';
                          if (isSubmitted && oi === q.correct_index) {
                            cls = 'bg-emerald-600/15 border-emerald-600 text-fg-primary font-medium';
                          } else if (isSubmitted && selected && oi !== q.correct_index) {
                            cls = 'bg-red-600/15 border-red-600 text-fg-primary';
                          } else if (selected) {
                            cls = 'bg-accent-soft border-accent text-accent-text font-medium';
                          }
                          return (
                            <button
                              key={oi}
                              type="button"
                              disabled={isSubmitted}
                              onClick={() => setQuizAnswers((prev) => ({ ...prev, [q.id]: oi }))}
                              className={`w-full text-left px-2.5 py-1.5 rounded-md border text-xs transition-colors ${cls}`}
                            >
                              {opt}
                            </button>
                          );
                        })}
                      </div>
                      {isSubmitted && (
                        <div className="pt-1.5 text-xs text-fg-secondary border-t border-border-def space-y-1">
                          <div className={isCorrect ? 'text-emerald-600 font-medium' : 'text-red-600 dark:text-red-400 font-medium'}>
                            {isCorrect ? 'Correct' : 'Missed — review explanation:'}
                          </div>
                          <p>{q.explanation}</p>
                          {!isCorrect && q.timestamp_sec != null && (
                            <button
                              type="button"
                              onClick={() => handleSeek(q.timestamp_sec!)}
                              className="inline-flex items-center gap-1 px-2 py-1 rounded bg-accent-soft text-accent-text font-mono text-xs font-medium"
                            >
                              <Play className="w-3 h-3" /> Replay Explanation {q.timestamp_str || formatTime(q.timestamp_sec)}
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
                {!quizResult && (
                  <button
                    type="button"
                    onClick={handleSubmitQuiz}
                    disabled={quizLoading}
                    className="w-full py-2 rounded-lg bg-accent hover:bg-accent-hover text-white text-xs font-semibold"
                  >
                    Submit Answers
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* Tab 3: PYQs */}
        {rightTab === 'pyq' && (
          <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
            {pyqs.length === 0 ? (
              <div className="text-xs text-fg-muted text-center py-8">
                <BookOpen className="w-5 h-5 mx-auto mb-2 opacity-60" />
                No matched past exam questions for this lesson yet.
              </div>
            ) : (
              pyqs.map((p) => (
                <div key={p.id} className="p-3 rounded-lg bg-canvas border border-border-def space-y-1.5">
                  <div className="flex items-center justify-between text-xs text-fg-muted">
                    <span>{p.paper_title || 'Past Paper'}</span>
                    {p.marks ? <span className="font-mono font-semibold text-amber-600">{p.marks}M</span> : null}
                  </div>
                  <p className="text-xs text-fg-primary leading-relaxed">{p.question_text}</p>
                  <button
                    type="button"
                    onClick={() => {
                      setRightTab('qa');
                      setQaInput(`Solve this university exam question step-by-step: ${p.question_text}`);
                    }}
                    className="text-xs text-accent-text hover:underline font-medium"
                  >
                    Ask AI to Solve →
                  </button>
                </div>
              ))
            )}
          </div>
        )}
      </aside>
    </div>
  );
};
