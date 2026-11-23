/** Typed REST API client with AbortController support and error normalization. */

export interface Course {
  id: string;
  title: string;
  goal_query: string;
  target_date: string;
  minutes_per_day: number;
  playback_speed: number;
  rest_days: string[];
  revision_buffer_days: number;
  schedule_strategy?: string;
  progress_pct?: number;
  total_lessons?: number;
  completed_lessons?: number;
}

export interface Allocation {
  id: string;
  course_id: string;
  lesson_id: string;
  lesson_title: string;
  video_id?: string;
  video_url?: string;
  scheduled_date: string;
  allocated_start_sec: number;
  allocated_end_sec: number;
  effective_minutes: number;
  is_completed: boolean;
  is_skipped: boolean;
  priority?: string;
  pyq_hit_count?: number;
}

export interface ScheduleDay {
  date: string;
  day_name: string;
  is_rest_day: boolean;
  is_revision_buffer: boolean;
  total_minutes: number;
  allocations: Allocation[];
}

export interface ScheduleResponse {
  course_id: string;
  days: ScheduleDay[];
  projected_finish_date?: string;
  is_behind_schedule?: boolean;
  behind_days?: number;
  can_undo?: boolean;
}

export interface LessonNote {
  lesson_id: string;
  content_markdown: string;
  personal_notes: string;
}

export interface SourceItem {
  id: string;
  course_id: string;
  source_type: string;
  title: string;
  url?: string;
  is_approved: boolean;
  duration_sec?: number;
}

export interface QuizQuestion {
  id: string;
  chunk_id: string;
  lesson_id?: string;
  quote: string;
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
  question_type?: string;
  timestamp_sec?: number;
  timestamp_str?: string;
  replay_url?: string;
}

export interface QuizResponse {
  id: string;
  course_id: string;
  lesson_id?: string;
  quiz_type: string;
  title: string;
  questions: QuizQuestion[];
}

export interface Flashcard {
  id: string;
  course_id: string;
  lesson_id?: string;
  front: string;
  back: string;
  due_date: string;
  state_name: string;
  reps: number;
  interval_previews?: Record<string, string>;
}

export interface QAItem {
  id: string;
  query: string;
  answer_markdown: string;
  citations?: Array<{ chunk_id?: string; source_title?: string; start_sec?: number; timestamp_str?: string }>;
}

export interface PYQItem {
  id: string;
  paper_title?: string;
  question_number?: string;
  question_text: string;
  marks?: number;
  lesson_id?: string;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      msg = body.detail || body.message || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Courses
  listCourses: () => request<Course[]>('/api/courses'),
  createCourse: (payload: Record<string, unknown>) =>
    request<Course>('/api/courses', { method: 'POST', body: JSON.stringify(payload) }),
  deleteCourse: (courseId: string) =>
    request<{ success: boolean }>(`/api/courses/${courseId}`, { method: 'DELETE' }),
  importYoutubeSource: (courseId: string, url: string, is_approved = true) =>
    request<Record<string, unknown>>(`/api/courses/${courseId}/sources/import`, {
      method: 'POST',
      body: JSON.stringify({ url, is_approved }),
    }),
  listSources: (courseId: string) => request<SourceItem[]>(`/api/courses/${courseId}/sources`),
  deleteSource: (courseId: string, sourceId: string) =>
    request<{ success: boolean }>(`/api/courses/${courseId}/sources/${sourceId}`, { method: 'DELETE' }),
  uploadPdfSource: async (courseId: string, file: File, title: string) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('title', title || file.name);
    const res = await fetch(`/api/courses/${courseId}/sources/pdf`, { method: 'POST', body: fd });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`);
    return res.json();
  },
  importWebSource: (courseId: string, url: string, title?: string) =>
    request<Record<string, unknown>>(`/api/courses/${courseId}/sources/web`, {
      method: 'POST',
      body: JSON.stringify({ url, title }),
    }),

  // Schedule
  getSchedule: (courseId: string, signal?: AbortSignal) =>
    request<ScheduleResponse>(`/api/courses/${courseId}/schedule`, { signal }),
  generateSchedule: (courseId: string) =>
    request<ScheduleResponse>(`/api/courses/${courseId}/schedule/generate`, { method: 'POST', body: '{}' }),
  replanSchedule: (courseId: string, payload: Record<string, unknown>) =>
    request<ScheduleResponse>(`/api/courses/${courseId}/schedule/replan`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  undoReplan: (courseId: string) =>
    request<ScheduleResponse>(`/api/courses/${courseId}/schedule/undo`, { method: 'POST', body: '{}' }),
  toggleAllocation: (courseId: string, allocId: string) =>
    request<ScheduleResponse>(`/api/courses/${courseId}/schedule/allocations/${allocId}/toggle`, { method: 'POST' }),
  skipAllocation: (courseId: string, allocId: string) =>
    request<ScheduleResponse>(`/api/courses/${courseId}/schedule/allocations/${allocId}/skip`, { method: 'POST' }),

  // Notes & Media
  getLessonNotes: (lessonId: string, signal?: AbortSignal) =>
    request<LessonNote>(`/api/lessons/${lessonId}/notes`, { signal }),
  regenerateLessonNotes: (lessonId: string) =>
    request<LessonNote>(`/api/lessons/${lessonId}/notes/regenerate`, { method: 'POST' }),
  savePersonalNotes: (lessonId: string, personal_notes: string) =>
    request<{ success: boolean }>(`/api/lessons/${lessonId}/notes/personal`, {
      method: 'PUT',
      body: JSON.stringify({ personal_notes }),
    }),
  transcribeLesson: (lessonId: string) =>
    request<Record<string, unknown>>(`/api/lessons/${lessonId}/transcribe`, { method: 'POST' }),
  captureScreenshots: (lessonId: string) =>
    request<Array<Record<string, unknown>>>(`/api/lessons/${lessonId}/screenshots`, { method: 'POST' }),

  // Ask AI
  getQAHistory: (courseId: string, signal?: AbortSignal) =>
    request<QAItem[]>(`/api/courses/${courseId}/qa`, { signal }),
  askQuestion: (courseId: string, query: string, lesson_id?: string | null) =>
    request<QAItem>(`/api/courses/${courseId}/qa`, {
      method: 'POST',
      body: JSON.stringify({ query, lesson_id: lesson_id || null }),
    }),

  // Quizzes, Flashcards, PYQs, Cram Sheet
  generateQuiz: (courseId: string, quiz_type: 'lesson' | 'diagnostic' | 'mock_exam', lesson_id?: string | null, question_count = 5) =>
    request<QuizResponse>(`/api/courses/${courseId}/quizzes/generate`, {
      method: 'POST',
      body: JSON.stringify({ quiz_type, lesson_id: lesson_id || null, question_count }),
    }),
  submitQuiz: (courseId: string, quizId: string, answers: Record<string, number>, time_taken_seconds = 60) =>
    request<Record<string, unknown>>(`/api/courses/${courseId}/quizzes/${quizId}/submit`, {
      method: 'POST',
      body: JSON.stringify({ answers, short_answers: {}, time_taken_seconds }),
    }),
  listFlashcards: (courseId: string, due_only = false) =>
    request<Flashcard[]>(`/api/courses/${courseId}/flashcards?due_only=${due_only}`),
  reviewFlashcard: (courseId: string, cardId: string, rating: number) =>
    request<Flashcard>(`/api/courses/${courseId}/flashcards/${cardId}/review`, {
      method: 'POST',
      body: JSON.stringify({ rating }),
    }),
  deleteFlashcard: (courseId: string, cardId: string) =>
    request<{ success: boolean }>(`/api/courses/${courseId}/flashcards/${cardId}`, { method: 'DELETE' }),
  listPYQs: (courseId: string, lesson_id?: string) =>
    request<PYQItem[]>(lesson_id ? `/api/courses/${courseId}/lessons/${lesson_id}/pyq` : `/api/courses/${courseId}/pyq`),
  getCramSheet: (courseId: string) =>
    request<{ content_markdown: string }>(`/api/courses/${courseId}/cram-sheet`),
  generateCramSheet: (courseId: string) =>
    request<{ content_markdown: string }>(`/api/courses/${courseId}/cram-sheet/generate`, { method: 'POST' }),
  generateCramSheetAsync: (courseId: string) =>
    request<{ job_id: string; status: string }>(`/api/courses/${courseId}/cram-sheet/generate-full-async`, { method: 'POST' }),
  getJob: (jobId: string) => request<Record<string, unknown>>(`/api/jobs/${jobId}`),

  // Settings
  getSettings: () => request<Record<string, unknown>>('/api/settings'),
  saveKeys: (keys: Record<string, string>) =>
    request<{ success: boolean; message: string }>('/api/settings/keys', {
      method: 'POST',
      body: JSON.stringify(keys),
    }),
  testConnection: (provider: string, api_key?: string, base_url?: string) =>
    request<{ success: boolean; message: string }>('/api/settings/test-connection', {
      method: 'POST',
      body: JSON.stringify({ provider, api_key, base_url }),
    }),
  cleanupCache: () => request<{ success: boolean; message: string }>('/api/settings/cleanup-cache', { method: 'POST' }),
  vacuumDb: () => request<{ success: boolean; message: string }>('/api/settings/vacuum', { method: 'POST' }),
};
