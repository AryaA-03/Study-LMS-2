export interface Course {
  id: string;
  title: string;
  goal_query?: string;
  target_date?: string;
  minutes_per_day?: number;
  preferred_daily_minutes?: number;
  playback_speed?: number;
  rest_days?: string[];
  revision_buffer_days?: number;
  schedule_strategy?: 'paced' | 'fixed';
  status?: string;
  created_at?: string;
}

export interface SourceItem {
  id: string;
  course_id: string;
  source_type: string;
  title: string;
  url?: string;
  external_id?: string;
  is_approved?: number;
  created_at?: string;
}

export interface Lesson {
  id: string;
  course_id: string;
  source_id?: string;
  title: string;
  chapter_title?: string;
  video_id?: string;
  video_url?: string;
  start_sec?: number;
  end_sec?: number;
  raw_duration_sec?: number;
  priority?: string;
  order_index?: number;
  is_excluded?: number | boolean;
  is_tested_out?: number | boolean;
  has_transcript?: number | boolean;
  pyq_hit_count?: number;
  pyq_total_marks?: number;
  status?: string;
}

export interface AllocationItem {
  id: string;
  lesson_id: string;
  lesson_title: string;
  chapter_title?: string;
  video_id?: string;
  video_url?: string;
  scheduled_date: string;
  allocated_start_sec?: number;
  allocated_end_sec?: number;
  effective_minutes: number;
  is_completed: boolean;
  is_skipped: boolean;
  priority?: string;
  pyq_hit_count?: number;
  pyq_total_marks?: number;
  split_index?: number;
  split_count?: number;
}

export interface ScheduleDay {
  date: string;
  day_number?: number;
  day_label?: string;
  total_minutes?: number;
  total_effective_minutes?: number;
  completed_minutes?: number;
  allocations: AllocationItem[];
}

export interface ScheduleResponse {
  course_id: string;
  days: ScheduleDay[];
  total_lessons?: number;
  completed_lessons?: number;
  progress_pct?: number;
  total_effective_minutes?: number;
  remaining_effective_minutes?: number;
  completed_effective_minutes?: number;
  projected_finish_date?: string;
  target_date?: string;
  is_behind_schedule?: boolean;
  behind_message?: string;
  effective_daily_target_minutes?: number;
  schedule_strategy?: string;
  can_undo?: boolean;
}

export interface LessonNotes {
  lesson_id: string;
  content_markdown: string;
  personal_notes?: string;
  generation_mode?: 'llm' | 'deterministic' | string;
  lesson_title?: string;
  is_generated_by_llm?: boolean;
  updated_at?: string;
}

export interface QACitation {
  chunk_id?: string;
  start_sec?: number;
  timestamp_label?: string;
  lesson_id?: string;
  lesson_title?: string;
}

export interface QAItem {
  id?: string;
  query?: string;
  question?: string;
  answer_markdown?: string;
  answer?: string;
  citations?: QACitation[];
  created_at?: string;
}

export interface QuizQuestion {
  id: string;
  question?: string;
  question_text?: string;
  question_type: string;
  options: string[];
  correct_index?: number;
  explanation?: string;
  timestamp_sec?: number;
  timestamp_str?: string;
  source_timestamp_sec?: number;
  lesson_id?: string;
}

export interface Quiz {
  id: string;
  course_id: string;
  lesson_id?: string;
  quiz_type: string;
  title?: string;
  questions: QuizQuestion[];
  score?: number;
  completed_at?: string;
}

export interface QuizSubmitResult {
  quiz_id: string;
  score: number;
  correct_count: number;
  total_questions: number;
  mastery_status?: string;
  schedule_updated?: boolean;
  flashcards_created?: number;
  results?: Array<{
    question_id: string;
    is_correct: boolean;
    correct_index?: number;
    explanation?: string;
    source_timestamp_sec?: number;
    lesson_id?: string;
  }>;
}

export interface Flashcard {
  id: string;
  course_id: string;
  lesson_id?: string;
  front: string;
  back: string;
  due_date?: string;
  source_timestamp_sec?: number;
  state?: number;
  reps?: number;
}

export interface PYQItem {
  id: string;
  question_number?: string;
  question_text: string;
  marks?: number;
  paper_title?: string;
  paper_id?: string;
  matched_lesson_id?: string;
  matched_lesson_title?: string;
}

export interface PYQSummary {
  papers: Array<{ id: string; title: string; question_count?: number; created_at?: string }>;
  questions: PYQItem[];
  total_questions?: number;
}

export interface CramSheet {
  id?: string;
  course_id: string;
  content_markdown: string;
  is_generated_by_llm?: boolean;
  cached?: boolean;
  updated_at?: string;
}

export interface JobStatus {
  id: string;
  job_type: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress_pct: number;
  message?: string;
  result?: any;
  error_text?: string;
}

export interface SystemSettings {
  ai_provider?: string;
  has_gemini_key?: boolean;
  has_groq_key?: boolean;
  has_openrouter_key?: boolean;
  ollama_base_url?: string;
  ollama_model?: string;
  whisper_model?: string;
  cookies_browser?: string;
  [key: string]: any;
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const isFormData = options.body instanceof FormData;
  const headers: Record<string, string> = isFormData
    ? {}
    : { 'Content-Type': 'application/json' };
  const res = await fetch(url, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string> | undefined) },
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail || data.message || detail;
    } catch {
      // ignore non-json
    }
    throw new Error(detail);
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    return res.json() as Promise<T>;
  }
  return (await res.text()) as unknown as T;
}

export const api = {
  // Courses
  listCourses: () => request<Course[]>('/api/courses'),
  createCourse: (payload: Partial<Course>) =>
    request<Course>('/api/courses', { method: 'POST', body: JSON.stringify(payload) }),
  updateCourse: (courseId: string, payload: Partial<Course>) =>
    request<Course>(`/api/courses/${courseId}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteCourse: (courseId: string) =>
    request<{ success: boolean }>(`/api/courses/${courseId}`, { method: 'DELETE' }),
  smartPrepareCourse: (courseId: string, forceRepartition = false, background = false) => {
    const qs = new URLSearchParams();
    if (forceRepartition) qs.set('force_repartition', 'true');
    if (background) qs.set('background', 'true');
    const qstr = qs.toString();
    return request<{ repartitioned_sources?: number; new_semantic_clips?: number; topics_clustered?: number; background_job_id?: string; job_id?: string; status?: string }>(
      `/api/courses/${courseId}/smart-prepare${qstr ? `?${qstr}` : ''}`,
      { method: 'POST' },
    );
  },
  clusterTopics: (courseId: string) =>
    request<{ lessons_updated: number; topics_created: number; topics: Array<{ title: string; lesson_count: number }> }>(
      `/api/courses/${courseId}/topics/cluster`,
      { method: 'POST' },
    ),
  exportCourseJsonUrl: (courseId: string) => `/api/courses/${courseId}/export`,
  exportCourseMarkdownUrl: (courseId: string) => `/api/courses/${courseId}/export-markdown`,

  // Sources & Discovery
  discoverSources: async (courseId: string, query: string) => {
    const qs = query ? `?query=${encodeURIComponent(query)}` : '';
    const raw = await request<any>(`/api/courses/${courseId}/discover${qs}`, {
      method: 'POST',
    });
    const combined = [
      ...(raw.candidate_playlists || []),
      ...(raw.candidate_videos || []),
      ...(raw.candidates || []),
    ];
    return { candidates: combined };
  },
  importSource: (courseId: string, url: string, is_approved = true) =>
    request<SourceItem>(`/api/courses/${courseId}/sources/import`, {
      method: 'POST',
      body: JSON.stringify({ url, is_approved }),
    }),
  approveSources: (courseId: string, source_ids_to_approve: string[], source_ids_to_reject: string[] = []) =>
    request<SourceItem[]>(`/api/courses/${courseId}/sources/approve`, {
      method: 'POST',
      body: JSON.stringify({ source_ids_to_approve, source_ids_to_reject }),
    }),
  listSources: (courseId: string) => request<SourceItem[]>(`/api/courses/${courseId}/sources`),
  deleteSource: (courseId: string, sourceId: string) =>
    request<{ success: boolean }>(`/api/courses/${courseId}/sources/${sourceId}`, { method: 'DELETE' }),
  uploadPdfSource: (courseId: string, file: File, title?: string) => {
    const fd = new FormData();
    fd.append('file', file);
    if (title) fd.append('title', title);
    return request<any>(`/api/courses/${courseId}/sources/pdf`, { method: 'POST', body: fd });
  },
  importWebSource: (courseId: string, url: string, title?: string) =>
    request<any>(`/api/courses/${courseId}/sources/web`, {
      method: 'POST',
      body: JSON.stringify({ url, title }),
    }),
  submitManualTranscript: (courseId: string, title: string, transcript_text: string, url?: string) =>
    request<any>(`/api/courses/${courseId}/sources/manual-transcript`, {
      method: 'POST',
      body: JSON.stringify({ title, transcript_text, url: url || '' }),
    }),

  // Lessons & Syllabus
  listLessons: (courseId: string) => request<Lesson[]>(`/api/courses/${courseId}/lessons`),
  updateLesson: (courseId: string, lessonId: string, payload: Partial<Lesson>) =>
    request<Lesson>(`/api/courses/${courseId}/lessons/${lessonId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  toggleExcludeLesson: (courseId: string, lessonId: string) =>
    request<Lesson>(`/api/courses/${courseId}/lessons/${lessonId}/toggle-exclude`, { method: 'POST' }),
  matchSyllabus: (courseId: string, syllabus_text: string, strictness: 'strict' | 'balanced' | 'comprehensive' = 'balanced') =>
    request<any>(`/api/courses/${courseId}/syllabus/match`, {
      method: 'POST',
      body: JSON.stringify({ syllabus_text, strictness }),
    }),
  applySyllabus: (courseId: string, syllabus_text: string, included_lesson_ids: string[], strictness: 'strict' | 'balanced' | 'comprehensive' = 'balanced') =>
    request<any>(`/api/courses/${courseId}/syllabus/apply`, {
      method: 'POST',
      body: JSON.stringify({ syllabus_text, included_lesson_ids, strictness, regenerate_schedule: true }),
    }),

  // Schedule
  getSchedule: (courseId: string) => request<ScheduleResponse>(`/api/courses/${courseId}/schedule`),
  generateSchedule: (courseId: string) =>
    request<ScheduleResponse>(`/api/courses/${courseId}/schedule/generate`, { method: 'POST' }),
  replanSchedule: (courseId: string, mode: 'normal' | 'compress' | 'strict_pacing' = 'normal') =>
    request<any>(`/api/courses/${courseId}/schedule/replan`, {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),
  completeAllocation: (courseId: string, allocationId: string) =>
    request<ScheduleResponse>(`/api/courses/${courseId}/schedule/allocations/${allocationId}/complete`, { method: 'POST' }),
  toggleAllocation: (courseId: string, allocationId: string) =>
    request<any>(`/api/courses/${courseId}/schedule/allocations/${allocationId}/toggle`, { method: 'POST' }),
  skipAllocation: (courseId: string, allocationId: string) =>
    request<ScheduleResponse>(`/api/courses/${courseId}/schedule/allocations/${allocationId}/skip`, { method: 'POST' }),
  undoSchedule: (courseId: string) =>
    request<ScheduleResponse>(`/api/courses/${courseId}/schedule/undo`, { method: 'POST' }),

  // Notes
  getLessonNotes: (lessonId: string, signal?: AbortSignal) =>
    request<LessonNotes>(`/api/lessons/${lessonId}/notes`, { signal }),
  regenerateLessonNotes: (lessonId: string) =>
    request<LessonNotes>(`/api/lessons/${lessonId}/notes/regenerate`, { method: 'POST' }),
  savePersonalNotes: (lessonId: string, personal_notes: string) =>
    request<{ success: boolean }>(`/api/lessons/${lessonId}/notes/personal`, {
      method: 'PUT',
      body: JSON.stringify({ personal_notes }),
    }),

  // Ask AI
  getQAHistory: (courseId: string, signal?: AbortSignal) =>
    request<QAItem[]>(`/api/courses/${courseId}/qa`, { signal }),
  askQuestion: (courseId: string, query: string, scope: 'lesson' | 'course' = 'lesson', lesson_id?: string | null) =>
    request<QAItem>(`/api/courses/${courseId}/qa`, {
      method: 'POST',
      body: JSON.stringify({
        query,
        lesson_id: scope === 'lesson' ? lesson_id : null,
      }),
    }),

  // Quizzes (lesson, diagnostic, mock_exam)
  generateQuiz: (
    courseId: string,
    payload: { quiz_type: 'lesson' | 'diagnostic' | 'mock_exam'; lesson_id?: string | null; question_count?: number },
  ) =>
    request<Quiz>(`/api/courses/${courseId}/quizzes/generate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  listQuizzes: (courseId: string, quiz_type?: string, lesson_id?: string) => {
    const params = new URLSearchParams();
    if (quiz_type) params.set('quiz_type', quiz_type);
    if (lesson_id) params.set('lesson_id', lesson_id);
    const qs = params.toString();
    return request<Quiz[]>(`/api/courses/${courseId}/quizzes${qs ? `?${qs}` : ''}`);
  },
  submitQuiz: (
    courseId: string,
    quizId: string,
    answers: Record<string, number>,
    short_answers: Record<string, string> = {},
    time_taken_seconds = 60,
  ) =>
    request<QuizSubmitResult>(`/api/courses/${courseId}/quizzes/${quizId}/submit`, {
      method: 'POST',
      body: JSON.stringify({ answers, short_answers, time_taken_seconds }),
    }),

  // Flashcards (FSRS)
  listFlashcards: (courseId: string, dueOnly = false, lessonId?: string) => {
    const params = new URLSearchParams();
    if (dueOnly) params.set('due_only', 'true');
    if (lessonId) params.set('lesson_id', lessonId);
    const qs = params.toString();
    return request<Flashcard[]>(`/api/courses/${courseId}/flashcards${qs ? `?${qs}` : ''}`);
  },
  reviewFlashcard: (courseId: string, cardId: string, rating: 1 | 2 | 3 | 4) =>
    request<any>(`/api/courses/${courseId}/flashcards/${cardId}/review`, {
      method: 'POST',
      body: JSON.stringify({ rating }),
    }),
  createFlashcard: (courseId: string, payload: { front: string; back: string; lesson_id?: string; source_timestamp_sec?: number }) =>
    request<Flashcard>(`/api/courses/${courseId}/flashcards`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteFlashcard: (courseId: string, cardId: string) =>
    request<{ success: boolean }>(`/api/courses/${courseId}/flashcards/${cardId}`, { method: 'DELETE' }),
  generateLessonFlashcards: (courseId: string, lessonId: string) =>
    request<Flashcard[]>(`/api/courses/${courseId}/flashcards/lessons/${lessonId}/generate`, { method: 'POST' }),

  // PYQs
  getPyqSummary: (courseId: string) => request<PYQSummary>(`/api/courses/${courseId}/pyq`),
  getLessonPyqs: (courseId: string, lessonId: string) =>
    request<PYQItem[]>(`/api/courses/${courseId}/lessons/${lessonId}/pyq`),
  uploadPyqFile: (courseId: string, file: File, title?: string) => {
    const fd = new FormData();
    fd.append('file', file);
    if (title) fd.append('title', title);
    return request<any>(`/api/courses/${courseId}/pyq/upload-file`, { method: 'POST', body: fd });
  },
  uploadPyqText: (courseId: string, title: string, raw_text: string) =>
    request<any>(`/api/courses/${courseId}/pyq/upload-text`, {
      method: 'POST',
      body: JSON.stringify({ title, raw_text }),
    }),
  deletePyqPaper: (courseId: string, paperId: string) =>
    request<{ success: boolean }>(`/api/courses/${courseId}/pyq/papers/${paperId}`, { method: 'DELETE' }),

  // Cram Sheet & Background Jobs
  getCramSheet: (courseId: string, scope?: { source_id?: string; chapter_title?: string }) => {
    const qs = new URLSearchParams();
    if (scope?.source_id) qs.set('source_id', scope.source_id);
    if (scope?.chapter_title) qs.set('chapter_title', scope.chapter_title);
    const qstr = qs.toString();
    return request<CramSheet>(`/api/courses/${courseId}/cram-sheet${qstr ? `?${qstr}` : ''}`);
  },
  generateCramSheet: (
    courseId: string,
    force_refresh = true,
    scope?: { source_id?: string; chapter_title?: string },
  ) =>
    request<CramSheet>(`/api/courses/${courseId}/cram-sheet/generate`, {
      method: 'POST',
      body: JSON.stringify({ force_refresh, ...(scope || {}) }),
    }),
  generateFullCramSheetAsync: (courseId: string) =>
    request<{ job_id: string; status: string }>(`/api/courses/${courseId}/cram-sheet/generate-full-async`, {
      method: 'POST',
    }),
  getJob: (jobId: string) => request<JobStatus>(`/api/jobs/${jobId}`),
  listJobs: (courseId?: string) => request<{ jobs: JobStatus[] }>(`/api/jobs${courseId ? `?course_id=${encodeURIComponent(courseId)}` : ''}`),
  cancelJob: (jobId: string) => request<{ success: boolean }>(`/api/jobs/${jobId}/cancel`, { method: 'POST' }),
  downloadCramSheetUrl: (courseId: string) => `/api/courses/${courseId}/cram-sheet/download`,


  // Transcription & Keyframe Slides
  transcribeLesson: (lessonId: string) =>
    request<{ success: boolean; lesson_id: string; transcript_type: string; chunk_count: number }>(
      `/api/lessons/${lessonId}/transcribe`,
      { method: 'POST' },
    ),
  captureScreenshots: (lessonId: string) =>
    request<Array<{ id: string; timestamp_sec: number; image_url: string; caption?: string }>>(
      `/api/lessons/${lessonId}/screenshots`,
      { method: 'POST' },
    ),
  listScreenshots: (lessonId: string) =>
    request<Array<{ id: string; timestamp_sec: number; image_url: string; caption?: string }>>(
      `/api/lessons/${lessonId}/screenshots`,
    ),
  updateFlashcard: (courseId: string, cardId: string, payload: { front: string; back: string }) =>
    request<Flashcard>(`/api/courses/${courseId}/flashcards/${cardId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  discoverWebSources: (courseId: string) =>
    request<{ candidates: Array<{ title: string; url: string; snippet?: string }> }>(
      `/api/courses/${courseId}/sources/discover-web`,
    ),

  // Settings & Data Portability
  getSettings: () => request<SystemSettings>('/api/settings'),
  saveApiKeys: (keys: Record<string, string>) =>
    request<any>('/api/settings/keys', { method: 'POST', body: JSON.stringify(keys) }),
  saveSettings: (payload: Record<string, any>) =>
    request<any>('/api/settings', { method: 'POST', body: JSON.stringify(payload) }),
  testConnection: (provider = 'gemini') =>
    request<{ success: boolean; message: string }>('/api/settings/test-connection', {
      method: 'POST',
      body: JSON.stringify({ provider }),
    }),
  cleanupCache: () => request<any>('/api/settings/cleanup-cache', { method: 'POST' }),
  vacuumDb: () => request<any>('/api/settings/vacuum', { method: 'POST' }),
  updateYtdlp: () => request<any>('/api/settings/update-ytdlp', { method: 'POST' }),
  backupDbUrl: () => '/api/settings/backup',
  restoreDb: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<any>('/api/settings/restore', { method: 'POST', body: fd });
  },
};
