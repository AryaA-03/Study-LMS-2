/**
 * Learn LMS Client - Frontend Application
 * Strictly communicates with backend OpenAPI endpoints and YouTube IFrame Player API.
 */

// State
let currentCourseId = null;
let currentCourse = null;
let currentSchedule = null;
let activeAllocation = null;
let ytPlayer = null;
let isYtReady = false;

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
const statProjectedFinish = document.getElementById('stat-projected-finish');
const statTargetDate = document.getElementById('stat-target-date');

const inlinePlaybackSpeed = document.getElementById('inline-playback-speed');
const inlineMinutesDay = document.getElementById('inline-minutes-day');
const btnReplanNow = document.getElementById('btn-replan-now');

const activeLessonTitle = document.getElementById('active-lesson-title');
const activeLessonTime = document.getElementById('active-lesson-time');
const activeLessonPriority = document.getElementById('active-lesson-priority');
const activeLessonSplit = document.getElementById('active-lesson-split');
const btnToggleActiveComplete = document.getElementById('btn-toggle-active-complete');
const activeCompleteLabel = document.getElementById('active-complete-label');
const btnSkipActive = document.getElementById('btn-skip-active');

// --- YouTube IFrame API Initialization ---
window.onYouTubeIframeAPIReady = function() {
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
  document.getElementById('yt-player-placeholder').classList.add('hidden');
}

function onPlayerStateChange(event) {
  // Can be used for watch time tracking
}

function playVideoSlice(videoId, startSec, endSec) {
  if (!videoId) return;
  const placeholder = document.getElementById('yt-player-placeholder');
  if (placeholder) placeholder.classList.add('hidden');

  if (isYtReady && ytPlayer && ytPlayer.loadVideoById) {
    ytPlayer.loadVideoById({
      videoId: videoId,
      startSeconds: startSec || 0,
      endSeconds: endSec || undefined,
    });
  }
}

// --- App Boot ---
document.addEventListener('DOMContentLoaded', async () => {
  setupEventListeners();
  setDefaultTargetDate();
  await loadSettings();
  await refreshCourseList();
});

function setDefaultTargetDate() {
  const d = new Date();
  d.setDate(d.getDate() + 21); // 3 weeks by default
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

  btnActionCompress.addEventListener('click', () => {
    replanCourse('compress');
  });

  btnActionExtend.addEventListener('click', () => {
    replanCourse('extend');
  });

  btnUndoDiff.addEventListener('click', handleUndo);
  btnDismissDiff.addEventListener('click', () => diffBanner.classList.add('hidden'));

  // Settings Modal
  btnSettings.addEventListener('click', () => settingsModal.classList.remove('hidden'));
  btnCloseSettings.addEventListener('click', () => settingsModal.classList.add('hidden'));
  document.getElementById('btn-update-ytdlp').addEventListener('click', handleUpdateYtdlp);
  document.getElementById('btn-cleanup-cache').addEventListener('click', handleCleanupCache);
  document.getElementById('btn-save-keys').addEventListener('click', handleSaveKeys);
  document.getElementById('settings-browser-cookies').addEventListener('change', handleUpdateBrowserCookies);
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
  try {
    const res = await fetch('/api/courses');
    const courses = await res.json();
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
    console.error('Error fetching courses:', err);
  }
}

async function loadCourse(courseId) {
  try {
    currentCourseId = courseId;
    const res = await fetch(`/api/courses/${courseId}`);
    currentCourse = await res.json();

    inlinePlaybackSpeed.value = currentCourse.playback_speed;
    inlineMinutesDay.value = currentCourse.minutes_per_day;

    await loadSchedule(courseId);
    showWorkspaceView();
  } catch (err) {
    console.error('Failed to load course:', err);
  }
}

async function loadSchedule(courseId) {
  try {
    const res = await fetch(`/api/courses/${courseId}/schedule`);
    currentSchedule = await res.json();
    renderSchedule(currentSchedule);
  } catch (err) {
    console.error('Failed to load schedule:', err);
  }
}

function renderSchedule(sched) {
  scheduleDaysContainer.innerHTML = '';

  // Update Progress Dashboard Stats
  const pct = Math.round((sched.completed_effective_minutes / (sched.total_effective_minutes || 1)) * 100);
  progressPct.textContent = `${pct}%`;
  progressBarFill.style.width = `${pct}%`;

  const remHours = Math.floor(sched.remaining_effective_minutes / 60);
  const remMins = Math.round(sched.remaining_effective_minutes % 60);
  statEffectiveLeft.textContent = `${remHours}h ${remMins.toString().padStart(2, '0')}m`;

  statProjectedFinish.textContent = sched.projected_finish_date || '--';
  statTargetDate.textContent = sched.target_date || '--';

  // Behind Schedule Alert
  if (sched.is_behind_schedule) {
    behindScheduleBanner.classList.remove('hidden');
    behindScheduleMsg.textContent = `Projected finish (${sched.projected_finish_date}) encroaches on your ${sched.revision_buffer_days}-day revision buffer before ${sched.target_date}.`;
  } else {
    behindScheduleBanner.classList.add('hidden');
  }

  // Render Day Groups
  sched.days.forEach(day => {
    const dayEl = document.createElement('div');
    dayEl.className = 'bg-surface-900 border border-slate-800/80 rounded-xl overflow-hidden';

    // Header
    let badgeHtml = '';
    if (day.is_revision_day) {
      badgeHtml = '<span class="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800">Revision Buffer</span>';
    } else if (day.is_rest_day) {
      badgeHtml = '<span class="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-400">Rest Day</span>';
    }

    const dayHeader = `
      <div class="px-3.5 py-2.5 bg-surface-850 border-b border-slate-800/80 flex items-center justify-between text-xs">
        <div class="flex items-center gap-2">
          <span class="font-bold text-slate-200">${day.day_name}, ${formatDateDisplay(day.date)}</span>
          ${badgeHtml}
        </div>
        <span class="text-slate-400 font-mono">${Math.round(day.total_effective_minutes)} min</span>
      </div>
    `;

    // Allocations
    let allocsHtml = '';
    if (day.allocations.length === 0) {
      allocsHtml = `
        <div class="p-3 text-xs text-slate-500 italic text-center">
          ${day.is_revision_day ? 'Dedicated strictly for comprehensive revision & mock exams.' : day.is_rest_day ? 'Rest & recharge day.' : 'No study allocations.'}
        </div>
      `;
    } else {
      allocsHtml = `<div class="divide-y divide-slate-800/50">`;
      day.allocations.forEach(alloc => {
        const isCompleted = alloc.is_completed;
        const isSkipped = alloc.is_skipped;
        const splitText = alloc.split_count > 1 ? `Part ${alloc.split_index + 1}/${alloc.split_count}` : '';
        const priorityBadge = alloc.priority === 'deep-dive' 
          ? '<span class="text-[9px] uppercase px-1.5 py-0.2 rounded bg-purple-950 text-purple-300 border border-purple-800">Deep-Dive</span>'
          : '<span class="text-[9px] uppercase px-1.5 py-0.2 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">Core</span>';

        allocsHtml += `
          <div class="p-3 hover:bg-surface-800/40 transition flex items-start gap-3 cursor-pointer alloc-item ${isCompleted ? 'opacity-60' : ''}" data-alloc-id="${alloc.id}">
            <input type="checkbox" class="mt-0.5 rounded text-indigo-600 focus:ring-0 alloc-checkbox" data-alloc-id="${alloc.id}" ${isCompleted ? 'checked' : ''}>
            <div class="flex-1 min-w-0" onclick="window.selectAllocation('${alloc.id}')">
              <div class="flex items-center gap-1.5 mb-0.5">
                ${priorityBadge}
                ${splitText ? `<span class="text-[10px] text-amber-400 font-mono">${splitText}</span>` : ''}
                <span class="text-[10px] text-slate-400 font-mono">[${formatDurationSec(alloc.allocated_start_sec)} - ${formatDurationSec(alloc.allocated_end_sec)}]</span>
              </div>
              <h4 class="text-xs font-medium text-slate-200 truncate ${isCompleted ? 'line-through text-slate-400' : ''}">${alloc.lesson_title}</h4>
              <div class="text-[11px] text-slate-500 mt-0.5 font-mono">${alloc.effective_minutes} min (effective)</div>
            </div>
            <button class="text-slate-500 hover:text-amber-400 p-1 text-xs" title="Skip lesson" onclick="window.skipAllocation('${alloc.id}', event)">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 5l7 7-7 7M5 5l7 7-7 7"/></svg>
            </button>
          </div>
        `;
      });
      allocsHtml += `</div>`;
    }

    dayEl.innerHTML = dayHeader + allocsHtml;
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
    // If all completed, select first
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
        return;
      }
    }
  }
};

function updateActiveLessonUI(alloc) {
  activeLessonTitle.textContent = alloc.lesson_title;
  activeLessonTime.textContent = `Time Slice: [${formatDurationSec(alloc.allocated_start_sec)} - ${formatDurationSec(alloc.allocated_end_sec)}] • ${alloc.effective_minutes} min`;
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
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/schedule/allocations/${allocId}/toggle`, {
      method: 'POST',
    });
    const updated = await res.json();
    await loadSchedule(currentCourseId);
    if (activeAllocation && activeAllocation.id === allocId) {
      activeAllocation.is_completed = updated.is_completed;
      updateActiveLessonUI(activeAllocation);
    }
  } catch (err) {
    console.error('Failed to toggle allocation:', err);
  }
}

window.skipAllocation = async function(allocId, evt) {
  if (evt) evt.stopPropagation();
  if (!confirm('Skip this lesson allocation and automatically reflow remaining schedule?')) return;
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/schedule/allocations/${allocId}/skip`, {
      method: 'POST',
    });
    currentSchedule = await res.json();
    renderSchedule(currentSchedule);
  } catch (err) {
    console.error('Failed to skip allocation:', err);
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
  try {
    const payload = {
      mode: mode,
      ...params,
    };
    const res = await fetch(`/api/courses/${currentCourseId}/schedule/replan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (data.success) {
      currentSchedule = data.schedule;
      renderSchedule(currentSchedule);

      // Show Diff Banner
      const diff = data.diff;
      let diffMsg = `Finish date: ${diff.old_finish_date || '--'} → ${diff.new_finish_date || '--'}`;
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
    console.error('Failed to replan schedule:', err);
  }
}

async function handleUndo() {
  try {
    const res = await fetch(`/api/courses/${currentCourseId}/schedule/undo`, {
      method: 'POST',
    });
    currentSchedule = await res.json();
    renderSchedule(currentSchedule);
    diffBanner.classList.add('hidden');
  } catch (err) {
    alert('No earlier snapshot to undo or error reverting.');
  }
}

// --- Course Creator & Discovery ---
async function handleCourseCreate(e) {
  e.preventDefault();
  const title = document.getElementById('input-course-title').value.trim();
  const goalQuery = document.getElementById('input-goal-query').value.trim();
  const targetDate = document.getElementById('input-target-date').value;
  const minutesDay = parseInt(document.getElementById('input-minutes-day').value, 10);
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

  try {
    // 1. Create Course Record
    const coursePayload = {
      title: title,
      goal_query: goalQuery,
      target_date: targetDate,
      minutes_per_day: minutesDay,
      playback_speed: playbackSpeed,
      rest_days: restDays,
      revision_buffer_days: revBuffer,
    };

    const resCourse = await fetch('/api/courses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(coursePayload),
    });
    const courseData = await resCourse.json();
    currentCourseId = courseData.id;

    // Check if goalQuery is direct YouTube URL
    if (goalQuery.includes('youtube.com') || goalQuery.includes('youtu.be')) {
      const resImport = await fetch(`/api/courses/${currentCourseId}/sources/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: goalQuery, is_approved: true }),
      });
      // Generate initial schedule directly
      await fetch(`/api/courses/${currentCourseId}/schedule/generate`, { method: 'POST' });
      await refreshCourseList();
      return;
    }

    // 2. Autonomous Discovery via yt-dlp
    const resDiscovery = await fetch(`/api/courses/${currentCourseId}/discover`, {
      method: 'POST',
    });
    const discovery = await resDiscovery.json();

    renderApprovalGate(discovery);
  } catch (err) {
    alert('Failed to discover sources: ' + err.message);
  } finally {
    spinner.classList.add('hidden');
    btnText.textContent = 'Discover & Build Roadmap';
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
      item.className = 'flex items-start gap-2.5 p-2 rounded-lg bg-surface-900 border border-slate-700/60 cursor-pointer hover:bg-surface-850 text-xs';
      item.innerHTML = `
        <input type="checkbox" name="approved_source" value="${pl.source_id}" checked class="mt-0.5 text-indigo-600 rounded">
        <div>
          <div class="font-medium text-slate-200">${pl.title}</div>
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
      item.className = 'flex items-start gap-2.5 p-2 rounded-lg bg-surface-900 border border-slate-700/60 cursor-pointer hover:bg-surface-850 text-xs';
      item.innerHTML = `
        <input type="checkbox" name="approved_source" value="${v.source_id}" checked class="mt-0.5 text-indigo-600 rounded">
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

    // Generate Schedule
    await fetch(`/api/courses/${currentCourseId}/schedule/generate`, {
      method: 'POST',
    });

    await refreshCourseList();
  } catch (err) {
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

    // API Key Badges
    const badgeGemini = document.getElementById('badge-gemini');
    if (s.has_gemini_key) {
      badgeGemini.classList.replace('bg-slate-800', 'bg-emerald-900');
      badgeGemini.classList.replace('text-slate-400', 'text-emerald-300');
      badgeGemini.textContent = 'Gemini (Connected)';
    }

    const badgeGroq = document.getElementById('badge-groq');
    if (s.has_groq_key) {
      badgeGroq.classList.replace('bg-slate-800', 'bg-emerald-900');
      badgeGroq.classList.replace('text-slate-400', 'text-emerald-300');
      badgeGroq.textContent = 'Groq (Connected)';
    }
  } catch (err) {
    console.error('Failed to load settings:', err);
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
  const groq = document.getElementById('input-key-groq').value.trim();
  const updates = {};
  if (gemini) updates.GEMINI_API_KEY = gemini;
  if (groq) updates.GROQ_API_KEY = groq;

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
    document.getElementById('input-key-groq').value = '';
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
