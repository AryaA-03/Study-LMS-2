/**
 * Learn LMS Client - Frontend Application (CourseIt & NotebookLM Inspired)
 * Features:
 * - Rich F12 browser console logging
 * - Collapsible split-screen studio & collapsible day cards
 * - Dual scheduling strategies: Paced to Exam Date vs Fixed Daily Goal
 * - Granular lesson inclusion & quick smart filtering (Concepts vs Examples)
 * - YouTube IFrame Player API integration
 */

// --- Structured F12 Console Logger ---
const Logger = {
  api(method, url, status, timeMs, data) {
    const badge = `%c[LearnLMS:API]`;
    const style = 'background: #2563eb; color: #ffffff; padding: 2px 5px; border-radius: 4px; font-weight: bold;';
    console.groupCollapsed(`${badge} %c${method} ${url} -> ${status} (${timeMs}ms)`, style, 'color: #38bdf8;');
    if (data) console.log('Payload / Response:', data);
    console.trace('Callstack');
    console.groupEnd();
  },
  player(action, details) {
    const badge = `%c[LearnLMS:Player]`;
    const style = 'background: #dc2626; color: #ffffff; padding: 2px 5px; border-radius: 4px; font-weight: bold;';
    console.log(`${badge} ${action}:`, details);
  },
  schedule(action, details) {
    const badge = `%c[LearnLMS:Schedule]`;
    const style = 'background: #0284c7; color: #ffffff; padding: 2px 5px; border-radius: 4px; font-weight: bold;';
    console.log(`${badge} ${action}:`, details);
  },
  quiz(action, details) {
    const badge = `%c[LearnLMS:Quiz]`;
    const style = 'background: #d97706; color: #ffffff; padding: 2px 5px; border-radius: 4px; font-weight: bold;';
    console.log(`${badge} ${action}:`, details);
  },
  fsrs(action, details) {
    const badge = `%c[LearnLMS:FSRS]`;
    const style = 'background: #059669; color: #ffffff; padding: 2px 5px; border-radius: 4px; font-weight: bold;';
    console.log(`${badge} ${action}:`, details);
  },
  filter(action, count) {
    const badge = `%c[LearnLMS:Filter]`;
    const style = 'background: #059669; color: #ffffff; padding: 2px 5px; border-radius: 4px; font-weight: bold;';
    console.log(`${badge} ${action} (${count} affected)`);
  },
  theme(themeName) {
    const badge = `%c[LearnLMS:Theme]`;
    const style = 'background: #18181b; color: #ffffff; padding: 2px 5px; border-radius: 4px; font-weight: bold;';
    console.log(`${badge} Switched to ${themeName} theme`);
  },
  layout(action, details) {
    const badge = `%c[LearnLMS:Layout]`;
    const style = 'background: #0284c7; color: #ffffff; padding: 2px 5px; border-radius: 4px; font-weight: bold;';
    console.log(`${badge} ${action}:`, details);
  },
  error(msg, err) {
    console.error(`%c[LearnLMS:Error] ${msg}`, 'background: #991b1b; color: #ffffff; padding: 2px 5px; font-weight: bold;', err);
  }
};

// State
let currentCourseId = null;
let currentCourse = null;
let currentSchedule = null;
let currentLessons = [];
let activeAllocation = null;
let currentLessonId = null;
let qaScope = 'lesson'; // 'lesson' | 'notebook'
let ytPlayer = null;
let isYtReady = false;
let pendingVideoSlice = null;
let collapsedDays = new Set();
let areAllDaysCollapsed = false;

// DOM Elements
const btnThemeToggle = document.getElementById('btn-theme-toggle');
const themeIconSun = document.getElementById('theme-icon-sun');
const themeIconMoon = document.getElementById('theme-icon-moon');

const pillBufferZero = document.getElementById('pill-buffer-zero');
const pillBufferTwo = document.getElementById('pill-buffer-two');
const pacingNoteDetail = document.getElementById('pacing-note-detail');

// Edit Course & KPI Elements
const btnEditCourse = document.getElementById('btn-edit-course');
const kpiCardExamDate = document.getElementById('kpi-card-exam-date');
const kpiCardPaceSpeed = document.getElementById('kpi-card-pace-speed');
const kpiMinutesDisplay = document.getElementById('kpi-minutes-display');
const kpiSpeedDisplay = document.getElementById('kpi-speed-display');

const editCourseModal = document.getElementById('edit-course-modal');
const formEditCourse = document.getElementById('form-edit-course');
const btnCloseEditCourse = document.getElementById('btn-close-edit-course');
const btnCancelEditCourse = document.getElementById('btn-cancel-edit-course');

// Edit Lesson Elements
const btnEditActiveTitle = document.getElementById('btn-edit-active-title');
const btnEditActiveLesson = document.getElementById('btn-edit-active-lesson');
const btnToggleActivePriority = document.getElementById('btn-toggle-active-priority');

const editLessonModal = document.getElementById('edit-lesson-modal');
const formEditLesson = document.getElementById('form-edit-lesson');
const btnCloseEditLesson = document.getElementById('btn-close-edit-lesson');
const btnCancelEditLesson = document.getElementById('btn-cancel-edit-lesson');
const editLessonId = document.getElementById('edit-lesson-id');
const editLessonAllocId = document.getElementById('edit-lesson-alloc-id');
const editLessonTitleInput = document.getElementById('edit-lesson-title-input');
const editLessonPriorityInput = document.getElementById('edit-lesson-priority-input');
const editLessonRescheduleDate = document.getElementById('edit-lesson-reschedule-date');
const editLessonSummaryInput = document.getElementById('edit-lesson-summary-input');

// Edit Flashcard Elements
const editCardModal = document.getElementById('edit-card-modal');
const formEditCard = document.getElementById('form-edit-card');
const btnCloseEditCard = document.getElementById('btn-close-edit-card');
const btnCancelEditCard = document.getElementById('btn-cancel-edit-card');
const btnDeleteCardFromModal = document.getElementById('btn-delete-card-from-modal');
const editCardId = document.getElementById('edit-card-id');
const editCardFrontInput = document.getElementById('edit-card-front-input');
const editCardBackInput = document.getElementById('edit-card-back-input');
const btnEditActiveCard = document.getElementById('btn-edit-active-card');

// Personal Notes & Toast Elements
const btnSavePersonalNotes = document.getElementById('btn-save-personal-notes');
const personalNotesWordCount = document.getElementById('personal-notes-word-count');
const toastContainer = document.getElementById('toast-container');
let currentCardUnderReview = null;

// DOM Elements
const courseSelector = document.getElementById('course-selector');
const btnNewCourse = document.getElementById('btn-new-course');
const btnSettings = document.getElementById('btn-settings');
const settingsModal = document.getElementById('settings-modal');
const btnCloseSettings = document.getElementById('btn-close-settings');

const workspaceView = document.getElementById('workspace-view');
const creatorView = document.getElementById('creator-view');
const courseCreateForm = document.getElementById('course-create-form');
const btnCancelCreator = document.getElementById('btn-cancel-creator');

const paneStudio = document.getElementById('pane-studio');
const paneSchedule = document.getElementById('pane-schedule');
const btnCollapsePlayer = document.getElementById('btn-collapse-player');
const btnCollapseSchedule = document.getElementById('btn-collapse-schedule');

const pillStrategyPaced = document.getElementById('pill-strategy-paced');
const pillStrategyFixed = document.getElementById('pill-strategy-fixed');
const pacingModeLabel = document.getElementById('pacing-mode-label');
const statDailyTarget = document.getElementById('stat-daily-target');

const diffBanner = document.getElementById('diff-banner');
const diffText = document.getElementById('diff-text');
const btnUndoDiff = document.getElementById('btn-undo-diff');
const btnDismissDiff = document.getElementById('btn-dismiss-diff');

const behindScheduleBanner = document.getElementById('behind-schedule-banner');
const behindScheduleMsg = document.getElementById('behind-schedule-msg');
const btnActionCompress = document.getElementById('btn-action-compress');
const btnActionExtend = document.getElementById('btn-action-extend');

const approvalGate = document.getElementById('approval-gate');
const candidatePlaylistsList = document.getElementById('candidate-playlists-list');
const candidateVideosList = document.getElementById('candidate-videos-list');
const btnApproveSelected = document.getElementById('btn-approve-selected');

const scheduleDaysContainer = document.getElementById('schedule-days-container');
const progressPct = document.getElementById('progress-pct');
const progressBarFill = document.getElementById('progress-bar-fill');
const statEffectiveLeft = document.getElementById('stat-effective-left');
const statEffectiveDone = document.getElementById('stat-effective-done');
const statProjectedFinish = document.getElementById('stat-projected-finish');
const statTargetDate = document.getElementById('stat-target-date');

const inlinePlaybackSpeed = document.getElementById('inline-playback-speed');
const inlineMinutesDay = document.getElementById('inline-minutes-day');
const btnReplanNow = document.getElementById('btn-replan-now');

const activeLessonTitle = document.getElementById('active-lesson-title');
const activeLessonTime = document.getElementById('active-lesson-time');
const activeLessonEffMin = document.getElementById('active-lesson-eff-min');
const activeLessonPriority = document.getElementById('active-lesson-priority');
const activeLessonSplit = document.getElementById('active-lesson-split');
const btnToggleActiveComplete = document.getElementById('btn-toggle-active-complete');
const activeCompleteLabel = document.getElementById('active-complete-label');
const btnSkipActive = document.getElementById('btn-skip-active');

// Curriculum Drawer
const curriculumDrawer = document.getElementById('curriculum-drawer');
const btnToggleCurriculum = document.getElementById('btn-toggle-curriculum');
const btnCloseCurriculum = document.getElementById('btn-close-curriculum');
const curriculumLessonsList = document.getElementById('curriculum-lessons-list');
const curriculumSearch = document.getElementById('curriculum-search');
const btnCurriculumIncludeAll = document.getElementById('btn-curriculum-include-all');
const btnCurriculumSkipExamples = document.getElementById('btn-curriculum-skip-examples');
const headerLessonCount = document.getElementById('header-lesson-count');

// Smart Filters
const btnFilterAll = document.getElementById('btn-filter-all');
const btnFilterConcepts = document.getElementById('btn-filter-concepts');
const btnFilterExamples = document.getElementById('btn-filter-examples');
const btnToggleCollapseAll = document.getElementById('btn-toggle-collapse-all');

// Notes, Keyframes & Transcription Elements
const tabGroundedNotes = document.getElementById('tab-grounded-notes');
const tabPersonalNotes = document.getElementById('tab-personal-notes');
const paneGroundedNotes = document.getElementById('pane-grounded-notes');
const panePersonalNotes = document.getElementById('pane-personal-notes');
const notesContent = document.getElementById('notes-content');
const inputPersonalNotes = document.getElementById('input-personal-notes');
const personalNoteSaveStatus = document.getElementById('personal-note-save-status');
const btnTranscribeLesson = document.getElementById('btn-transcribe-lesson');
const transcribeBtnLabel = document.getElementById('transcribe-btn-label');
const transcribeStatusPill = document.getElementById('transcribe-status-pill');
const btnCaptureKeyframes = document.getElementById('btn-capture-keyframes');
const btnRegenerateNotes = document.getElementById('btn-regenerate-notes');
const keyframesStrip = document.getElementById('keyframes-strip');

// Multi-Source & Q&A Elements
const tabQaNotebook = document.getElementById('tab-qa-notebook');
const paneQaNotebook = document.getElementById('pane-qa-notebook');
const qaMessagesList = document.getElementById('qa-messages-list');
const qaInputForm = document.getElementById('qa-input-form');
const inputQaQuery = document.getElementById('input-qa-query');
const btnSubmitQa = document.getElementById('btn-submit-qa');
const qaBtnText = document.getElementById('qa-btn-text');
const qaSpinner = document.getElementById('qa-spinner');
const qaScopeLesson = document.getElementById('qa-scope-lesson');
const qaScopeNotebook = document.getElementById('qa-scope-notebook');
const floatingExplainPill = document.getElementById('floating-explain-pill');

const sourcesPillsList = document.getElementById('sources-pills-list');
const btnOpenAddSource = document.getElementById('btn-open-add-source');
const addSourceModal = document.getElementById('add-source-modal');
const btnCloseAddSource = document.getElementById('btn-close-add-source');
const tabSrcPdf = document.getElementById('tab-src-pdf');
const tabSrcWeb = document.getElementById('tab-src-web');
const formUploadPdf = document.getElementById('form-upload-pdf');
const formImportWeb = document.getElementById('form-import-web');

// Quiz & Mastery Elements
const tabQuizMastery = document.getElementById('tab-quiz-mastery');
const paneQuizMastery = document.getElementById('pane-quiz-mastery');
const quizTitleHeading = document.getElementById('quiz-title-heading');
const quizMasteryBadge = document.getElementById('quiz-mastery-badge');
const quizQuestionCount = document.getElementById('quiz-question-count');
const btnGenerateLessonQuiz = document.getElementById('btn-generate-lesson-quiz');
const quizResultsBanner = document.getElementById('quiz-results-banner');
const quizForm = document.getElementById('quiz-form');
const quizQuestionsList = document.getElementById('quiz-questions-list');
const quizSubmitBar = document.getElementById('quiz-submit-bar');

// FSRS Flashcard Elements
const tabFlashcardsFsrs = document.getElementById('tab-flashcards-fsrs');
const paneFlashcardsFsrs = document.getElementById('pane-flashcards-fsrs');
const fsrsRetentionPill = document.getElementById('fsrs-retention-pill');
const statFcTotal = document.getElementById('stat-fc-total');
const statFcDue = document.getElementById('stat-fc-due');
const statFcNew = document.getElementById('stat-fc-new');
const statFcLearning = document.getElementById('stat-fc-learning');
const statFcReview = document.getElementById('stat-fc-review');
const badgeDueFlashcards = document.getElementById('badge-due-flashcards');
const btnAddCardManual = document.getElementById('btn-add-card-manual');
const fcEmptyState = document.getElementById('fc-empty-state');
const fcActiveCardContainer = document.getElementById('fc-active-card-container');
const fsrsCardFlipper = document.getElementById('fsrs-card-flipper');
const fsrsCardFront = document.getElementById('fsrs-card-front');
const fsrsCardBack = document.getElementById('fsrs-card-back');
const fsrsFrontText = document.getElementById('fsrs-front-text');
const fsrsBackText = document.getElementById('fsrs-back-text');
const fsrsQuoteBox = document.getElementById('fsrs-quote-box');
const fsrsRatingBar = document.getElementById('fsrs-rating-bar');
const btnFsrsAgain = document.getElementById('btn-fsrs-again');
const btnFsrsHard = document.getElementById('btn-fsrs-hard');
const btnFsrsGood = document.getElementById('btn-fsrs-good');
const btnFsrsEasy = document.getElementById('btn-fsrs-easy');
const intervalAgain = document.getElementById('interval-again');
const intervalHard = document.getElementById('interval-hard');
const intervalGood = document.getElementById('interval-good');
const intervalEasy = document.getElementById('interval-easy');

// Diagnostic Pre-Test & Mock Exam Elements
const btnDiagnosticTest = document.getElementById('btn-diagnostic-test');
const diagnosticModal = document.getElementById('diagnostic-modal');
const btnCloseDiagnostic = document.getElementById('btn-close-diagnostic');
const diagnosticContentContainer = document.getElementById('diagnostic-content-container');
const btnSubmitDiagnostic = document.getElementById('btn-submit-diagnostic');

const btnMockExam = document.getElementById('btn-mock-exam');
const mockExamModal = document.getElementById('mock-exam-modal');
const btnCloseMockExam = document.getElementById('btn-close-mock-exam');
const mockExamTimer = document.getElementById('mock-exam-timer');
const mockExamContent = document.getElementById('mock-exam-content');
const mockAnsweredCount = document.getElementById('mock-answered-count');
const mockTotalCount = document.getElementById('mock-total-count');
const btnSubmitMockExam = document.getElementById('btn-submit-mock-exam');

const addCardModal = document.getElementById('add-card-modal');
const btnCloseAddCard = document.getElementById('btn-close-add-card');
const formCreateCard = document.getElementById('form-create-card');
const inputCardFront = document.getElementById('input-card-front');
const inputCardBack = document.getElementById('input-card-back');
const inputCardQuote = document.getElementById('input-card-quote');

// Pyodide Web Worker & Storage Guard Elements
const tabPyodideScratchpad = document.getElementById('tab-pyodide-scratchpad');
const panePyodideScratchpad = document.getElementById('pane-pyodide-scratchpad');
const pyodideStatusPill = document.getElementById('pyodide-status-pill');
const pyodidePresets = document.getElementById('pyodide-presets');
const btnRunPyodide = document.getElementById('btn-run-pyodide');
const btnClearCode = document.getElementById('btn-clear-code');
const pyodideCodeInput = document.getElementById('pyodide-code-input');
const pyodideOutput = document.getElementById('pyodide-output');
const pyodideExecTime = document.getElementById('pyodide-exec-time');

const btnVacuumDb = document.getElementById('btn-vacuum-db');
const btnDownloadDb = document.getElementById('btn-download-db');
const btnExportBundle = document.getElementById('btn-export-bundle');

// --- YouTube IFrame API Initialization ---
window.onYouTubeIframeAPIReady = function() {
  Logger.player('API Ready', 'Initializing YouTube IFrame API instance');
  ytPlayer = new YT.Player('yt-player', {
    height: '100%',
    width: '100%',
    playerVars: {
      playsinline: 1,
      modestbranding: 1,
      rel: 0,
    },
    events: {
      onReady: onPlayerReady,
      onStateChange: onPlayerStateChange,
    }
  });
};

function onPlayerReady(event) {
  isYtReady = true;
    if (pendingVideoSlice) { const _p = pendingVideoSlice; pendingVideoSlice = null; playVideoSlice(_p.videoId, _p.startSec, _p.endSec); }
  Logger.player('Player Ready', event);
  const placeholder = document.getElementById('yt-player-placeholder');
  if (placeholder) placeholder.classList.add('hidden');
}

let playerTimeSyncInterval = null;
let isAutoAdvanceEnabled = localStorage.getItem('learn_lms_auto_advance') !== 'false';
let isAutoAdvancing = false;

function onPlayerStateChange(event) {
  Logger.player('Player State Change', event.data);

  if (event.data === 1) { // PLAYING
    startPlayerTimeSync();
  } else {
    stopPlayerTimeSync();
  }

  if (event.data === 0) { // ENDED
    if (isAutoAdvanceEnabled && activeAllocation && !isAutoAdvancing) {
      triggerAutoAdvance();
    }
  }
}

function startPlayerTimeSync() {
  if (playerTimeSyncInterval) clearInterval(playerTimeSyncInterval);
  playerTimeSyncInterval = setInterval(() => {
    if (!isYtReady || !ytPlayer || !ytPlayer.getCurrentTime) return;
    try {
      const curTime = ytPlayer.getCurrentTime();
      syncLiveNoteTimestamp(curTime);

      // Auto-advance check at slice boundary
      if (isAutoAdvanceEnabled && activeAllocation && !isAutoAdvancing) {
        const endSec = activeAllocation.allocated_end_sec;
        if (endSec && curTime >= (endSec - 0.75)) {
          triggerAutoAdvance();
        }
      }
    } catch (e) {
      // Ignore transient errors
    }
  }, 350);
}

function stopPlayerTimeSync() {
  if (playerTimeSyncInterval) {
    clearInterval(playerTimeSyncInterval);
    playerTimeSyncInterval = null;
  }
}

function syncLiveNoteTimestamp(curTime) {
  const container = document.getElementById('notes-content') || document.getElementById('grounded-notes-container');
  if (!container) return;

  const buttons = container.querySelectorAll('.timestamp-link, .qa-citation-badge');
  if (!buttons || buttons.length === 0) return;

  let closestBtn = null;
  let minDiff = Infinity;

  buttons.forEach(btn => {
    const secStr = btn.getAttribute('data-timestamp-sec');
    if (!secStr) return;
    const sec = parseFloat(secStr);
    if (sec <= (curTime + 0.5)) {
      const diff = curTime - sec;
      if (diff < minDiff) {
        minDiff = diff;
        closestBtn = btn;
      }
    }
  });

  // Remove active highlight from all buttons
  buttons.forEach(b => {
    b.classList.remove('active-live-timestamp', 'ring-2', 'ring-accent', 'bg-accent', '!text-white', 'scale-105');
  });

  // Highlight active button if within 60s
  if (closestBtn && minDiff < 60) {
    closestBtn.classList.add('active-live-timestamp', 'ring-2', 'ring-accent', 'bg-accent', '!text-white', 'scale-105');
  }
}

async function triggerAutoAdvance() {
  if (isAutoAdvancing || !activeAllocation) return;
  isAutoAdvancing = true;
  showToast('⚡ Slice complete! Auto-advancing to next lesson...', 'success');

  const currentAllocId = activeAllocation.id;

  // 1. Mark current allocation complete
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/schedule/allocations/${currentAllocId}/complete`, {
      method: 'POST'
    });
    if (res.ok) {
      const updatedSched = await res.json();
      currentSchedule = updatedSched;
      renderSchedule(updatedSched);
    }
  } catch (err) {
    Logger.error('Auto-advance completion error', err);
  }

  // 2. Find next incomplete allocation in currentSchedule
  let nextAlloc = null;
  if (currentSchedule && currentSchedule.days) {
    for (const d of currentSchedule.days) {
      for (const a of d.allocations) {
        if (!a.is_completed && !a.is_skipped && a.id !== currentAllocId) {
          nextAlloc = a;
          break;
        }
      }
      if (nextAlloc) break;
    }
  }

  if (nextAlloc) {
    setTimeout(() => {
      selectAllocation(nextAlloc.id);
      isAutoAdvancing = false;
    }, 700);
  } else {
    showToast('🏆 Course Complete! All scheduled lessons completed.', 'success');
    isAutoAdvancing = false;
  }
}

function playVideoSlice(videoId, startSec, endSec) {
    if (!isYtReady || !ytPlayer || typeof ytPlayer.loadVideoById !== 'function') {
        pendingVideoSlice = { videoId, startSec, endSec };
        return;
    }
  if (!videoId) return;
  const placeholder = document.getElementById('yt-player-placeholder');
  if (placeholder) placeholder.classList.add('hidden');

  Logger.player('Seek & Play Slice', { videoId, startSec, endSec });

  if (isYtReady && ytPlayer && ytPlayer.loadVideoById) {
    if (currentCourse && currentCourse.playback_speed && typeof ytPlayer.setPlaybackRate === 'function') { try { ytPlayer.setPlaybackRate(Number(currentCourse.playback_speed)); } catch (_) {} }
        ytPlayer.loadVideoById({
      videoId: videoId,
      startSeconds: startSec || 0,
      endSeconds: endSec || undefined,
    });
  }
}

window.seekToSeconds = function(seconds) {
  Logger.player('Seek To Seconds', { seconds });
  if (isYtReady && ytPlayer && ytPlayer.seekTo) {
    ytPlayer.seekTo(seconds, true);
    if (ytPlayer.playVideo) {
      ytPlayer.playVideo();
    }
  }
};

// --- Theme Management (Dual Dark & Light Themes) ---
function initTheme() {
  const saved = localStorage.getItem('learn_lms_theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = saved ? saved === 'dark' : (saved === null ? true : false); // Default to sleek dark if unspecified
  applyTheme(isDark);
  Logger.theme(isDark ? 'dark' : 'light');
}

function toggleTheme() {
  const isCurrentlyDark = document.documentElement.classList.contains('dark');
  const newDark = !isCurrentlyDark;
  applyTheme(newDark);
  const themeName = newDark ? 'dark' : 'light';
  localStorage.setItem('learn_lms_theme', themeName);
  Logger.theme(themeName);
}

function applyTheme(isDark) {
  if (isDark) {
    document.documentElement.classList.add('dark');
    document.documentElement.classList.remove('light');
    if (themeIconSun) themeIconSun.classList.remove('hidden');
    if (themeIconMoon) themeIconMoon.classList.add('hidden');
  } else {
    document.documentElement.classList.remove('dark');
    document.documentElement.classList.add('light');
    if (themeIconSun) themeIconSun.classList.add('hidden');
    if (themeIconMoon) themeIconMoon.classList.remove('hidden');
  }
}

async function setRevisionBuffer(days) {
  Logger.schedule('Revision Buffer Change', `${days} days`);
  await replanCourse('normal', { revision_buffer_days: days });
}

// --- App Boot ---
document.addEventListener('DOMContentLoaded', async () => {
  console.log('%c[LearnLMS] Booting Personal LMS & Exam Prep...', 'color: #3b82f6; font-size: 14px; font-weight: bold;');
  initTheme();
  initSplitPanes();
  setupEventListeners();
  setDefaultTargetDate();
  await loadSettings();
  await refreshCourseList();
});

function setDefaultTargetDate() {
  const d = new Date();
  d.setDate(d.getDate() + 21);
  const dateStr = d.toISOString().split('T')[0];
  const targetDateInput = document.getElementById('input-target-date');
  if (targetDateInput) targetDateInput.value = dateStr;
}

function setupEventListeners() {
  courseSelector.addEventListener('change', (e) => {
    if (e.target.value) {
      loadCourse(e.target.value);
    }
  });

  btnNewCourse.addEventListener('click', showCreatorView);
  btnCancelCreator.addEventListener('click', () => {
    if (currentCourseId) showWorkspaceView();
  });

  // Preset Cards & Chips
  const populatePreset = (title, query) => {
    document.getElementById('input-course-title').value = title;
    document.getElementById('input-goal-query').value = query;
    const _presetTitleEl = document.getElementById('input-course-title');
    if (_presetTitleEl) {
        _presetTitleEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
        _presetTitleEl.classList.add('ring-2', 'ring-blue-500');
        setTimeout(() => _presetTitleEl.classList.remove('ring-2', 'ring-blue-500'), 1500);
    }
  };

  const selectExistingOrPopulate = (titleMatch, query, fallbackTitle) => {
    const opts = Array.from(courseSelector.options);
    const found = opts.find(o => o.textContent.toLowerCase().includes(titleMatch.toLowerCase()));
    if (found && found.value) {
      courseSelector.value = found.value;
      loadCourse(found.value);
      showWorkspaceView();
      return;
    }
    populatePreset(fallbackTitle, query);
  };

  document.getElementById('card-preset-dbms')?.addEventListener('click', () => {
    selectExistingOrPopulate('dbms', 'https://youtu.be/YRnjGeQbsHQ', 'Complete DBMS Marathon • One Shot Semester Prep');
  });

  document.getElementById('card-preset-toc')?.addEventListener('click', () => {
    selectExistingOrPopulate('theory of computation', 'https://youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev&si=rlyiJ9fIMBnIWFnj', 'Theory of Computation • Neso Academy Complete Playlist');
  });

  document.getElementById('chip-dbms-video')?.addEventListener('click', (e) => {
    e.preventDefault();
    populatePreset('Complete DBMS Marathon • One Shot Semester Prep', 'https://youtu.be/YRnjGeQbsHQ');
  });

  document.getElementById('chip-toc-playlist')?.addEventListener('click', (e) => {
    e.preventDefault();
    populatePreset('Theory of Computation • Neso Academy Complete Playlist', 'https://youtube.com/playlist?list=PLBlnK6fEyqRgp46KUv4ZY69yXmpwKOIev&si=rlyiJ9fIMBnIWFnj');
  });

  document.getElementById('chip-goal-text')?.addEventListener('click', (e) => {
    e.preventDefault();
    populatePreset('DBMS Comprehensive Exam Prep', 'DBMS end-term in 2 weeks, I know basics, 90 min/day');
  });

  courseCreateForm.addEventListener('submit', handleCourseCreate);
  btnApproveSelected.addEventListener('click', handleApproveSources);

  btnToggleActiveComplete.addEventListener('click', handleToggleActiveAllocation);
  btnSkipActive.addEventListener('click', handleSkipActiveAllocation);

  // Auto-Advance Toggle
  const btnAutoAdv = document.getElementById('btn-toggle-auto-advance');
  const lblAutoAdv = document.getElementById('auto-advance-label');
  if (btnAutoAdv && lblAutoAdv) {
    const updateAutoAdvUI = () => {
      lblAutoAdv.textContent = isAutoAdvanceEnabled ? 'ON' : 'OFF';
      if (isAutoAdvanceEnabled) {
        btnAutoAdv.className = 'bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/60 dark:hover:bg-amber-900/80 text-amber-700 dark:text-amber-300 text-xs px-2.5 py-1.5 rounded-lg border border-amber-300 dark:border-amber-700/80 transition flex items-center gap-1.5 active:scale-95 shadow-sm';
      } else {
        btnAutoAdv.className = 'bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-500 dark:text-slate-400 text-xs px-2.5 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 transition flex items-center gap-1.5 active:scale-95';
      }
    };
    updateAutoAdvUI();
    btnAutoAdv.addEventListener('click', () => {
      isAutoAdvanceEnabled = !isAutoAdvanceEnabled;
      localStorage.setItem('learn_lms_auto_advance', isAutoAdvanceEnabled ? 'true' : 'false');
      updateAutoAdvUI();
      showToast(`Auto-Advance turned ${isAutoAdvanceEnabled ? 'ON' : 'OFF'}`, 'info');
    });
  }

  // Global Keyboard Shortcuts for Frictionless Study
  document.addEventListener('keydown', (e) => {
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
    if (document.activeElement?.isContentEditable) return;

    if (e.code === 'Space') {
      if (isYtReady && ytPlayer && ytPlayer.getPlayerState) {
        e.preventDefault();
        const state = ytPlayer.getPlayerState();
        if (state === 1) {
          ytPlayer.pauseVideo();
          showToast('⏸ Paused', 'info');
        } else {
          ytPlayer.playVideo();
          showToast('▶ Playing', 'info');
        }
      }
    } else if (e.code === 'BracketLeft' || (e.code === 'ArrowLeft' && e.altKey)) {
      if (isYtReady && ytPlayer && ytPlayer.getCurrentTime) {
        e.preventDefault();
        const t = Math.max(0, ytPlayer.getCurrentTime() - 10);
        window.seekToSeconds(t);
        showToast('⏪ -10s', 'info');
      }
    } else if (e.code === 'BracketRight' || (e.code === 'ArrowRight' && e.altKey)) {
      if (isYtReady && ytPlayer && ytPlayer.getCurrentTime) {
        e.preventDefault();
        const t = ytPlayer.getCurrentTime() + 10;
        window.seekToSeconds(t);
        showToast('⏩ +10s', 'info');
      }
    } else if (e.code === 'KeyM' && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      btnToggleActiveComplete.click();
    } else if (e.code === 'Escape') {
      document.querySelectorAll('.fixed.z-50:not(.hidden)').forEach(m => m.classList.add('hidden'));
    }
  });

  btnReplanNow.addEventListener('click', () => {
    const speed = parseFloat(inlinePlaybackSpeed.value);
    const minDay = parseInt(inlineMinutesDay.value, 10);
    replanCourse('normal', { playback_speed: speed, minutes_per_day: minDay });
  });

  pillStrategyPaced.addEventListener('click', () => setStrategy('paced'));
  pillStrategyFixed.addEventListener('click', () => setStrategy('fixed'));

  if (pillBufferZero) pillBufferZero.addEventListener('click', () => setRevisionBuffer(0));
  if (pillBufferTwo) pillBufferTwo.addEventListener('click', () => setRevisionBuffer(2));
  if (btnThemeToggle) btnThemeToggle.addEventListener('click', toggleTheme);

  btnActionCompress.addEventListener('click', () => replanCourse('compress'));
  btnActionExtend.addEventListener('click', () => replanCourse('extend'));

  btnUndoDiff.addEventListener('click', handleUndo);
  btnDismissDiff.addEventListener('click', () => diffBanner.classList.add('hidden'));

  // Collapsible Layout Toggles
  btnCollapsePlayer.addEventListener('click', togglePlayerCollapse);
  btnCollapseSchedule.addEventListener('click', toggleScheduleCollapse);
  document.getElementById('btn-expand-rail-top')?.addEventListener('click', toggleScheduleCollapse);
  btnToggleCollapseAll.addEventListener('click', toggleCollapseAllDays);

  // Curriculum Drawer
  btnToggleCurriculum.addEventListener('click', () => curriculumDrawer.classList.toggle('hidden'));
  btnCloseCurriculum.addEventListener('click', () => curriculumDrawer.classList.add('hidden'));
  curriculumSearch.addEventListener('input', filterCurriculumDrawer);
  btnCurriculumIncludeAll?.addEventListener('click', () => handleFilterLessons('all'));
  btnCurriculumSkipExamples?.addEventListener('click', () => handleFilterLessons('concepts'));

  // Quick Filters (All / Concepts / Examples)
  btnFilterAll?.addEventListener('click', () => handleFilterLessons('all'));
  btnFilterConcepts?.addEventListener('click', () => handleFilterLessons('concepts'));
  btnFilterExamples?.addEventListener('click', () => handleFilterLessons('examples'));

  // Settings Modal
  btnSettings.addEventListener('click', () => settingsModal.classList.remove('hidden'));
  btnCloseSettings.addEventListener('click', () => settingsModal.classList.add('hidden'));
  document.getElementById('settings-llm-provider')?.addEventListener('change', handleLlmProviderChange);
  document.getElementById('btn-test-connection')?.addEventListener('click', handleTestConnection);
  document.getElementById('btn-save-keys')?.addEventListener('click', handleSaveKeys);
  document.getElementById('btn-save-study-defaults')?.addEventListener('click', handleSaveStudyDefaults);
  document.getElementById('btn-update-ytdlp')?.addEventListener('click', handleUpdateYtdlp);
  document.getElementById('btn-cleanup-cache')?.addEventListener('click', handleCleanupCache);
  document.getElementById('settings-browser-cookies')?.addEventListener('change', handleUpdateBrowserCookies);
  document.getElementById('btn-export-markdown')?.addEventListener('click', handleExportMarkdown);
  document.getElementById('btn-submit-manual-fallback')?.addEventListener('click', handleManualFallbackSubmit);

  // Edit Course Listeners
  btnEditCourse?.addEventListener('click', openEditCourseModal);
  kpiCardExamDate?.addEventListener('click', openEditCourseModal);
  kpiCardPaceSpeed?.addEventListener('click', openEditCourseModal);
  btnCloseEditCourse?.addEventListener('click', () => editCourseModal.classList.add('hidden'));
  btnCancelEditCourse?.addEventListener('click', () => editCourseModal.classList.add('hidden'));
  formEditCourse?.addEventListener('submit', handleSaveCourse);

  // Edit Lesson Listeners
  btnEditActiveTitle?.addEventListener('click', () => {
    if (activeAllocation) openEditLessonModal(activeAllocation.lesson_id, activeAllocation.id);
  });
  activeLessonTitle?.addEventListener('click', () => {
    if (activeAllocation) openEditLessonModal(activeAllocation.lesson_id, activeAllocation.id);
  });
  btnEditActiveLesson?.addEventListener('click', () => {
    if (activeAllocation) openEditLessonModal(activeAllocation.lesson_id, activeAllocation.id);
  });
  btnToggleActivePriority?.addEventListener('click', toggleActivePriority);
  btnCloseEditLesson?.addEventListener('click', () => editLessonModal.classList.add('hidden'));
  btnCancelEditLesson?.addEventListener('click', () => editLessonModal.classList.add('hidden'));
  formEditLesson?.addEventListener('submit', handleSaveLesson);

  // Edit Flashcard Listeners
  btnEditActiveCard?.addEventListener('click', openEditCardModal);
  document.getElementById('btn-edit-active-card-back')?.addEventListener('click', openEditCardModal);
  btnCloseEditCard?.addEventListener('click', () => editCardModal.classList.add('hidden'));
  btnCancelEditCard?.addEventListener('click', () => editCardModal.classList.add('hidden'));
  btnDeleteCardFromModal?.addEventListener('click', handleDeleteCardFromModal);
  formEditCard?.addEventListener('submit', handleSaveEditCard);

  // Markdown Toolbar & Personal Notes Save
  document.querySelectorAll('.md-tool-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const format = btn.getAttribute('data-format');
      applyMarkdownFormat(format);
    });
  });
  btnSavePersonalNotes?.addEventListener('click', handleSavePersonalNotesManual);
  inputPersonalNotes?.addEventListener('input', updatePersonalNotesCount);

  // Notes Tabs & Actions
  tabGroundedNotes.addEventListener('click', () => switchNotesTab('grounded'));
  tabPersonalNotes.addEventListener('click', () => switchNotesTab('personal'));
  tabQaNotebook.addEventListener('click', () => switchNotesTab('qa'));
  qaInputForm?.addEventListener('submit', handleAskQuestion);
  qaScopeLesson?.addEventListener('click', () => setQAScope('lesson'));
  qaScopeNotebook?.addEventListener('click', () => setQAScope('notebook'));
  document.querySelectorAll('.quick-prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.getAttribute('data-prompt') || chip.textContent.trim();
      useQuickPrompt(prompt);
    });
  });
  initHighlightToExplain();
  btnTranscribeLesson.addEventListener('click', handleTranscribeLesson);
  btnCaptureKeyframes.addEventListener('click', handleCaptureKeyframes);
  document.getElementById('btn-snap-current-to-notes')?.addEventListener('click', () => insertCurrentFrameToNotes());
  document.getElementById('btn-toolbar-snap-frame')?.addEventListener('click', () => insertCurrentFrameToNotes());
  document.getElementById('btn-print-grounded-notes')?.addEventListener('click', () => printGroundedNotes());
  document.getElementById('btn-download-grounded-notes')?.addEventListener('click', () => downloadGroundedNotesMarkdown());
  document.getElementById('btn-copy-to-personal-notes')?.addEventListener('click', () => copyGroundedToPersonalNotes());
  btnRegenerateNotes.addEventListener('click', () => {
    if (activeAllocation) loadLessonNotesAndArtifacts(activeAllocation.lesson_id, true);
  });
  inputPersonalNotes.addEventListener('input', handlePersonalNotesInput);

  // Add Source Modal & Tabs
  btnOpenAddSource.addEventListener('click', () => addSourceModal.classList.remove('hidden'));
  btnCloseAddSource.addEventListener('click', () => addSourceModal.classList.add('hidden'));
  tabSrcPdf.addEventListener('click', () => switchSourceModalTab('pdf'));
  tabSrcWeb.addEventListener('click', () => switchSourceModalTab('web'));
  document.getElementById('tab-src-discover-web')?.addEventListener('click', () => switchSourceModalTab('discover-web'));
  document.getElementById('btn-approve-web-docs')?.addEventListener('click', handleApproveWebDocs);
  formUploadPdf.addEventListener('submit', handleUploadPdf);
  formImportWeb.addEventListener('submit', handleImportWeb);

  // Past Papers (PYQ) Listeners
  document.getElementById('tab-src-pyq')?.addEventListener('click', () => switchSourceModalTab('pyq'));
  document.getElementById('form-upload-pyq')?.addEventListener('submit', handleUploadPyq);
  document.getElementById('tab-pyq-questions')?.addEventListener('click', () => switchNotesTab('pyq'));
  document.getElementById('btn-open-pyq-upload-shortcut')?.addEventListener('click', () => openAddSourceModalWithTab('pyq'));

  // PYQ High-Yield Filter Listener
  const btnFilterPyq = document.getElementById('btn-filter-pyq');
  if (btnFilterPyq) {
    btnFilterPyq.addEventListener('click', () => {
      if (window.currentLessonFilter === 'pyq') {
        window.currentLessonFilter = null;
        btnFilterPyq.className = 'px-2 py-0.5 rounded text-[11px] font-medium text-amber-700 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-950/40 border border-transparent hover:border-amber-300 dark:hover:border-amber-700/60 transition';
      } else {
        window.currentLessonFilter = 'pyq';
        btnFilterPyq.className = 'px-2 py-0.5 rounded text-[11px] font-bold bg-amber-600 text-white shadow-sm border border-amber-700 transition';
      }
      if (currentSchedule) {
        renderSchedule(currentSchedule);
      }
    });
  }

  // Settings Modal Duplicate Action Handlers
  document.getElementById('modal-btn-edit-course')?.addEventListener('click', openEditCourseModal);
  document.getElementById('modal-pill-strategy-paced')?.addEventListener('click', () => setStrategy('paced'));
  document.getElementById('modal-pill-strategy-fixed')?.addEventListener('click', () => setStrategy('fixed'));
  document.getElementById('modal-btn-diagnostic-test')?.addEventListener('click', openDiagnosticPreTest);
  document.getElementById('modal-btn-toggle-curriculum')?.addEventListener('click', () => curriculumDrawer.classList.toggle('hidden'));

  // Last-Night Cram Sheet Listeners
  document.getElementById('btn-open-cram-sheet')?.addEventListener('click', () => loadCramSheet(false));
  document.getElementById('btn-close-cram-sheet')?.addEventListener('click', () => {
    document.getElementById('modal-cram-sheet')?.classList.add('hidden');
  });
  document.getElementById('btn-refresh-cram-sheet')?.addEventListener('click', () => loadCramSheet(true, false));
  document.getElementById('btn-full-cram-sheet')?.addEventListener('click', () => loadCramSheet(true, true));
  document.getElementById('btn-print-cram-sheet')?.addEventListener('click', () => window.print());
  document.getElementById('btn-download-cram-md')?.addEventListener('click', () => {
    if (!currentCourseId) {
      alert('Select a course first.');
      return;
    }
    window.open(`/api/courses/${currentCourseId}/cram-sheet/download`, '_blank');
  });

  // Syllabus Alignment & Matcher Listeners
  document.getElementById('btn-open-syllabus-modal')?.addEventListener('click', openSyllabusModal);
  document.getElementById('btn-curriculum-match-syllabus')?.addEventListener('click', openSyllabusModal);
  document.getElementById('modal-btn-match-syllabus')?.addEventListener('click', openSyllabusModal);
  document.getElementById('btn-close-syllabus-modal')?.addEventListener('click', closeSyllabusModal);
  document.getElementById('btn-analyze-syllabus')?.addEventListener('click', handleAnalyzeSyllabus);
  document.getElementById('btn-apply-syllabus')?.addEventListener('click', handleApplySyllabus);
  document.getElementById('btn-syl-back')?.addEventListener('click', () => {
    document.getElementById('syllabus-step-review')?.classList.add('hidden');
    document.getElementById('syllabus-step-input')?.classList.remove('hidden');
  });
  document.getElementById('tab-syl-topics')?.addEventListener('click', () => switchSyllabusReviewTab('topics'));
  document.getElementById('tab-syl-checklist')?.addEventListener('click', () => switchSyllabusReviewTab('checklist'));
  document.getElementById('pill-syl-balanced')?.addEventListener('click', () => setSyllabusStrictness('balanced'));
  document.getElementById('pill-syl-strict')?.addEventListener('click', () => setSyllabusStrictness('strict'));
  document.getElementById('pill-syl-comprehensive')?.addEventListener('click', () => setSyllabusStrictness('comprehensive'));

  document.getElementById('btn-syl-select-matched')?.addEventListener('click', () => {
    if (window.currentSyllabusMatch) {
      window.selectedSyllabusLessonIds = new Set(
        window.currentSyllabusMatch.lessons.filter(l => l.is_matched).map(l => l.id)
      );
      renderSyllabusChecklistView(window.currentSyllabusMatch);
      updateSyllabusSelectedCount();
    }
  });
  document.getElementById('btn-syl-select-all')?.addEventListener('click', () => {
    if (window.currentSyllabusMatch) {
      window.selectedSyllabusLessonIds = new Set(
        window.currentSyllabusMatch.lessons.map(l => l.id)
      );
      renderSyllabusChecklistView(window.currentSyllabusMatch);
      updateSyllabusSelectedCount();
    }
  });
  document.getElementById('btn-syl-deselect-all')?.addEventListener('click', () => {
    window.selectedSyllabusLessonIds.clear();
    if (window.currentSyllabusMatch) {
      renderSyllabusChecklistView(window.currentSyllabusMatch);
    }
    updateSyllabusSelectedCount();
  });

  // Quiz & Mastery Listeners
  tabQuizMastery.addEventListener('click', () => switchNotesTab('quiz'));
  btnGenerateLessonQuiz.addEventListener('click', () => {
    const count = parseInt(quizQuestionCount.value, 10) || 5;
    handleGenerateLessonQuiz(count);
  });
  quizForm.addEventListener('submit', handleLessonQuizSubmit);

  // FSRS Flashcards Listeners
  tabFlashcardsFsrs.addEventListener('click', () => switchNotesTab('flashcards'));
  btnAddCardManual.addEventListener('click', () => addCardModal.classList.remove('hidden'));
  btnCloseAddCard.addEventListener('click', () => addCardModal.classList.add('hidden'));
  formCreateCard.addEventListener('submit', handleCreateCardManual);
  fsrsCardFlipper.addEventListener('click', flipActiveCard);
  btnFsrsAgain.addEventListener('click', () => submitCardRating(1));
  btnFsrsHard.addEventListener('click', () => submitCardRating(2));
  btnFsrsGood.addEventListener('click', () => submitCardRating(3));
  btnFsrsEasy.addEventListener('click', () => submitCardRating(4));

  // Diagnostic Pre-Test & Mock Exam Listeners
  btnDiagnosticTest.addEventListener('click', openDiagnosticPreTest);
  btnCloseDiagnostic.addEventListener('click', () => diagnosticModal.classList.add('hidden'));
  btnSubmitDiagnostic.addEventListener('click', handleSubmitDiagnostic);
  btnMockExam.addEventListener('click', openMockExam);
  btnCloseMockExam.addEventListener('click', closeMockExam);
  btnSubmitMockExam.addEventListener('click', handleSubmitMockExam);

  // Global Keyboard Shortcuts
  document.addEventListener('keydown', handleFlashcardKeydown);

  // Pyodide Web Worker Listeners
  tabPyodideScratchpad.addEventListener('click', () => switchNotesTab('pyodide'));
  btnRunPyodide.addEventListener('click', runPythonCode);
  document.getElementById('btn-stop-pyodide')?.addEventListener('click', stopPythonWorker);
  btnClearCode.addEventListener('click', () => { pyodideCodeInput.value = ''; pyodideOutput.textContent = ''; });
  pyodidePresets.addEventListener('change', handlePyodidePresetChange);

  // Storage Vacuum, Backup & Export
  btnVacuumDb.addEventListener('click', handleVacuumDb);
  btnDownloadDb.addEventListener('click', handleDownloadDbBackup);
  btnExportBundle.addEventListener('click', handleExportCourseBundle);
}

// --- Dual Splitters & Layout Resizing ---
function initSplitPanes() {
  const getIframe = () => document.getElementById('yt-iframe') || document.querySelector('#yt-player iframe');

  // 1. Horizontal Splitter (Video vs Notes)
  const videoNotesSplitter = document.getElementById('video-notes-splitter');
  const playerWrapper = document.getElementById('player-wrapper');
  const snapCompact = document.getElementById('snap-compact-video');
  const snapBalanced = document.getElementById('snap-balanced-video');
  const snapToggle = document.getElementById('snap-toggle-video') || document.getElementById('btn-collapse-player');

  // Restore saved video pane height from localStorage
  const savedVideoHeight = localStorage.getItem('lms_video_pane_height');
  if (savedVideoHeight && playerWrapper) {
    playerWrapper.style.setProperty('--video-pane-height', savedVideoHeight);
    playerWrapper.style.height = savedVideoHeight;
  }

  const setVideoHeight = (val) => {
    if (!playerWrapper) return;
    playerWrapper.style.setProperty('--video-pane-height', val);
    playerWrapper.style.height = val;
    localStorage.setItem('lms_video_pane_height', val);
  };

  if (snapCompact) {
    snapCompact.addEventListener('click', (e) => {
      e.stopPropagation();
      setVideoHeight('25vh');
    });
  }
  if (snapBalanced) {
    snapBalanced.addEventListener('click', (e) => {
      e.stopPropagation();
      setVideoHeight('38vh');
    });
  }
  if (snapToggle && snapToggle.id === 'snap-toggle-video') {
    snapToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      togglePlayerCollapse();
    });
  }

  if (videoNotesSplitter && playerWrapper) {
    let isDragging = false;
    let startY = 0;
    let startHeight = 0;

    videoNotesSplitter.addEventListener('mousedown', (e) => {
      if (e.target.closest('button')) return;
      isDragging = true;
      startY = e.clientY;
      startHeight = playerWrapper.getBoundingClientRect().height;
      const iframe = getIframe();
      if (iframe) iframe.style.pointerEvents = 'none';
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';
    });

    videoNotesSplitter.addEventListener('dblclick', (e) => {
      if (e.target.closest('button')) return;
      setVideoHeight('34vh');
    });

    window.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const deltaY = e.clientY - startY;
      const newHeight = startHeight + deltaY;
      const vh55 = window.innerHeight * 0.55;
      const clamped = Math.max(180, Math.min(vh55, newHeight));
      const heightVal = `${Math.round(clamped)}px`;
      playerWrapper.style.setProperty('--video-pane-height', heightVal);
      playerWrapper.style.height = heightVal;
    });

    window.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        const iframe = getIframe();
        if (iframe) iframe.style.pointerEvents = 'auto';
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        if (playerWrapper.style.height) {
          localStorage.setItem('lms_video_pane_height', playerWrapper.style.height);
        }
      }
    });
  }

  // 2. Vertical Splitter (Center Study Column vs Right Studio Panel)
  const studioSplitter = document.getElementById('studio-splitter');
  const paneRightStudio = document.getElementById('pane-right-studio');
  const btnToggleStudio = document.getElementById('btn-toggle-studio');

  // Restore saved right studio width and collapsed state
  const savedStudioWidth = localStorage.getItem('lms_studio_panel_width');
  if (savedStudioWidth && paneRightStudio) {
    paneRightStudio.style.width = savedStudioWidth;
  }
  const savedStudioCollapsed = localStorage.getItem('lms_studio_collapsed');
  if (savedStudioCollapsed === 'true' && paneRightStudio) {
    paneRightStudio.classList.add('hidden');
    if (studioSplitter) studioSplitter.classList.add('hidden');
  }

  const toggleStudio = () => {
    if (!paneRightStudio) return;
    const isHidden = paneRightStudio.classList.toggle('hidden');
    if (studioSplitter) {
      if (isHidden) studioSplitter.classList.add('hidden');
      else studioSplitter.classList.remove('hidden');
    }
    localStorage.setItem('lms_studio_collapsed', isHidden ? 'true' : 'false');
  };

  if (btnToggleStudio) {
    btnToggleStudio.addEventListener('click', toggleStudio);
  }

  if (studioSplitter && paneRightStudio) {
    let isDraggingStudio = false;
    let startX = 0;
    let startW = 0;

    studioSplitter.addEventListener('mousedown', (e) => {
      isDraggingStudio = true;
      startX = e.clientX;
      startW = paneRightStudio.getBoundingClientRect().width;
      const iframe = getIframe();
      if (iframe) iframe.style.pointerEvents = 'none';
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    });

    studioSplitter.addEventListener('dblclick', () => {
      paneRightStudio.style.width = '380px';
      localStorage.setItem('lms_studio_panel_width', '380px');
    });

    window.addEventListener('mousemove', (e) => {
      if (!isDraggingStudio) return;
      const deltaX = startX - e.clientX;
      const newWidth = startW + deltaX;
      const maxW = window.innerWidth * 0.55;
      const clamped = Math.max(300, Math.min(maxW, newWidth));
      const widthVal = `${Math.round(clamped)}px`;
      paneRightStudio.style.width = widthVal;
    });

    window.addEventListener('mouseup', () => {
      if (isDraggingStudio) {
        isDraggingStudio = false;
        const iframe = getIframe();
        if (iframe) iframe.style.pointerEvents = 'auto';
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        if (paneRightStudio.style.width) {
          localStorage.setItem('lms_studio_panel_width', paneRightStudio.style.width);
        }
      }
    });
  }

  // 3. Left Rail Collapsed State Persistence
  const savedRailCollapsed = localStorage.getItem('lms_rail_collapsed');
  if (savedRailCollapsed === 'true' && paneSchedule) {
    paneSchedule.classList.add('rail-collapsed');
  }
}

// --- Layout Collapsing ---
function togglePlayerCollapse() {
  const isHidden = document.getElementById('player-wrapper').classList.toggle('hidden');
  Logger.player('Toggle Player Collapse', { isHidden });
}

function toggleScheduleCollapse() {
  if (!paneSchedule) return;
  const isCollapsed = paneSchedule.classList.toggle('rail-collapsed');
  localStorage.setItem('lms_rail_collapsed', isCollapsed ? 'true' : 'false');
  Logger.layout('Toggle Schedule Rail Collapse', { isCollapsed });
}

function renderCollapsedRailBadges(days) {
  const container = document.getElementById('collapsed-rail-badges');
  if (!container || !days) return;
  container.innerHTML = '';
  days.forEach((day, idx) => {
    const dayNum = idx + 1;
    const allDone = day.allocations && day.allocations.length > 0 && day.allocations.every(a => a.is_completed);
    const hasToday = (day.date === new Date().toISOString().split('T')[0]);

    const badge = document.createElement('button');
    badge.type = 'button';
    badge.className = `w-9 h-9 rounded-xl flex flex-col items-center justify-center text-xs font-mono font-bold transition shadow-sm active:scale-95 ${
      hasToday 
        ? 'bg-accent text-white ring-2 ring-accent/40' 
        : allDone 
        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800'
        : 'bg-bg-canvas hover:bg-bg-card text-text-primary border border-border-subtle'
    }`;
    badge.title = `${day.day_name}, ${day.date} • ${Math.round(day.total_effective_minutes)}m`;
    badge.innerHTML = allDone 
      ? `<span>D${dayNum}</span><span class="text-[9px] leading-none">✓</span>`
      : `<span>D${dayNum}</span>`;

    badge.addEventListener('click', () => {
      toggleScheduleCollapse();
      setTimeout(() => {
        const el = document.querySelector(`[data-day-date="${day.date}"]`);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 50);
    });
    container.appendChild(badge);
  });
}

function toggleCollapseAllDays() {
  areAllDaysCollapsed = !areAllDaysCollapsed;
  const dayBodies = document.querySelectorAll('.day-body');
  const dayChevrons = document.querySelectorAll('.day-chevron');
  dayBodies.forEach(b => {
    if (areAllDaysCollapsed) b.classList.add('hidden');
    else b.classList.remove('hidden');
  });
  dayChevrons.forEach(c => {
    c.style.transform = areAllDaysCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)';
  });
  btnToggleCollapseAll.textContent = areAllDaysCollapsed ? 'Expand Days' : 'Collapse Days';
}

window.toggleDayCollapse = function(dayDate) {
  const body = document.getElementById(`day-body-${dayDate}`);
  const chevron = document.getElementById(`day-chevron-${dayDate}`);
  if (!body) return;
  const isNowHidden = body.classList.toggle('hidden');
  if (chevron) {
    chevron.style.transform = isNowHidden ? 'rotate(-90deg)' : 'rotate(0deg)';
  }
  if (isNowHidden) collapsedDays.add(dayDate);
  else collapsedDays.delete(dayDate);
};

// --- Toast Notification System ---
function showToast(message, type = 'info') {
  if (!toastContainer) return;
  const toast = document.createElement('div');
  const bg = type === 'success' 
    ? 'bg-emerald-600 text-white shadow-emerald-500/20' 
    : type === 'error' 
    ? 'bg-red-600 text-white shadow-red-500/20' 
    : 'bg-accent text-white shadow-blue-500/20';
  toast.className = `px-4 py-2.5 rounded-2xl shadow-xl flex items-center gap-2 text-xs font-semibold ${bg} transition-all duration-300 transform translate-y-4 opacity-0 pointer-events-auto border border-white/20`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✓' : type === 'error' ? '✕' : '⚡'}</span>
    <span>${escapeHtml(message)}</span>
  `;
  toastContainer.appendChild(toast);
  requestAnimationFrame(() => {
    toast.classList.remove('translate-y-4', 'opacity-0');
  });
  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// --- Edit Course Settings Handlers ---
function openEditCourseModal() {
  if (!currentCourse) return;
  document.getElementById('edit-course-title').value = currentCourse.title || '';
  document.getElementById('edit-course-target-date').value = currentCourse.target_date || '';
  document.getElementById('edit-course-minutes').value = currentCourse.minutes_per_day || 90;
  document.getElementById('edit-course-speed').value = currentCourse.playback_speed || 1.25;
  document.getElementById('edit-course-buffer').value = currentCourse.revision_buffer_days ?? 2;
  const daysInput = document.getElementById('edit-course-days');
  if (daysInput) daysInput.value = currentCourse.num_study_days || '';
  const prefMinInput = document.getElementById('edit-course-pref-minutes');
  if (prefMinInput) prefMinInput.value = currentCourse.preferred_daily_minutes || 60;
  
  const strat = currentCourse.schedule_strategy || 'paced';
  const pacedRadio = document.getElementById('edit-strat-paced');
  const fixedRadio = document.getElementById('edit-strat-fixed');
  if (pacedRadio && fixedRadio) {
    if (strat === 'paced') pacedRadio.checked = true;
    else fixedRadio.checked = true;
  }

  const restDays = currentCourse.rest_days || ['Sunday'];
  document.querySelectorAll('.edit-rest-checkbox').forEach(cb => {
    cb.checked = restDays.includes(cb.value);
  });

  editCourseModal.classList.remove('hidden');
}

async function handleSaveCourse(e) {
  e.preventDefault();
  if (!currentCourseId) return;

  const title = document.getElementById('edit-course-title').value.trim();
  const targetDate = document.getElementById('edit-course-target-date').value;
  const minutes = parseInt(document.getElementById('edit-course-minutes').value, 10);
  const speed = parseFloat(document.getElementById('edit-course-speed').value);
  const buffer = parseInt(document.getElementById('edit-course-buffer').value, 10);
  const strategy = document.querySelector('input[name="edit-strategy"]:checked')?.value || 'paced';
  
  const restDays = [];
  document.querySelectorAll('.edit-rest-checkbox:checked').forEach(cb => {
    restDays.push(cb.value);
  });

  const daysVal = document.getElementById('edit-course-days')?.value;
  const numDays = daysVal ? parseInt(daysVal, 10) : null;
  const prefMinVal = document.getElementById('edit-course-pref-minutes')?.value;
  const prefMinutes = prefMinVal ? parseInt(prefMinVal, 10) : (minutes || 60);

  try {
    const payload = {
      title,
      target_date: targetDate,
      minutes_per_day: minutes,
      playback_speed: speed,
      revision_buffer_days: buffer,
      schedule_strategy: strategy,
      rest_days: restDays,
      num_study_days: numDays,
      preferred_daily_minutes: prefMinutes,
    };

    let res = await fetch(`/api/courses/${currentCourseId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    // Fallback to PUT if PATCH returns 405 (Method Not Allowed)
    if (res.status === 405) {
      res = await fetch(`/api/courses/${currentCourseId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    }

    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.detail || 'Failed to update course');
    }

    editCourseModal.classList.add('hidden');
    showToast('Course settings updated! Replanning schedule...', 'success');

    // Automatically replan to reflow schedule with new params
    await replanCourse('normal', {
      target_date: targetDate,
      minutes_per_day: minutes,
      playback_speed: speed,
      revision_buffer_days: buffer,
      schedule_strategy: strategy,
      rest_days: restDays,
      num_study_days: numDays,
      preferred_daily_minutes: prefMinutes,
    });
    await refreshCourseList();
  } catch (err) {
    Logger.error('Failed to update course', err);
    showToast('Failed to update course: ' + err.message, 'error');
  }
}

// --- Edit Lesson Handlers ---
async function openEditLessonModal(lessonId, allocId) {
  if (!lessonId) return;
  const lesson = currentLessons.find(l => l.id === lessonId);
  if (!lesson) return;

  editLessonId.value = lessonId;
  editLessonAllocId.value = allocId || '';
  editLessonTitleInput.value = lesson.title || '';
  editLessonPriorityInput.value = lesson.priority || 'core';
  editLessonSummaryInput.value = lesson.summary || '';

  if (allocId && currentSchedule) {
    for (const d of currentSchedule.days) {
      const a = d.allocations.find(x => x.id === allocId);
      if (a) {
        editLessonRescheduleDate.value = a.scheduled_date;
        break;
      }
    }
  } else {
    editLessonRescheduleDate.value = '';
  }

  editLessonModal.classList.remove('hidden');
}

window.editScheduleLesson = function(lessonId, allocId, event) {
  if (event) event.stopPropagation();
  openEditLessonModal(lessonId, allocId);
};

window.toggleAllocPriority = async function(lessonId, event) {
  if (event) event.stopPropagation();
  if (!currentCourseId || !lessonId) return;
  const current = currentLessons.find(l => l.id === lessonId);
  const newPriority = (current && current.priority === 'deep-dive') ? 'core' : 'deep-dive';
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/lessons/${lessonId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ priority: newPriority }),
    });
    if (!res.ok) throw new Error('Failed to update priority');
    showToast(`Priority changed to ${newPriority.toUpperCase()}`, 'success');
    await loadLessons(currentCourseId);
    await loadSchedule(currentCourseId);
    if (activeAllocation && activeAllocation.lesson_id === lessonId) {
      activeAllocation.priority = newPriority;
      if (activeLessonPriority) activeLessonPriority.textContent = newPriority.toUpperCase();
    }
  } catch (err) {
    Logger.error('Failed to toggle priority', err);
    showToast('Failed to toggle priority: ' + err.message, 'error');
  }
};

async function handleSaveLesson(e) {
  e.preventDefault();
  const lid = editLessonId.value;
  const aid = editLessonAllocId.value;
  if (!lid || !currentCourseId) return;

  const newTitle = editLessonTitleInput.value.trim();
  const newPriority = editLessonPriorityInput.value;
  const newSummary = editLessonSummaryInput.value.trim();
  const newDate = editLessonRescheduleDate.value;

  try {
    const res = await fetch(`/api/courses/${currentCourseId}/lessons/${lid}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: newTitle,
        priority: newPriority,
        summary: newSummary,
      }),
    });
    if (!res.ok) throw new Error('Failed to update lesson');

    if (aid && newDate) {
      await fetch(`/api/courses/${currentCourseId}/schedule/allocations/${aid}/reschedule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_date: newDate }),
      });
    }

    editLessonModal.classList.add('hidden');
    showToast('Lesson updated successfully!', 'success');

    await loadLessons(currentCourseId);
    await loadSchedule(currentCourseId);
    if (activeAllocation && activeAllocation.lesson_id === lid) {
      activeLessonTitle.textContent = newTitle;
      activeLessonPriority.textContent = newPriority.toUpperCase();
    }
  } catch (err) {
    Logger.error('Failed to save lesson', err);
    showToast('Error updating lesson: ' + err.message, 'error');
  }
}

async function toggleActivePriority() {
  if (!activeAllocation || !currentCourseId) return;
  const currentP = (activeAllocation.priority || 'core').toLowerCase();
  const nextP = currentP === 'core' ? 'deep-dive' : 'core';

  try {
    const res = await fetch(`/api/courses/${currentCourseId}/lessons/${activeAllocation.lesson_id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ priority: nextP }),
    });
    if (!res.ok) throw new Error('Failed to toggle priority');

    activeAllocation.priority = nextP;
    activeLessonPriority.textContent = nextP.toUpperCase();
    showToast(`Switched priority to ${nextP.toUpperCase()}`, 'info');
    await loadSchedule(currentCourseId);
  } catch (err) {
    Logger.error('Failed to toggle priority', err);
    showToast('Error toggling priority: ' + err.message, 'error');
  }
}

// --- Edit Flashcard Handlers ---
function openEditCardModal() {
  if (!currentCardUnderReview) return;
  editCardId.value = currentCardUnderReview.id;
  editCardFrontInput.value = currentCardUnderReview.front || '';
  editCardBackInput.value = currentCardUnderReview.back || '';
  editCardModal.classList.remove('hidden');
}

async function handleSaveEditCard(e) {
  e.preventDefault();
  const cid = editCardId.value;
  if (!cid || !currentCourseId) return;

  const front = editCardFrontInput.value.trim();
  const back = editCardBackInput.value.trim();

  try {
    const res = await fetch(`/api/courses/${currentCourseId}/flashcards/${cid}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ front, back }),
    });
    if (!res.ok) throw new Error('Update card failed');
    const updated = await res.json();
    currentCardUnderReview = updated;

    fsrsFrontText.textContent = front;
    fsrsBackText.textContent = back;

    editCardModal.classList.add('hidden');
    showToast('Flashcard updated!', 'success');
  } catch (err) {
    Logger.error('Failed to update card', err);
    showToast('Error updating card: ' + err.message, 'error');
  }
}

async function handleDeleteCardFromModal() {
  const cid = editCardId.value;
  if (!cid || !currentCourseId) return;
  if (!confirm('Are you sure you want to delete this flashcard?')) return;

  try {
    const res = await fetch(`/api/courses/${currentCourseId}/flashcards/${cid}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Delete failed');
    editCardModal.classList.add('hidden');
    showToast('Flashcard deleted!', 'info');
    await updateFlashcardCounts();
    await loadFlashcards();
  } catch (err) {
    Logger.error('Failed to delete card', err);
    showToast('Error deleting card: ' + err.message, 'error');
  }
}

// --- Markdown Toolbar Handlers ---
function applyMarkdownFormat(format) {
  if (!inputPersonalNotes) return;
  const start = inputPersonalNotes.selectionStart;
  const end = inputPersonalNotes.selectionEnd;
  const text = inputPersonalNotes.value;
  const selected = text.substring(start, end);

  let replacement = '';
  let newCursorPos = start;

  switch (format) {
    case 'bold':
      replacement = `**${selected || 'bold text'}**`;
      newCursorPos = selected ? end + 4 : start + 2;
      break;
    case 'italic':
      replacement = `*${selected || 'italic text'}*`;
      newCursorPos = selected ? end + 2 : start + 1;
      break;
    case 'heading':
      replacement = `\n## ${selected || 'Heading'}\n`;
      newCursorPos = selected ? end + 5 : start + 4;
      break;
    case 'code':
      replacement = `\`${selected || 'code'}\``;
      newCursorPos = selected ? end + 2 : start + 1;
      break;
    case 'bullet':
      replacement = `\n- ${selected || 'List item'}\n`;
      newCursorPos = selected ? end + 4 : start + 3;
      break;
    case 'quote':
      replacement = `\n> ${selected || 'Quote'}\n`;
      newCursorPos = selected ? end + 4 : start + 3;
      break;
    default:
      return;
  }

  inputPersonalNotes.value = text.substring(0, start) + replacement + text.substring(end);
  inputPersonalNotes.focus();
  inputPersonalNotes.setSelectionRange(newCursorPos, newCursorPos);
  updatePersonalNotesCount();
}

function updatePersonalNotesCount() {
  if (!personalNotesWordCount || !inputPersonalNotes) return;
  const val = inputPersonalNotes.value.trim();
  const words = val ? val.split(/\s+/).length : 0;
  personalNotesWordCount.textContent = `${words} word${words === 1 ? '' : 's'}`;
}

async function handleSavePersonalNotesManual() {
  if (!activeAllocation) {
    showToast('Select a lesson first', 'info');
    return;
  }
  const text = inputPersonalNotes.value;
  try {
    const res = await fetch(`/api/lessons/${activeAllocation.lesson_id}/notes/personal`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ personal_notes: text }),
    });
    if (!res.ok) throw new Error('Save failed');
    personalNoteSaveStatus.textContent = '✓ Saved ' + new Date().toLocaleTimeString();
    showToast('Personal notes saved!', 'success');
  } catch (err) {
    Logger.error('Failed to save personal notes', err);
    showToast('Error saving notes', 'error');
  }
}

// --- Strategy Switching (Paced vs Fixed) ---
function updateStrategyPills(strategy) {
  if (strategy === 'paced') {
    pillStrategyPaced.className = 'px-2 py-0.5 rounded font-medium transition strategy-btn bg-blue-600 text-white shadow-sm';
    pillStrategyFixed.className = 'px-2 py-0.5 rounded font-medium transition strategy-btn text-alabaster-muted dark:text-charcoal-muted hover:text-alabaster-text dark:hover:text-charcoal-text';
  } else {
    pillStrategyFixed.className = 'px-2 py-0.5 rounded font-medium transition strategy-btn bg-blue-600 text-white shadow-sm';
    pillStrategyPaced.className = 'px-2 py-0.5 rounded font-medium transition strategy-btn text-alabaster-muted dark:text-charcoal-muted hover:text-alabaster-text dark:hover:text-charcoal-text';
  }
}

async function setStrategy(strategy) {
  updateStrategyPills(strategy);
  Logger.schedule('Strategy Change', strategy);
  await replanCourse('normal', { schedule_strategy: strategy });
}

// --- View Navigation ---
function showWorkspaceView() {
  workspaceView.classList.remove('hidden');
  creatorView.classList.add('hidden');
}

function showCreatorView() {
  workspaceView.classList.add('hidden');
  creatorView.classList.remove('hidden');
  approvalGate.classList.add('hidden');
}

// --- API Calls & Handlers ---
async function refreshCourseList() {
  const t0 = performance.now();
  try {
    const res = await fetch('/api/courses');
    const courses = await res.json();
    Logger.api('GET', '/api/courses', res.status, Math.round(performance.now() - t0), courses);

    courseSelector.innerHTML = '';
    if (courses.length === 0) {
      courseSelector.innerHTML = '<option value="">No courses yet</option>';
      showCreatorView();
      return;
    }

    courses.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = `${c.title} (${Math.round(c.completion_percentage)}%)`;
      courseSelector.appendChild(opt);
    });

    if (!currentCourseId || !courses.find(c => c.id === currentCourseId)) {
      currentCourseId = courses[0].id;
    }
    courseSelector.value = currentCourseId;
    await loadCourse(currentCourseId);
  } catch (err) {
    Logger.error('Failed to fetch courses', err);
  }
}

async function loadCourse(courseId) {
  const t0 = performance.now();
  try {
    currentCourseId = courseId;
    const res = await fetch(`/api/courses/${courseId}`);
    currentCourse = await res.json();
    Logger.api('GET', `/api/courses/${courseId}`, res.status, Math.round(performance.now() - t0), currentCourse);

    inlinePlaybackSpeed.value = currentCourse.playback_speed;
    inlineMinutesDay.value = currentCourse.minutes_per_day;

    // Update Strategy Buttons & Buffer Indicator
    const strat = currentCourse.schedule_strategy || 'paced';
    updateStrategyPills(strat);
    if (pacingModeLabel) {
      pacingModeLabel.textContent = strat === 'paced'
        ? (currentCourse.revision_buffer_days === 0 ? 'Finish on Exam Date' : 'Paced (2d Buffer)')
        : 'Fixed Daily Spend';
    }

    await loadLessons(courseId);
    await loadCourseSources(courseId);
    await loadSchedule(courseId);
    updateFilterButtonsUI(window.currentLessonFilterMode || 'all');
    showWorkspaceView();
  } catch (err) {
    Logger.error('Failed to load course', err);
  }
}

async function loadLessons(courseId) {
  try {
    const res = await fetch(`/api/courses/${courseId}/lessons`);
    currentLessons = await res.json();
    headerLessonCount.textContent = currentLessons.length;
    renderCurriculumDrawer(currentLessons);
  } catch (err) {
    Logger.error('Failed to load lessons', err);
  }
}

async function loadSchedule(courseId) {
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${courseId}/schedule`);
    currentSchedule = await res.json();
    Logger.api('GET', `/api/courses/${courseId}/schedule`, res.status, Math.round(performance.now() - t0), currentSchedule);
    renderSchedule(currentSchedule);
  } catch (err) {
    Logger.error('Failed to load schedule', err);
  }
}

function renderSchedule(sched) {
  scheduleDaysContainer.innerHTML = '';
  renderCollapsedRailBadges(sched.days);

  // Stats
  const pct = Math.round((sched.completed_effective_minutes / (sched.total_effective_minutes || 1)) * 100);
  progressPct.textContent = `${pct}%`;
  progressBarFill.style.width = `${pct}%`;

  const remHours = Math.floor(sched.remaining_effective_minutes / 60);
  const remMins = Math.round(sched.remaining_effective_minutes % 60);
  statEffectiveLeft.textContent = `${remHours}h ${remMins.toString().padStart(2, '0')}m`;

  const doneHours = Math.floor(sched.completed_effective_minutes / 60);
  const doneMins = Math.round(sched.completed_effective_minutes % 60);
  statEffectiveDone.textContent = `${doneHours}h ${doneMins.toString().padStart(2, '0')}m`;

  statProjectedFinish.textContent = sched.projected_finish_date || '--';
  statTargetDate.textContent = sched.target_date || '--';

  statDailyTarget.textContent = `~${Math.round(sched.effective_daily_target_minutes || 0)} min`;

  // Update KPI bar minutes and speed displays
  const kpiMin = document.getElementById('kpi-minutes-display');
  const kpiSpd = document.getElementById('kpi-speed-display');
  const speed = sched.playback_speed || (currentCourse ? currentCourse.playback_speed : 1.25);
  const minutes = sched.minutes_per_day || (currentCourse ? currentCourse.minutes_per_day : 90);
  if (kpiMin) kpiMin.textContent = `${minutes}m`;
  if (kpiSpd) kpiSpd.textContent = `${speed}x`;

  // Update Pacing Mode & Buffer Visual Indicators
  updateStrategyPills(sched.schedule_strategy || 'paced');
  if (pillBufferZero && pillBufferTwo) {
    if (sched.revision_buffer_days === 0) {
      pillBufferZero.className = 'px-1.5 py-0.5 rounded font-semibold transition bg-blue-600 text-white shadow-sm';
      pillBufferTwo.className = 'px-1.5 py-0.5 rounded font-medium transition text-alabaster-muted dark:text-charcoal-muted hover:text-alabaster-text dark:hover:text-charcoal-text';
    } else {
      pillBufferTwo.className = 'px-1.5 py-0.5 rounded font-semibold transition bg-blue-600 text-white shadow-sm';
      pillBufferZero.className = 'px-1.5 py-0.5 rounded font-medium transition text-alabaster-muted dark:text-charcoal-muted hover:text-alabaster-text dark:hover:text-charcoal-text';
    }
  }

  if (pacingNoteDetail) {
    if (sched.schedule_strategy === 'paced') {
      if (sched.revision_buffer_days === 0) {
        pacingNoteDetail.textContent = '✓ Finishes on exam day';
      } else {
        pacingNoteDetail.textContent = `✓ Finishes ${sched.revision_buffer_days}d before exam`;
      }
    } else {
      pacingNoteDetail.textContent = '⚡ Sprint mode';
    }
  }

  if (pacingModeLabel) {
    pacingModeLabel.textContent = sched.schedule_strategy === 'paced'
      ? (sched.revision_buffer_days === 0 ? 'Finish on Exam Date' : 'Paced (2d Buffer)')
      : 'Fixed Daily Spend';
  }

  // Behind Schedule Alert
  if (sched.is_behind_schedule || sched.exceeds_budget) {
    behindScheduleBanner.classList.remove('hidden');
    behindScheduleMsg.textContent = sched.pace_notice
      ? sched.pace_notice
      : `Projected finish (${sched.projected_finish_date}) encroaches on your ${sched.revision_buffer_days}-day revision buffer before ${sched.target_date}.`;
  } else {
    behindScheduleBanner.classList.add('hidden');
  }

  const todayStr = new Date().toISOString().split('T')[0];

  // Render Day Groups (Clean, Calm Academic Layout)
  sched.days.forEach(day => {
    const isToday = (day.date === todayStr);
    const dayEl = document.createElement('div');
    dayEl.className = `day-group-card bg-alabaster-card dark:bg-charcoal-card border border-alabaster-border dark:border-charcoal-border rounded-xl overflow-hidden shadow-none transition-all duration-150 ${isToday ? 'ring-1 ring-blue-500/50' : ''}`;
    dayEl.setAttribute('data-day-date', day.date);
    dayEl.setAttribute('ondragover', 'window.handleDayDragOver(event, this)');
    dayEl.setAttribute('ondragleave', 'window.handleDayDragLeave(event, this)');
    dayEl.setAttribute('ondrop', `window.handleDayDrop(event, this, '${day.date}')`);

    let badgeHtml = '';
    if (isToday) {
      badgeHtml += '<span class="text-[9px] font-semibold uppercase px-1.5 py-0.2 rounded bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300 font-mono">Today</span>';
    }
    if (day.is_revision_day) {
      badgeHtml += '<span class="text-[9px] font-medium uppercase px-1.5 py-0.2 rounded bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800 font-mono">Buffer</span>';
    } else if (day.is_rest_day) {
      badgeHtml += '<span class="text-[9px] font-medium uppercase px-1.5 py-0.2 rounded bg-alabaster-subcard text-alabaster-muted dark:bg-charcoal-subcard dark:text-charcoal-muted font-mono">Rest</span>';
    }

    const isCollapsed = collapsedDays.has(day.date);

    const dayHeader = `
      <div class="px-3 py-1.5 bg-alabaster-subcard/50 dark:bg-charcoal-subcard/50 border-b border-alabaster-border dark:border-charcoal-border flex items-center justify-between text-xs cursor-pointer select-none" onclick="window.toggleDayCollapse('${day.date}')">
        <div class="flex items-center gap-1.5">
          <svg id="day-chevron-${day.date}" class="w-3.5 h-3.5 text-alabaster-muted dark:text-charcoal-muted transition-transform day-chevron" style="transform: ${isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)'};" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
          <span class="font-medium text-alabaster-text dark:text-charcoal-text">${day.day_name}, ${formatDateDisplay(day.date)}</span>
          ${badgeHtml}
        </div>
        <span class="text-blue-600 dark:text-blue-400 font-mono font-semibold text-[11px]">${Math.round(day.total_effective_minutes)}m</span>
      </div>
    `;

    let allocsHtml = '';
    if (day.allocations.length === 0) {
      allocsHtml = `
        <div class="p-2.5 text-xs text-alabaster-muted dark:text-charcoal-muted italic text-center space-y-1.5">
          <div>${day.is_revision_day ? 'Dedicated strictly for comprehensive revision.' : day.is_rest_day ? 'Rest & recharge.' : 'No study allocations.'}</div>
          ${day.is_revision_day ? `
            <button type="button" onclick="window.loadCramSheet(false)" class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-700 dark:text-amber-300 border border-amber-500/30 text-xs font-semibold transition active:scale-95 shadow-sm">
              <span>⚡ Open Last-Night Cram Sheet</span>
            </button>
          ` : ''}
        </div>
      `;
    } else {
      const matchedAllocs = day.allocations.filter(alloc => {
        if (window.currentLessonFilter === 'pyq') {
          return alloc.pyq_hit_count && alloc.pyq_hit_count > 0;
        }
        return true;
      });

      if (matchedAllocs.length === 0 && day.allocations.length > 0) {
        allocsHtml = `<div class="p-2.5 text-[11px] text-alabaster-muted/70 dark:text-charcoal-muted/70 italic text-center">No high-yield PYQ topics on this day.</div>`;
      } else {
        allocsHtml = `<div class="divide-y divide-alabaster-border/40 dark:divide-charcoal-border/40">`;
        matchedAllocs.forEach(alloc => {
          const isCompleted = alloc.is_completed;
          const splitBadge = alloc.split_count > 1 ? `<span class="ml-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-600 dark:text-amber-400 border border-amber-500/30 shrink-0 font-medium">Part ${alloc.split_index + 1}/${alloc.split_count}</span>` : '';
          const pyqBadge = (alloc.pyq_hit_count && alloc.pyq_hit_count > 0)
            ? `<span class="ml-1 text-[9px] font-mono px-1.5 py-0.2 rounded bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/25 shrink-0 font-semibold" title="${alloc.pyq_hit_count} past exam questions matched (${alloc.pyq_total_marks || 0} marks)">PYQ ×${alloc.pyq_hit_count}</span>`
            : '';

          allocsHtml += `
            <div class="allocation-card px-2.5 py-1.5 hover:bg-alabaster-hover dark:hover:bg-charcoal-hover transition flex items-center justify-between gap-2 cursor-pointer alloc-item group ${isCompleted ? 'opacity-40' : ''}" 
                 data-alloc-id="${alloc.id}" 
                 data-source-date="${day.date}"
                 draggable="true"
                 ondragstart="window.handleCardDragStart(event, '${alloc.id}', '${day.date}')"
                 ondragend="window.handleCardDragEnd(event, this)"
                 onclick="window.selectAllocation('${alloc.id}')">
              
              <div class="flex items-center gap-1.5 min-w-0 flex-1">
                <div class="drag-handle text-alabaster-muted/40 hover:text-blue-500 cursor-grab active:cursor-grabbing shrink-0 select-none text-[11px]" title="Drag to move to another day">
                  ⋮⋮
                </div>
                <input type="checkbox" class="btn-complete-allocation rounded text-blue-600 focus:ring-0 alloc-checkbox cursor-pointer w-3.5 h-3.5 shrink-0" data-alloc-id="${alloc.id}" ${isCompleted ? 'checked' : ''} onclick="event.stopPropagation()">
                <h4 class="text-[13.5px] leading-snug text-text-primary font-normal group-hover:text-accent transition flex items-start gap-1 min-w-0 line-clamp-2 break-words ${isCompleted ? 'line-through text-text-secondary' : ''}">
                  <span class="line-clamp-2 break-words">${alloc.lesson_title}</span>
                  ${splitBadge}
                  ${pyqBadge}
                </h4>
              </div>

              <div class="flex items-center gap-1.5 shrink-0">
                <span class="text-[11px] font-mono text-alabaster-muted dark:text-charcoal-muted">${Math.round(alloc.effective_minutes)}m</span>
                <div class="flex items-center opacity-0 group-hover:opacity-100 transition">
                  <button class="p-0.5 rounded text-alabaster-muted hover:text-blue-600 dark:hover:text-blue-400" title="Edit lesson" onclick="window.editScheduleLesson('${alloc.lesson_id}', '${alloc.id}', event)">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
                  </button>
                  <button class="btn-skip-allocation p-0.5 rounded text-alabaster-muted hover:text-amber-500" title="Skip lesson & reflow" onclick="window.skipAllocation('${alloc.id}', event)">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 5l7 7-7 7M5 5l7 7-7 7"/></svg>
                  </button>
                </div>
              </div>
            </div>
          `;
        });
        allocsHtml += `</div>`;
      }
    }

    dayEl.innerHTML = dayHeader + `<div id="day-body-${day.date}" class="day-body ${isCollapsed ? 'hidden' : ''}">${allocsHtml}</div>`;
    scheduleDaysContainer.appendChild(dayEl);
  });

  // Attach Checkbox Handlers
  document.querySelectorAll('.alloc-checkbox').forEach(cb => {
    cb.addEventListener('change', async (e) => {
      e.stopPropagation();
      const aid = e.target.getAttribute('data-alloc-id');
      await toggleAllocation(aid);
    });
  });

  // Auto-select first uncompleted allocation if none active
  if (!activeAllocation && sched.days) {
    for (const d of sched.days) {
      for (const a of d.allocations) {
        if (!a.is_completed && !a.is_skipped) {
          selectAllocation(a.id);
          return;
        }
      }
    }
    if (sched.days[0]?.allocations[0]) {
      selectAllocation(sched.days[0].allocations[0].id);
    }
  }
}

// --- Drag-and-Drop Schedule Reordering Handlers ---
window.draggedAllocInfo = null;

window.handleCardDragStart = function(event, allocId, sourceDate) {
  event.stopPropagation();
  window.draggedAllocInfo = { allocId, sourceDate };
  try {
    event.dataTransfer.setData('text/plain', JSON.stringify({ allocId, sourceDate }));
    event.dataTransfer.effectAllowed = 'move';
  } catch (e) {}
  const target = event.currentTarget || event.target;
  target.classList.add('opacity-40', 'scale-95', 'ring-2', 'ring-accent');
};

window.handleCardDragEnd = function(event, cardEl) {
  if (cardEl) {
    cardEl.classList.remove('opacity-40', 'scale-95', 'ring-2', 'ring-accent');
  }
  window.draggedAllocInfo = null;
  document.querySelectorAll('.day-group-card').forEach(d => {
    d.classList.remove('ring-2', 'ring-accent', 'bg-accent-soft/40');
  });
};

window.handleDayDragOver = function(event, dayEl) {
  event.preventDefault();
  try { event.dataTransfer.dropEffect = 'move'; } catch (e) {}
  dayEl.classList.add('ring-2', 'ring-accent', 'bg-accent-soft/40');
};

window.handleDayDragLeave = function(event, dayEl) {
  if (!dayEl.contains(event.relatedTarget)) {
    dayEl.classList.remove('ring-2', 'ring-accent', 'bg-accent-soft/40');
  }
};

window.handleDayDrop = async function(event, dayEl, targetDate) {
  event.preventDefault();
  dayEl.classList.remove('ring-2', 'ring-accent', 'bg-accent-soft/40');

  let data = window.draggedAllocInfo;
  if (!data) {
    try {
      data = JSON.parse(event.dataTransfer.getData('text/plain'));
    } catch (e) {
      return;
    }
  }

  if (!data || !data.allocId) return;
  const { allocId, sourceDate } = data;

  if (sourceDate === targetDate) {
    return; // Dropped on same day
  }

  showToast(`Moving lesson to ${formatDateDisplay(targetDate)}...`, 'info');

  try {
    const res = await fetch(`/api/courses/${currentCourseId}/schedule/allocations/${allocId}/reschedule`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_date: targetDate }),
    });
    if (!res.ok) {
      throw new Error(`Server returned ${res.status}`);
    }
    const updatedSched = await res.json();
    currentSchedule = updatedSched;
    renderSchedule(updatedSched);
    showToast(`✓ Lesson moved to ${formatDateDisplay(targetDate)}!`, 'success');
  } catch (err) {
    Logger.error('Reschedule drop error', err);
    showToast(`Failed to move lesson: ${err.message}`, 'error');
  }
};

window.selectAllocation = function(allocId) {
  if (!currentSchedule) return;
  for (const d of currentSchedule.days) {
    for (const a of d.allocations) {
      if (a.id === allocId) {
        activeAllocation = a;
        currentLessonId = a.lesson_id;
        updateActiveLessonUI(a);
        playVideoSlice(a.video_id, a.allocated_start_sec, a.allocated_end_sec);
        loadLessonNotesAndArtifacts(a.lesson_id);
        return;
      }
    }
  }
};

function updateActiveLessonUI(alloc) {
  activeLessonTitle.textContent = alloc.lesson_title;
  activeLessonTime.textContent = `[${formatDurationSec(alloc.allocated_start_sec)} - ${formatDurationSec(alloc.allocated_end_sec)}]`;
  activeLessonEffMin.textContent = `${alloc.effective_minutes} min`;
  activeLessonPriority.textContent = alloc.priority;
  activeLessonSplit.textContent = alloc.split_count > 1 ? `Part ${alloc.split_index + 1} of ${alloc.split_count}` : 'Whole Lesson';

  if (alloc.is_completed) {
    activeCompleteLabel.textContent = 'Completed';
    btnToggleActiveComplete.className = 'bg-alabaster-hover dark:bg-charcoal-hover text-alabaster-muted dark:text-charcoal-muted text-[11px] font-medium px-2.5 py-1 rounded transition flex items-center gap-1';
  } else {
    activeCompleteLabel.textContent = 'Mark Complete';
    btnToggleActiveComplete.className = 'bg-blue-600 hover:bg-blue-700 text-white text-[11px] font-medium px-2.5 py-1 rounded transition flex items-center gap-1 shadow-sm active:scale-95';
  }

  // Highlight active allocation card in left syllabus rail
  document.querySelectorAll('.allocation-card').forEach(card => {
    if (card.getAttribute('data-alloc-id') === alloc.id) {
      card.classList.add('bg-blue-50/80', 'dark:bg-blue-950/40', 'border-l-2', 'border-blue-600', 'dark:border-blue-400');
    } else {
      card.classList.remove('bg-blue-50/80', 'dark:bg-blue-950/40', 'border-l-2', 'border-blue-600', 'dark:border-blue-400');
    }
  });
}

async function toggleAllocation(allocId) {
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/schedule/allocations/${allocId}/toggle`, {
      method: 'POST',
    });
    const updated = await res.json();
    Logger.api('POST', `/api/courses/.../allocations/${allocId}/toggle`, res.status, Math.round(performance.now() - t0), updated);

    await loadSchedule(currentCourseId);
    if (activeAllocation && activeAllocation.id === allocId) {
      activeAllocation.is_completed = updated.is_completed;
      updateActiveLessonUI(activeAllocation);
    }
  } catch (err) {
    Logger.error('Failed to toggle allocation', err);
  }
}

window.skipAllocation = async function(allocId, evt) {
  if (evt) evt.stopPropagation();
  if (!confirm('Skip this lesson allocation and automatically reflow remaining schedule?')) return;
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/schedule/allocations/${allocId}/skip`, {
      method: 'POST',
    });
    currentSchedule = await res.json();
    Logger.api('POST', `/api/courses/.../allocations/${allocId}/skip`, res.status, Math.round(performance.now() - t0), currentSchedule);
    renderSchedule(currentSchedule);
  } catch (err) {
    Logger.error('Failed to skip allocation', err);
  }
};

async function handleToggleActiveAllocation() {
  if (!activeAllocation) return;
  await toggleAllocation(activeAllocation.id);
}

async function handleSkipActiveAllocation() {
  if (!activeAllocation) return;
  await window.skipAllocation(activeAllocation.id);
}

async function replanCourse(mode, params = {}) {
  const t0 = performance.now();
  try {
    const payload = {
      mode: mode,
      ...params,
    };
    Logger.schedule(`Replan Requested (Mode: ${mode})`, payload);
    const res = await fetch(`/api/courses/${currentCourseId}/schedule/replan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    Logger.api('POST', `/api/courses/.../schedule/replan`, res.status, Math.round(performance.now() - t0), data);

    if (data.success) {
      currentSchedule = data.schedule;
      renderSchedule(currentSchedule);

      const diff = data.diff;
      let diffMsg = `Finish: ${diff.old_finish_date || '--'} → ${diff.new_finish_date || '--'}`;
      if (diff.pace_change) {
        diffMsg += ` • ${diff.pace_change}`;
      }
      if (diff.dropped_deep_dive_count > 0) {
        diffMsg += ` • Dropped ${diff.dropped_deep_dive_count} deep-dive topics to compress schedule.`;
      }
      if (diff.deficit_message || diff.pace_notice) {
        diffMsg += ` • ⚠️ ${diff.deficit_message || diff.pace_notice}`;
      } else if (data.schedule && data.schedule.pace_notice) {
        diffMsg += ` • ⚠️ ${data.schedule.pace_notice}`;
      }
      diffText.textContent = diffMsg;
      diffBanner.classList.remove('hidden');
    }
  } catch (err) {
    Logger.error('Failed to replan schedule', err);
  }
}

async function handleUndo() {
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/schedule/undo`, {
      method: 'POST',
    });
    currentSchedule = await res.json();
    Logger.api('POST', `/api/courses/.../schedule/undo`, res.status, Math.round(performance.now() - t0), currentSchedule);
    renderSchedule(currentSchedule);
    diffBanner.classList.add('hidden');
  } catch (err) {
    Logger.error('Undo failed', err);
    alert('No earlier snapshot to undo.');
  }
}

// --- Smart Filtering & Curriculum Drawer ---
function updateFilterButtonsUI(mode) {
  const normalizedMode = (mode === 'concepts' || mode === false)
    ? 'concepts'
    : (mode === 'examples' || mode === true)
      ? 'examples'
      : 'all';
  window.currentLessonFilterMode = normalizedMode;

  const btnAll = document.getElementById('btn-filter-all');
  const btnConcepts = document.getElementById('btn-filter-concepts');
  const btnExamples = document.getElementById('btn-filter-examples');

  const activeClasses = ['bg-accent', 'text-white', 'shadow-sm', 'font-semibold'];
  const inactiveClasses = ['text-text-secondary', 'hover:text-text-primary', 'hover:bg-bg-card', 'font-medium'];

  const setBtnState = (btn, isActive) => {
    if (!btn) return;
    if (isActive) {
      btn.classList.add(...activeClasses);
      btn.classList.remove(...inactiveClasses);
    } else {
      btn.classList.remove(...activeClasses);
      btn.classList.add(...inactiveClasses);
    }
  };

  setBtnState(btnAll, normalizedMode === 'all');
  setBtnState(btnConcepts, normalizedMode === 'concepts');
  setBtnState(btnExamples, normalizedMode === 'examples');
}

async function handleFilterLessons(modeOrFlag) {
  const t0 = performance.now();
  let mode = 'all';
  if (typeof modeOrFlag === 'string') {
    mode = modeOrFlag.toLowerCase();
  } else if (modeOrFlag === true) {
    mode = 'examples';
  } else if (modeOrFlag === false) {
    mode = 'concepts';
  }

  // Update UI pill immediately for instantaneous response
  updateFilterButtonsUI(mode);

  try {
    const payload = {
      filter_mode: mode,
    };
    const res = await fetch(`/api/courses/${currentCourseId}/lessons/filter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || `Filter failed (status ${res.status})`);
    }
    const updatedLessons = await res.json();
    Logger.api('POST', `/api/courses/.../lessons/filter`, res.status, Math.round(performance.now() - t0), updatedLessons);
    currentLessons = updatedLessons;
    renderCurriculumDrawer(currentLessons);

    // Regenerate schedule to reflect included/excluded lessons
    const schedRes = await fetch(`/api/courses/${currentCourseId}/schedule/generate`, { method: 'POST' });
    if (!schedRes.ok) {
      const errSched = await schedRes.json().catch(() => ({}));
      throw new Error(errSched.detail || 'Failed to regenerate schedule');
    }
    await loadSchedule(currentCourseId);

    const modeLabels = {
      'all': 'All lessons included (theory & examples)',
      'concepts': 'Concepts & theory view (examples skipped)',
      'examples': 'Examples, questions & practicals view'
    };
    showToast(modeLabels[mode] || `Filter applied: ${mode}`);
  } catch (err) {
    Logger.error('Failed to filter lessons', err);
    showToast(err.message, 'warning');
  }
}
window.updateFilterButtonsUI = updateFilterButtonsUI;
window.handleFilterLessons = handleFilterLessons;

window.toggleLessonExclude = async function(lessonId) {
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/lessons/${lessonId}/toggle-exclude`, {
      method: 'POST',
    });
    const updated = await res.json();
    Logger.api('POST', `/api/courses/.../lessons/${lessonId}/toggle-exclude`, res.status, Math.round(performance.now() - t0), updated);

    // Update in local state
    const idx = currentLessons.findIndex(l => l.id === lessonId);
    if (idx !== -1) currentLessons[idx] = updated;
    renderCurriculumDrawer(currentLessons);

    // Regenerate schedule
    await fetch(`/api/courses/${currentCourseId}/schedule/generate`, { method: 'POST' });
    await loadSchedule(currentCourseId);
  } catch (err) {
    Logger.error('Failed to toggle lesson exclusion', err);
  }
};

function renderCurriculumDrawer(lessons) {
  curriculumLessonsList.innerHTML = '';
  lessons.forEach(l => {
    const item = document.createElement('div');
    item.className = `p-2.5 rounded-xl flex items-start gap-2.5 text-xs hover:bg-slate-100 dark:hover:bg-slate-800/60 transition ${l.is_excluded ? 'opacity-40' : ''}`;
    const priorityPill = l.priority === 'core'
      ? '<span class="text-[9px] uppercase px-1.5 py-0.2 rounded-full bg-accent-soft text-accent-soft-text border border-border-subtle font-mono font-bold">Core</span>'
      : '<span class="text-[9px] uppercase px-1.5 py-0.2 rounded-full bg-bg-card text-text-secondary border border-border-subtle font-mono font-bold">Deep-Dive</span>';

    item.innerHTML = `
      <input type="checkbox" class="mt-1 rounded text-accent focus:ring-0 cursor-pointer" ${!l.is_excluded ? 'checked' : ''} onchange="window.toggleLessonExclude('${l.id}')">
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-1.5 mb-1">
          ${priorityPill}
          <span class="text-[10px] text-cyan-600 dark:text-cyan-400 font-mono font-medium">${formatDurationSec(l.raw_duration_sec)}</span>
        </div>
        <div class="font-semibold text-slate-900 dark:text-slate-100 truncate ${l.is_excluded ? 'line-through text-slate-400 dark:text-slate-500' : ''}">${l.title}</div>
      </div>
    `;
    curriculumLessonsList.appendChild(item);
  });
}

function filterCurriculumDrawer() {
  const q = curriculumSearch.value.toLowerCase();
  const filtered = currentLessons.filter(l => l.title.toLowerCase().includes(q));
  renderCurriculumDrawer(filtered);
}

// --- Course Creator & Discovery ---
async function handleCourseCreate(e) {
  e.preventDefault();
  const title = document.getElementById('input-course-title').value.trim();
  const goalQuery = document.getElementById('input-goal-query').value.trim();
  const targetDate = document.getElementById('input-target-date').value;
  const strategy = document.getElementById('input-schedule-strategy').value;
  const minutesDay = parseInt(document.getElementById('input-minutes-day')?.value || '90', 10);
  const playbackSpeed = parseFloat(document.getElementById('input-playback-speed').value);
  const revBuffer = parseInt(document.getElementById('input-rev-buffer').value, 10);

  const restDays = [];
  document.querySelectorAll('input[name="rest_day"]:checked').forEach(cb => {
    restDays.push(cb.value);
  });

  const spinner = document.getElementById('creator-spinner');
  const btnText = document.getElementById('creator-btn-text');
  spinner.classList.remove('hidden');
  btnText.textContent = 'Discovering sources...';

  const t0 = performance.now();
  try {
    const coursePayload = {
      title: title,
      goal_query: goalQuery,
      target_date: targetDate,
      minutes_per_day: minutesDay,
      playback_speed: playbackSpeed,
      rest_days: restDays,
      revision_buffer_days: revBuffer,
      schedule_strategy: strategy,
    };

    const resCourse = await fetch('/api/courses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(coursePayload),
    });
    const courseData = await resCourse.json();
    currentCourseId = courseData.id;
    Logger.api('POST', '/api/courses', resCourse.status, Math.round(performance.now() - t0), courseData);

    // If direct YouTube link
    if (goalQuery.includes('youtube.com') || goalQuery.includes('youtu.be')) {
      const t1 = performance.now();
      const resImport = await fetch(`/api/courses/${currentCourseId}/sources/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: goalQuery, is_approved: true }),
      });
      if (!resImport.ok) {
        const errData = await resImport.json().catch(() => ({}));
        const errorMsg = errData.detail || 'Could not fetch YouTube video or playlist metadata.';
        Logger.error('Failed to import YouTube URL', errorMsg);
        showImportError(errorMsg);
        return;
      }
      const importData = await resImport.json();
      Logger.api('POST', `/api/courses/.../sources/import`, resImport.status, Math.round(performance.now() - t1), importData);

      await fetch(`/api/courses/${currentCourseId}/schedule/generate`, { method: 'POST' });
      await refreshCourseList();
      return;
    }

    // Autonomous Discovery
    const t2 = performance.now();
    const resDiscovery = await fetch(`/api/courses/${currentCourseId}/discover`, { method: 'POST' });
    const discovery = await resDiscovery.json();
    Logger.api('POST', `/api/courses/.../discover`, resDiscovery.status, Math.round(performance.now() - t2), discovery);

    renderApprovalGate(discovery);
  } catch (err) {
    Logger.error('Failed to create course / discover', err);
    alert('Failed to discover sources: ' + err.message);
  } finally {
    spinner.classList.add('hidden');
    btnText.textContent = 'Discover & Build Study Plan';
  }
}

function showImportError(msg) {
  const banner = document.getElementById('import-error-banner');
  const msgEl = document.getElementById('import-error-message');
  if (banner && msgEl) {
    msgEl.textContent = msg;
    banner.classList.remove('hidden');
    banner.scrollIntoView({ behavior: 'smooth' });
  }
}

async function handleManualFallbackSubmit() {
  const text = document.getElementById('input-manual-transcript').value.trim();
  const fileInput = document.getElementById('input-manual-transcript-file');
  let content = text;
  if (!content && fileInput && fileInput.files && fileInput.files[0]) {
    content = await fileInput.files[0].text();
  }
  if (!content) {
    alert('Please enter or upload transcript text.');
    return;
  }
  if (!currentCourseId) {
    alert('No active course selected.');
    return;
  }

  const btn = document.getElementById('btn-submit-manual-fallback');
  btn.disabled = true;
  btn.textContent = 'Importing...';

  try {
    const res = await fetch(`/api/courses/${currentCourseId}/sources/manual-transcript`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: 'Manual Lecture Notes',
        transcript_text: content,
        raw_duration_sec: 1200,
        priority: 'core',
      }),
    });
    if (!res.ok) throw new Error('Failed to import manual transcript');
    document.getElementById('import-error-banner').classList.add('hidden');
    await refreshCourseList();
  } catch (err) {
    alert('Error saving manual transcript: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Import Manual Transcript & Build Schedule';
  }
}

function renderApprovalGate(discovery) {
  candidatePlaylistsList.innerHTML = '';
  candidateVideosList.innerHTML = '';

  const playlists = discovery.candidate_playlists || [];
  const videos = discovery.candidate_videos || [];

  if (playlists.length === 0) {
    candidatePlaylistsList.innerHTML = '<div class="text-xs text-slate-500 italic">No playlists discovered.</div>';
  } else {
    playlists.forEach(pl => {
      const item = document.createElement('label');
      item.className = 'flex items-start gap-2.5 p-2 rounded-xl bg-bg-card border border-border-subtle border border-slate-700/60 cursor-pointer hover:bg-bg-card border border-border-subtle text-xs';
      item.innerHTML = `
        <input type="checkbox" name="approved_source" value="${pl.source_id}" checked class="mt-0.5 text-accent rounded">
        <div>
          <div class="font-semibold text-slate-200">${pl.title}</div>
          <div class="text-[11px] text-slate-400">${pl.channel || 'YouTube'} • ${pl.item_count || 'Playlist'}</div>
        </div>
      `;
      candidatePlaylistsList.appendChild(item);
    });
  }

  if (videos.length === 0) {
    candidateVideosList.innerHTML = '<div class="text-xs text-slate-500 italic">No videos discovered.</div>';
  } else {
    videos.forEach(v => {
      const item = document.createElement('label');
      item.className = 'flex items-start gap-2.5 p-2 rounded-xl bg-bg-card border border-border-subtle border border-slate-700/60 cursor-pointer hover:bg-bg-card border border-border-subtle text-xs';
      item.innerHTML = `
        <input type="checkbox" name="approved_source" value="${v.source_id}" checked class="mt-0.5 text-accent rounded">
        <div>
          <div class="font-medium text-slate-200 line-clamp-1">${v.title}</div>
          <div class="text-[11px] text-slate-400">${v.channel || 'YouTube'} • ${v.duration_str || ''}</div>
        </div>
      `;
      candidateVideosList.appendChild(item);
    });
  }

  approvalGate.classList.remove('hidden');
  approvalGate.scrollIntoView({ behavior: 'smooth' });
}

async function handleApproveSources() {
  const approvedIds = [];
  document.querySelectorAll('input[name="approved_source"]:checked').forEach(cb => {
    approvedIds.push(cb.value);
  });

  if (approvedIds.length === 0) {
    alert('Please check at least one source to approve.');
    return;
  }

  try {
    btnApproveSelected.textContent = 'Processing & Splitting Lessons...';
    await fetch(`/api/courses/${currentCourseId}/sources/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_ids_to_approve: approvedIds,
        source_ids_to_reject: [],
      }),
    });

    await fetch(`/api/courses/${currentCourseId}/schedule/generate`, {
      method: 'POST',
    });

    await refreshCourseList();
  } catch (err) {
    Logger.error('Error approving sources', err);
    alert('Error approving sources: ' + err.message);
  } finally {
    btnApproveSelected.textContent = 'Approve & Generate Schedule';
  }
}

// --- Settings & Maintenance ---
let currentSettings = null;

async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    const s = await res.json();
    currentSettings = s;
    document.getElementById('settings-ytdlp-version').textContent = s.ytdlp_version;
    document.getElementById('settings-browser-cookies').value = s.cookies_browser || '';
    document.getElementById('settings-db-size').textContent = formatBytes(s.db_size_bytes);
    document.getElementById('settings-transcripts-size').textContent = formatBytes(s.transcripts_size_bytes);
    document.getElementById('settings-screenshots-size').textContent = formatBytes(s.screenshots_size_bytes);

    const totalBytes = s.transcripts_size_bytes + s.screenshots_size_bytes;
    document.getElementById('settings-total-disk').textContent = formatBytes(totalBytes);

    // Study Defaults
    if (document.getElementById('settings-pref-minutes-day')) {
      document.getElementById('settings-pref-minutes-day').value = s.default_minutes_per_day || 90;
    }
    if (document.getElementById('settings-pref-playback-speed')) {
      document.getElementById('settings-pref-playback-speed').value = String(s.default_playback_speed || 1.25);
    }
    if (document.getElementById('settings-pref-rest-sun')) {
      document.getElementById('settings-pref-rest-sun').checked = (s.default_rest_days || []).includes('Sunday');
    }
    if (document.getElementById('settings-pref-rest-sat')) {
      document.getElementById('settings-pref-rest-sat').checked = (s.default_rest_days || []).includes('Saturday');
    }
    if (document.getElementById('settings-pref-rev-buffer')) {
      document.getElementById('settings-pref-rev-buffer').value = String(s.default_revision_buffer_days ?? 2);
    }

    handleLlmProviderChange();
  } catch (err) {
    Logger.error('Failed to load settings', err);
  }
}

function handleLlmProviderChange() {
  const providerSelect = document.getElementById('settings-llm-provider');
  if (!providerSelect) return;
  const provider = providerSelect.value;
  const modelInput = document.getElementById('settings-llm-model');
  const baseUrlInput = document.getElementById('settings-llm-base-url');
  const baseUrlWrapper = document.getElementById('wrapper-llm-base-url');
  const keyWrapper = document.getElementById('wrapper-llm-key');
  const keyInput = document.getElementById('settings-llm-key');
  const resultBox = document.getElementById('connection-test-result');
  if (resultBox) resultBox.classList.add('hidden');

  if (provider === 'gemini') {
    modelInput.value = currentSettings?.gemini_model || 'gemini-2.5-flash';
    baseUrlWrapper.classList.add('hidden');
    keyWrapper.classList.remove('hidden');
    keyInput.placeholder = currentSettings?.has_gemini_key ? '•••••••••••• (API Key Configured in .env)' : 'Paste Gemini API Key';
  } else if (provider === 'groq') {
    modelInput.value = currentSettings?.groq_model || 'llama-3.3-70b-versatile';
    baseUrlWrapper.classList.add('hidden');
    keyWrapper.classList.remove('hidden');
    keyInput.placeholder = currentSettings?.has_groq_key ? '•••••••••••• (API Key Configured in .env)' : 'Paste Groq API Key';
  } else if (provider === 'openrouter') {
    modelInput.value = currentSettings?.openrouter_model || 'google/gemini-2.5-flash';
    baseUrlInput.value = currentSettings?.openrouter_base_url || 'https://openrouter.ai/api/v1';
    baseUrlWrapper.classList.remove('hidden');
    keyWrapper.classList.remove('hidden');
    keyInput.placeholder = currentSettings?.has_openrouter_key ? '•••••••••••• (API Key Configured in .env)' : 'Paste OpenRouter API Key';
  } else if (provider === 'ollama') {
    modelInput.value = currentSettings?.ollama_model || 'llama3.2';
    baseUrlInput.value = currentSettings?.ollama_base_url || 'http://localhost:11434';
    baseUrlWrapper.classList.remove('hidden');
    keyWrapper.classList.add('hidden');
  }
}

async function handleTestConnection() {
  const provider = document.getElementById('settings-llm-provider').value;
  const model = document.getElementById('settings-llm-model').value.trim();
  const baseUrl = document.getElementById('settings-llm-base-url').value.trim();
  const apiKey = document.getElementById('settings-llm-key').value.trim();
  const resultBox = document.getElementById('connection-test-result');

  resultBox.classList.remove('hidden');
  resultBox.className = 'p-2.5 rounded-lg text-xs leading-relaxed border bg-zinc-100 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200 border-zinc-300 dark:border-zinc-700';
  resultBox.textContent = `Testing connection to ${provider}...`;

  try {
    const res = await fetch('/api/settings/test-connection', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider,
        api_key: apiKey || undefined,
        model: model || undefined,
        base_url: baseUrl || undefined,
      }),
    });
    const data = await res.json();
    if (data.success) {
      resultBox.className = 'p-2.5 rounded-lg text-xs leading-relaxed border bg-emerald-50 dark:bg-emerald-950/80 text-emerald-800 dark:text-emerald-200 border-emerald-300 dark:border-emerald-800';
      resultBox.textContent = `✅ ${data.message}`;
    } else {
      resultBox.className = 'p-2.5 rounded-lg text-xs leading-relaxed border bg-amber-50 dark:bg-amber-950/80 text-amber-800 dark:text-amber-200 border-amber-300 dark:border-amber-800';
      let guideText = data.guide ? `\n\nSetup Guide:\n${data.guide}` : '';
      resultBox.textContent = `⚠️ ${data.message}${guideText}`;
    }
  } catch (err) {
    resultBox.className = 'p-2.5 rounded-lg text-xs leading-relaxed border bg-red-50 dark:bg-red-950/80 text-red-800 dark:text-red-200 border-red-300 dark:border-red-800';
    resultBox.textContent = `❌ Network Error: ${err.message}`;
  }
}

async function handleUpdateYtdlp() {
  const btn = document.getElementById('btn-update-ytdlp');
  btn.textContent = 'Updating...';
  try {
    const res = await fetch('/api/settings/update-ytdlp', { method: 'POST' });
    const data = await res.json();
    alert(data.message);
    await loadSettings();
  } catch (err) {
    alert('Update failed: ' + err.message);
  } finally {
    btn.textContent = 'Update yt-dlp';
  }
}

async function handleCleanupCache() {
  if (!confirm('Clear all cached transcripts and screenshot files?')) return;
  try {
    const res = await fetch('/api/settings/cleanup-cache', { method: 'POST' });
    const data = await res.json();
    alert(data.message);
    await loadSettings();
  } catch (err) {
    alert('Cleanup failed: ' + err.message);
  }
}

async function handleSaveKeys() {
  const provider = document.getElementById('settings-llm-provider').value;
  const model = document.getElementById('settings-llm-model').value.trim();
  const baseUrl = document.getElementById('settings-llm-base-url').value.trim();
  const key = document.getElementById('settings-llm-key').value.trim();

  const updates = {};
  if (provider === 'gemini') {
    if (key) updates.GEMINI_API_KEY = key;
    if (model) updates.GEMINI_MODEL = model;
  } else if (provider === 'groq') {
    if (key) updates.GROQ_API_KEY = key;
    if (model) updates.GROQ_MODEL = model;
  } else if (provider === 'openrouter') {
    if (key) updates.OPENROUTER_API_KEY = key;
    if (model) updates.OPENROUTER_MODEL = model;
    if (baseUrl) updates.OPENROUTER_BASE_URL = baseUrl;
  } else if (provider === 'ollama') {
    if (baseUrl) updates.OLLAMA_BASE_URL = baseUrl;
    if (model) updates.OLLAMA_MODEL = model;
  }

  if (Object.keys(updates).length === 0) {
    alert('No changes to save.');
    return;
  }

  try {
    const res = await fetch('/api/settings/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    const data = await res.json();
    alert(data.message);
    document.getElementById('settings-llm-key').value = '';
    await loadSettings();
  } catch (err) {
    alert('Failed to save keys: ' + err.message);
  }
}

async function handleSaveStudyDefaults() {
  const minDay = parseInt(document.getElementById('settings-pref-minutes-day').value, 10);
  const speed = parseFloat(document.getElementById('settings-pref-playback-speed').value);
  const restDays = [];
  if (document.getElementById('settings-pref-rest-sun').checked) restDays.push('Sunday');
  if (document.getElementById('settings-pref-rest-sat').checked) restDays.push('Saturday');
  const buffer = parseInt(document.getElementById('settings-pref-rev-buffer').value, 10);

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        minutes_per_day: minDay,
        playback_speed: speed,
        rest_days: restDays,
        revision_buffer_days: buffer,
      }),
    });
    const data = await res.json();
    alert('Study preferences saved successfully.');
    await loadSettings();
  } catch (err) {
    alert('Failed to save defaults: ' + err.message);
  }
}

function handleExportMarkdown() {
  if (!currentCourseId) {
    alert('Select a course first to export its study bundle.');
    return;
  }
  window.open(`/api/courses/${currentCourseId}/export-markdown`, '_blank');
}

async function handleUpdateBrowserCookies(e) {
  const val = e.target.value;
  await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cookies_browser: val }),
  });
}

// --- Utilities ---
function formatDateDisplay(isoDate) {
  if (!isoDate) return '';
  const parts = isoDate.split('-');
  if (parts.length < 3) return isoDate;
  const d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function formatDurationSec(sec) {
  if (sec === undefined || sec === null) return '00:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  const h = Math.floor(m / 60);
  const remM = m % 60;
  if (h > 0) {
    return `${h.toString().padStart(2, '0')}:${remM.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${remM.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// --- Notes, Transcription & Keyframe Functions ---
function switchNotesTab(tab) {
  const inactiveClass = ['font-medium', 'text-alabaster-muted', 'dark:text-charcoal-muted', 'hover:text-alabaster-text', 'dark:hover:text-charcoal-text', 'border-transparent'];
  const activeClass = ['font-semibold', 'text-blue-600', 'dark:text-blue-400', 'border-blue-600', 'dark:border-blue-400'];

  const studioTabs = [
    { 
      id: 'personal', 
      btn: tabPersonalNotes, 
      pane: panePersonalNotes,
    },
    { 
      id: 'quiz', 
      btn: tabQuizMastery, 
      pane: paneQuizMastery,
    },
    { 
      id: 'flashcards', 
      btn: tabFlashcardsFsrs, 
      pane: paneFlashcardsFsrs,
    },
    { 
      id: 'qa', 
      btn: tabQaNotebook, 
      pane: paneQaNotebook,
    },
    { 
      id: 'pyodide', 
      btn: tabPyodideScratchpad, 
      pane: panePyodideScratchpad,
    },
    { 
      id: 'pyq', 
      btn: document.getElementById('tab-pyq-questions'), 
      pane: document.getElementById('pane-pyq-questions'),
    },
  ];

  // If user requested 'grounded' (e.g. from legacy script), ensure center reading pane is visible and show personal notes or quiz on right
  if (tab === 'grounded') {
    if (paneGroundedNotes) paneGroundedNotes.classList.remove('hidden');
    tab = 'quiz';
  }

  studioTabs.forEach(t => {
    if (t.btn) {
      t.btn.classList.remove(...activeClass);
      t.btn.classList.add(...inactiveClass);
    }
    if (t.pane) {
      t.pane.classList.add('hidden');
    }
  });

  const active = studioTabs.find(t => t.id === tab);
  if (active) {
    if (active.btn) {
      active.btn.classList.remove(...inactiveClass);
      active.btn.classList.add(...activeClass);
    }
    if (active.pane) {
      active.pane.classList.remove('hidden');
    }
  }

  // Ensure center grounded notes canvas is visible
  if (paneGroundedNotes) {
    paneGroundedNotes.classList.remove('hidden');
  }

  if (tab === 'qa' && currentCourseId) {
    loadQAHistory(currentCourseId);
  } else if (tab === 'quiz' && activeAllocation) {
    checkOrCreateLessonQuiz(activeAllocation.lesson_id);
  } else if (tab === 'pyq' && activeAllocation) {
    loadLessonPyqs(activeAllocation.lesson_id);
  } else if (tab === 'flashcards') {
    loadFlashcards();
  } else if (tab === 'pyodide') {
    initPyodide();
  }
}

async function loadLessonNotesAndArtifacts(lessonId, forceRegen = false) {
  if (!lessonId) return;
  const t0 = performance.now();

  try {
    // 1. Fetch transcript status
    const resStatus = await fetch(`/api/lessons/${lessonId}/status`);
    if (resStatus.ok) {
      const statusData = await resStatus.json();
      if (statusData.has_transcript) {
        transcribeBtnLabel.textContent = 'Transcribed';
        transcribeStatusPill.classList.remove('hidden');
        transcribeStatusPill.textContent = (statusData.transcript_type || 'CAPTION').toUpperCase();
      } else {
        transcribeBtnLabel.textContent = 'Transcribe';
        transcribeStatusPill.classList.add('hidden');
      }
    }

    // 2. Fetch screenshots
    const resShots = await fetch(`/api/lessons/${lessonId}/screenshots`);
    if (resShots.ok) {
      const shots = await resShots.json();
      renderKeyframesStrip(shots);
    }

    // 3. Fetch notes
    const endpoint = forceRegen ? `/api/lessons/${lessonId}/notes/regenerate` : `/api/lessons/${lessonId}/notes`;
    const method = forceRegen ? 'POST' : 'GET';
    const resNotes = await fetch(endpoint, { method });
    if (resNotes.ok) {
      const noteData = await resNotes.json();
      renderMarkdownNotes(noteData.content_markdown);
      if (inputPersonalNotes) {
        if (currentLoadedLessonNotesId !== lessonId || noteData.personal_notes) {
          inputPersonalNotes.value = noteData.personal_notes || '';
          currentLoadedLessonNotesId = lessonId;
        }
      }
      Logger.api(method, endpoint, resNotes.status, Math.round(performance.now() - t0), noteData);
    }

    // 4. Fetch matched PYQs for this lesson
    await loadLessonPyqs(lessonId);
  } catch (err) {
    Logger.error('Failed to load lesson notes & artifacts', err);
  }
}

let currentLessonShots = [];
let currentLoadedLessonMarkdown = '';
let currentLoadedLessonNotesId = null;

function renderKeyframesStrip(shots) {
  currentLessonShots = shots || [];
  if (!shots || shots.length === 0) {
    keyframesStrip.classList.add('hidden');
    keyframesStrip.innerHTML = '';
    return;
  }

  keyframesStrip.classList.remove('hidden');
  keyframesStrip.innerHTML = shots.map((s, idx) => `
    <div class="relative shrink-0 group rounded-lg overflow-hidden border border-border-subtle hover:border-accent transition shadow bg-bg-card flex flex-col">
      <div class="relative cursor-pointer" onclick="window.seekToSeconds(${s.timestamp_sec})" title="Jump to ${s.formatted_time}">
        <img src="${s.url}" alt="${s.caption}" class="w-28 h-16 object-cover">
        <span class="absolute bottom-1 right-1 bg-black/80 text-white font-mono text-[9px] px-1 py-0.2 rounded font-semibold">${s.formatted_time}</span>
        <div class="absolute inset-0 bg-accent/20 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
          <svg class="w-5 h-5 text-white drop-shadow" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
        </div>
      </div>
      <button type="button" class="btn-add-shot-to-notes w-full text-center py-1 bg-bg-card hover:bg-accent hover:text-white text-text-primary text-[10px] font-medium border-t border-border-subtle transition flex items-center justify-center gap-1 active:scale-95" data-idx="${idx}" title="Save screenshot & timestamp into My Notes">
        <span>+ Add to Notes</span>
      </button>
    </div>
  `).join('');

  // Attach event listeners to Add to Notes buttons
  keyframesStrip.querySelectorAll('.btn-add-shot-to-notes').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const idx = parseInt(btn.getAttribute('data-idx'), 10);
      const shot = shots[idx];
      if (shot) {
        insertScreenshotToNotes(shot.url, shot.formatted_time, shot.caption);
      }
    });
  });
}

function insertScreenshotToNotes(imageUrl, formattedTime, caption = '') {
  if (!inputPersonalNotes) return;
  const timeTag = formattedTime || '00:00';
  const imgTag = imageUrl ? `![${caption || 'Lecture Frame'}](${imageUrl})\n\n` : '';
  const noteTemplate = `\n\n### 📸 Frame [${timeTag}]\n${imgTag}**[${timeTag}] My Note:** `;

  // Append to personal notes
  const existing = inputPersonalNotes.value;
  inputPersonalNotes.value = existing + noteTemplate;

  // Switch to personal notes tab so user sees it immediately
  switchNotesTab('personal');

  // Focus at the end of the text
  inputPersonalNotes.focus();
  inputPersonalNotes.setSelectionRange(inputPersonalNotes.value.length, inputPersonalNotes.value.length);
  inputPersonalNotes.scrollTop = inputPersonalNotes.scrollHeight;

  // Autosave
  handlePersonalNotesInput();
  showToast(`Screenshot at [${timeTag}] saved to Notes! Type your notes below it.`, 'success');
}
window.insertScreenshotToNotes = insertScreenshotToNotes;

async function insertCurrentFrameToNotes() {
  const alloc = activeAllocation || (currentSchedule && currentSchedule.days && currentSchedule.days[0] && currentSchedule.days[0].allocations && currentSchedule.days[0].allocations[0]);
  if (!alloc) {
    showToast('Please select a lesson first to capture notes.', 'error');
    return;
  }
  if (!activeAllocation) {
    activeAllocation = alloc;
  }

  let curSec = 0;
  if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function') {
    try {
      curSec = Math.floor(ytPlayer.getCurrentTime() || 0);
    } catch (_) {}
  }
  const m = Math.floor(curSec / 60);
  const s = curSec % 60;
  const timeStr = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;

  // Find closest captured keyframe
  let imageUrl = '';
  if (currentLessonShots && currentLessonShots.length > 0) {
    let closest = currentLessonShots[0];
    let minDiff = Math.abs(closest.timestamp_sec - curSec);
    for (const shot of currentLessonShots) {
      const diff = Math.abs(shot.timestamp_sec - curSec);
      if (diff < minDiff) {
        minDiff = diff;
        closest = shot;
      }
    }
    imageUrl = closest.url;
  } else if (activeAllocation.video_id) {
    imageUrl = `https://img.youtube.com/vi/${activeAllocation.video_id}/hqdefault.jpg`;
  }

  insertScreenshotToNotes(imageUrl, timeStr, `Lecture frame at ${timeStr}`);
}
window.insertCurrentFrameToNotes = insertCurrentFrameToNotes;

function printGroundedNotes() {
  const container = document.getElementById('grounded-notes-print-container');
  if (!container) return;
  const lessonTitle = activeAllocation ? activeAllocation.lesson_title : (currentCourse ? currentCourse.title : 'Lecture Study Notes');
  const courseTitle = currentCourse ? currentCourse.title : 'Course';
  const dateStr = new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
  const rawHtml = notesContent ? notesContent.innerHTML : '';

  container.innerHTML = `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.65; color: #111;">
      <div style="border-bottom: 2px solid #2563eb; padding-bottom: 12px; margin-bottom: 24px;">
        <div style="font-size: 11px; color: #4b5563; text-transform: uppercase; letter-spacing: 0.08em; font-weight: bold;">
          ${escapeHtml(courseTitle)} • Grounded Lecture Notes
        </div>
        <h1 style="font-size: 22pt; font-weight: 800; margin: 6px 0 8px 0; color: #181a1f; line-height: 1.25;">
          ${escapeHtml(lessonTitle)}
        </h1>
        <div style="font-size: 10pt; color: #6b7280;">
          Generated from AI Subtitles Grounding • Printed on ${dateStr}
        </div>
      </div>
      <div class="print-notes-body" style="font-size: 11pt; color: #1f2937;">
        ${rawHtml}
      </div>
    </div>
  `;

  document.body.classList.add('printing-grounded-notes');
  window.print();
  setTimeout(() => {
    document.body.classList.remove('printing-grounded-notes');
  }, 1000);
}
window.printGroundedNotes = printGroundedNotes;

function downloadGroundedNotesMarkdown() {
  if (!currentLoadedLessonMarkdown) {
    showToast('No notes content available to download.', 'error');
    return;
  }
  const lessonTitle = activeAllocation ? activeAllocation.lesson_title : 'Lesson_Notes';
  const courseTitle = currentCourse ? currentCourse.title : 'Course';
  const safeTitle = lessonTitle.replace(/[^a-zA-Z0-9_\-]/g, '_');

  const header = `# ${lessonTitle}\n\n**Course:** ${courseTitle}\n**Date:** ${new Date().toLocaleDateString()}\n\n---\n\n`;
  const fullContent = header + currentLoadedLessonMarkdown;

  const blob = new Blob([fullContent], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${safeTitle}_Grounded_Notes.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('Notes downloaded as Markdown (.md)!', 'success');
}
window.downloadGroundedNotesMarkdown = downloadGroundedNotesMarkdown;

function copyGroundedToPersonalNotes() {
  if (!currentLoadedLessonMarkdown) {
    showToast('No notes content available to copy.', 'error');
    return;
  }
  if (!inputPersonalNotes) return;
  const existing = inputPersonalNotes.value.trim();
  const separator = existing ? '\n\n---\n\n' : '';
  inputPersonalNotes.value = existing + separator + currentLoadedLessonMarkdown;
  switchNotesTab('personal');
  handlePersonalNotesInput();
  showToast('Grounded notes copied to Personal Notes space! You can now edit & annotate them.', 'success');
}
window.copyGroundedToPersonalNotes = copyGroundedToPersonalNotes;

// Clean conversational intros from LLM output
function stripConversationalIntro(text) {
  if (!text) return '';
  return text
    .replace(/^(?:As an? (?:expert )?(?:college )?(?:professor|educator|teacher|tutor|instructor)[^.\n]*[.:]\s*)+/i, '')
    .replace(/^(?:Alright,? let'?s break down[^.\n]*[.:]\s*)+/i, '')
    .replace(/^(?:Here is a (?:comprehensive )?(?:breakdown|summary|overview)[^.\n]*[.:]\s*)+/i, '')
    .replace(/^(?:Sure,? (?:here is|let's)[^.\n]*[.:]\s*)+/i, '')
    .trim();
}

// Strip raw chunk IDs and normalize timestamps
function cleanCitationsAndTimestamps(text) {
  if (!text) return '';
  // Convert [ref:chk_..., 00:00] or [ref:..., MM:SS] into [MM:SS]
  let cleaned = text.replace(/\[ref:[^,\]]+,\s*(\d{1,2}:\d{2})\]/g, '[$1]');
  // Convert [ref:chk_...][MM:SS] into [MM:SS]
  cleaned = cleaned.replace(/\[ref:[^\]]+\]\s*\[(\d{1,2}:\d{2})\]/g, '[$1]');
  // Strip orphan chunk IDs like [ref:chk_576623c69961; 00:00] -> [00:00]
  cleaned = cleaned.replace(/\[ref:[^;\]]+;\s*(\d{1,2}:\d{2})\]/g, '[$1]');
  // Strip raw chunk references without timestamp
  cleaned = cleaned.replace(/\[ref:[a-zA-Z0-9_\-]+\]/g, '');
  return cleaned;
}

function renderMarkdownNotes(markdownText) {
  currentLoadedLessonMarkdown = markdownText || '';
  const toolbar = document.getElementById('grounded-notes-toolbar');
  if (toolbar) toolbar.classList.remove('hidden');

  if (!markdownText) {
    notesContent.innerHTML = '<p class="text-text-secondary italic text-xs">No notes generated for this lesson yet. Click "Transcribe" above.</p>';
    return;
  }

  let text = stripConversationalIntro(markdownText);
  text = cleanCitationsAndTimestamps(text);

  // Escape basic HTML tags to prevent XSS
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Monospace code blocks ```lang ... ```
  html = html.replace(/```([a-zA-Z0-9_\-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre class="my-3 p-3.5 rounded-xl bg-bg-canvas border border-border-subtle overflow-x-auto text-[14px] font-mono leading-relaxed text-text-primary"><code>${code.trim()}</code></pre>`;
  });

  // Markdown tables: lines with pipes
  html = html.replace(/((?:^\|[^\n]+\|\r?\n)+)/gm, (tableBlock) => {
    const rows = tableBlock.trim().split(/\r?\n/).map(r => r.trim()).filter(Boolean);
    if (rows.length < 2) return tableBlock;
    const isSeparator = /^\|(?:\s*:?-+:?\s*\|)+$/.test(rows[1]);
    let out = '<div class="overflow-x-auto my-3 rounded-xl border border-border-subtle shadow-sm"><table class="w-full text-left text-xs sm:text-sm border-collapse">';
    let bodyStarted = false;
    rows.forEach((row, idx) => {
      if (idx === 1 && isSeparator) return;
      const cells = row.split('|').slice(1, -1).map(c => c.trim());
      if (idx === 0) {
        out += '<thead class="bg-bg-sidebar text-text-primary font-bold border-b border-border-subtle"><tr>';
        cells.forEach(c => { out += `<th class="p-2 sm:p-2.5 font-bold text-text-primary">${c}</th>`; });
        out += '</tr></thead><tbody>';
        bodyStarted = true;
      } else {
        if (!bodyStarted) { out += '<tbody>'; bodyStarted = true; }
        out += '<tr class="border-b border-border-subtle/50 hover:bg-bg-sidebar/50 transition">';
        cells.forEach(c => { out += `<td class="p-2 sm:p-2.5 text-text-primary">${c}</td>`; });
        out += '</tr>';
      }
    });
    if (bodyStarted) out += '</tbody>';
    out += '</table></div>';
    return out;
  });

  // GitHub style alerts: > [!NOTE], > [!IMPORTANT], > [!TIP], > [!WARNING]
  html = html.replace(/&gt; \[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\n((?:&gt; .*\n?)+)/gi, (match, p1, p2) => {
    const alertType = p1.toUpperCase();
    const alertBody = p2.replace(/&gt; ?/g, '');
    let colorClass = 'border-accent bg-accent-soft/40 text-accent-soft-text';
    if (alertType === 'IMPORTANT') colorClass = 'border-amber-500 bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-200';
    if (alertType === 'WARNING') colorClass = 'border-red-500 bg-red-50 dark:bg-red-950/40 text-red-900 dark:text-red-200';
    if (alertType === 'TIP') colorClass = 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-900 dark:text-emerald-200';
    return `<div class="p-3.5 my-3 border-l-4 rounded-r-xl ${colorClass} text-xs sm:text-sm leading-relaxed">
      <div class="font-bold uppercase tracking-wider mb-1">${alertType}</div>
      <div>${alertBody}</div>
    </div>`;
  });

  // Images ![caption](url)
  html = html.replace(/!\[(.*?)\]\((.*?)\)/g, '<div class="my-3"><img src="$2" alt="$1" class="rounded-xl border border-border-subtle max-h-60 object-cover shadow-sm mx-auto"><div class="text-[11px] text-center text-text-secondary mt-1 italic">$1</div></div>');

  // Headings (H1 through H6)
  html = html.replace(/^###### (.*$)/gim, '<h6 class="text-xs sm:text-sm font-semibold text-text-primary mt-3 mb-1">$1</h6>');
  html = html.replace(/^##### (.*$)/gim, '<h5 class="text-xs sm:text-sm font-bold text-text-primary mt-3.5 mb-1">$1</h5>');
  html = html.replace(/^#### (.*$)/gim, '<h4 class="text-sm sm:text-base font-bold text-text-primary mt-4 mb-1.5">$1</h4>');
  html = html.replace(/^### (.*$)/gim, '<h3 class="text-base sm:text-[18px] font-bold text-text-primary mt-5 mb-2">$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2 class="text-lg sm:text-[22px] font-bold text-text-primary mt-6 mb-2.5 pb-1 border-b border-border-subtle">$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1 class="text-xl sm:text-2xl font-extrabold text-text-primary mt-6 mb-3 pb-1 border-b border-border-subtle">$1</h1>');

  // Bullets (support both - and * lists)
  html = html.replace(/^[-*]\s+(.*$)/gim, '<div class="flex items-start gap-2 my-1 text-[15px] sm:text-[16px] text-text-primary leading-[1.65]"><span class="text-accent mt-0.5">•</span><span>$1</span></div>');

  // Bold & Italic
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="text-text-primary font-bold">$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em class="text-text-secondary italic">$1</em>');

  // Code spans
  html = html.replace(/`([^`]+)`/g, '<code class="bg-accent-soft text-accent-soft-text px-1.5 py-0.5 rounded text-[13px] font-mono border border-border-subtle">$1</code>');

  // Markdown seek links [text](seek://seconds) or [[04:12]](seek://252)
  html = html.replace(/\[(?:\[)?([^\]]+?)(?:\])?\]\(seek:\/\/(\d+)\)/g, (match, label, sec) => {
    const totalSec = parseInt(sec, 10);
    return `<button type="button" data-timestamp-sec="${totalSec}" onclick="window.seekToSeconds(${totalSec})" class="timestamp-link inline-flex items-center gap-1 font-mono text-[11px] font-semibold bg-accent-soft hover:bg-blue-200 dark:hover:bg-blue-900 text-accent-soft-text border border-border-subtle rounded px-1.5 py-0.5 cursor-pointer transition shadow-sm active:scale-95" title="Jump to ${label}"><span>▶</span> ${label}</button>`;
  });

  // Standard markdown links [label](url)
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-accent hover:underline font-medium">$1</a>');

  // Clickable Timestamps [MM:SS] or [HH:MM:SS]
  html = html.replace(/\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]/g, (match, p1, p2, p3) => {
    let totalSec = 0;
    if (p3 !== undefined) {
      totalSec = parseInt(p1, 10) * 3600 + parseInt(p2, 10) * 60 + parseInt(p3, 10);
    } else {
      totalSec = parseInt(p1, 10) * 60 + parseInt(p2, 10);
    }
    return `<button type="button" data-timestamp-sec="${totalSec}" onclick="window.seekToSeconds(${totalSec})" class="timestamp-link inline-flex items-center gap-1 font-mono text-[11px] font-semibold bg-accent-soft hover:bg-blue-200 dark:hover:bg-blue-900 text-accent-soft-text border border-border-subtle rounded px-1.5 py-0.5 cursor-pointer transition shadow-sm active:scale-95" title="Jump video to ${match}"><span>▶</span> ${match}</button>`;
  });

  // High-yield PYQ notice banner
  if (activeAllocation && activeAllocation.pyq_hit_count && activeAllocation.pyq_hit_count > 0) {
    const pyqBanner = `
      <div class="mb-3.5 p-3 rounded-xl bg-amber-500/10 border border-amber-500/25 flex items-center justify-between gap-2 text-xs shadow-sm">
        <div class="flex items-center gap-2">
          <span class="text-amber-600 dark:text-amber-400 font-bold">🔥 High-Yield Exam Topic</span>
          <span class="text-[11px] text-amber-700 dark:text-amber-300 font-medium">${activeAllocation.pyq_hit_count} past exam questions matched (${activeAllocation.pyq_total_marks || 0} marks)</span>
        </div>
        <button type="button" onclick="switchNotesTab('pyq')" class="text-[11px] font-semibold text-amber-600 dark:text-amber-400 hover:underline cursor-pointer">
          View Exam Questions →
        </button>
      </div>
    `;
    html = pyqBanner + html;
  }

  notesContent.innerHTML = html;
}

async function handleTranscribeLesson() {
  if (!activeAllocation) return;
  const lessonId = activeAllocation.lesson_id;
  transcribeBtnLabel.textContent = 'Transcribing...';
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/lessons/${lessonId}/transcribe`, { method: 'POST' });
    const data = await res.json();
    Logger.api('POST', `/api/lessons/${lessonId}/transcribe`, res.status, Math.round(performance.now() - t0), data);
    await loadLessonNotesAndArtifacts(lessonId, true);
  } catch (err) {
    Logger.error('Transcription failed', err);
    transcribeBtnLabel.textContent = 'Transcribe';
  }
}

async function handleCaptureKeyframes() {
  if (!activeAllocation) return;
  const lessonId = activeAllocation.lesson_id;
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/lessons/${lessonId}/screenshots`, { method: 'POST' });
    const shots = await res.json();
    Logger.api('POST', `/api/lessons/${lessonId}/screenshots`, res.status, Math.round(performance.now() - t0), shots);
    renderKeyframesStrip(shots);
    await loadLessonNotesAndArtifacts(lessonId, false);
  } catch (err) {
    Logger.error('Capture keyframes failed', err);
  }
}

let personalNotesTimeout = null;
function handlePersonalNotesInput() {
  personalNoteSaveStatus.textContent = 'Saving...';
  clearTimeout(personalNotesTimeout);
  personalNotesTimeout = setTimeout(async () => {
    if (!activeAllocation) return;
    const lessonId = activeAllocation.lesson_id;
    const text = inputPersonalNotes.value;
    try {
      const res = await fetch(`/api/lessons/${lessonId}/notes/personal`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ personal_notes: text }),
      });
      if (res.ok) {
        personalNoteSaveStatus.textContent = 'Saved ✓';
        setTimeout(() => { personalNoteSaveStatus.textContent = ''; }, 2000);
      }
    } catch (err) {
      personalNoteSaveStatus.textContent = 'Error saving';
    }
  }, 800);
}

// --- Multi-Source & Q&A Functions ---
function switchSourceModalTab(tab) {
  const tabPdf = document.getElementById('tab-src-pdf');
  const tabWeb = document.getElementById('tab-src-web');
  const tabPyq = document.getElementById('tab-src-pyq');
  const tabDisc = document.getElementById('tab-src-discover-web');
  const formPdf = document.getElementById('form-upload-pdf');
  const formWeb = document.getElementById('form-import-web');
  const formPyq = document.getElementById('form-upload-pyq');
  const viewDisc = document.getElementById('view-discover-web');

  [tabPdf, tabWeb, tabPyq, tabDisc].forEach(t => {
    if (t) {
      t.classList.remove('bg-white', 'dark:bg-zinc-800', 'font-semibold', 'text-zinc-900', 'dark:text-white', 'shadow-sm');
      t.classList.add('text-zinc-500', 'dark:text-zinc-400');
    }
  });
  if (formPdf) formPdf.classList.add('hidden');
  if (formWeb) formWeb.classList.add('hidden');
  if (formPyq) formPyq.classList.add('hidden');
  if (viewDisc) viewDisc.classList.add('hidden');

  if (tab === 'pdf') {
    if (tabPdf) {
      tabPdf.classList.add('bg-white', 'dark:bg-zinc-800', 'font-semibold', 'text-zinc-900', 'dark:text-white', 'shadow-sm');
      tabPdf.classList.remove('text-zinc-500', 'dark:text-zinc-400');
    }
    if (formPdf) formPdf.classList.remove('hidden');
  } else if (tab === 'web') {
    if (tabWeb) {
      tabWeb.classList.add('bg-white', 'dark:bg-zinc-800', 'font-semibold', 'text-zinc-900', 'dark:text-white', 'shadow-sm');
      tabWeb.classList.remove('text-zinc-500', 'dark:text-zinc-400');
    }
    if (formWeb) formWeb.classList.remove('hidden');
  } else if (tab === 'pyq') {
    if (tabPyq) {
      tabPyq.classList.add('bg-white', 'dark:bg-zinc-800', 'font-semibold', 'text-zinc-900', 'dark:text-white', 'shadow-sm');
      tabPyq.classList.remove('text-zinc-500', 'dark:text-zinc-400');
    }
    if (formPyq) formPyq.classList.remove('hidden');
  } else if (tab === 'discover-web') {
    if (tabDisc) {
      tabDisc.classList.add('bg-white', 'dark:bg-zinc-800', 'font-semibold', 'text-zinc-900', 'dark:text-white', 'shadow-sm');
      tabDisc.classList.remove('text-zinc-500', 'dark:text-zinc-400');
    }
    if (viewDisc) viewDisc.classList.remove('hidden');
    loadWebDocsDiscovery();
  }
}

async function loadWebDocsDiscovery() {
  if (!currentCourseId) return;
  const listEl = document.getElementById('candidate-web-docs-list');
  if (!listEl) return;
  listEl.innerHTML = '<div class="text-xs text-zinc-500 italic p-3">Searching curated study docs & guides...</div>';
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/sources/discover-web`);
    const data = await res.json();
    listEl.innerHTML = '';
    const candidates = data.candidates || [];
    if (candidates.length === 0) {
      listEl.innerHTML = '<div class="text-xs text-zinc-500 italic p-3">No web candidates found.</div>';
      return;
    }
    candidates.forEach(c => {
      const label = document.createElement('label');
      label.className = 'flex items-start gap-2.5 p-2 rounded-xl bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-750 text-xs';
      label.innerHTML = `
        <input type="checkbox" name="approved_web_doc" value="${c.url}" data-title="${c.title}" checked class="mt-0.5 rounded text-zinc-900 focus:ring-0">
        <div>
          <div class="font-semibold text-zinc-900 dark:text-zinc-100">${c.title}</div>
          <div class="text-[11px] text-zinc-500 dark:text-zinc-400">${c.site} • ${c.summary}</div>
        </div>
      `;
      listEl.appendChild(label);
    });
  } catch (err) {
    listEl.innerHTML = `<div class="text-xs text-red-400 p-3">Error loading docs: ${err.message}</div>`;
  }
}

async function handleApproveWebDocs() {
  const checked = document.querySelectorAll('input[name="approved_web_doc"]:checked');
  if (checked.length === 0) {
    alert('Select at least one document to import.');
    return;
  }
  const btn = document.getElementById('btn-approve-web-docs');
  btn.disabled = true;
  btn.textContent = 'Ingesting Docs...';

  try {
    for (const cb of checked) {
      const url = cb.value;
      const title = cb.getAttribute('data-title') || 'Web Document';
      await fetch(`/api/courses/${currentCourseId}/sources/web`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, title }),
      });
    }
    document.getElementById('add-source-modal').classList.add('hidden');
    await loadCourseSources(currentCourseId);
  } catch (err) {
    alert('Failed to import web doc: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Approve & Ingest Selected Docs';
  }
}

async function loadCourseSources(courseId) {
  if (!courseId) return;
  try {
    const res = await fetch(`/api/courses/${courseId}/sources`);
    if (!res.ok) return;
    const sources = await res.json();
    renderSourcesPills(sources);
  } catch (err) {
    Logger.error('Failed to load course sources', err);
  }
}

function renderSourcesPills(sources) {
  if (!sourcesPillsList) return;
  sourcesPillsList.innerHTML = '<span class="text-[11px] text-slate-500 font-medium shrink-0">SOURCES:</span>';
  if (!sources || sources.length === 0) {
    sourcesPillsList.innerHTML += '<span class="text-[11px] text-slate-500 italic">No sources attached yet</span>';
    return;
  }

  sources.forEach(s => {
    const pill = document.createElement('span');
    pill.className = 'px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 shrink-0 ';
    let icon = '▶';
    if (s.source_type === 'pdf') {
      icon = '📄';
      pill.className += 'bg-blue-950/80 text-blue-300 border border-blue-800/60';
    } else if (s.source_type === 'web_page') {
      icon = '🌐';
      pill.className += 'bg-emerald-950/80 text-emerald-300 border border-emerald-800/60';
    } else {
      pill.className += 'bg-accent-soft text-accent-soft-text border border-border-subtle';
    }
    const chunkInfo = s.metadata && s.metadata.chunk_count ? ` (${s.metadata.chunk_count} chk)` : '';
    pill.innerHTML = `<span>${icon}</span> <span class="max-w-[120px] truncate" title="${s.title}">${s.title}</span><span class="text-slate-400 text-[9px]">${chunkInfo}</span>`;
    sourcesPillsList.appendChild(pill);
  });
}

async function handleUploadPdf(e) {
  e.preventDefault();
  if (!currentCourseId) return;
  const fileInput = document.getElementById('input-pdf-file');
  const titleInput = document.getElementById('input-pdf-title');
  if (!fileInput.files || fileInput.files.length === 0) return;

  const btn = document.getElementById('btn-submit-pdf');
  const oldText = btn.textContent;
  btn.textContent = 'Uploading & Chunking...';
  btn.disabled = true;

  const fd = new FormData();
  fd.append('file', fileInput.files[0]);
  if (titleInput.value.trim()) {
    fd.append('title', titleInput.value.trim());
  }

  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/sources/pdf`, {
      method: 'POST',
      body: fd,
    });
    const data = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/sources/pdf`, res.status, Math.round(performance.now() - t0), data);
    addSourceModal.classList.add('hidden');
    formUploadPdf.reset();
    await loadCourseSources(currentCourseId);
    alert(`PDF uploaded successfully: "${data.title}" indexed into ${data.chunk_count} chunks.`);
  } catch (err) {
    Logger.error('PDF upload failed', err);
    alert('Failed to upload PDF: ' + err.message);
  } finally {
    btn.textContent = oldText;
    btn.disabled = false;
  }
}

async function handleImportWeb(e) {
  e.preventDefault();
  if (!currentCourseId) return;
  const urlInput = document.getElementById('input-web-url');
  const titleInput = document.getElementById('input-web-title');
  const url = urlInput.value.trim();
  if (!url) return;

  const btn = document.getElementById('btn-submit-web');
  const oldText = btn.textContent;
  btn.textContent = 'Fetching Article...';
  btn.disabled = true;

  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/sources/web`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: url,
        title: titleInput.value.trim() || undefined,
      }),
    });
    const data = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/sources/web`, res.status, Math.round(performance.now() - t0), data);
    if (!res.ok) {
      alert('Failed to import web article: ' + (data.detail || 'Error'));
    } else {
      addSourceModal.classList.add('hidden');
      formImportWeb.reset();
      await loadCourseSources(currentCourseId);
      alert(`Article imported: "${data.title}" indexed into ${data.chunk_count} chunks.`);
    }
  } catch (err) {
    Logger.error('Web import failed', err);
    alert('Failed to import web article: ' + err.message);
  } finally {
    btn.textContent = oldText;
    btn.disabled = false;
  }
}

// --- Past Exam Papers (PYQ) Management & High-Yield Analysis ---
async function handleUploadPyq(e) {
  e.preventDefault();
  if (!currentCourseId) {
    alert('Select a course first.');
    return;
  }

  const titleInput = document.getElementById('input-pyq-title');
  const fileInput = document.getElementById('input-pyq-file');
  const rawTextInput = document.getElementById('input-pyq-raw-text');
  const submitBtn = document.getElementById('btn-submit-pyq');

  const title = (titleInput?.value || '').trim() || 'Past Examination Paper';
  const rawText = (rawTextInput?.value || '').trim();
  const file = fileInput?.files?.[0];

  if (!file && !rawText) {
    alert('Please choose an exam PDF/text file or paste question text.');
    return;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Extracting & Matching...';
  }

  const t0 = performance.now();
  try {
    let res;
    if (file) {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', title);
      res = await fetch(`/api/courses/${currentCourseId}/pyq/upload-file`, {
        method: 'POST',
        body: formData,
      });
    } else {
      res = await fetch(`/api/courses/${currentCourseId}/pyq/upload-text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title, raw_text: rawText }),
      });
    }

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(errData.detail || 'Failed to process exam paper');
    }

    const data = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/pyq/upload`, res.status, Math.round(performance.now() - t0), data);

    // Reset inputs
    if (titleInput) titleInput.value = '';
    if (fileInput) fileInput.value = '';
    if (rawTextInput) rawTextInput.value = '';

    // Close modal
    if (addSourceModal) addSourceModal.classList.add('hidden');

    alert(`Successfully processed "${data.title || title}"!\n• Extracted ${data.questions_count} questions.\n• Matched ${data.matched_count} to syllabus lessons.`);

    // Reload schedule to reflect new PYQ badges and hit counts
    await loadSchedule(currentCourseId);
    if (activeAllocation) {
      await loadLessonPyqs(activeAllocation.lesson_id);
    }
  } catch (err) {
    Logger.error('PYQ upload failed', err);
    alert('PYQ upload failed: ' + err.message);
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Extract & Match PYQs';
    }
  }
}

async function loadLessonPyqs(lessonId) {
  if (!currentCourseId || !lessonId) return;
  const container = document.getElementById('pyq-questions-container');
  const badgeCount = document.getElementById('badge-lesson-pyq-count');
  const badgeHeader = document.getElementById('pyq-lesson-badge-header');

  if (!container) return;

  try {
    const res = await fetch(`/api/courses/${currentCourseId}/lessons/${lessonId}/pyq`);
    if (!res.ok) {
      container.innerHTML = '<div class="text-xs text-alabaster-muted dark:text-charcoal-muted italic p-2">Failed to load past questions.</div>';
      return;
    }
    const data = await res.json();
    const questions = Array.isArray(data) ? data : (data.questions || []);
    const count = questions.length;
    const marks = questions.reduce((acc, q) => acc + (q.marks || 0), 0);

    if (badgeCount) {
      if (count > 0) {
        badgeCount.textContent = count;
        badgeCount.classList.remove('hidden');
      } else {
        badgeCount.classList.add('hidden');
      }
    }

    if (badgeHeader) {
      badgeHeader.textContent = count > 0 ? `${count} Matched (${marks} Marks)` : '0 Matched';
      if (count > 0) {
        badgeHeader.className = 'text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-700/60 font-semibold';
      } else {
        badgeHeader.className = 'text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-700';
      }
    }

    if (questions.length === 0) {
      container.innerHTML = `
        <div class="p-4 rounded-xl border border-dashed border-alabaster-border dark:border-charcoal-border text-center space-y-2">
          <div class="text-sm">📝</div>
          <p class="text-xs text-alabaster-muted dark:text-charcoal-muted">No past-exam questions matched for this specific lesson yet.</p>
          <button type="button" onclick="window.openAddSourceModalWithTab('pyq')" class="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 font-semibold hover:underline">
            <span>+ Upload Past Papers (PYQ)</span>
          </button>
        </div>
      `;
      return;
    }

    container.innerHTML = questions.map((q, idx) => {
      const qNum = q.question_number || `Q${idx + 1}`;
      const marksBadge = q.marks ? `<span class="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-700 dark:text-amber-300 font-mono text-[10px] font-bold border border-amber-500/25 shrink-0">${q.marks} Marks</span>` : '';
      const paperBadge = q.paper_title ? `<span class="text-[10px] text-alabaster-muted dark:text-charcoal-muted font-mono truncate max-w-[140px]">${q.paper_title}</span>` : '';
      const escapedText = q.question_text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

      return `
        <div class="p-3 rounded-xl bg-alabaster-card dark:bg-charcoal-card border border-alabaster-border dark:border-charcoal-border hover:border-amber-400/50 dark:hover:border-amber-500/50 transition space-y-2 group shadow-sm">
          <div class="flex items-center justify-between gap-1.5">
            <div class="flex items-center gap-1.5 min-w-0">
              <span class="font-bold text-xs font-mono text-amber-600 dark:text-amber-400">${qNum}</span>
              ${marksBadge}
            </div>
            ${paperBadge}
          </div>
          <p class="text-xs text-alabaster-text dark:text-charcoal-text leading-relaxed whitespace-pre-wrap">${escapedText}</p>
          <div class="pt-1 flex items-center justify-end gap-2 border-t border-alabaster-border/40 dark:border-charcoal-border/40">
            <button type="button" onclick="window.askPyqInQa(${JSON.stringify(q.question_text).replace(/"/g, '&quot;')})" class="text-[11px] font-semibold text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1">
              <span>💬 Ask AI Solution</span>
            </button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    Logger.error('Failed to load lesson PYQs', err);
    if (container) container.innerHTML = '<div class="text-xs text-red-400 p-2">Error loading past exam questions.</div>';
  }
}

function askPyqInQa(questionText) {
  switchNotesTab('qa');
  if (inputQaQuery) {
    inputQaQuery.value = `Explain how to solve this past exam question step-by-step with full exam-ready answer:\n"${questionText}"`;
    inputQaQuery.focus();
  }
}
window.askPyqInQa = askPyqInQa;

function openAddSourceModalWithTab(tab) {
  if (addSourceModal) {
    addSourceModal.classList.remove('hidden');
    switchSourceModalTab(tab);
  }
}
window.openAddSourceModalWithTab = openAddSourceModalWithTab;

// --- Last-Night Cram Sheet Generator ---
function renderCramSheetMarkdown(markdownText) {
  if (!markdownText) return '<div class="text-center p-6 text-text-secondary">No cram sheet content generated yet.</div>';

  let text = stripConversationalIntro(markdownText);
  text = cleanCitationsAndTimestamps(text);

  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Monospace code blocks
  html = html.replace(/```([a-zA-Z0-9_\-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre class="my-3 p-3.5 rounded-xl bg-bg-canvas border border-border-subtle overflow-x-auto text-[14px] font-mono leading-relaxed text-text-primary print-break-inside-avoid"><code>${code.trim()}</code></pre>`;
  });

  // Markdown tables: lines with pipes
  html = html.replace(/((?:^\|[^\n]+\|\r?\n)+)/gm, (tableBlock) => {
    const rows = tableBlock.trim().split(/\r?\n/).map(r => r.trim()).filter(Boolean);
    if (rows.length < 2) return tableBlock;
    const isSeparator = /^\|(?:\s*:?-+:?\s*\|)+$/.test(rows[1]);
    let out = '<div class="overflow-x-auto my-3 rounded-xl border border-border-subtle shadow-sm print-break-inside-avoid"><table class="w-full text-left text-xs sm:text-sm border-collapse">';
    let bodyStarted = false;
    rows.forEach((row, idx) => {
      if (idx === 1 && isSeparator) return;
      const cells = row.split('|').slice(1, -1).map(c => c.trim());
      if (idx === 0) {
        out += '<thead class="bg-bg-sidebar text-text-primary font-bold border-b border-border-subtle"><tr>';
        cells.forEach(c => { out += `<th class="p-2 sm:p-2.5 font-bold text-text-primary">${c}</th>`; });
        out += '</tr></thead><tbody>';
        bodyStarted = true;
      } else {
        if (!bodyStarted) { out += '<tbody>'; bodyStarted = true; }
        out += '<tr class="border-b border-border-subtle/50 hover:bg-bg-sidebar/50 transition">';
        cells.forEach(c => { out += `<td class="p-2 sm:p-2.5 text-text-primary">${c}</td>`; });
        out += '</tr>';
      }
    });
    if (bodyStarted) out += '</tbody>';
    out += '</table></div>';
    return out;
  });

  // Callouts
  html = html.replace(/&gt; \[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\n((?:&gt; .*\n?)+)/gi, (match, p1, p2) => {
    const alertType = p1.toUpperCase();
    const alertBody = p2.replace(/&gt; ?/g, '');
    let colorClass = 'border-amber-500 bg-amber-50 dark:bg-amber-950/40 text-amber-900 dark:text-amber-200';
    return `<div class="p-3.5 my-2.5 border-l-4 rounded-r-xl ${colorClass} text-xs sm:text-sm leading-relaxed print-break-inside-avoid">
      <div class="font-bold uppercase tracking-wider mb-0.5">${alertType}</div>
      <div>${alertBody}</div>
    </div>`;
  });

  // Headings
  html = html.replace(/^###### (.*$)/gim, '<h6 class="text-xs sm:text-sm font-semibold text-text-primary mt-3 mb-1 print-break-inside-avoid">$1</h6>');
  html = html.replace(/^##### (.*$)/gim, '<h5 class="text-xs sm:text-sm font-bold text-text-primary mt-3.5 mb-1 print-break-inside-avoid">$1</h5>');
  html = html.replace(/^#### (.*$)/gim, '<h4 class="text-sm sm:text-base font-bold text-text-primary mt-4 mb-1.5 print-break-inside-avoid">$1</h4>');
  html = html.replace(/^### (.*$)/gim, '<h3 class="text-base sm:text-[18px] font-bold text-text-primary mt-5 mb-2 print-break-inside-avoid">$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2 class="text-lg sm:text-[22px] font-bold text-text-primary mt-6 mb-2.5 pb-1 border-b border-border-subtle print-break-inside-avoid flex items-center gap-1.5">$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1 class="text-xl sm:text-2xl font-extrabold text-text-primary mt-6 mb-3 pb-1 border-b-2 border-border-subtle print-break-inside-avoid">$1</h1>');

  // Bullets (support both - and * lists)
  html = html.replace(/^[-*]\s+(.*$)/gim, '<div class="flex items-start gap-2 my-1 text-[15px] sm:text-[16px] text-text-primary leading-[1.65]"><span class="text-accent font-bold mt-0.5">•</span><span>$1</span></div>');

  // Bold & Italic
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="text-text-primary font-bold">$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em class="italic text-text-secondary">$1</em>');

  // Code spans
  html = html.replace(/`([^`]+)`/g, '<code class="bg-accent-soft text-accent-soft-text px-1 py-0.5 rounded text-[13px] font-mono border border-border-subtle">$1</code>');

  // Markdown seek links [text](seek://seconds) or [[04:12]](seek://252)
  html = html.replace(/\[(?:\[)?([^\]]+?)(?:\])?\]\(seek:\/\/(\d+)\)/g, (match, label, sec) => {
    const totalSec = parseInt(sec, 10);
    return `<button type="button" data-timestamp-sec="${totalSec}" onclick="window.seekToSeconds(${totalSec})" class="timestamp-link inline-flex items-center gap-1 font-mono text-[11px] font-semibold bg-accent-soft hover:bg-blue-200 dark:hover:bg-blue-900 text-accent-soft-text border border-border-subtle rounded px-1.5 py-0.5 cursor-pointer transition shadow-sm active:scale-95" title="Jump to ${label}"><span>▶</span> ${label}</button>`;
  });

  // Standard markdown links [label](url)
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-accent hover:underline font-medium">$1</a>');

  // Clickable Timestamps [MM:SS] or [HH:MM:SS]
  html = html.replace(/\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]/g, (match, p1, p2, p3) => {
    let totalSec = 0;
    if (p3 !== undefined) {
      totalSec = parseInt(p1, 10) * 3600 + parseInt(p2, 10) * 60 + parseInt(p3, 10);
    } else {
      totalSec = parseInt(p1, 10) * 60 + parseInt(p2, 10);
    }
    return `<button type="button" data-timestamp-sec="${totalSec}" onclick="window.seekToSeconds(${totalSec})" class="timestamp-link inline-flex items-center gap-1 font-mono text-[11px] font-semibold bg-accent-soft hover:bg-blue-200 dark:hover:bg-blue-900 text-accent-soft-text border border-border-subtle rounded px-1.5 py-0.5 cursor-pointer transition shadow-sm active:scale-95" title="Jump video to ${match}"><span>▶</span> ${match}</button>`;
  });

  return html;
}

async function loadCramSheet(forceRefresh = false, fullSyllabus = false) {
  if (!currentCourseId) {
    alert('Please select or create a course first.');
    return;
  }

  const modal = document.getElementById('modal-cram-sheet');
  const container = document.getElementById('cram-sheet-content');
  const badgeCache = document.getElementById('badge-cram-cache');
  const btnRefresh = document.getElementById('btn-refresh-cram-sheet');
  const btnFull = document.getElementById('btn-full-cram-sheet');

  if (modal) modal.classList.remove('hidden');
  if (container) {
    let msg = 'Retrieving high-density exam revision sheet...';
    if (fullSyllabus) {
      msg = '⚡ Progressively processing entire syllabus in batches of 3-5 lessons... Synthesizing full-course cheat sheet.';
    } else if (forceRefresh) {
      msg = 'Re-synthesizing Last-Night Cram Sheet from latest notes & past papers...';
    }
    container.innerHTML = `
      <div class="py-12 flex flex-col items-center justify-center space-y-3">
        <div class="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin"></div>
        <p class="text-xs font-semibold text-text-secondary text-center max-w-md">
          ${msg}
        </p>
      </div>
    `;
  }
  if (btnRefresh) btnRefresh.disabled = true;
  if (btnFull) btnFull.disabled = true;

  const t0 = performance.now();
  try {
    const endpoint = fullSyllabus
      ? `/api/courses/${currentCourseId}/cram-sheet/generate-full`
      : `/api/courses/${currentCourseId}/cram-sheet/generate`;
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force_refresh: forceRefresh, full_syllabus: fullSyllabus })
    });
    if (!res.ok) {
      throw new Error(`Failed to generate cram sheet (status ${res.status})`);
    }
    const data = await res.json();
    Logger.api('POST', endpoint, res.status, Math.round(performance.now() - t0), data);

    if (badgeCache) {
      const shortHash = (data.notes_hash || '').slice(0, 8);
      badgeCache.textContent = `SHA: ${shortHash}`;
      badgeCache.title = `Cached by content hash: ${data.notes_hash}`;
    }

    if (container) {
      container.innerHTML = renderCramSheetMarkdown(data.content_markdown);
    }
  } catch (err) {
    Logger.error('Failed to load cram sheet', err);
    if (container) {
      container.innerHTML = `
        <div class="p-6 text-center text-xs text-red-500 bg-red-50 dark:bg-red-950/30 rounded-xl border border-red-200 dark:border-red-900">
          <p class="font-bold mb-1">Failed to generate Last-Night Cram Sheet</p>
          <p>${escapeHtml(err.message)}</p>
        </div>
      `;
    }
  } finally {
    if (btnRefresh) btnRefresh.disabled = false;
    if (btnFull) btnFull.disabled = false;
  }
}
window.loadCramSheet = loadCramSheet;

// --- Syllabus Alignment & Auto-Curator ---
window.syllabusStrictness = 'balanced';
window.currentSyllabusMatch = null;
window.selectedSyllabusLessonIds = new Set();

async function openSyllabusModal() {
  if (!currentCourseId) {
    showToast('Please select or create a course first.', 'warning');
    return;
  }
  const modal = document.getElementById('modal-syllabus-match');
  if (!modal) return;
  modal.classList.remove('hidden');

  // Show Step 1, hide Step 2
  const stepInput = document.getElementById('syllabus-step-input');
  const stepReview = document.getElementById('syllabus-step-review');
  if (stepInput) stepInput.classList.remove('hidden');
  if (stepReview) stepReview.classList.add('hidden');

  // Attempt to pre-fill with existing saved syllabus text
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/syllabus`);
    if (res.ok) {
      const data = await res.json();
      const textarea = document.getElementById('input-syllabus-text');
      if (textarea && data.syllabus_text && !textarea.value.trim()) {
        textarea.value = data.syllabus_text;
      }
    }
  } catch (err) {
    Logger.error('Could not load course syllabus', err);
  }
}

function closeSyllabusModal() {
  const modal = document.getElementById('modal-syllabus-match');
  if (modal) modal.classList.add('hidden');
}

function setSyllabusStrictness(strictness) {
  window.syllabusStrictness = strictness;
  const pills = {
    'balanced': document.getElementById('pill-syl-balanced'),
    'strict': document.getElementById('pill-syl-strict'),
    'comprehensive': document.getElementById('pill-syl-comprehensive'),
  };
  const activeClass = ['bg-accent', 'text-white', 'shadow-sm', 'font-semibold'];
  const inactiveClass = ['text-text-secondary', 'hover:text-text-primary', 'font-medium'];

  Object.entries(pills).forEach(([key, el]) => {
    if (!el) return;
    if (key === strictness) {
      el.classList.add(...activeClass);
      el.classList.remove(...inactiveClass);
    } else {
      el.classList.remove(...activeClass);
      el.classList.add(...inactiveClass);
    }
  });
}

async function handleAnalyzeSyllabus() {
  const textarea = document.getElementById('input-syllabus-text');
  const text = textarea ? textarea.value.trim() : '';
  if (!text || text.length < 5) {
    showToast('Please paste your syllabus text first (at least a few topics).', 'warning');
    if (textarea) textarea.focus();
    return;
  }

  const btn = document.getElementById('btn-analyze-syllabus');
  const btnText = document.getElementById('btn-analyze-syllabus-text');
  if (btn) btn.disabled = true;
  if (btnText) btnText.textContent = 'Analyzing & Matching...';

  try {
    const res = await fetch(`/api/courses/${currentCourseId}/syllabus/match`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        syllabus_text: text,
        strictness: window.syllabusStrictness || 'balanced',
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Matching failed (status ${res.status})`);
    }

    const data = await res.json();
    window.currentSyllabusMatch = data;

    // Pre-populate selected lesson IDs with all matched lessons
    window.selectedSyllabusLessonIds = new Set(
      data.lessons.filter(l => l.is_matched).map(l => l.id)
    );

    renderSyllabusReviewScreen(data);

    // Switch view to Step 2
    document.getElementById('syllabus-step-input')?.classList.add('hidden');
    document.getElementById('syllabus-step-review')?.classList.remove('hidden');
  } catch (err) {
    Logger.error('Syllabus analysis failed', err);
    showToast(err.message || 'Syllabus analysis failed', 'error');
  } finally {
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = 'Analyze & Match Videos';
  }
}

function renderSyllabusReviewScreen(data) {
  // 1. Stats Bar
  const matchedStat = document.getElementById('stat-syl-matched-count');
  if (matchedStat) matchedStat.textContent = `${data.matched_lessons_count} / ${data.total_lessons}`;

  const savedStat = document.getElementById('stat-syl-saved-time');
  if (savedStat) {
    const hours = Math.floor(data.saved_minutes / 60);
    const mins = data.saved_minutes % 60;
    savedStat.textContent = `${hours}h ${mins}m saved`;
  }

  const coverageStat = document.getElementById('stat-syl-coverage');
  if (coverageStat) coverageStat.textContent = `${data.matched_percentage}%`;

  // 2. View A: By Syllabus Topic
  const topicsContainer = document.getElementById('syllabus-view-topics');
  if (topicsContainer) {
    const lessonMap = new Map(data.lessons.map(l => [l.id, l]));
    topicsContainer.innerHTML = data.topics.map(t => {
      const matchedLessons = t.matched_lesson_ids.map(id => lessonMap.get(id)).filter(Boolean);
      return `
        <div class="p-3 rounded-xl border border-border-subtle bg-bg-card space-y-2">
          <div class="flex items-center justify-between gap-2">
            <div>
              <span class="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-accent-soft text-accent-soft-text font-bold">${escapeHtml(t.unit || 'Topic')}</span>
              <span class="text-xs font-bold text-text-primary ml-1.5">${escapeHtml(t.topic)}</span>
            </div>
            <span class="text-[11px] font-semibold text-text-secondary">${matchedLessons.length} video${matchedLessons.length === 1 ? '' : 's'}</span>
          </div>
          ${matchedLessons.length > 0 ? `
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5 pt-1">
              ${matchedLessons.map(l => `
                <div class="p-1.5 rounded-lg bg-bg-canvas border border-border-subtle flex items-center justify-between text-[11px] gap-2">
                  <span class="font-medium text-text-primary truncate" title="${escapeHtml(l.title)}">${escapeHtml(l.title)}</span>
                  <span class="text-[10px] font-mono text-cyan-600 dark:text-cyan-400 shrink-0 font-medium">${formatDurationSec(l.raw_duration_sec)}</span>
                </div>
              `).join('')}
            </div>
          ` : `
            <p class="text-[11px] text-text-secondary italic">No playlist videos matched this specific topic directly.</p>
          `}
        </div>
      `;
    }).join('');
  }

  // 3. View B: All Videos Checklist
  renderSyllabusChecklistView(data);
  updateSyllabusSelectedCount();
}

function renderSyllabusChecklistView(data) {
  const listContainer = document.getElementById('syllabus-view-checklist');
  if (!listContainer) return;

  listContainer.innerHTML = data.lessons.map(l => {
    const isChecked = window.selectedSyllabusLessonIds.has(l.id);
    const badge = l.is_matched
      ? `<span class="text-[10px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30 truncate" title="${escapeHtml(l.match_reason)}">✓ ${escapeHtml(l.match_reason)}</span>`
      : `<span class="text-[10px] font-medium px-2 py-0.5 rounded-full bg-bg-canvas text-text-secondary border border-border-subtle">Out of Syllabus</span>`;

    return `
      <div class="py-2 px-2.5 rounded-lg flex items-center gap-3 hover:bg-bg-card transition cursor-pointer ${isChecked ? '' : 'opacity-50'}" onclick="window.toggleSyllabusLessonSelect('${l.id}')">
        <input type="checkbox" class="rounded text-accent focus:ring-0 cursor-pointer" ${isChecked ? 'checked' : ''} onclick="event.stopPropagation(); window.toggleSyllabusLessonSelect('${l.id}')">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-0.5">
            <span class="font-semibold text-xs text-text-primary truncate ${isChecked ? '' : 'line-through text-text-secondary'}">${escapeHtml(l.title)}</span>
            <span class="text-[10px] font-mono text-cyan-600 dark:text-cyan-400 shrink-0">${formatDurationSec(l.raw_duration_sec)}</span>
          </div>
          <div>${badge}</div>
        </div>
      </div>
    `;
  }).join('');
}

window.toggleSyllabusLessonSelect = function(lessonId) {
  if (window.selectedSyllabusLessonIds.has(lessonId)) {
    window.selectedSyllabusLessonIds.delete(lessonId);
  } else {
    window.selectedSyllabusLessonIds.add(lessonId);
  }
  if (window.currentSyllabusMatch) {
    renderSyllabusChecklistView(window.currentSyllabusMatch);
  }
  updateSyllabusSelectedCount();
};

function updateSyllabusSelectedCount() {
  const count = window.selectedSyllabusLessonIds.size;
  const label = document.getElementById('syllabus-selected-label');
  if (label) label.textContent = `${count} video${count === 1 ? '' : 's'} selected`;
}

function switchSyllabusReviewTab(tab) {
  const tabTopics = document.getElementById('tab-syl-topics');
  const tabChecklist = document.getElementById('tab-syl-checklist');
  const viewTopics = document.getElementById('syllabus-view-topics');
  const viewChecklist = document.getElementById('syllabus-view-checklist');

  const activeClasses = ['bg-accent', 'text-white', 'font-semibold'];
  const inactiveClasses = ['text-text-secondary', 'hover:text-text-primary', 'font-medium'];

  if (tab === 'topics') {
    tabTopics?.classList.add(...activeClasses);
    tabTopics?.classList.remove(...inactiveClasses);
    tabChecklist?.classList.remove(...activeClasses);
    tabChecklist?.classList.add(...inactiveClasses);
    viewTopics?.classList.remove('hidden');
    viewChecklist?.classList.add('hidden');
  } else {
    tabChecklist?.classList.add(...activeClasses);
    tabChecklist?.classList.remove(...inactiveClasses);
    tabTopics?.classList.remove(...activeClasses);
    tabTopics?.classList.add(...inactiveClasses);
    viewTopics?.classList.add('hidden');
    viewChecklist?.classList.remove('hidden');
  }
}

async function handleApplySyllabus() {
  if (!currentCourseId) return;
  const textarea = document.getElementById('input-syllabus-text');
  const text = textarea ? textarea.value.trim() : '';

  const selectedIds = Array.from(window.selectedSyllabusLessonIds);
  if (selectedIds.length === 0) {
    showToast('Please select at least 1 video to include in your study schedule.', 'warning');
    return;
  }

  const btn = document.getElementById('btn-apply-syllabus');
  const btnText = document.getElementById('btn-apply-syllabus-text');
  if (btn) btn.disabled = true;
  if (btnText) btnText.textContent = 'Applying & Rescheduling...';

  try {
    const res = await fetch(`/api/courses/${currentCourseId}/syllabus/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        syllabus_text: text,
        included_lesson_ids: selectedIds,
        strictness: window.syllabusStrictness || 'balanced',
        regenerate_schedule: true,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to apply syllabus (status ${res.status})`);
    }

    const data = await res.json();
    closeSyllabusModal();

    // Reload course curriculum, drawer, and schedule
    await loadLessons(currentCourseId);
    await loadSchedule(currentCourseId);

    showToast(`🎉 ${data.message || 'Syllabus aligned and schedule reflowed!'}`);
  } catch (err) {
    Logger.error('Failed to apply syllabus alignment', err);
    showToast(err.message || 'Failed to apply syllabus alignment', 'error');
  } finally {
    if (btn) btn.disabled = false;
    if (btnText) btnText.textContent = 'Apply & Auto-Reschedule Course';
  }
}

window.openSyllabusModal = openSyllabusModal;
window.closeSyllabusModal = closeSyllabusModal;
window.handleAnalyzeSyllabus = handleAnalyzeSyllabus;
window.handleApplySyllabus = handleApplySyllabus;

async function loadQAHistory(courseId) {
  if (!courseId) return;
  try {
    const res = await fetch(`/api/courses/${courseId}/qa`);
    if (!res.ok) return;
    const threads = await res.json();
    renderQAThreads(threads);
  } catch (err) {
    Logger.error('Failed to load QA history', err);
  }
}

function setQAScope(scope) {
  qaScope = scope === 'notebook' ? 'notebook' : 'lesson';
  const activeClasses = ['bg-blue-600', 'text-white', 'shadow-sm'];
  const inactiveClasses = ['text-alabaster-muted', 'dark:text-charcoal-muted', 'hover:text-alabaster-text', 'dark:hover:text-charcoal-text'];

  if (qaScopeLesson && qaScopeNotebook) {
    if (qaScope === 'lesson') {
      qaScopeLesson.classList.add(...activeClasses);
      qaScopeLesson.classList.remove(...inactiveClasses);
      qaScopeNotebook.classList.remove(...activeClasses);
      qaScopeNotebook.classList.add(...inactiveClasses);
    } else {
      qaScopeNotebook.classList.add(...activeClasses);
      qaScopeNotebook.classList.remove(...inactiveClasses);
      qaScopeLesson.classList.remove(...activeClasses);
      qaScopeLesson.classList.add(...inactiveClasses);
    }
  }
}
window.setQAScope = setQAScope;

function useQuickPrompt(promptText) {
  switchNotesTab('qa');
  if (!inputQaQuery) return;
  const currentVal = inputQaQuery.value.trim();
  if (!currentVal) {
    inputQaQuery.value = promptText;
  } else if (!currentVal.startsWith(promptText)) {
    inputQaQuery.value = `${promptText} ${currentVal}`;
  }
  inputQaQuery.focus();
  const len = inputQaQuery.value.length;
  inputQaQuery.setSelectionRange(len, len);
}
window.useQuickPrompt = useQuickPrompt;

async function saveAIReplyToNotes(answerText) {
  const lessonId = currentLessonId || (activeAllocation ? activeAllocation.lesson_id : null);
  if (!currentCourseId || !lessonId) {
    showToast('Please select a lesson to save notes', 'error');
    return;
  }
  if (!answerText) return;

  const currentText = inputPersonalNotes ? inputPersonalNotes.value.trim() : '';
  const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const heading = `\n\n### 💡 AI Explanation (${timeStr})\n`;
  const updatedPersonalNotes = currentText 
    ? `${currentText}${heading}${answerText}` 
    : `### 💡 AI Explanation\n${answerText}`;

  if (inputPersonalNotes) {
    inputPersonalNotes.value = updatedPersonalNotes;
    updatePersonalNotesCount();
  }

  try {
    let saved = false;
    try {
      const res = await fetch(`/api/courses/${currentCourseId}/lessons/${lessonId}/notes`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ personal_notes: updatedPersonalNotes }),
      });
      if (res.ok) saved = true;
    } catch (e) {
      // fallback below
    }

    if (!saved) {
      const fallbackRes = await fetch(`/api/lessons/${lessonId}/notes/personal`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ personal_notes: updatedPersonalNotes }),
      });
      if (!fallbackRes.ok) throw new Error('Failed to persist note update');
    }

    showToast('Saved AI reply to My Notes! 📌', 'success');
  } catch (err) {
    Logger.error('Failed to save AI reply to notes', err);
    showToast('Failed to save to notes: ' + err.message, 'error');
  }
}
window.saveAIReplyToNotes = saveAIReplyToNotes;

function renderQAThreads(threads) {
  if (!qaMessagesList) return;
  if (!threads || threads.length === 0) {
    qaMessagesList.innerHTML = `
      <div class="p-4 bg-bg-card rounded-2xl border border-dashed border-border-subtle text-xs text-text-secondary">
        <p class="font-bold text-text-primary mb-1">Grounded Q&A Workspace</p>
        <p class="text-text-secondary leading-relaxed">Ask any conceptual question, request a summary, or verify exam formulas. All answers cite exact verbatim source passages from YouTube transcripts, uploaded PDFs, and web articles.</p>
      </div>
    `;
    return;
  }

  qaMessagesList.innerHTML = '';
  threads.forEach(t => {
    const item = document.createElement('div');
    item.className = 'space-y-2';

    // Question balloon
    const qDiv = document.createElement('div');
    qDiv.className = 'flex items-start gap-2 justify-end';
    qDiv.innerHTML = `
      <div class="bg-accent text-white text-xs sm:text-sm px-4 py-2.5 rounded-2xl rounded-tr-sm max-w-[85%] shadow-sm font-medium leading-relaxed">
        ${escapeHtml(t.query)}
      </div>
    `;
    item.appendChild(qDiv);

    // Answer balloon
    const aDiv = document.createElement('div');
    aDiv.className = 'qa-answer-bubble flex items-start gap-2';

    let answerHtml = formatGroundedAnswerHtml(t.answer_markdown);
    let citationsHtml = '';
    if (t.citations && t.citations.length > 0) {
      citationsHtml = `
        <div class="mt-2.5 pt-2 border-t border-border-subtle flex flex-wrap gap-1.5">
          <span class="text-[10px] text-text-secondary font-semibold uppercase shrink-0">Citations:</span>
          ${t.citations.map(c => {
            const timeTag = c.start_sec !== null && c.start_sec !== undefined ? ` [${formatDurationSec(c.start_sec)}]` : '';
            return `<button type="button" data-timestamp-sec="${c.start_sec !== null && c.start_sec !== undefined ? c.start_sec : ''}" onclick="${c.start_sec !== null && c.start_sec !== undefined ? `window.seekToSeconds(${c.start_sec})` : ''}" class="qa-citation-badge inline-flex items-center gap-1 px-2 py-0.5 rounded bg-accent-soft text-accent-soft-text border border-border-subtle font-mono text-[10px] hover:bg-blue-200 dark:hover:bg-blue-900 transition" title="${escapeHtml(c.excerpt)}">
              <span>📌</span> ${escapeHtml(c.source_title)}${timeTag}
            </button>`;
          }).join('')}
        </div>
      `;
    }

    aDiv.innerHTML = `
      <div class="w-7 h-7 rounded-full bg-accent-soft border border-border-subtle text-accent-soft-text flex items-center justify-center text-[11px] font-bold shrink-0 mt-0.5">LM</div>
      <div class="bg-bg-card border border-border-subtle text-text-primary text-[15px] sm:text-[16px] px-4 py-3 rounded-2xl rounded-tl-sm max-w-[92%] shadow-sm space-y-2 leading-[1.65]">
        ${answerHtml}
        ${citationsHtml}
        <div class="mt-2 pt-2 border-t border-border-subtle flex justify-end">
          <button type="button" class="btn-save-ai-reply inline-flex items-center gap-1 px-2.5 py-1 rounded bg-bg-canvas hover:bg-bg-sidebar text-text-secondary hover:text-text-primary border border-border-subtle text-[11px] font-medium transition active:scale-95 shadow-sm cursor-pointer" title="Save this AI answer into your personal notes">
            <span>📌</span>
            <span>Save to My Notes</span>
          </button>
        </div>
      </div>
    `;

    const saveBtn = aDiv.querySelector('.btn-save-ai-reply');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => {
        saveAIReplyToNotes(t.answer_markdown);
      });
    }

    item.appendChild(aDiv);
    qaMessagesList.appendChild(item);
  });

  qaMessagesList.scrollTop = qaMessagesList.scrollHeight;
}

function formatGroundedAnswerHtml(markdown) {
  if (!markdown) return '';
  let text = stripConversationalIntro(markdown);
  text = cleanCitationsAndTimestamps(text);

  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Timestamps [MM:SS]
  html = html.replace(/\[(\d{1,2}):(\d{2})\]/g, (match, p1, p2) => {
    const s = parseInt(p1, 10) * 60 + parseInt(p2, 10);
    return `<button type="button" data-timestamp-sec="${s}" onclick="window.seekToSeconds(${s})" class="inline-flex items-center font-mono text-[11px] font-bold text-accent-soft-text hover:text-accent bg-accent-soft px-1.5 py-0.5 rounded border border-border-subtle cursor-pointer transition active:scale-95">▶ ${match}</button>`;
  });

  // Bullets
  html = html.replace(/^- (.*$)/gim, '<div class="ml-2 flex items-start gap-1.5 my-1 text-[15px] sm:text-[16px] leading-[1.65]"><span class="text-accent mt-0.5">•</span><span>$1</span></div>');

  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="text-text-primary font-bold">$1</strong>');
  return html.replace(/\n\n/g, '<br>');
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function handleAskQuestion(e) {
  e.preventDefault();
  if (!currentCourseId) return;
  const q = inputQaQuery.value.trim();
  if (!q) return;

  qaBtnText.textContent = '';
  qaSpinner.classList.remove('hidden');
  btnSubmitQa.disabled = true;

  // Append user message immediately
  const tempMsg = document.createElement('div');
  tempMsg.className = 'space-y-2';
  tempMsg.innerHTML = `
    <div class="flex items-start gap-2 justify-end">
      <div class="bg-accent text-white text-xs sm:text-sm px-4 py-2.5 rounded-2xl rounded-tr-sm max-w-[85%] shadow-sm font-medium leading-relaxed">
        ${escapeHtml(q)}
      </div>
    </div>
    <div class="flex items-start gap-2">
      <div class="w-7 h-7 rounded-full bg-accent-soft border border-border-subtle text-accent-soft-text flex items-center justify-center text-[11px] font-bold shrink-0 mt-0.5">LM</div>
      <div class="bg-bg-card border border-border-subtle text-text-secondary text-xs px-3.5 py-2.5 rounded-2xl rounded-tl-sm flex items-center gap-2">
        <div class="w-3.5 h-3.5 border-2 border-accent border-t-transparent rounded-full animate-spin"></div>
        <span>Searching FTS5 evidence chunks & synthesizing answer...</span>
      </div>
    </div>
  `;
  qaMessagesList.appendChild(tempMsg);
  qaMessagesList.scrollTop = qaMessagesList.scrollHeight;
  inputQaQuery.value = '';

  const activeLessonId = currentLessonId || (activeAllocation ? activeAllocation.lesson_id : null);
  const targetLessonId = qaScope === 'lesson' ? (activeLessonId || null) : null;

  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/qa`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: q,
        lesson_id: targetLessonId
      }),
    });
    const data = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/qa`, res.status, Math.round(performance.now() - t0), data);
    await loadQAHistory(currentCourseId);
  } catch (err) {
    Logger.error('Grounded Q&A failed', err);
    alert('Failed to get answer: ' + err.message);
  } finally {
    qaBtnText.textContent = 'Ask';
    qaSpinner.classList.add('hidden');
    btnSubmitQa.disabled = false;
  }
}

// Highlight-to-Explain System
let selectedExplainText = '';

function initHighlightToExplain() {
  if (!floatingExplainPill) return;

  document.addEventListener('mouseup', handleHighlightSelection);
  document.addEventListener('keyup', (e) => {
    if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Shift'].includes(e.key)) {
      handleHighlightSelection();
    }
  });

  document.addEventListener('mousedown', (e) => {
    if (floatingExplainPill && !floatingExplainPill.contains(e.target)) {
      floatingExplainPill.classList.add('hidden');
    }
  });

  document.addEventListener('scroll', () => {
    if (floatingExplainPill && !floatingExplainPill.classList.contains('hidden')) {
      floatingExplainPill.classList.add('hidden');
    }
  }, true);

  floatingExplainPill.addEventListener('click', () => {
    if (!selectedExplainText) return;
    switchNotesTab('qa');
    if (inputQaQuery) {
      inputQaQuery.value = `Explain this: "${selectedExplainText}"`;
      inputQaQuery.focus();
      const len = inputQaQuery.value.length;
      inputQaQuery.setSelectionRange(len, len);
    }
    floatingExplainPill.classList.add('hidden');
  });
}

function handleHighlightSelection() {
  if (!floatingExplainPill) return;
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed) {
    floatingExplainPill.classList.add('hidden');
    return;
  }

  const text = selection.toString().trim();
  if (text.length < 10) {
    floatingExplainPill.classList.add('hidden');
    return;
  }

  selectedExplainText = text;
  try {
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
      floatingExplainPill.classList.add('hidden');
      return;
    }

    const pillTop = Math.max(10, rect.top - 42);
    const pillLeft = Math.max(10, Math.min(window.innerWidth - 170, rect.left + (rect.width / 2) - 75));

    floatingExplainPill.style.top = `${pillTop}px`;
    floatingExplainPill.style.left = `${pillLeft}px`;
    floatingExplainPill.classList.remove('hidden');
  } catch (e) {
    floatingExplainPill.classList.add('hidden');
  }
}

// ==========================================
// QUIZ & MASTERY LOOP FUNCTIONS (M4)
// ==========================================
let currentQuiz = null;
let quizStartTime = null;

async function checkOrCreateLessonQuiz(lessonId) {
  if (!currentCourseId || !lessonId) return;
  quizTitleHeading.textContent = `Lesson Quiz: ${activeAllocation ? activeAllocation.lesson_title : 'Active Lesson'}`;
  quizResultsBanner.classList.add('hidden');

  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/quizzes?lesson_id=${lessonId}`);
    if (res.ok) {
      const quizzes = await res.json();
      Logger.api('GET', `/api/courses/${currentCourseId}/quizzes?lesson_id=${lessonId}`, res.status, Math.round(performance.now() - t0), quizzes);
      if (quizzes.length > 0) {
        renderQuiz(quizzes[0]);
        return;
      }
    }
  } catch (err) {
    Logger.error('Failed to check existing quiz', err);
  }

  // Not created yet -> show prompt
  quizQuestionsList.innerHTML = `
    <div class="text-center py-8 text-slate-500 text-xs">
      <svg class="w-10 h-10 mx-auto mb-2 text-amber-500/80" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>
      <p class="font-bold text-slate-300 mb-1">Citation Quiz Ready</p>
      <p class="mb-4">Generate 3 to 10 questions strictly cited from this lesson's transcript chunks.</p>
      <button type="button" onclick="handleGenerateLessonQuiz(5)" class="px-4 py-2 rounded-xl bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white font-bold text-xs shadow-md transition active:scale-95">Generate 5-Question Quiz</button>
    </div>
  `;
  quizSubmitBar.classList.add('hidden');
}

window.handleGenerateLessonQuiz = async function(count = 5) {
  if (!currentCourseId || !activeAllocation) {
    alert('Select an active lesson from the schedule first.');
    return;
  }
  btnGenerateLessonQuiz.disabled = true;
  quizQuestionsList.innerHTML = `
    <div class="flex items-center justify-center gap-2 py-12 text-slate-400 text-xs">
      <div class="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
      <span>Extracting grounded definitions & facts from transcripts...</span>
    </div>
  `;

  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/quizzes/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lesson_id: activeAllocation.lesson_id,
        quiz_type: 'lesson',
        question_count: count,
      }),
    });
    const quizData = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/quizzes/generate`, res.status, Math.round(performance.now() - t0), quizData);
    if (!res.ok) throw new Error(quizData.detail || 'Quiz generation failed');
    renderQuiz(quizData);
  } catch (err) {
    Logger.error('Quiz generation failed', err);
    quizQuestionsList.innerHTML = `<div class="p-4 text-xs text-red-400 bg-red-950/40 rounded-xl border border-red-800">Quiz generation failed: ${escapeHtml(err.message)}</div>`;
  } finally {
    btnGenerateLessonQuiz.disabled = false;
  }
};

function renderQuiz(quiz) {
  currentQuiz = quiz;
  quizStartTime = Date.now();
  quizResultsBanner.classList.add('hidden');

  if (quiz.score !== null && quiz.score !== undefined) {
    showQuizScoreBanner(quiz);
  } else {
    quizMasteryBadge.classList.add('hidden');
  }

  const html = quiz.questions.map((q, idx) => {
    const isCompleted = quiz.score !== null && quiz.score !== undefined;
    const isShortAnswer = q.question_type === 'short_answer';
    const evalItem = (quiz.short_answer_evaluations || []).find(e => e.question_id === q.id);

    return `
      <div class="p-3.5 bg-bg-card border border-border-subtle rounded-xl border border-slate-800 space-y-2.5">
        <div class="flex items-start justify-between gap-2">
          <div class="flex items-center gap-2 flex-wrap">
            <span class="w-5 h-5 rounded-full bg-bg-sidebar text-slate-300 text-[10px] font-bold flex items-center justify-center font-mono">${idx + 1}</span>
            <span class="text-xs font-semibold text-white leading-relaxed">${escapeHtml(q.question)}</span>
            ${isShortAnswer ? `
              <span class="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 shrink-0">
                Section B &bull; 5 Marks Subjective
              </span>
            ` : ''}
          </div>
          <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-accent-soft text-accent-soft-text border border-border-subtle shrink-0">
            [${escapeHtml(q.chunk_id)}]
          </span>
        </div>

        <!-- Cited quote evidence preview -->
        <div class="px-2.5 py-1.5 rounded-lg bg-bg-canvas/80 border border-slate-800/80 text-[11px] text-slate-400 italic">
          &ldquo;${escapeHtml(q.quote)}&rdquo;
        </div>

        ${isShortAnswer ? `
          <!-- 5-Mark Subjective Rubric & Answer Box -->
          <div class="px-2.5 py-2 rounded-lg bg-bg-canvas/90 border border-slate-800/90 text-[11px] text-slate-400 space-y-1">
            <span class="font-semibold text-slate-300">Exam Rubric (Max 5.0 Marks):</span>
            <ul class="list-disc list-inside space-y-0.5 text-[10.5px]">
              ${(q.rubric || [
                "Definition & Conceptual Core (2.0 Marks): Clear definition, intuition, and formal role.",
                "Technical Mechanism & Steps (2.0 Marks): Detailed explanation of working principle, properties, or operations.",
                "Practical Example & Application (1.0 Mark): Concrete scenario, code snippet, or engineering use-case."
              ]).map(r => `<li>${escapeHtml(r)}</li>`).join('')}
            </ul>
          </div>

          <div class="pt-1">
            <textarea name="quiz_sa_${q.id}" class="w-full h-24 p-2.5 rounded-lg bg-bg-card border border-border-subtle border border-slate-700/60 text-slate-200 text-xs focus:ring-1 focus:ring-amber-500 resize-y placeholder:text-slate-500" placeholder="Write your structured 5-mark answer covering: 1) Definition & intuition, 2) Technical mechanism & steps, 3) Practical example..." ${isCompleted ? 'disabled' : ''}>${escapeHtml(q.user_answer || '')}</textarea>
          </div>

          ${evalItem ? `
            <div class="mt-2 p-2.5 rounded-lg bg-bg-canvas border border-amber-800/60 text-xs space-y-1.5">
              <div class="flex items-center justify-between font-semibold text-amber-300">
                <span>Awarded: ${evalItem.marks_awarded} / ${q.max_marks || 5.0} Marks</span>
                <span class="text-[10px] font-mono text-slate-400">Def: ${evalItem.breakdown?.definition ?? 0} | Mech: ${evalItem.breakdown?.mechanism ?? 0} | Ex: ${evalItem.breakdown?.example ?? 0}</span>
              </div>
              <div class="text-[11px] text-slate-300 leading-relaxed">${escapeHtml(evalItem.feedback || '')}</div>
              ${q.sample_solution ? `
                <div class="mt-1 pt-1.5 border-t border-slate-800/80 text-[10.5px] text-slate-400">
                  <span class="font-semibold text-slate-300">Model Sample Solution:</span>
                  <div class="whitespace-pre-line mt-0.5 font-mono text-[10px] text-slate-300/90">${escapeHtml(q.sample_solution)}</div>
                </div>
              ` : ''}
            </div>
          ` : ''}
        ` : `
          <!-- Multiple Choice Options -->
          <div class="space-y-1.5 pt-1">
            ${(q.options || []).map((opt, optIdx) => {
              let optClass = 'bg-bg-card border border-border-subtle hover:bg-bg-sidebar border-slate-700/60 text-slate-300';
              const isUserChoice = (q.user_answer !== undefined && q.user_answer !== null && parseInt(q.user_answer, 10) === optIdx);
              if (isCompleted) {
                if (optIdx === q.correct_index) {
                  optClass = 'bg-emerald-950/70 border-emerald-700 text-emerald-200 font-semibold';
                } else if (isUserChoice) {
                  optClass = 'bg-rose-950/70 border-rose-700 text-rose-200 font-semibold';
                }
              }
              return `
                <label class="quiz-option-label flex items-center gap-2 p-2.5 rounded-lg border text-xs cursor-pointer transition ${optClass}">
                  <input type="radio" name="quiz_q_${q.id}" value="${optIdx}" ${isUserChoice ? 'checked' : ''} ${isCompleted ? 'disabled' : ''} class="quiz-option-input text-amber-500 focus:ring-0">
                  <span class="leading-relaxed">${escapeHtml(opt)}</span>
                </label>
              `;
            }).join('')}
          </div>

          ${isCompleted ? `
            <div class="mt-2 pt-2 border-t border-slate-800/80 flex items-center justify-between flex-wrap gap-2">
              <div class="text-[11px] text-slate-400 font-mono flex-1 min-w-[200px]">
                💡 ${escapeHtml(q.explanation)}
              </div>
              <button type="button" onclick="window.seekToSeconds(${q.timestamp_sec !== undefined && q.timestamp_sec !== null ? q.timestamp_sec : (q.start_sec || 0)})" class="replay-explanation-btn inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-accent-soft text-accent-soft-text hover:bg-blue-200 dark:hover:bg-blue-900 border border-border-subtle font-mono text-[11px] font-semibold cursor-pointer transition active:scale-95 shadow-sm shrink-0" title="Replay Explanation in video">
                <span>▶</span> Replay Explanation [${q.timestamp_str || (q.timestamp_sec ? formatDurationSec(q.timestamp_sec) : '00:00')}]
              </button>
            </div>
          ` : ''}
        `}
      </div>
    `;
  }).join('');

  quizQuestionsList.innerHTML = html;
  if (quiz.score === null || quiz.score === undefined) {
    quizSubmitBar.classList.remove('hidden');
  } else {
    quizSubmitBar.classList.add('hidden');
  }
}

function showQuizScoreBanner(data) {
  quizResultsBanner.classList.remove('hidden');
  const score = data.score;
  const passed = data.passed || score >= 80;
  const marksDetail = data.total_marks_possible ? ` (${data.total_marks_obtained ?? 0} / ${data.total_marks_possible} Marks)` : '';

  quizMasteryBadge.classList.remove('hidden');
  if (passed) {
    quizMasteryBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full font-mono bg-emerald-950 text-emerald-300 border border-emerald-800';
    quizMasteryBadge.textContent = '✨ MASTERED / TESTED OUT';
    quizResultsBanner.className = 'mb-4 p-3 rounded-xl border flex items-center justify-between text-xs bg-emerald-950/60 border-emerald-700 text-emerald-200';
    quizResultsBanner.innerHTML = `
      <div class="flex items-center gap-2">
        <svg class="w-4 h-4 text-emerald-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
        <div>
          <strong class="text-white text-sm">${score}% Score${marksDetail}</strong> &mdash; Concept Mastered!
          <span class="block text-[11px] text-emerald-300/80">Lesson marked Tested Out and freed from your remaining study schedule.</span>
        </div>
      </div>
    `;
  } else if (score < 60) {
    quizMasteryBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full font-mono bg-amber-950 text-amber-300 border border-amber-800';
    quizMasteryBadge.textContent = '⚠️ NEEDS REVIEW';
    quizResultsBanner.className = 'mb-4 p-3 rounded-xl border flex items-center justify-between text-xs bg-amber-950/60 border-amber-700 text-amber-200';
    quizResultsBanner.innerHTML = `
      <div class="flex items-center gap-2">
        <svg class="w-4 h-4 text-amber-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
        <div>
          <strong class="text-white text-sm">${score}% Score${marksDetail}</strong> &mdash; Review Recommended.
          <span class="block text-[11px] text-amber-300/80">Targeted FSRS flashcards generated for missed concepts. Drill them in the Flashcards tab!</span>
        </div>
      </div>
    `;
  } else {
    quizMasteryBadge.className = 'text-[10px] font-bold px-2 py-0.5 rounded-full font-mono bg-blue-950 text-blue-300 border border-blue-800';
    quizMasteryBadge.textContent = 'PASSED';
    quizResultsBanner.className = 'mb-4 p-3 rounded-xl border flex items-center justify-between text-xs bg-blue-950/60 border-blue-700 text-blue-200';
    quizResultsBanner.innerHTML = `
      <div><strong class="text-white text-sm">${score}% Score${marksDetail}</strong> &mdash; Solid progress! Score 80%+ to test out completely.</div>
    `;
  }
}

async function handleLessonQuizSubmit(e) {
  e.preventDefault();
  if (!currentQuiz) return;

  const answers = {};
  const short_answers = {};
  for (const q of currentQuiz.questions) {
    if (q.question_type === 'short_answer') {
      const ta = document.querySelector(`textarea[name="quiz_sa_${q.id}"]`);
      if (ta) {
        short_answers[q.id] = ta.value.trim();
        q.user_answer = ta.value.trim();
      }
    } else {
      const checked = document.querySelector(`input[name="quiz_q_${q.id}"]:checked`);
      if (checked) {
        answers[q.id] = parseInt(checked.value, 10);
        q.user_answer = parseInt(checked.value, 10);
      }
    }
  }

  const answeredCount = Object.keys(answers).length + Object.keys(short_answers).length;
  const timeTaken = quizStartTime ? Math.round((Date.now() - quizStartTime) / 1000) : 0;
  Logger.quiz('Submit Lesson Quiz', { quizId: currentQuiz.id, answers, short_answers, answeredCount, timeTaken });

  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/quizzes/${currentQuiz.id}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers, short_answers, time_taken_seconds: timeTaken }),
    });
    const result = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/quizzes/${currentQuiz.id}/submit`, res.status, Math.round(performance.now() - t0), result);

    if (!res.ok) throw new Error(result.detail || 'Submission failed');

    currentQuiz.score = result.score;
    currentQuiz.passed = result.passed;
    currentQuiz.short_answer_evaluations = result.short_answer_evaluations || [];
    currentQuiz.total_marks_obtained = result.total_marks_obtained;
    currentQuiz.total_marks_possible = result.total_marks_possible;
    renderQuiz(currentQuiz);

    // Feature 2: Automated Replanning on Quiz Drops ("Plan updated — Undo" banner)
    if (result.schedule_updated) {
      await loadSchedule(currentCourseId);
      if (result.diff_summary) {
        const diff = result.diff_summary;
        let diffMsg = `Plan updated — Undo: Finish ${diff.old_finish_date || '--'} → ${diff.new_finish_date || '--'}`;
        if (diff.dropped_deep_dive_count > 0) {
          diffMsg += ` • Dropped ${diff.dropped_deep_dive_count} deep-dive topics to compress schedule.`;
        }
        if (diff.deficit_message) {
          diffMsg += ` • ⚠️ ${diff.deficit_message}`;
        }
        diffText.textContent = diffMsg;
        diffBanner.classList.remove('hidden');
      }
    } else if (result.tested_out_lessons && result.tested_out_lessons.length > 0) {
      await loadSchedule(currentCourseId);
    }
    updateFlashcardCounts();
  } catch (err) {
    Logger.error('Quiz submission error', err);
    alert('Submission failed: ' + err.message);
  }
}

// ==========================================
// FSRS SPACED REPETITION FLASHCARDS (M4)
// ==========================================
let dueCards = [];
let activeCardIndex = 0;
let isCardFlipped = false;

async function loadFlashcards() {
  if (!currentCourseId) return;
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/flashcards/due`);
    if (res.ok) {
      dueCards = await res.json();
      Logger.api('GET', `/api/courses/${currentCourseId}/flashcards/due`, res.status, Math.round(performance.now() - t0), dueCards);
      activeCardIndex = 0;
      renderActiveCard();
    }
    updateFlashcardCounts();
  } catch (err) {
    Logger.error('Failed to load flashcards', err);
  }
}

async function updateFlashcardCounts() {
  if (!currentCourseId) return;
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/flashcards/counts`);
    if (res.ok) {
      const counts = await res.json();
      statFcTotal.textContent = counts.total;
      statFcDue.textContent = counts.due;
      statFcNew.textContent = counts.new;
      statFcLearning.textContent = counts.learning;
      statFcReview.textContent = counts.review;

      if (counts.due > 0) {
        badgeDueFlashcards.textContent = counts.due;
        badgeDueFlashcards.classList.remove('hidden');
      } else {
        badgeDueFlashcards.classList.add('hidden');
      }
    }
  } catch (err) {
    Logger.error('Failed to update flashcard counts', err);
  }
}

function renderActiveCard() {
  isCardFlipped = false;
  fsrsCardFront.classList.remove('hidden');
  fsrsCardBack.classList.add('hidden');
  fsrsRatingBar.classList.add('hidden');
  fsrsCardFlipper.classList.remove('rotate-y-180');

  if (!dueCards || dueCards.length === 0 || activeCardIndex >= dueCards.length) {
    fcEmptyState.classList.remove('hidden');
    fcActiveCardContainer.classList.add('hidden');
    return;
  }

  fcEmptyState.classList.add('hidden');
  fcActiveCardContainer.classList.remove('hidden');

  const card = dueCards[activeCardIndex];
  fsrsFrontText.textContent = card.front;
  fsrsBackText.textContent = card.back;

  if (card.source_quote) {
    fsrsQuoteBox.textContent = `Source Evidence: "${card.source_quote}"`;
    fsrsQuoteBox.classList.remove('hidden');
  } else {
    fsrsQuoteBox.classList.add('hidden');
  }

  if (card.intervals) {
    intervalAgain.textContent = card.intervals[1] || '1m';
    intervalHard.textContent = card.intervals[2] || '5m';
    intervalGood.textContent = card.intervals[3] || '10m';
    intervalEasy.textContent = card.intervals[4] || '7d';
  }
}

function flipActiveCard() {
  if (!dueCards || dueCards.length === 0 || activeCardIndex >= dueCards.length) return;
  isCardFlipped = !isCardFlipped;

  if (isCardFlipped) {
    fsrsCardFlipper.classList.add('rotate-y-180');
    setTimeout(() => {
      fsrsCardFront.classList.add('hidden');
      fsrsCardBack.classList.remove('hidden');
      fsrsRatingBar.classList.remove('hidden');
    }, 150);
  } else {
    fsrsCardFlipper.classList.remove('rotate-y-180');
    setTimeout(() => {
      fsrsCardBack.classList.add('hidden');
      fsrsCardFront.classList.remove('hidden');
      fsrsRatingBar.classList.add('hidden');
    }, 150);
  }
  Logger.fsrs('Card Flipped', { isCardFlipped, cardId: dueCards[activeCardIndex].id });
}

async function submitCardRating(rating) {
  if (!dueCards || activeCardIndex >= dueCards.length) return;
  const card = dueCards[activeCardIndex];

  Logger.fsrs('Submit Rating', { cardId: card.id, rating });
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/flashcards/${card.id}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    });
    const reviewData = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/flashcards/${card.id}/review`, res.status, Math.round(performance.now() - t0), reviewData);

    activeCardIndex++;
    renderActiveCard();
    updateFlashcardCounts();
  } catch (err) {
    Logger.error('Flashcard review failed', err);
    alert('Review failed: ' + err.message);
  }
}

function handleFlashcardKeydown(e) {
  if (paneFlashcardsFsrs.classList.contains('hidden')) return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

  if (e.code === 'Space') {
    e.preventDefault();
    flipActiveCard();
  } else if (isCardFlipped) {
    if (e.key === '1') { e.preventDefault(); submitCardRating(1); }
    else if (e.key === '2') { e.preventDefault(); submitCardRating(2); }
    else if (e.key === '3') { e.preventDefault(); submitCardRating(3); }
    else if (e.key === '4') { e.preventDefault(); submitCardRating(4); }
  }
}

async function handleCreateCardManual(e) {
  e.preventDefault();
  if (!currentCourseId) return;

  const front = inputCardFront.value.trim();
  const back = inputCardBack.value.trim();
  const quote = inputCardQuote.value.trim() || null;
  if (!front || !back) return;

  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/flashcards`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        front,
        back,
        lesson_id: activeAllocation ? activeAllocation.lesson_id : null,
        source_quote: quote,
      }),
    });
    const newCard = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/flashcards`, res.status, Math.round(performance.now() - t0), newCard);
    addCardModal.classList.add('hidden');
    inputCardFront.value = '';
    inputCardBack.value = '';
    inputCardQuote.value = '';
    loadFlashcards();
  } catch (err) {
    Logger.error('Failed to create flashcard', err);
    alert('Failed to save flashcard: ' + err.message);
  }
}

// ==========================================
// DIAGNOSTIC PRE-TEST & TIMED MOCK EXAM (M4)
// ==========================================
let diagnosticQuiz = null;
let diagnosticTimerInterval = null;
let diagnosticSecondsLeft = 180; // 3-minute timed test

function updateDiagnosticTimerBadge() {
  const badge = document.getElementById('diagnostic-timer-badge');
  if (!badge) return;
  const m = Math.floor(diagnosticSecondsLeft / 60);
  const s = diagnosticSecondsLeft % 60;
  badge.textContent = `⏱️ ${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  if (diagnosticSecondsLeft <= 30) {
    badge.className = 'text-xs font-mono font-bold px-2.5 py-0.5 rounded-full bg-red-500/10 text-red-600 dark:text-red-400 border border-red-400/40 animate-pulse';
  } else {
    badge.className = 'text-xs font-mono font-bold px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-400/40';
  }
}

async function openDiagnosticPreTest() {
  if (!currentCourseId) {
    showToast('Please select or create a course first.', 'warning');
    return;
  }
  diagnosticModal.classList.remove('hidden');
  diagnosticSecondsLeft = 180;
  updateDiagnosticTimerBadge();

  if (diagnosticTimerInterval) clearInterval(diagnosticTimerInterval);

  diagnosticContentContainer.innerHTML = `
    <div class="flex items-center justify-center gap-3 py-16 text-slate-500 dark:text-slate-400 text-xs">
      <div class="w-5 h-5 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
      <span class="font-medium">Synthesizing 5 high-yield diagnostic questions across your syllabus...</span>
    </div>
  `;

  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/quizzes/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        quiz_type: 'diagnostic',
        question_count: 5,
        title: '3-Minute Course Diagnostic Pre-Test',
      }),
    });
    diagnosticQuiz = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/quizzes/generate (diagnostic)`, res.status, Math.round(performance.now() - t0), diagnosticQuiz);

    if (!diagnosticQuiz.questions || diagnosticQuiz.questions.length === 0) {
      diagnosticContentContainer.innerHTML = `
        <div class="p-6 text-center text-xs text-slate-500">
          No syllabus questions could be generated. Ensure your course has approved lessons or transcripts.
        </div>
      `;
      return;
    }

    diagnosticContentContainer.innerHTML = diagnosticQuiz.questions.map((q, idx) => `
      <div class="p-4 bg-bg-card rounded-2xl border border-border-subtle space-y-3 transition hover:border-accent">
        <div class="flex items-start justify-between gap-3">
          <span class="text-xs font-bold text-text-primary leading-relaxed">${idx + 1}. ${escapeHtml(q.question)}</span>
          <span class="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-accent-soft text-accent-soft-text border border-border-subtle shrink-0 max-w-[220px] truncate" title="${escapeHtml(q.topic_name || ('Topic ' + (idx + 1)))}">Topic ${idx + 1}: ${escapeHtml(q.topic_name || ('Topic ' + (idx + 1)))}</span>
        </div>
        <div class="space-y-2 pt-1">
          ${q.options.map((opt, optIdx) => `
            <label class="diagnostic-option-card flex items-center gap-3 p-3 rounded-xl border border-border-subtle bg-bg-canvas text-xs text-text-primary hover:border-accent cursor-pointer transition active:scale-[0.99] select-none" onclick="window.selectDiagOption(this)">
              <input type="radio" name="diag_q_${q.id}" value="${optIdx}" class="text-accent focus:ring-0 cursor-pointer">
              <span class="flex-1">${escapeHtml(opt)}</span>
            </label>
          `).join('')}
        </div>
      </div>
    `).join('');

    // Start 3-minute countdown timer
    diagnosticTimerInterval = setInterval(() => {
      diagnosticSecondsLeft--;
      updateDiagnosticTimerBadge();
      if (diagnosticSecondsLeft <= 0) {
        clearInterval(diagnosticTimerInterval);
        showToast('⏱️ Time expired! Submitting your diagnostic answers...', 'info');
        handleSubmitDiagnostic();
      }
    }, 1000);

  } catch (err) {
    Logger.error('Diagnostic generation failed', err);
    diagnosticContentContainer.innerHTML = `<div class="p-6 text-xs text-red-500 font-medium">Failed to load diagnostic test: ${escapeHtml(err.message)}</div>`;
  }
}

window.selectDiagOption = function(labelEl) {
  const container = labelEl.closest('.space-y-2');
  if (container) {
    container.querySelectorAll('.diagnostic-option-card').forEach(c => {
      c.classList.remove('ring-2', 'ring-amber-500', 'border-amber-500', 'bg-amber-50/50', 'dark:bg-amber-950/30');
    });
  }
  labelEl.classList.add('ring-2', 'ring-amber-500', 'border-amber-500', 'bg-amber-50/50', 'dark:bg-amber-950/30');
};

async function handleSubmitDiagnostic() {
  if (!diagnosticQuiz) return;
  if (diagnosticTimerInterval) clearInterval(diagnosticTimerInterval);

  const answers = {};
  for (const q of diagnosticQuiz.questions) {
    const checked = document.querySelector(`input[name="diag_q_${q.id}"]:checked`);
    if (checked) answers[q.id] = parseInt(checked.value, 10);
  }

  const timeSpent = 180 - diagnosticSecondsLeft;
  diagnosticContentContainer.innerHTML = `
    <div class="flex items-center justify-center gap-3 py-16 text-slate-500 text-xs">
      <div class="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin"></div>
      <span class="font-medium">Evaluating topic mastery and optimizing your schedule...</span>
    </div>
  `;

  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/quizzes/${diagnosticQuiz.id}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers, time_taken_seconds: Math.max(10, timeSpent) }),
    });
    const result = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/quizzes/${diagnosticQuiz.id}/submit`, res.status, Math.round(performance.now() - t0), result);

    const testedOutCount = (result.tested_out_lessons || []).length;
    const testedOutLessons = result.tested_out_lessons || [];
    const testedOutTitles = (diagnosticQuiz.questions || [])
      .filter(q => testedOutLessons.includes(q.lesson_id))
      .map(q => q.topic_name)
      .filter(Boolean);

    // Celebratory Results Screen
    diagnosticContentContainer.innerHTML = `
      <div class="py-8 px-4 text-center space-y-4">
        <div class="w-16 h-16 mx-auto rounded-full bg-gradient-to-tr from-accent to-emerald-500 flex items-center justify-center text-white text-2xl shadow-lg shadow-emerald-500/20">
          ✓
        </div>
        <div>
          <h3 class="text-lg font-bold text-text-primary">Diagnostic Assessment Complete!</h3>
          <p class="text-xs text-text-secondary mt-1">Score: <strong class="text-accent text-sm font-mono">${result.score}%</strong> (${result.correct_count} of ${result.total_questions} topics answered correctly)</p>
        </div>
        <div class="p-4 rounded-2xl bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800/80 max-w-md mx-auto text-xs text-emerald-800 dark:text-emerald-300">
          <div class="font-bold text-sm mb-1">🎉 ${testedOutCount} Topics Mastered & Tested Out!</div>
          <p>These lessons have been removed from your active study plan, shrinking your schedule and saving study time!</p>
          ${testedOutTitles.length > 0 ? `
            <div class="mt-2.5 pt-2 border-t border-emerald-200 dark:border-emerald-800 text-left">
              <div class="font-semibold text-[11px] mb-1 text-emerald-900 dark:text-emerald-200">Tested-Out Syllabus Topics:</div>
              <ul class="space-y-1 text-[11px]">
                ${testedOutTitles.map(t => `<li class="flex items-center gap-1.5"><span class="text-emerald-600 dark:text-emerald-400 font-bold">✓</span><span>${escapeHtml(t)}</span></li>`).join('')}
              </ul>
            </div>
          ` : ''}
        </div>
        <div class="pt-2">
          <button id="btn-finish-diagnostic" class="bg-accent hover:bg-blue-600 text-white font-bold text-xs px-6 py-2.5 rounded-xl shadow-md transition active:scale-95">
            Return to Updated Schedule
          </button>
        </div>
      </div>
    `;

    document.getElementById('btn-finish-diagnostic')?.addEventListener('click', () => {
      diagnosticModal.classList.add('hidden');
    });

    showToast(`🎉 Diagnostic complete! ${testedOutCount} topics tested out.`, 'success');
    await loadSchedule(currentCourseId);

  } catch (err) {
    Logger.error('Diagnostic submission failed', err);
    showToast(`Submission failed: ${err.message}`, 'error');
  }
}

// --- Timed Mock Exam ---
let mockExamQuiz = null;
let mockExamTimerInterval = null;
let mockExamSecondsLeft = 900;

async function openMockExam() {
  if (!currentCourseId) {
    alert('Please select or create a course first.');
    return;
  }
  mockExamModal.classList.remove('hidden');
  mockExamSecondsLeft = 900;
  updateMockExamTimerDisplay();
  startMockExamTimer();

  mockExamContent.innerHTML = `
    <div class="flex items-center justify-center gap-2 py-12 text-slate-400 text-xs">
      <div class="w-4 h-4 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin"></div>
      <span>Assembling timed full-course mock exam from indexed chunks...</span>
    </div>
  `;

  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/quizzes/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        quiz_type: 'mock_exam',
        question_count: 10,
        title: 'Course Mock Exam',
      }),
    });
    mockExamQuiz = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/quizzes/generate (mock_exam)`, res.status, Math.round(performance.now() - t0), mockExamQuiz);

    mockTotalCount.textContent = mockExamQuiz.questions.length;
    mockAnsweredCount.textContent = '0';

    mockExamContent.innerHTML = mockExamQuiz.questions.map((q, idx) => `
      <div class="p-3.5 bg-bg-card border border-border-subtle rounded-xl border border-slate-700/80 space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-white">${idx + 1}. ${escapeHtml(q.question)}</span>
          <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">[${escapeHtml(q.chunk_id)}]</span>
        </div>
        <div class="space-y-1.5 pt-1">
          ${q.options.map((opt, optIdx) => `
            <label class="diagnostic-option flex items-center gap-2 p-2 rounded-lg border border-slate-700 text-xs text-slate-300 hover:bg-bg-sidebar cursor-pointer">
              <input type="radio" name="mock_q_${q.id}" value="${optIdx}" onchange="updateMockAnsweredCount()" class="text-emerald-500 focus:ring-0">
              <span>${escapeHtml(opt)}</span>
            </label>
          `).join('')}
        </div>
      </div>
    `).join('');
  } catch (err) {
    Logger.error('Mock exam generation failed', err);
    mockExamContent.innerHTML = `<div class="p-4 text-xs text-red-400">Failed to load mock exam: ${escapeHtml(err.message)}</div>`;
  }
}

function startMockExamTimer() {
  if (mockExamTimerInterval) clearInterval(mockExamTimerInterval);
  mockExamTimerInterval = setInterval(() => {
    mockExamSecondsLeft--;
    updateMockExamTimerDisplay();
    if (mockExamSecondsLeft <= 0) {
      clearInterval(mockExamTimerInterval);
      alert("Time is up! Submitting your mock exam automatically.");
      handleSubmitMockExam();
    }
  }, 1000);
}

function updateMockExamTimerDisplay() {
  const mins = Math.floor(mockExamSecondsLeft / 60);
  const secs = mockExamSecondsLeft % 60;
  mockExamTimer.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  if (mockExamSecondsLeft < 120) {
    mockExamTimer.className = 'text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-red-950 text-red-300 border border-red-800 animate-pulse';
  } else {
    mockExamTimer.className = 'text-xs font-mono font-bold px-2.5 py-1 rounded-lg bg-emerald-950 text-emerald-300 border border-emerald-800';
  }
}

window.updateMockAnsweredCount = function() {
  if (!mockExamQuiz) return;
  let count = 0;
  for (const q of mockExamQuiz.questions) {
    if (document.querySelector(`input[name="mock_q_${q.id}"]:checked`)) count++;
  }
  mockAnsweredCount.textContent = count;
};

function closeMockExam() {
  if (mockExamTimerInterval) clearInterval(mockExamTimerInterval);
  mockExamModal.classList.add('hidden');
}

async function handleSubmitMockExam() {
  if (!mockExamQuiz) return;
  if (mockExamTimerInterval) clearInterval(mockExamTimerInterval);

  const answers = {};
  for (const q of mockExamQuiz.questions) {
    const checked = document.querySelector(`input[name="mock_q_${q.id}"]:checked`);
    if (checked) answers[q.id] = parseInt(checked.value, 10);
  }

  const timeTaken = 900 - mockExamSecondsLeft;
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/quizzes/${mockExamQuiz.id}/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers, time_taken_seconds: timeTaken }),
    });
    const result = await res.json();
    Logger.api('POST', `/api/courses/${currentCourseId}/quizzes/${mockExamQuiz.id}/submit (mock_exam)`, res.status, Math.round(performance.now() - t0), result);

    alert(`Mock Exam Complete!\nScore: ${result.score}% (${result.correct_count}/${result.total_questions})\nMissed: ${result.missed_count}\nFlashcards created: ${result.flashcards_created || 0}`);
    closeMockExam();
    updateFlashcardCounts();
  } catch (err) {
    Logger.error('Mock exam submission failed', err);
    alert('Submission failed: ' + err.message);
  }
}

// ==========================================
// PYODIDE IN-BROWSER WEB WORKER (M5)
// ==========================================
let pyodideWorker = null;
let isWorkerReady = false;

function initPyodide() {
  if (pyodideWorker) return;
  pyodideStatusPill.textContent = 'Initializing Pyodide...';
  pyodideWorker = new Worker('/static/js/pyodide_worker.js');
  pyodideWorker.postMessage({ type: 'init' });

  pyodideWorker.onmessage = function(e) {
    const msg = e.data;
    if (msg.type === 'ready') {
      isWorkerReady = true;
      pyodideStatusPill.textContent = 'Worker: Ready';
      pyodideStatusPill.className = 'text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800';
      Logger.api('WORKER', 'pyodide_worker.js', 200, 0, 'Pyodide ready in client thread');
    } else if (msg.type === 'result') {
      pyodideExecTime.textContent = `${msg.executionMs} ms`;
      btnRunPyodide.disabled = false;
      btnRunPyodide.innerHTML = `
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
        <span>Run Python</span>
      `;

      let output = '';
      if (msg.stdout) output += msg.stdout + '\n';
      if (msg.result) output += `=> ${msg.result}\n`;
      if (msg.stderr) output += `[stderr]: ${msg.stderr}\n`;
      if (!msg.success && msg.error) {
        output += `[Error]: ${msg.error}\n`;
      }
      pyodideOutput.textContent = output.trim() || '[Execution finished with no output]';
      if (!msg.success) {
        pyodideOutput.className = 'flex-1 overflow-y-auto text-red-400 whitespace-pre-wrap';
      } else {
        pyodideOutput.className = 'flex-1 overflow-y-auto text-slate-200 whitespace-pre-wrap';
      }
    } else if (msg.type === 'error') {
      pyodideStatusPill.textContent = 'Worker: Error';
      pyodideStatusPill.className = 'text-[10px] font-mono px-2 py-0.5 rounded-full bg-red-950 text-red-300 border border-red-800';
      pyodideOutput.textContent = msg.error;
    }
  };
}

function runPythonCode() {
  const code = pyodideCodeInput.value;
  if (!code.trim()) return;

  if (!pyodideWorker) {
    initPyodide();
  }

  btnRunPyodide.disabled = true;
  btnRunPyodide.innerHTML = `
    <div class="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
    <span>Executing...</span>
  `;
  pyodideOutput.textContent = 'Executing locally inside in-browser Web Worker...';
  pyodideWorker.postMessage({ type: 'run', code, id: Date.now() });
}

function stopPythonWorker() {
  if (pyodideWorker) {
    pyodideWorker.terminate();
    pyodideWorker = null;
    isWorkerReady = false;
  }
  btnRunPyodide.disabled = false;
  btnRunPyodide.innerHTML = `
    <svg class="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
    <span>Run Python</span>
  `;
  pyodideOutput.textContent = '[Execution stopped: Worker killed by user within 2s. Browser UI remained 100% responsive.]';
  pyodideOutput.className = 'flex-1 overflow-y-auto text-amber-400 whitespace-pre-wrap';
  pyodideStatusPill.textContent = 'Worker: Terminated';
  pyodideStatusPill.className = 'text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-950 text-amber-300 border border-amber-800';
  Logger.api('WORKER', 'pyodide_worker.js', 200, 0, 'Worker terminated by user stop signal');
}

function handlePyodidePresetChange(e) {
  const val = e.target.value;
  if (val === 'dfa') {
    pyodideCodeInput.value = `# DFA Simulator in Python
class DFA:
    def __init__(self):
        self.state = 'q0'
    def transition(self, char):
        if self.state == 'q0':
            self.state = 'q1' if char == '0' else 'q0'
        elif self.state == 'q1':
            self.state = 'q2' if char == '1' else 'q1'
        elif self.state == 'q2':
            self.state = 'q1' if char == '0' else 'q0'
    def accepts(self, s):
        self.state = 'q0'
        for c in s:
            self.transition(c)
        return self.state == 'q2'

dfa = DFA()
for s in ['101', '0101', '100', '11101', '00']:
    print(f"String '{s}' accepted? {dfa.accepts(s)}")
`;
  } else if (val === 'math') {
    pyodideCodeInput.value = `# Exam Formula Calculator
import math

# Pacing calculation
target_days = 20
total_hours = 18.5
speed = 1.25

effective_hours = total_hours / speed
daily_hours = effective_hours / target_days
daily_mins = daily_hours * 60

print(f"Total raw: {total_hours}h")
print(f"At {speed}x speed: {effective_hours:.2f}h")
print(f"Required study time per day: {daily_mins:.1f} minutes")
`;
  } else if (val === 'regex') {
    pyodideCodeInput.value = `# Regex Pattern Tester
import re

pattern = r'^(0|1(01*0)*1)*$'
test_cases = ['0', '11', '1001', '10101', '10']

for tc in test_cases:
    match = bool(re.match(pattern, tc))
    print(f"Binary string '{tc}' matches divisible-by-3? {match}")
`;
  }
}

// ==========================================
// STORAGE VACUUM, BACKUP & EXPORT (M5)
// ==========================================
async function handleVacuumDb() {
  btnVacuumDb.disabled = true;
  const t0 = performance.now();
  try {
    const res = await fetch('/api/settings/vacuum', { method: 'POST' });
    const data = await res.json();
    Logger.api('POST', '/api/settings/vacuum', res.status, Math.round(performance.now() - t0), data);
    alert(data.message || 'SQLite database vacuumed successfully.');
    loadSettings();
  } catch (err) {
    Logger.error('Vacuum failed', err);
    alert('Vacuum failed: ' + err.message);
  } finally {
    btnVacuumDb.disabled = false;
  }
}

function handleDownloadDbBackup() {
  Logger.api('GET', '/api/settings/backup', 200, 0, 'Downloading SQLite backup');
  window.open('/api/settings/backup', '_blank', 'noopener,noreferrer');
}

async function handleExportCourseBundle() {
  if (!currentCourseId) {
    alert('Select a course first to export its study bundle.');
    return;
  }
  btnExportBundle.disabled = true;
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/export`);
    if (!res.ok) throw new Error('Export failed with status ' + res.status);
    const bundle = await res.json();
    Logger.api('GET', `/api/courses/${currentCourseId}/export`, res.status, Math.round(performance.now() - t0), bundle);

    // Trigger download of JSON bundle
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${bundle.course.title.replace(/[^a-zA-Z0-9_-]/g, '_')}_study_bundle.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    Logger.error('Export failed', err);
    alert('Export failed: ' + err.message);
  } finally {
    btnExportBundle.disabled = false;
  }
}

// --- Global Debug & Inspection Object for F12 Console ---
window.learnLMS = {
  getCurrentCourse: () => currentCourse,
  getCurrentSchedule: () => currentSchedule,
  getCurrentLessons: () => currentLessons,
  getActiveAllocation: () => activeAllocation,
  setStrategy: setStrategy,
  setRevisionBuffer: setRevisionBuffer,
  toggleTheme: toggleTheme,
  filterLessons: handleFilterLessons,
  loadCramSheet: loadCramSheet,
  loadLessonPyqs: loadLessonPyqs,
  logger: Logger,
};


// Phase 1 fix: wire collapsed rail settings button
document.addEventListener('DOMContentLoaded', () => {
    const collapsedSettingsBtn = document.getElementById('btn-collapsed-settings');
    if (collapsedSettingsBtn) {
        collapsedSettingsBtn.addEventListener('click', () => {
            const mainSettingsBtn = document.getElementById('btn-settings');
            if (mainSettingsBtn) mainSettingsBtn.click();
        });
    }
});

// =========================================================================
// Phase 4: Command Palette (Cmd+K / Ctrl+K) & URL Hash Deep Linking
// =========================================================================
function updateUrlHash(courseId, lessonId) {
    try {
        if (!courseId) return;
        const hash = lessonId ? `#/course/${encodeURIComponent(courseId)}/lesson/${encodeURIComponent(lessonId)}` : `#/course/${encodeURIComponent(courseId)}`;
        if (window.location.hash !== hash) {
            window.history.replaceState(null, '', hash);
        }
    } catch (_) {}
}

function getInitialHashTarget() {
    const m = (window.location.hash || '').match(/^#\/course\/([^/]+)(?:\/lesson\/([^/]+))?/);
    if (!m) return null;
    return { courseId: decodeURIComponent(m[1]), lessonId: m[2] ? decodeURIComponent(m[2]) : null };
}

function initCommandPalette() {
    const modal = document.getElementById('command-palette-modal');
    const input = document.getElementById('command-palette-input');
    const list = document.getElementById('command-palette-list');
    if (!modal || !input || !list) return;

    const closePalette = () => {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    };

    const getItems = () => {
        const items = [
            { label: 'New Learning Goal / Course', type: 'Action', run: () => document.getElementById('btn-new-course')?.click() },
            { label: 'Open Cram Sheet', type: 'Action', run: () => document.getElementById('btn-open-cram-sheet')?.click() },
            { label: 'Start Mock Exam', type: 'Action', run: () => document.getElementById('btn-open-mock-exam')?.click() },
            { label: 'Open Settings', type: 'Action', run: () => document.getElementById('btn-settings')?.click() },
            { label: 'Toggle Light / Dark Theme', type: 'Action', run: () => document.getElementById('btn-theme-toggle')?.click() },
            { label: 'Replan Schedule Now', type: 'Action', run: () => document.getElementById('btn-replan-now')?.click() },
        ];
        if (Array.isArray(currentLessons)) {
            currentLessons.slice(0, 60).forEach((l) => {
                items.push({
                    label: l.title || 'Untitled Lesson',
                    type: 'Lesson',
                    run: () => {
                        const card = document.querySelector(`[data-lesson-id="${CSS.escape(l.id)}"]`);
                        if (card) card.click();
                        updateUrlHash(currentCourseId, l.id);
                    },
                });
            });
        }
        return items;
    };

    const renderList = (query) => {
        const q = (query || '').trim().toLowerCase();
        const matched = getItems().filter((it) => !q || it.label.toLowerCase().includes(q) || it.type.toLowerCase().includes(q)).slice(0, 12);
        list.textContent = '';
        if (matched.length === 0) {
            const li = document.createElement('li');
            li.className = 'px-3 py-3 text-xs text-text-secondary';
            li.textContent = 'No matching commands or lessons.';
            list.appendChild(li);
            return;
        }
        matched.forEach((it) => {
            const li = document.createElement('li');
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'w-full flex items-center justify-between px-3 py-2 text-left text-sm rounded-lg hover:bg-bg-sidebar text-text-primary';
            const spanLabel = document.createElement('span');
            spanLabel.textContent = it.label;
            const spanType = document.createElement('span');
            spanType.className = 'text-xs text-text-secondary px-1.5 py-0.5 rounded bg-bg-sidebar';
            spanType.textContent = it.type;
            btn.appendChild(spanLabel);
            btn.appendChild(spanType);
            btn.addEventListener('click', () => {
                closePalette();
                it.run();
            });
            li.appendChild(btn);
            list.appendChild(li);
        });
    };

    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            if (modal.classList.contains('hidden')) {
                modal.classList.remove('hidden');
                modal.classList.add('flex');
                input.value = '';
                renderList('');
                input.focus();
            } else {
                closePalette();
            }
        } else if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
            closePalette();
        }
    });

    input.addEventListener('input', () => renderList(input.value));
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closePalette();
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initCommandPalette();
});
