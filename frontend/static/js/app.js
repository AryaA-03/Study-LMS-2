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
    const style = 'background: #4f46e5; color: #ffffff; padding: 2px 5px; border-radius: 4px; font-weight: bold;';
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
    const style = 'background: #8b5cf6; color: #ffffff; padding: 2px 5px; border-radius: 4px; font-weight: bold;';
    console.log(`${badge} ${action}:`, details);
  },
  filter(action, count) {
    const badge = `%c[LearnLMS:Filter]`;
    const style = 'background: #059669; color: #ffffff; padding: 2px 5px; border-radius: 4px; font-weight: bold;';
    console.log(`${badge} ${action} (${count} affected)`);
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
let ytPlayer = null;
let isYtReady = false;
let collapsedDays = new Set();
let areAllDaysCollapsed = false;

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
  Logger.player('Player Ready', event);
  const placeholder = document.getElementById('yt-player-placeholder');
  if (placeholder) placeholder.classList.add('hidden');
}

function onPlayerStateChange(event) {
  Logger.player('Player State Change', event.data);
}

function playVideoSlice(videoId, startSec, endSec) {
  if (!videoId) return;
  const placeholder = document.getElementById('yt-player-placeholder');
  if (placeholder) placeholder.classList.add('hidden');

  Logger.player('Seek & Play Slice', { videoId, startSec, endSec });

  if (isYtReady && ytPlayer && ytPlayer.loadVideoById) {
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

// --- App Boot ---
document.addEventListener('DOMContentLoaded', async () => {
  console.log('%c[LearnLMS] Booting Personal LMS & Exam Prep...', 'color: #8b5cf6; font-size: 14px; font-weight: bold;');
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

  courseCreateForm.addEventListener('submit', handleCourseCreate);
  btnApproveSelected.addEventListener('click', handleApproveSources);

  btnToggleActiveComplete.addEventListener('click', handleToggleActiveAllocation);
  btnSkipActive.addEventListener('click', handleSkipActiveAllocation);

  btnReplanNow.addEventListener('click', () => {
    const speed = parseFloat(inlinePlaybackSpeed.value);
    const minDay = parseInt(inlineMinutesDay.value, 10);
    replanCourse('normal', { playback_speed: speed, minutes_per_day: minDay });
  });

  pillStrategyPaced.addEventListener('click', () => setStrategy('paced'));
  pillStrategyFixed.addEventListener('click', () => setStrategy('fixed'));

  btnActionCompress.addEventListener('click', () => replanCourse('compress'));
  btnActionExtend.addEventListener('click', () => replanCourse('extend'));

  btnUndoDiff.addEventListener('click', handleUndo);
  btnDismissDiff.addEventListener('click', () => diffBanner.classList.add('hidden'));

  // Collapsible Layout Toggles
  btnCollapsePlayer.addEventListener('click', togglePlayerCollapse);
  btnCollapseSchedule.addEventListener('click', toggleScheduleCollapse);
  btnToggleCollapseAll.addEventListener('click', toggleCollapseAllDays);

  // Curriculum Drawer
  btnToggleCurriculum.addEventListener('click', () => curriculumDrawer.classList.toggle('hidden'));
  btnCloseCurriculum.addEventListener('click', () => curriculumDrawer.classList.add('hidden'));
  curriculumSearch.addEventListener('input', filterCurriculumDrawer);
  btnCurriculumIncludeAll.addEventListener('click', () => handleFilterLessons(true));
  btnCurriculumSkipExamples.addEventListener('click', () => handleFilterLessons(false));

  // Quick Filters
  btnFilterAll.addEventListener('click', () => handleFilterLessons(null));
  btnFilterConcepts.addEventListener('click', () => handleFilterLessons(false));
  btnFilterExamples.addEventListener('click', () => handleFilterLessons(true));

  // Settings Modal
  btnSettings.addEventListener('click', () => settingsModal.classList.remove('hidden'));
  btnCloseSettings.addEventListener('click', () => settingsModal.classList.add('hidden'));
  document.getElementById('btn-update-ytdlp').addEventListener('click', handleUpdateYtdlp);
  document.getElementById('btn-cleanup-cache').addEventListener('click', handleCleanupCache);
  document.getElementById('btn-save-keys').addEventListener('click', handleSaveKeys);
  document.getElementById('settings-browser-cookies').addEventListener('change', handleUpdateBrowserCookies);

  // Notes Tabs & Actions
  tabGroundedNotes.addEventListener('click', () => switchNotesTab('grounded'));
  tabPersonalNotes.addEventListener('click', () => switchNotesTab('personal'));
  btnTranscribeLesson.addEventListener('click', handleTranscribeLesson);
  btnCaptureKeyframes.addEventListener('click', handleCaptureKeyframes);
  btnRegenerateNotes.addEventListener('click', () => {
    if (activeAllocation) loadLessonNotesAndArtifacts(activeAllocation.lesson_id, true);
  });
  inputPersonalNotes.addEventListener('input', handlePersonalNotesInput);
}

// --- Layout Collapsing ---
function togglePlayerCollapse() {
  const isHidden = document.getElementById('player-wrapper').classList.toggle('hidden');
  Logger.player('Toggle Player Collapse', { isHidden });
}

function toggleScheduleCollapse() {
  if (paneSchedule.classList.contains('hidden')) {
    paneSchedule.classList.remove('hidden');
    paneStudio.classList.replace('md:w-full', 'md:w-7/12');
  } else {
    paneSchedule.classList.add('hidden');
    paneStudio.classList.replace('md:w-7/12', 'md:w-full');
  }
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

// --- Strategy Switching (Paced vs Fixed) ---
async function setStrategy(strategy) {
  if (strategy === 'paced') {
    pillStrategyPaced.classList.add('bg-violet-600', 'text-white', 'shadow-sm');
    pillStrategyPaced.classList.remove('text-slate-400');
    pillStrategyFixed.classList.remove('bg-violet-600', 'text-white', 'shadow-sm');
    pillStrategyFixed.classList.add('text-slate-400');
  } else {
    pillStrategyFixed.classList.add('bg-violet-600', 'text-white', 'shadow-sm');
    pillStrategyFixed.classList.remove('text-slate-400');
    pillStrategyPaced.classList.remove('bg-violet-600', 'text-white', 'shadow-sm');
    pillStrategyPaced.classList.add('text-slate-400');
  }

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

    // Update Strategy Buttons
    const strat = currentCourse.schedule_strategy || 'paced';
    if (strat === 'paced') {
      pillStrategyPaced.classList.add('bg-violet-600', 'text-white');
      pillStrategyPaced.classList.remove('text-slate-400');
      pillStrategyFixed.classList.remove('bg-violet-600', 'text-white');
      pillStrategyFixed.classList.add('text-slate-400');
      pacingModeLabel.textContent = 'Paced to Exam Date';
    } else {
      pillStrategyFixed.classList.add('bg-violet-600', 'text-white');
      pillStrategyFixed.classList.remove('text-slate-400');
      pillStrategyPaced.classList.remove('bg-violet-600', 'text-white');
      pillStrategyPaced.classList.add('text-slate-400');
      pacingModeLabel.textContent = 'Fixed Daily Goal';
    }

    await loadLessons(courseId);
    await loadSchedule(courseId);
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

  // Behind Schedule Alert
  if (sched.is_behind_schedule) {
    behindScheduleBanner.classList.remove('hidden');
    behindScheduleMsg.textContent = `Projected finish (${sched.projected_finish_date}) encroaches on your ${sched.revision_buffer_days}-day revision buffer before ${sched.target_date}.`;
  } else {
    behindScheduleBanner.classList.add('hidden');
  }

  // Render Day Groups (CourseIt style)
  sched.days.forEach(day => {
    const dayEl = document.createElement('div');
    dayEl.className = 'bg-surface-900 border border-slate-800/80 rounded-2xl overflow-hidden shadow-sm transition hover:border-slate-700/70';

    let badgeHtml = '';
    if (day.is_revision_day) {
      badgeHtml = '<span class="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-amber-950/80 text-amber-300 border border-amber-800/80 font-mono">Revision Buffer</span>';
    } else if (day.is_rest_day) {
      badgeHtml = '<span class="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-surface-800 text-slate-400 font-mono">Rest Day</span>';
    }

    const isCollapsed = collapsedDays.has(day.date);

    const dayHeader = `
      <div class="px-3.5 py-2.5 bg-surface-850/80 border-b border-slate-800/80 flex items-center justify-between text-xs cursor-pointer select-none" onclick="window.toggleDayCollapse('${day.date}')">
        <div class="flex items-center gap-2">
          <svg id="day-chevron-${day.date}" class="w-3.5 h-3.5 text-slate-400 transition-transform day-chevron" style="transform: ${isCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)'};" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
          <span class="font-bold text-slate-200">${day.day_name}, ${formatDateDisplay(day.date)}</span>
          ${badgeHtml}
        </div>
        <span class="text-violet-300 font-mono font-medium">${Math.round(day.total_effective_minutes)} min</span>
      </div>
    `;

    let allocsHtml = '';
    if (day.allocations.length === 0) {
      allocsHtml = `
        <div class="p-3 text-xs text-slate-500 italic text-center">
          ${day.is_revision_day ? 'Dedicated strictly for comprehensive revision & mock exams.' : day.is_rest_day ? 'Rest & recharge day.' : 'No study allocations.'}
        </div>
      `;
    } else {
      allocsHtml = `<div class="divide-y divide-slate-800/40">`;
      day.allocations.forEach(alloc => {
        const isCompleted = alloc.is_completed;
        const splitText = alloc.split_count > 1 ? `Part ${alloc.split_index + 1}/${alloc.split_count}` : '';
        const priorityBadge = alloc.priority === 'deep-dive' 
          ? '<span class="text-[9px] uppercase px-1.5 py-0.2 rounded bg-purple-950 text-purple-300 border border-purple-800">Deep-Dive</span>'
          : '<span class="text-[9px] uppercase px-1.5 py-0.2 rounded bg-violet-950 text-violet-300 border border-violet-800">Core</span>';

        allocsHtml += `
          <div class="p-2.5 hover:bg-surface-850/70 transition flex items-start gap-2.5 cursor-pointer alloc-item ${isCompleted ? 'opacity-50' : ''}" data-alloc-id="${alloc.id}">
            <input type="checkbox" class="mt-1 rounded text-violet-600 focus:ring-0 alloc-checkbox cursor-pointer" data-alloc-id="${alloc.id}" ${isCompleted ? 'checked' : ''}>
            <div class="flex-1 min-w-0" onclick="window.selectAllocation('${alloc.id}')">
              <div class="flex items-center gap-1.5 mb-0.5">
                ${priorityBadge}
                ${splitText ? `<span class="text-[10px] text-amber-400 font-mono font-medium">${splitText}</span>` : ''}
                <span class="text-[10px] text-slate-400 font-mono">[${formatDurationSec(alloc.allocated_start_sec)} - ${formatDurationSec(alloc.allocated_end_sec)}]</span>
              </div>
              <h4 class="text-xs font-medium text-slate-200 truncate ${isCompleted ? 'line-through text-slate-400' : ''}">${alloc.lesson_title}</h4>
              <div class="text-[10px] text-slate-500 mt-0.5 font-mono">${alloc.effective_minutes} min (effective)</div>
            </div>
            <button class="text-slate-500 hover:text-amber-400 p-1 text-xs shrink-0" title="Skip lesson" onclick="window.skipAllocation('${alloc.id}', event)">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 5l7 7-7 7M5 5l7 7-7 7"/></svg>
            </button>
          </div>
        `;
      });
      allocsHtml += `</div>`;
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

window.selectAllocation = function(allocId) {
  if (!currentSchedule) return;
  for (const d of currentSchedule.days) {
    for (const a of d.allocations) {
      if (a.id === allocId) {
        activeAllocation = a;
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
    btnToggleActiveComplete.classList.replace('bg-emerald-600', 'bg-slate-700');
  } else {
    activeCompleteLabel.textContent = 'Mark Complete';
    btnToggleActiveComplete.classList.replace('bg-slate-700', 'bg-emerald-600');
  }
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
      if (diff.dropped_deep_dive_count > 0) {
        diffMsg += ` • Dropped ${diff.dropped_deep_dive_count} deep-dive topics to compress schedule.`;
      }
      if (diff.deficit_message) {
        diffMsg += ` • ⚠️ ${diff.deficit_message}`;
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
async function handleFilterLessons(includeExamples) {
  const t0 = performance.now();
  try {
    const payload = {};
    if (includeExamples !== null) {
      payload.include_examples = includeExamples;
    }
    const res = await fetch(`/api/courses/${currentCourseId}/lessons/filter`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const updatedLessons = await res.json();
    Logger.api('POST', `/api/courses/.../lessons/filter`, res.status, Math.round(performance.now() - t0), updatedLessons);
    currentLessons = updatedLessons;
    renderCurriculumDrawer(currentLessons);

    // Regenerate schedule to reflect included/excluded lessons
    await fetch(`/api/courses/${currentCourseId}/schedule/generate`, { method: 'POST' });
    await loadSchedule(currentCourseId);
  } catch (err) {
    Logger.error('Failed to filter lessons', err);
  }
}

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
    item.className = `p-2 rounded-lg flex items-start gap-2.5 text-xs hover:bg-surface-800/60 ${l.is_excluded ? 'opacity-40' : ''}`;
    item.innerHTML = `
      <input type="checkbox" class="mt-0.5 rounded text-violet-600 focus:ring-0 cursor-pointer" ${!l.is_excluded ? 'checked' : ''} onchange="window.toggleLessonExclude('${l.id}')">
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-1.5 mb-0.5">
          <span class="text-[9px] uppercase px-1 rounded ${l.priority === 'core' ? 'bg-violet-950 text-violet-300' : 'bg-purple-950 text-purple-300'}">${l.priority}</span>
          <span class="text-[10px] text-slate-400 font-mono">${formatDurationSec(l.raw_duration_sec)}</span>
        </div>
        <div class="font-medium text-slate-200 truncate ${l.is_excluded ? 'line-through text-slate-500' : ''}">${l.title}</div>
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
      item.className = 'flex items-start gap-2.5 p-2 rounded-xl bg-surface-900 border border-slate-700/60 cursor-pointer hover:bg-surface-850 text-xs';
      item.innerHTML = `
        <input type="checkbox" name="approved_source" value="${pl.source_id}" checked class="mt-0.5 text-violet-600 rounded">
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
      item.className = 'flex items-start gap-2.5 p-2 rounded-xl bg-surface-900 border border-slate-700/60 cursor-pointer hover:bg-surface-850 text-xs';
      item.innerHTML = `
        <input type="checkbox" name="approved_source" value="${v.source_id}" checked class="mt-0.5 text-violet-600 rounded">
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
async function loadSettings() {
  try {
    const res = await fetch('/api/settings');
    const s = await res.json();
    document.getElementById('settings-ytdlp-version').textContent = s.ytdlp_version;
    document.getElementById('settings-browser-cookies').value = s.cookies_browser || '';
    document.getElementById('settings-db-size').textContent = formatBytes(s.db_size_bytes);
    document.getElementById('settings-transcripts-size').textContent = formatBytes(s.transcripts_size_bytes);
    document.getElementById('settings-screenshots-size').textContent = formatBytes(s.screenshots_size_bytes);

    const totalBytes = s.transcripts_size_bytes + s.screenshots_size_bytes;
    document.getElementById('settings-total-disk').textContent = formatBytes(totalBytes);

    const badgeGemini = document.getElementById('badge-gemini');
    if (s.has_gemini_key) {
      badgeGemini.classList.replace('bg-slate-800', 'bg-emerald-950');
      badgeGemini.classList.replace('text-slate-400', 'text-emerald-300');
      badgeGemini.textContent = 'Gemini (Connected)';
    }
  } catch (err) {
    Logger.error('Failed to load settings', err);
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
  const gemini = document.getElementById('input-key-gemini').value.trim();
  const updates = {};
  if (gemini) updates.GEMINI_API_KEY = gemini;

  if (Object.keys(updates).length === 0) return;

  try {
    const res = await fetch('/api/settings/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    const data = await res.json();
    alert(data.message);
    document.getElementById('input-key-gemini').value = '';
    await loadSettings();
  } catch (err) {
    alert('Failed to save keys: ' + err.message);
  }
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
  if (tab === 'grounded') {
    tabGroundedNotes.classList.add('bg-surface-800', 'text-white');
    tabGroundedNotes.classList.remove('text-slate-400');
    tabPersonalNotes.classList.remove('bg-surface-800', 'text-white');
    tabPersonalNotes.classList.add('text-slate-400');

    paneGroundedNotes.classList.remove('hidden');
    panePersonalNotes.classList.add('hidden');
  } else {
    tabPersonalNotes.classList.add('bg-surface-800', 'text-white');
    tabPersonalNotes.classList.remove('text-slate-400');
    tabGroundedNotes.classList.remove('bg-surface-800', 'text-white');
    tabGroundedNotes.classList.add('text-slate-400');

    panePersonalNotes.classList.remove('hidden');
    paneGroundedNotes.classList.add('hidden');
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
        inputPersonalNotes.value = noteData.personal_notes || '';
      }
      Logger.api(method, endpoint, resNotes.status, Math.round(performance.now() - t0), noteData);
    }
  } catch (err) {
    Logger.error('Failed to load lesson notes & artifacts', err);
  }
}

function renderKeyframesStrip(shots) {
  if (!shots || shots.length === 0) {
    keyframesStrip.classList.add('hidden');
    keyframesStrip.innerHTML = '';
    return;
  }

  keyframesStrip.classList.remove('hidden');
  keyframesStrip.innerHTML = shots.map(s => `
    <div class="relative shrink-0 group cursor-pointer rounded-lg overflow-hidden border border-slate-700 hover:border-violet-500 transition shadow" onclick="window.seekToSeconds(${s.timestamp_sec})" title="Jump to ${s.formatted_time}">
      <img src="${s.url}" alt="${s.caption}" class="w-24 h-14 object-cover">
      <span class="absolute bottom-1 right-1 bg-black/80 text-white font-mono text-[9px] px-1 py-0.2 rounded font-semibold">${s.formatted_time}</span>
      <div class="absolute inset-0 bg-violet-600/20 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
        <svg class="w-5 h-5 text-white drop-shadow" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
      </div>
    </div>
  `).join('');
}

function renderMarkdownNotes(markdownText) {
  if (!markdownText) {
    notesContent.innerHTML = '<p class="text-slate-500 italic text-xs">No notes generated for this lesson yet. Click "Transcribe" above.</p>';
    return;
  }

  // Escape basic HTML tags to prevent XSS
  let html = markdownText
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // GitHub style alerts: > [!NOTE], > [!IMPORTANT], > [!TIP], > [!WARNING]
  html = html.replace(/&gt; \[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\n((?:&gt; .*\n?)+)/gi, (match, p1, p2) => {
    const alertType = p1.toUpperCase();
    const alertBody = p2.replace(/&gt; ?/g, '');
    let colorClass = 'border-blue-500/60 bg-blue-950/40 text-blue-200';
    if (alertType === 'IMPORTANT') colorClass = 'border-amber-500/60 bg-amber-950/40 text-amber-200';
    if (alertType === 'WARNING') colorClass = 'border-red-500/60 bg-red-950/40 text-red-200';
    if (alertType === 'TIP') colorClass = 'border-emerald-500/60 bg-emerald-950/40 text-emerald-200';
    return `<div class="p-3 my-2 border-l-4 rounded-r-lg ${colorClass} text-xs leading-relaxed">
      <div class="font-bold uppercase tracking-wider mb-1">${alertType}</div>
      <div>${alertBody}</div>
    </div>`;
  });

  // Images ![caption](url)
  html = html.replace(/!\[(.*?)\]\((.*?)\)/g, '<div class="my-3"><img src="$2" alt="$1" class="rounded-lg border border-slate-700 max-h-56 object-cover shadow-lg mx-auto"><div class="text-[11px] text-center text-slate-400 mt-1 italic">$1</div></div>');

  // Headings
  html = html.replace(/^### (.*$)/gim, '<h3 class="text-sm font-bold text-violet-300 mt-3 mb-1">$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2 class="text-base font-bold text-white mt-4 mb-2 pb-1 border-b border-slate-800">$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1 class="text-lg font-extrabold text-white mt-4 mb-2 pb-1 border-b border-slate-700">$1</h1>');

  // Bold & Italic
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="text-white font-semibold">$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em class="text-slate-300">$1</em>');

  // Code spans
  html = html.replace(/`([^`]+)`/g, '<code class="bg-surface-950 text-violet-300 px-1.5 py-0.5 rounded text-[11px] font-mono border border-slate-800">$1</code>');

  // Bullets
  html = html.replace(/^- (.*$)/gim, '<div class="flex items-start gap-2 my-1 text-xs text-slate-300 leading-normal"><span class="text-violet-400 mt-0.5">•</span><span>$1</span></div>');

  // Clickable Timestamps [MM:SS] or [HH:MM:SS]
  html = html.replace(/\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]/g, (match, p1, p2, p3) => {
    let totalSec = 0;
    if (p3 !== undefined) {
      totalSec = parseInt(p1, 10) * 3600 + parseInt(p2, 10) * 60 + parseInt(p3, 10);
    } else {
      totalSec = parseInt(p1, 10) * 60 + parseInt(p2, 10);
    }
    return `<button type="button" onclick="window.seekToSeconds(${totalSec})" class="inline-flex items-center gap-1 font-mono text-[11px] font-medium bg-violet-950/90 hover:bg-violet-800 text-violet-300 border border-violet-700/60 rounded px-1.5 py-0.5 cursor-pointer transition shadow-sm active:scale-95" title="Jump video to ${match}"><span>▶</span> ${match}</button>`;
  });

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

