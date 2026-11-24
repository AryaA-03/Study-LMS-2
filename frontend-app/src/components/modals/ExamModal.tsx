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

export const ExamModal: React.FC<{
  courseId: string;
  mode: 'diagnostic' | 'mock_exam';
  onClose: () => void;
  onSeekTimestamp: (sec: number) => void;
  onScheduleChanged: () => void;
  onToast: (msg: string) => void;
}> = ({ courseId, mode, onClose, onSeekTimestamp, onScheduleChanged, onToast }) => {
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [result, setResult] = useState<QuizSubmitResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    setLoading(true);
    api
      .generateQuiz(courseId, {
        quiz_type: mode,
        question_count: mode === 'diagnostic' ? 6 : 12,
      })
      .then((q) => setQuiz(q))
      .catch((e: any) => onToast(`Failed to generate ${mode}: ${e.message}`))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, mode]);

  useEffect(() => {
    if (!quiz || result) return;
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [quiz, result]);

  const handleSubmit = async () => {
    if (!quiz) return;
    setLoading(true);
    try {
      const res = await api.submitQuiz(courseId, quiz.id, answers, {}, elapsed);
      setResult(res);
      if (res.schedule_updated) onScheduleChanged();
      onToast(
        mode === 'diagnostic'
          ? 'Diagnostic graded — mastered topics updated in your schedule!'
          : `Mock Exam graded: ${Math.round(res.score)}%`,
      );
    } catch (e: any) {
      onToast(`Submit error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalShell
      title={mode === 'diagnostic' ? '2-Minute Diagnostic Pre-Test' : 'Timed Subject Mock Exam'}
      subtitle={
        mode === 'diagnostic'
          ? 'Skip topics you already know — your schedule repacks automatically.'
          : `Elapsed: ${formatSecToPill(elapsed)} • Wrong answers link directly to video explanations.`
      }
      onClose={onClose}
      wide
    >
      {loading && !quiz ? (
        <div className="flex h-40 items-center justify-center gap-2 text-xs text-[var(--fg-secondary)]">
          <Loader2 className="h-5 w-5 animate-spin text-[var(--accent)]" />
          Preparing grounded exam questions...
        </div>
      ) : !quiz ? (
        <p className="text-xs text-[var(--fg-secondary)]">Could not load exam questions.</p>
      ) : (
        <div className="space-y-4">
          {result && (
            <div className="rounded-xl border border-[var(--accent)] bg-[var(--accent-soft)] p-3.5 text-xs text-[var(--accent-text)]">
              <div className="text-sm font-bold">
                Final Score: {Math.round(result.score)}% ({result.correct_count}/{result.total_questions})
              </div>
              {mode === 'diagnostic' && (
                <p className="mt-1">Mastered topics have been marked & schedule updated automatically.</p>
              )}
            </div>
          )}

          {quiz.questions.map((q, i) => {
            const isGraded = !!result;
            const ts = q.timestamp_sec ?? q.source_timestamp_sec;
            return (
              <div
                key={q.id}
                className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-3.5 space-y-2"
              >
                <div className="text-xs font-semibold text-[var(--fg-primary)]">
                  {i + 1}. {q.question || q.question_text}
                </div>
                <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                  {(q.options || []).map((opt, oi) => {
                    const chosen = answers[q.id] === oi;
                    const correctOpt = isGraded && q.correct_index === oi;
                    const wrongChosen = isGraded && chosen && !correctOpt;
                    return (
                      <button
                        key={oi}
                        type="button"
                        disabled={!!result}
                        onClick={() => setAnswers((p) => ({ ...p, [q.id]: oi }))}
                        className={`rounded-lg border px-3 py-2 text-left text-xs transition ${
                          correctOpt
                            ? 'border-[var(--success)] bg-[var(--success)]/15 font-semibold text-[var(--fg-primary)]'
                            : wrongChosen
                            ? 'border-[var(--danger)] bg-[var(--danger)]/15 font-semibold text-[var(--fg-primary)]'
                            : chosen
                            ? 'border-[var(--accent)] bg-[var(--accent-soft)] font-semibold text-[var(--accent-text)]'
                            : 'border-[var(--border-subtle)] bg-[var(--bg-card)] text-[var(--fg-primary)]'
                        }`}
                      >
                        <span className="mr-1.5 font-mono font-bold opacity-70">{String.fromCharCode(65 + oi)}.</span>
                        {opt}
                      </button>
                    );
                  })}
                </div>
                {isGraded && (
                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs text-[var(--fg-secondary)]">
                    <span>{q.explanation || 'Review the timestamp below for the full explanation.'}</span>
                    {ts !== undefined && ts !== null && (
                      <button
                        type="button"
                        onClick={() => {
                          onSeekTimestamp(ts);
                          onClose();
                        }}
                        className="inline-flex items-center gap-1 rounded bg-[var(--accent)] px-2 py-0.5 font-semibold text-white"
                      >
                        <Play className="h-3 w-3" /> Replay {formatSecToPill(ts)}
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {!result && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleSubmit}
                disabled={loading || Object.keys(answers).length === 0}
                className="rounded-lg bg-[var(--accent)] px-5 py-2 text-xs font-bold text-white"
              >
                Submit Exam
              </button>
            </div>
          )}
        </div>
      )}
    </ModalShell>
  );
};

/* ================= 6. SYLLABUS ALIGNMENT MODAL ================= */
