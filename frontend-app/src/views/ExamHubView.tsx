import React, { useEffect, useState } from 'react';
import { Layers, Clock, CheckCircle2, Trash2, RotateCcw } from 'lucide-react';
import { api, Course, Flashcard, QuizResponse } from '../api/client';

interface ExamHubViewProps {
  course: Course;
  onToast: (msg: string) => void;
}

export const ExamHubView: React.FC<ExamHubViewProps> = ({ course, onToast }) => {
  const [subTab, setSubTab] = useState<'flashcards' | 'diagnostic' | 'mock'>('flashcards');
  const [cards, setCards] = useState<Flashcard[]>([]);
  const [dueOnly, setDueOnly] = useState(true);
  const [cardIdx, setCardIdx] = useState(0);
  const [flipped, setFlipped] = useState(false);

  const [examQuiz, setExamQuiz] = useState<QuizResponse | null>(null);
  const [examAnswers, setExamAnswers] = useState<Record<string, number>>({});
  const [examResult, setExamResult] = useState<Record<string, unknown> | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const loadCards = () => {
    api
      .listFlashcards(course.id, dueOnly)
      .then((list) => {
        setCards(list);
        setCardIdx(0);
        setFlipped(false);
      })
      .catch(() => setCards([]));
  };

  useEffect(() => {
    loadCards();
  }, [course.id, dueOnly]);

  // Clean exam countdown timer — always cleared on unmount or tab change!
  useEffect(() => {
    if (secondsLeft === null || secondsLeft <= 0) return;
    const id = window.setInterval(() => {
      setSecondsLeft((s) => (s !== null && s > 0 ? s - 1 : 0));
    }, 1000);
    return () => window.clearInterval(id);
  }, [secondsLeft !== null]);

  // Context-aware Flashcard keyboard shortcuts (Space to flip, 1-4 to rate)
  useEffect(() => {
    if (subTab !== 'flashcards' || !cards[cardIdx]) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.code === 'Space') {
        e.preventDefault();
        setFlipped((f) => !f);
      } else if (flipped && ['1', '2', '3', '4'].includes(e.key)) {
        e.preventDefault();
        void handleRate(parseInt(e.key, 10));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [subTab, cards, cardIdx, flipped]);

  const handleRate = async (rating: number) => {
    const card = cards[cardIdx];
    if (!card) return;
    try {
      await api.reviewFlashcard(course.id, card.id, rating);
      setFlipped(false);
      if (cardIdx + 1 < cards.length) {
        setCardIdx((i) => i + 1);
      } else {
        loadCards();
        onToast('Flashcard session complete');
      }
    } catch (e: any) {
      onToast(e.message || 'Could not record review');
    }
  };

  const handleDeleteCard = async (cardId: string) => {
    try {
      await api.deleteFlashcard(course.id, cardId);
      onToast('Flashcard deleted');
      loadCards();
    } catch (e: any) {
      onToast(e.message || 'Could not delete card');
    }
  };

  const startExam = async (kind: 'diagnostic' | 'mock_exam') => {
    setLoading(true);
    setExamResult(null);
    setExamAnswers({});
    try {
      const q = await api.generateQuiz(course.id, kind, null, kind === 'diagnostic' ? 5 : 10);
      setExamQuiz(q);
      setSecondsLeft(kind === 'diagnostic' ? 180 : 900);
    } catch (e: any) {
      onToast(e.message || 'Could not generate exam');
    } finally {
      setLoading(false);
    }
  };

  const submitExam = async () => {
    if (!examQuiz) return;
    setLoading(true);
    setSecondsLeft(null);
    try {
      const res = await api.submitQuiz(course.id, examQuiz.id, examAnswers, 120);
      setExamResult(res);
      onToast(`Exam finished: ${Math.round(Number(res.score || 0))}%`);
    } catch (e: any) {
      onToast(e.message || 'Submission failed');
    } finally {
      setLoading(false);
    }
  };

  const activeCard = cards[cardIdx];

  return (
    <div className="h-full overflow-y-auto p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-fg-primary">Exam Prep Hub</h1>
          <p className="text-sm text-fg-secondary">Spaced-repetition FSRS flashcards, diagnostic test-out, and timed mock exams.</p>
        </div>
        <div role="tablist" className="inline-flex rounded-lg bg-subtle p-1 border border-border-def">
          {[
            { id: 'flashcards' as const, label: 'FSRS Flashcards', icon: Layers },
            { id: 'diagnostic' as const, label: 'Diagnostic Pre-Test', icon: CheckCircle2 },
            { id: 'mock' as const, label: 'Timed Mock Exam', icon: Clock },
          ].map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={subTab === t.id}
                type="button"
                onClick={() => {
                  setSubTab(t.id);
                  setExamQuiz(null);
                  setExamResult(null);
                  setSecondsLeft(null);
                }}
                className={`px-3 py-1.5 rounded-md text-xs font-medium inline-flex items-center gap-1.5 ${
                  subTab === t.id ? 'bg-surface text-fg-primary shadow-xs' : 'text-fg-secondary hover:text-fg-primary'
                }`}
              >
                <Icon className="w-3.5 h-3.5" /> {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {subTab === 'flashcards' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="inline-flex rounded-lg bg-subtle p-0.5 border border-border-def text-xs">
              <button
                type="button"
                onClick={() => setDueOnly(true)}
                className={`px-3 py-1 rounded-md font-medium ${dueOnly ? 'bg-accent text-white' : 'text-fg-secondary'}`}
              >
                Due Now
              </button>
              <button
                type="button"
                onClick={() => setDueOnly(false)}
                className={`px-3 py-1 rounded-md font-medium ${!dueOnly ? 'bg-accent text-white' : 'text-fg-secondary'}`}
              >
                Full Deck
              </button>
            </div>
            <span className="text-xs font-mono text-fg-muted">
              {cards.length > 0 ? `Card ${cardIdx + 1} / ${cards.length}` : '0 cards'}
            </span>
          </div>

          {!activeCard ? (
            <div className="p-10 rounded-xl bg-surface border border-border-def text-center text-sm text-fg-secondary">
              No {dueOnly ? 'due ' : ''}flashcards in this course yet. Missed quiz questions automatically populate here.
            </div>
          ) : (
            <div className="rounded-xl bg-surface border border-border-def p-6 space-y-5 shadow-xs">
              <div className="flex items-center justify-between text-xs text-fg-muted">
                <span className="px-2 py-0.5 rounded bg-subtle font-medium">{activeCard.state_name}</span>
                <button
                  type="button"
                  onClick={() => handleDeleteCard(activeCard.id)}
                  className="text-red-600 dark:text-red-400 hover:underline inline-flex items-center gap-1"
                >
                  <Trash2 className="w-3.5 h-3.5" /> Delete
                </button>
              </div>
              <div className="min-h-[120px] flex flex-col justify-center">
                <p className="text-base font-semibold text-fg-primary whitespace-pre-wrap">{activeCard.front}</p>
                {flipped && (
                  <div className="mt-4 pt-4 border-t border-border-def text-sm text-fg-secondary whitespace-pre-wrap">
                    {activeCard.back}
                  </div>
                )}
              </div>
              {!flipped ? (
                <button
                  type="button"
                  onClick={() => setFlipped(true)}
                  className="w-full py-2.5 rounded-lg bg-accent hover:bg-accent-hover text-white text-sm font-medium inline-flex items-center justify-center gap-2"
                >
                  <RotateCcw className="w-4 h-4" /> Show Answer (Space)
                </button>
              ) : (
                <div className="grid grid-cols-4 gap-2">
                  {[
                    { r: 1, label: '1 · Again', cls: 'bg-red-700 hover:bg-red-800' },
                    { r: 2, label: '2 · Hard', cls: 'bg-amber-700 hover:bg-amber-800' },
                    { r: 3, label: '3 · Good', cls: 'bg-accent hover:bg-accent-hover' },
                    { r: 4, label: '4 · Easy', cls: 'bg-emerald-700 hover:bg-emerald-800' },
                  ].map((b) => (
                    <button
                      key={b.r}
                      type="button"
                      onClick={() => handleRate(b.r)}
                      className={`py-2 rounded-lg text-white text-xs font-semibold ${b.cls}`}
                    >
                      {b.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {(subTab === 'diagnostic' || subTab === 'mock') && (
        <div className="space-y-4">
          {!examQuiz ? (
            <div className="p-8 rounded-xl bg-surface border border-border-def text-center space-y-3">
              <h2 className="text-base font-semibold text-fg-primary">
                {subTab === 'diagnostic' ? '3-Minute Diagnostic Pre-Test' : '15-Minute Full-Course Mock Exam'}
              </h2>
              <p className="text-sm text-fg-secondary max-w-md mx-auto">
                {subTab === 'diagnostic'
                  ? 'Test out of topics you already know so your study schedule focuses only on gaps.'
                  : 'Simulate exam-hall conditions across your syllabus with automatic FSRS flashcard creation for missed topics.'}
              </p>
              <button
                type="button"
                disabled={loading}
                onClick={() => startExam(subTab === 'diagnostic' ? 'diagnostic' : 'mock_exam')}
                className="px-5 py-2.5 rounded-lg bg-accent hover:bg-accent-hover text-white text-sm font-semibold disabled:opacity-50"
              >
                {loading ? 'Preparing Exam...' : 'Start Exam'}
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 rounded-lg bg-subtle border border-border-def">
                <span className="text-sm font-semibold text-fg-primary">{examQuiz.title}</span>
                {secondsLeft !== null && (
                  <span className="font-mono text-sm font-bold text-accent-text">
                    {String(Math.floor(secondsLeft / 60)).padStart(2, '0')}:{String(secondsLeft % 60).padStart(2, '0')}
                  </span>
                )}
              </div>
              {examQuiz.questions.map((q, idx) => (
                <div key={q.id} className="p-4 rounded-xl bg-surface border border-border-def space-y-2.5">
                  <div className="text-sm font-medium text-fg-primary">
                    {idx + 1}. {q.question}
                  </div>
                  <div className="space-y-1.5">
                    {q.options.map((opt, oi) => (
                      <button
                        key={oi}
                        type="button"
                        disabled={examResult !== null}
                        onClick={() => setExamAnswers((p) => ({ ...p, [q.id]: oi }))}
                        className={`w-full text-left px-3 py-2 rounded-lg border text-xs ${
                          examAnswers[q.id] === oi
                            ? 'bg-accent-soft border-accent text-accent-text font-medium'
                            : 'bg-canvas border-border-def text-fg-primary hover:bg-subtle'
                        }`}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
              {examResult ? (
                <div className="p-4 rounded-xl bg-emerald-600/10 border border-emerald-600 text-sm text-fg-primary font-medium">
                  Score: {Math.round(Number(examResult.score || 0))}% · Missed questions added to your FSRS Flashcards.
                </div>
              ) : (
                <button
                  type="button"
                  onClick={submitExam}
                  disabled={loading}
                  className="w-full py-2.5 rounded-lg bg-accent hover:bg-accent-hover text-white text-sm font-semibold"
                >
                  Submit Exam
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
