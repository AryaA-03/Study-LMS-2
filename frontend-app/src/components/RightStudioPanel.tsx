import React, { useEffect, useRef, useState } from 'react';
import {
  BookmarkPlus,
  CheckCircle2,
  FileUp,
  Flame,
  Layers,
  Loader2,
  Play,
  Plus,
  RotateCcw,
  Save,
  Send,
  Sparkles,
  Pencil,
  Trash2,
  XCircle,
} from 'lucide-react';
import {
  api,
  Flashcard,
  Lesson,
  PYQItem,
  PYQSummary,
  QAItem,
  Quiz,
  QuizSubmitResult,
} from '../api/client';
import { formatSecToPill, MarkdownView } from './MarkdownView';

export type StudioTab = 'notes' | 'quiz' | 'flashcards' | 'ask' | 'pyqs';

interface RightStudioPanelProps {
  courseId: string;
  activeLesson: Lesson | null;
  activeTab: StudioTab;
  onTabChange: (tab: StudioTab) => void;
  width: number;
  personalNotes: string;
  onSavePersonalNotes: (text: string) => Promise<void>;
  onAppendToPersonalNotes: (snippet: string) => Promise<void>;
  onSeekTimestamp: (sec: number) => void;
  externalAskPrompt: { text: string; ts: number } | null;
  onScheduleChanged: () => void;
  onToast: (msg: string) => void;
}

export const RightStudioPanel: React.FC<RightStudioPanelProps> = ({
  courseId,
  activeLesson,
  activeTab,
  onTabChange,
  width,
  personalNotes,
  onSavePersonalNotes,
  onAppendToPersonalNotes,
  onSeekTimestamp,
  externalAskPrompt,
  onScheduleChanged,
  onToast,
}) => {
  // My Notes state
  const [myNotesDraft, setMyNotesDraft] = useState(personalNotes);
  const [savingNotes, setSavingNotes] = useState(false);

  // Ask AI state
  const [qaScope, setQaScope] = useState<'lesson' | 'course'>('lesson');
  const [qaHistory, setQaHistory] = useState<QAItem[]>([]);
  const [qaInput, setQaInput] = useState('');
  const [askingAi, setAskingAi] = useState(false);

  // Quiz state
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [quizLoading, setQuizLoading] = useState(false);
  const [quizAnswers, setQuizAnswers] = useState<Record<string, number>>({});
  const [shortAnswers, setShortAnswers] = useState<Record<string, string>>({});
  const [quizResult, setQuizResult] = useState<QuizSubmitResult | null>(null);

  // Flashcards state (moved right here to the Right Studio!)
  const [cards, setCards] = useState<Flashcard[]>([]);
  const [dueOnly, setDueOnly] = useState(false);
  const [cardIndex, setCardIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [cardsLoading, setCardsLoading] = useState(false);
  const [showNewCard, setShowNewCard] = useState(false);
  const [newFront, setNewFront] = useState('');
  const [newBack, setNewBack] = useState('');
  const [editingCardId, setEditingCardId] = useState<string | null>(null);

  // PYQs state
  const [pyqSummary, setPyqSummary] = useState<PYQSummary>({ papers: [], questions: [] });
  const [lessonPyqs, setLessonPyqs] = useState<PYQItem[]>([]);
  const [pyqScope, setPyqScope] = useState<'lesson' | 'course'>('lesson');
  const [pyqPasteText, setPyqPasteText] = useState('');
  const [pyqPasteTitle, setPyqPasteTitle] = useState('');
  const [pyqUploading, setPyqUploading] = useState(false);

  useEffect(() => {
    setMyNotesDraft(personalNotes);
  }, [personalNotes, activeLesson?.id]);

  // Load QA history
  useEffect(() => {
    if (!courseId) return;
    const ctrl = new AbortController();
    api
      .getQAHistory(courseId, ctrl.signal)
      .then((rows) => setQaHistory(Array.isArray(rows) ? rows : []))
      .catch(() => {});
    return () => ctrl.abort();
  }, [courseId]);

  // Trigger external Highlight-to-Explain prompt
  useEffect(() => {
    if (!externalAskPrompt?.text) return;
    onTabChange('ask');
    handleAskAI(`Explain this simply with an example: "${externalAskPrompt.text}"`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [externalAskPrompt?.ts]);

  // Load flashcards when tab active or course/filter changes
  const refreshCards = async () => {
    if (!courseId) return;
    setCardsLoading(true);
    try {
      const list = await api.listFlashcards(courseId, dueOnly);
      setCards(list || []);
      setCardIndex(0);
      setFlipped(false);
    } catch {
      // ignore
    } finally {
      setCardsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'flashcards') {
      refreshCards();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, courseId, dueOnly]);

  // Load PYQs when tab active
  const refreshPyqs = async () => {
    if (!courseId) return;
    try {
      const summary = await api.getPyqSummary(courseId);
      setPyqSummary(summary || { papers: [], questions: [] });
      if (activeLesson?.id) {
        const lq = await api.getLessonPyqs(courseId, activeLesson.id);
        setLessonPyqs(Array.isArray(lq) ? lq : []);
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    if (activeTab === 'pyqs') {
      refreshPyqs();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, courseId, activeLesson?.id]);

  const autoGenQuizRef = useRef<string | null>(null);
  const autoGenCardsRef = useRef<string | null>(null);

  // Reset quiz when lesson changes
  useEffect(() => {
    setQuiz(null);
    setQuizAnswers({});
    setQuizResult(null);
  }, [activeLesson?.id]);

  // Auto-load or auto-generate Quiz when user opens the Quiz tab (no manual click needed!)
  useEffect(() => {
    if (activeTab !== 'quiz' || !courseId || !activeLesson?.id || quiz || quizLoading) return;
    const key = `${courseId}:${activeLesson.id}`;
    if (autoGenQuizRef.current === key) return;
    autoGenQuizRef.current = key;
    setQuizLoading(true);
    api
      .listQuizzes(courseId, 'lesson', activeLesson.id)
      .then((existing) => {
        if (existing && existing.length > 0 && existing[0].questions?.length > 0) {
          setQuiz(existing[0]);
          return null;
        }
        return api.generateQuiz(courseId, { quiz_type: 'lesson', lesson_id: activeLesson.id, question_count: 5 });
      })
      .then((created) => {
        if (created) setQuiz(created);
      })
      .catch(() => {})
      .finally(() => setQuizLoading(false));
  }, [activeTab, courseId, activeLesson?.id, quiz, quizLoading]);

  // Auto-generate FSRS Flashcards when user opens Flashcards tab and deck is empty!
  useEffect(() => {
    if (activeTab !== 'flashcards' || !courseId || !activeLesson?.id || cardsLoading) return;
    if (cards.length > 0 || dueOnly) return;
    const key = `${courseId}:${activeLesson.id}`;
    if (autoGenCardsRef.current === key) return;
    autoGenCardsRef.current = key;
    api
      .generateLessonFlashcards(courseId, activeLesson.id)
      .then((created) => {
        if (created && created.length > 0) setCards(created);
      })
      .catch(() => {});
  }, [activeTab, courseId, activeLesson?.id, cards.length, cardsLoading, dueOnly]);

  const handleSaveNotes = async () => {
    if (!activeLesson) return;
    setSavingNotes(true);
    try {
      await onSavePersonalNotes(myNotesDraft);
      onToast('Saved personal notes');
    } finally {
      setSavingNotes(false);
    }
  };

  const handleAskAI = async (customPrompt?: string) => {
    const q = (customPrompt ?? qaInput).trim();
    if (!q || !courseId) return;
    setAskingAi(true);
    if (!customPrompt) setQaInput('');
    try {
      const res = await api.askQuestion(courseId, q, qaScope, activeLesson?.id);
      setQaHistory((prev) => [res, ...prev]);
    } catch (e: any) {
      onToast(`Ask AI error: ${e.message}`);
    } finally {
      setAskingAi(false);
    }
  };

  const handleGenerateQuiz = async () => {
    if (!courseId || !activeLesson) return;
    setQuizLoading(true);
    setQuizResult(null);
    setQuizAnswers({});
    try {
      const q = await api.generateQuiz(courseId, {
        quiz_type: 'lesson',
        lesson_id: activeLesson.id,
        question_count: 5,
      });
      setQuiz(q);
    } catch (e: any) {
      onToast(`Quiz error: ${e.message}`);
    } finally {
      setQuizLoading(false);
    }
  };

  const handleSubmitQuiz = async () => {
    if (!courseId || !quiz) return;
    setQuizLoading(true);
    try {
      const res = await api.submitQuiz(courseId, quiz.id, quizAnswers, shortAnswers);
      setQuizResult(res);
      if (res.schedule_updated) onScheduleChanged();
      if ((res.flashcards_created || 0) > 0) {
        onToast(`Added ${res.flashcards_created} missed concept(s) to FSRS Flashcards`);
      }
    } catch (e: any) {
      onToast(`Submit error: ${e.message}`);
    } finally {
      setQuizLoading(false);
    }
  };

  const handleGenerateLessonCards = async () => {
    if (!courseId || !activeLesson) return;
    setCardsLoading(true);
    try {
      const created = await api.generateLessonFlashcards(courseId, activeLesson.id);
      onToast(`Generated ${created.length} flashcards for this lesson`);
      await refreshCards();
    } catch (e: any) {
      onToast(`Flashcard error: ${e.message}`);
    } finally {
      setCardsLoading(false);
    }
  };

  const handleReviewCard = async (rating: 1 | 2 | 3 | 4) => {
    const card = cards[cardIndex];
    if (!card) return;
    try {
      await api.reviewFlashcard(courseId, card.id, rating);
      setFlipped(false);
      if (cardIndex + 1 < cards.length) {
        setCardIndex(cardIndex + 1);
      } else {
        await refreshCards();
        onToast('Deck review round complete!');
      }
    } catch (e: any) {
      onToast(`Review error: ${e.message}`);
    }
  };

  const handleCreateCard = async () => {
    if (!newFront.trim() || !newBack.trim()) return;
    try {
      if (editingCardId) {
        await api.updateFlashcard(courseId, editingCardId, {
          front: newFront.trim(),
          back: newBack.trim(),
        });
        onToast('Flashcard updated');
      } else {
        await api.createFlashcard(courseId, {
          front: newFront.trim(),
          back: newBack.trim(),
          lesson_id: activeLesson?.id,
        });
        onToast('Flashcard created');
      }
      setNewFront('');
      setNewBack('');
      setEditingCardId(null);
      setShowNewCard(false);
      await refreshCards();
    } catch (e: any) {
      onToast(`Error: ${e.message}`);
    }
  };

  const handlePyqFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPyqUploading(true);
    try {
      await api.uploadPyqFile(courseId, file, file.name);
      await refreshPyqs();
      onScheduleChanged();
      onToast('PYQ paper parsed & matched to syllabus');
    } catch (err: any) {
      onToast(`PYQ upload failed: ${err.message}`);
    } finally {
      setPyqUploading(false);
      e.target.value = '';
    }
  };

  const handlePyqTextSubmit = async () => {
    if (!pyqPasteText.trim()) return;
    setPyqUploading(true);
    try {
      await api.uploadPyqText(courseId, pyqPasteTitle.trim() || 'Past Exam Paper', pyqPasteText.trim());
      setPyqPasteText('');
      setPyqPasteTitle('');
      await refreshPyqs();
      onScheduleChanged();
      onToast('PYQ questions matched to your lessons');
    } catch (err: any) {
      onToast(`PYQ error: ${err.message}`);
    } finally {
      setPyqUploading(false);
    }
  };

  const currentCard = cards[cardIndex];
  const visiblePyqs = pyqScope === 'lesson' ? lessonPyqs : pyqSummary.questions || [];

  return (
    <aside
      style={{ width }}
      className="no-print flex h-full shrink-0 flex-col overflow-hidden bg-[var(--bg-sidebar)]"
    >
      {/* Top Tabs Bar (matches image_23084c.jpg, image_235a7d.jpg, image_235a84.jpg!) */}
      <div className="flex items-center border-b border-[var(--border-subtle)] bg-[var(--bg-sidebar)] px-2 pt-2">
        {([
          { id: 'notes', label: 'My Notes' },
          { id: 'quiz', label: 'Quiz' },
          { id: 'flashcards', label: 'Flashcards' },
          { id: 'ask', label: 'Ask AI' },
          { id: 'pyqs', label: 'PYQs' },
        ] as const).map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onTabChange(t.id)}
            className={`relative flex-1 pb-2.5 text-center text-xs font-semibold transition ${
              activeTab === t.id
                ? 'text-[var(--fg-primary)]'
                : 'text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
            }`}
          >
            {t.label}
            {activeTab === t.id && (
              <span className="absolute bottom-0 left-1 right-1 h-0.5 rounded-full bg-[var(--accent)]" />
            )}
          </button>
        ))}
      </div>

      {/* TAB 1: MY NOTES */}
      {activeTab === 'notes' && (
        <div className="flex flex-1 flex-col overflow-hidden p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold text-[var(--fg-primary)]">
              Personal Scratchpad {activeLesson ? `• ${activeLesson.title.slice(0, 26)}` : ''}
            </span>
            <button
              type="button"
              onClick={handleSaveNotes}
              disabled={savingNotes || !activeLesson}
              className="inline-flex items-center gap-1 rounded-md bg-[var(--accent)] px-2.5 py-1 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
            >
              {savingNotes ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
              Save
            </button>
          </div>
          <textarea
            value={myNotesDraft}
            onChange={(e) => setMyNotesDraft(e.target.value)}
            placeholder={
              activeLesson
                ? 'Write your own exam notes, mnemonics, or click "Save to My Notes" from Ask AI...'
                : 'Select a lesson from the left rail to take notes.'
            }
            disabled={!activeLesson}
            className="flex-1 resize-none rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 font-mono text-xs leading-relaxed text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
          />
        </div>
      )}

      {/* TAB 2: QUIZ (with wrong-answer [MM:SS] video jump!) */}
      {activeTab === 'quiz' && (
        <div className="flex flex-1 flex-col overflow-y-auto p-3 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xs font-bold text-[var(--fg-primary)]">Active Recall Quiz</h3>
              <p className="text-[11px] text-[var(--fg-secondary)]">
                Wrong answers jump straight to the exact video clip & add FSRS flashcards.
              </p>
            </div>
            <button
              type="button"
              onClick={handleGenerateQuiz}
              disabled={quizLoading || !activeLesson}
              className="inline-flex items-center gap-1 rounded-lg bg-[var(--accent)] px-2.5 py-1.5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
            >
              {quizLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              {quiz ? 'New Quiz' : 'Generate'}
            </button>
          </div>

          {quizResult && (
            <div className="rounded-xl border border-[var(--border-strong)] bg-[var(--bg-card)] p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-[var(--fg-primary)]">
                  Score: {Math.round(quizResult.score)}% ({quizResult.correct_count}/{quizResult.total_questions})
                </span>
                <span className="rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-bold uppercase text-[var(--accent-text)]">
                  {quizResult.mastery_status || 'reviewed'}
                </span>
              </div>
            </div>
          )}

          {!quiz ? (
            <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border-strong)] p-6 text-center">
              <p className="text-xs text-[var(--fg-secondary)]">
                {activeLesson
                  ? 'Generate a 5-question grounded quiz for this lesson.'
                  : 'Select a lesson to start a quiz.'}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {quiz.questions.map((q, idx) => {
                const chosenIdx = quizAnswers[q.id];
                const isGraded = !!quizResult;
                const isCorrectAnswer = isGraded && chosenIdx === q.correct_index;
                const ts = q.timestamp_sec ?? q.source_timestamp_sec;
                return (
                  <div
                    key={q.id}
                    className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2 text-xs font-semibold text-[var(--fg-primary)]">
                      <span>
                        {idx + 1}. {q.question || q.question_text}
                      </span>
                      {ts !== undefined && ts !== null && (
                        <button
                          type="button"
                          onClick={() => onSeekTimestamp(ts)}
                          className="ts-pill shrink-0"
                          title="Jump to lecture timestamp"
                        >
                          ▶ {formatSecToPill(ts)}
                        </button>
                      )}
                    </div>

                    {q.question_type === 'short_answer' ? (
                      <textarea
                        rows={3}
                        disabled={!!quizResult}
                        value={shortAnswers[q.id] || ''}
                        onChange={(e) => setShortAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                        placeholder="Write your concise exam answer here..."
                        className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-2 text-xs text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
                      />
                    ) : (
                    <div className="space-y-1.5">
                      {(q.options || []).map((opt, oIdx) => {
                        const chosen = quizAnswers[q.id] === oIdx;
                        const isCorrectOpt = isGraded && q.correct_index === oIdx;
                        const isWrongChosen = isGraded && chosen && !isCorrectAnswer;
                        return (
                          <button
                            key={oIdx}
                            type="button"
                            disabled={!!quizResult}
                            onClick={() => setQuizAnswers((prev) => ({ ...prev, [q.id]: oIdx }))}
                            className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left text-xs transition ${
                              isCorrectOpt
                                ? 'border-[var(--success)] bg-[var(--success)]/10 text-[var(--fg-primary)] font-semibold'
                                : isWrongChosen
                                ? 'border-[var(--danger)] bg-[var(--danger)]/10 text-[var(--fg-primary)]'
                                : chosen
                                ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent-text)] font-medium'
                                : 'border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-[var(--fg-primary)] hover:border-[var(--border-strong)]'
                            }`}
                          >
                            <span className="font-mono text-[10px] font-bold opacity-70">
                              {String.fromCharCode(65 + oIdx)}
                            </span>
                            <span className="flex-1">{opt}</span>
                            {isCorrectOpt && <CheckCircle2 className="h-3.5 w-3.5 text-[var(--success)]" />}
                            {isWrongChosen && <XCircle className="h-3.5 w-3.5 text-[var(--danger)]" />}
                          </button>
                        );
                      })}
                    </div>
                    )}

                    {isGraded && (
                      <div className="rounded-lg bg-[var(--bg-elevated)] p-2 text-[11px] text-[var(--fg-secondary)] space-y-1">
                        <p>{q.explanation || (isCorrectAnswer ? 'Correct!' : 'Review this concept in the lecture clip below.')}</p>
                        {!isCorrectAnswer && ts !== undefined && ts !== null && (
                          <button
                            type="button"
                            onClick={() => onSeekTimestamp(ts)}
                            className="inline-flex items-center gap-1 rounded bg-[var(--accent)] px-2 py-0.5 text-[11px] font-semibold text-white"
                          >
                            <Play className="h-3 w-3" /> Watch Explanation at {formatSecToPill(ts)}
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
                  disabled={quizLoading || (Object.keys(quizAnswers).length === 0 && Object.keys(shortAnswers).length === 0)}
                  className="w-full rounded-lg bg-[var(--accent)] py-2 text-xs font-bold text-white hover:opacity-90 disabled:opacity-50"
                >
                  Submit & Grade Quiz
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: FLASHCARDS (FSRS right inside the Studio!) */}
      {activeTab === 'flashcards' && (
        <div className="flex flex-1 flex-col overflow-y-auto p-3 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-1.5">
            <div className="flex rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] p-0.5 text-[11px]">
              <button
                type="button"
                onClick={() => setDueOnly(false)}
                className={`rounded-md px-2 py-0.5 font-semibold ${
                  !dueOnly ? 'bg-[var(--accent)] text-white' : 'text-[var(--fg-secondary)]'
                }`}
              >
                All ({cards.length})
              </button>
              <button
                type="button"
                onClick={() => setDueOnly(true)}
                className={`rounded-md px-2 py-0.5 font-semibold ${
                  dueOnly ? 'bg-[var(--accent)] text-white' : 'text-[var(--fg-secondary)]'
                }`}
              >
                Due Now
              </button>
            </div>

            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleGenerateLessonCards}
                disabled={cardsLoading || !activeLesson}
                className="inline-flex items-center gap-1 rounded-md bg-[var(--accent)] px-2 py-1 text-[11px] font-semibold text-white hover:opacity-90 disabled:opacity-50"
                title="Auto-generate FSRS cards from active lesson"
              >
                <Sparkles className="h-3 w-3" /> Auto-Gen
              </button>
              <button
                type="button"
                onClick={() => setShowNewCard((s) => !s)}
                className="inline-flex items-center gap-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-[11px] font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
              >
                <Plus className="h-3 w-3" /> Add
              </button>
            </div>
          </div>

          {showNewCard && (
            <div className="rounded-xl border border-[var(--border-strong)] bg-[var(--bg-card)] p-3 space-y-2">
              <input
                value={newFront}
                onChange={(e) => setNewFront(e.target.value)}
                placeholder="Front (Question / Term)"
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-xs text-[var(--fg-primary)] outline-none"
              />
              <textarea
                value={newBack}
                onChange={(e) => setNewBack(e.target.value)}
                placeholder="Back (Answer / Formula)"
                rows={3}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1.5 text-xs text-[var(--fg-primary)] outline-none"
              />
              <button
                type="button"
                onClick={handleCreateCard}
                className="w-full rounded-lg bg-[var(--accent)] py-1.5 text-xs font-semibold text-white"
              >
                Save Flashcard
              </button>
            </div>
          )}

          {cardsLoading ? (
            <div className="flex flex-1 items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-[var(--accent)]" />
            </div>
          ) : currentCard ? (
            <div className="flex flex-1 flex-col justify-between space-y-3">
              <div className="text-center text-[11px] text-[var(--fg-muted)]">
                Card {cardIndex + 1} of {cards.length}
              </div>

              <div
                onClick={() => setFlipped((f) => !f)}
                className="flex min-h-[210px] cursor-pointer flex-col justify-between rounded-xl border border-[var(--border-strong)] bg-[var(--bg-card)] p-4 shadow-sm transition hover:border-[var(--accent)]"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--accent)]">
                    {flipped ? 'Answer' : 'Question — Tap to Flip'}
                  </span>
                  <div className="flex items-center gap-1">
                    {currentCard.source_timestamp_sec !== undefined && currentCard.source_timestamp_sec !== null && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSeekTimestamp(currentCard.source_timestamp_sec!);
                        }}
                        className="ts-pill"
                      >
                        ▶ {formatSecToPill(currentCard.source_timestamp_sec)}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingCardId(currentCard.id);
                        setNewFront(currentCard.front);
                        setNewBack(currentCard.back);
                        setShowNewCard(true);
                      }}
                      className="rounded p-1 text-[var(--fg-muted)] hover:text-[var(--accent)]"
                      title="Edit card"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={async (e) => {
                        e.stopPropagation();
                        await api.deleteFlashcard(courseId, currentCard.id);
                        await refreshCards();
                      }}
                      className="rounded p-1 text-[var(--fg-muted)] hover:text-[var(--danger)]"
                      title="Delete card"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                <div className="my-4 text-sm font-medium leading-relaxed text-[var(--fg-primary)]">
                  {flipped ? currentCard.back : currentCard.front}
                </div>

                <div className="flex items-center justify-center gap-1 text-[10px] text-[var(--fg-muted)]">
                  <RotateCcw className="h-3 w-3" /> Click card to flip
                </div>
              </div>

              {flipped ? (
                <div className="grid grid-cols-4 gap-1.5">
                  {([
                    { r: 1, label: 'Again', cls: 'bg-red-500/15 text-red-600 dark:text-red-300 border-red-500/30' },
                    { r: 2, label: 'Hard', cls: 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30' },
                    { r: 3, label: 'Good', cls: 'bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30' },
                    { r: 4, label: 'Easy', cls: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30' },
                  ] as const).map((b) => (
                    <button
                      key={b.r}
                      type="button"
                      onClick={() => handleReviewCard(b.r)}
                      className={`rounded-lg border py-2 text-xs font-bold transition hover:opacity-85 ${b.cls}`}
                    >
                      {b.label}
                    </button>
                  ))}
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setFlipped(true)}
                  className="w-full rounded-lg bg-[var(--accent)] py-2 text-xs font-bold text-white"
                >
                  Show Answer
                </button>
              )}
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border-strong)] p-6 text-center space-y-2">
              <Layers className="h-7 w-7 text-[var(--fg-muted)]" />
              <p className="text-xs text-[var(--fg-secondary)]">
                No flashcards yet. Click <strong>Auto-Gen</strong> to build FSRS cards from this lesson, or miss a quiz question to auto-create review cards!
              </p>
            </div>
          )}
        </div>
      )}

      {/* TAB 4: ASK AI (This Lesson vs Notebook + Save to My Notes + Quick Chips!) */}
      {activeTab === 'ask' && (
        <div className="flex flex-1 flex-col overflow-hidden p-3">
          {/* Scope Toggle (matches image_2308a9.jpg & image_235a7d.jpg!) */}
          <div className="mb-2.5 grid grid-cols-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setQaScope('lesson')}
              className={`rounded-md py-1.5 font-semibold transition ${
                qaScope === 'lesson'
                  ? 'bg-[var(--accent)] text-white shadow-sm'
                  : 'text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
              }`}
            >
              This Lesson
            </button>
            <button
              type="button"
              onClick={() => setQaScope('course')}
              className={`rounded-md py-1.5 font-semibold transition ${
                qaScope === 'course'
                  ? 'bg-[var(--accent)] text-white shadow-sm'
                  : 'text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]'
              }`}
            >
              Notebook
            </button>
          </div>

          {/* Q&A Feed */}
          <div className="flex-1 space-y-3 overflow-y-auto pr-0.5">
            {askingAi && (
              <div className="flex items-center gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 text-xs text-[var(--fg-secondary)]">
                <Loader2 className="h-4 w-4 animate-spin text-[var(--accent)]" />
                Searching grounded transcripts & notes...
              </div>
            )}

            {qaHistory.length === 0 && !askingAi ? (
              <div className="rounded-xl border border-dashed border-[var(--border-strong)] p-5 text-center text-xs text-[var(--fg-secondary)]">
                Ask anything about {qaScope === 'lesson' ? 'this lecture' : 'your entire course notebook'}. Answers cite exact `[MM:SS]` video timestamps.
              </div>
            ) : (
              qaHistory.map((item, idx) => (
                <div
                  key={item.id || idx}
                  className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-3 space-y-2 shadow-sm"
                >
                  <div className="rounded-lg bg-[var(--bg-elevated)] px-2.5 py-1.5 text-xs font-semibold text-[var(--fg-primary)]">
                    {item.query || item.question}
                  </div>
                  <MarkdownView
                    markdown={item.answer_markdown || item.answer || ''}
                    onSeekTimestamp={onSeekTimestamp}
                    className="text-[13px]"
                  />
                  {item.citations && item.citations.filter((c) => c.start_sec !== undefined && c.start_sec !== null).length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-1">
                      {item.citations.filter((c) => c.start_sec !== undefined && c.start_sec !== null).map((c, ci) => (
                        <button
                          key={ci}
                          type="button"
                          onClick={() => onSeekTimestamp(c.start_sec || 0)}
                          className="ts-pill"
                        >
                          ▶ {c.timestamp_label || formatSecToPill(c.start_sec)}
                        </button>
                      ))}
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={async () => {
                      await onAppendToPersonalNotes(`\n\n### Q: ${item.query || item.question}\n${item.answer_markdown || item.answer || ''}\n`);
                      onToast('Saved AI answer to My Notes');
                    }}
                    className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] py-1.5 text-xs font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]"
                  >
                    <BookmarkPlus className="h-3.5 w-3.5 text-[var(--accent)]" />
                    Save to My Notes
                  </button>
                </div>
              ))
            )}
          </div>

          {/* Bottom Input + Quick Prompt Chips (matches image_235a7d.jpg!) */}
          <div className="mt-2.5 space-y-1.5 border-t border-[var(--border-subtle)] pt-2.5">
            <div className="flex items-center gap-1.5">
              <input
                value={qaInput}
                onChange={(e) => setQaInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleAskAI();
                  }
                }}
                placeholder="Ask a question..."
                className="flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] px-3 py-2 text-xs text-[var(--fg-primary)] outline-none focus:border-[var(--accent)]"
              />
              <button
                type="button"
                onClick={() => handleAskAI()}
                disabled={askingAi || !qaInput.trim()}
                className="inline-flex items-center gap-1 rounded-lg bg-[var(--accent)] px-3 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
              >
                <Send className="h-3.5 w-3.5" /> Ask
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {['Explain simply', 'Give an example', 'Exam traps', 'Key formulas'].map((chip) => (
                <button
                  key={chip}
                  type="button"
                  onClick={() => handleAskAI(chip)}
                  className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-card)] px-2 py-1 text-[11px] font-medium text-[var(--fg-secondary)] hover:border-[var(--accent)] hover:text-[var(--fg-primary)]"
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: PYQs (Past Exam Paper Matcher) */}
      {activeTab === 'pyqs' && (
        <div className="flex flex-1 flex-col overflow-y-auto p-3 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] p-0.5 text-[11px]">
              <button
                type="button"
                onClick={() => setPyqScope('lesson')}
                className={`rounded-md px-2 py-0.5 font-semibold ${
                  pyqScope === 'lesson' ? 'bg-[var(--accent)] text-white' : 'text-[var(--fg-secondary)]'
                }`}
              >
                This Lesson ({lessonPyqs.length})
              </button>
              <button
                type="button"
                onClick={() => setPyqScope('course')}
                className={`rounded-md px-2 py-0.5 font-semibold ${
                  pyqScope === 'course' ? 'bg-[var(--accent)] text-white' : 'text-[var(--fg-secondary)]'
                }`}
              >
                All ({pyqSummary.questions?.length || 0})
              </button>
            </div>

            <label className="inline-flex cursor-pointer items-center gap-1 rounded-md bg-[var(--accent)] px-2.5 py-1 text-[11px] font-semibold text-white hover:opacity-90">
              {pyqUploading ? <Loader2 className="h-3 w-3 animate-spin" /> : <FileUp className="h-3 w-3" />}
              Upload PDF
              <input type="file" accept=".pdf,.txt" className="hidden" onChange={handlePyqFileUpload} />
            </label>
          </div>

          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-2.5 space-y-1.5">
            <input
              value={pyqPasteTitle}
              onChange={(e) => setPyqPasteTitle(e.target.value)}
              placeholder="Paper title (e.g. End-Sem 2024)"
              className="w-full rounded border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2 py-1 text-xs text-[var(--fg-primary)] outline-none"
            />
            <textarea
              value={pyqPasteText}
              onChange={(e) => setPyqPasteText(e.target.value)}
              rows={2}
              placeholder="Or paste past exam questions (one per line) to auto-tag high-yield lessons..."
              className="w-full rounded border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2 py-1 text-xs text-[var(--fg-primary)] outline-none"
            />
            <button
              type="button"
              onClick={handlePyqTextSubmit}
              disabled={pyqUploading || !pyqPasteText.trim()}
              className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--bg-elevated)] py-1 text-xs font-semibold text-[var(--fg-primary)] hover:bg-[var(--bg-hover)] disabled:opacity-50"
            >
              Match Past Questions to Syllabus
            </button>
          </div>

          <div className="space-y-2">
            {visiblePyqs.length === 0 ? (
              <p className="py-4 text-center text-xs text-[var(--fg-secondary)]">
                No past exam questions matched yet. Upload a PYQ PDF or paste questions above.
              </p>
            ) : (
              visiblePyqs.map((q) => (
                <div
                  key={q.id}
                  className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-2.5 text-xs space-y-1"
                >
                  <div className="flex items-center justify-between text-[10px] font-bold text-[var(--warning)]">
                    <span className="inline-flex items-center gap-1">
                      <Flame className="h-3 w-3" /> {q.question_number || 'PYQ'} {q.marks ? `• ${q.marks} Marks` : ''}
                    </span>
                    <span className="text-[var(--fg-muted)]">{q.paper_title}</span>
                  </div>
                  <p className="text-[var(--fg-primary)] leading-snug">{q.question_text}</p>
                  {q.matched_lesson_title && (
                    <div className="text-[10px] text-[var(--accent-text)]">
                      Matched: {q.matched_lesson_title}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </aside>
  );
};
