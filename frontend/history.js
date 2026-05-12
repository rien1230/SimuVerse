// History page logic for loading runs, filtering them, and paging the results.
const API = window.SimuVerseAPI.API_BASE;
const PAGE_SIZE = 4;
const REFRESH_INTERVAL_MS = 8000;

function authHeader() { return {}; }

// Page state for filters, selection, sorting, and auto-refresh.
let allRuns = [];
let currentPage = 1;
let selectedRunIds = new Set();
let refreshTimer = null;
let backendOnline = null;
let sortKey = 'date';
let sortDir = 'desc';
let selectionStatusTimer = null;
let isReloadingAfterDelete = false;

function $(id){ return document.getElementById(id); }

// Label and format helpers keep cards, badges, and modal text consistent.
function escapeHtml(value){
  return String(value == null ? '' : value).replace(/[&<>"']/g, (char) => (
    {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]
  ));
}

function scenarioLabel(run){
  const raw = String(run?.scenario_name || run?.scenario_id || run?.environment || '').trim();
  if (!raw) return 'Unknown';
  const clean = raw.replace(/_/g, ' ');
  const labels = {
    office_proposal: 'Office',
    office_roles: 'Office',
    cafe_restaurant: 'Cafe',
    escape_puzzle: 'Escape',
  };
  return labels[raw] || clean.replace(/\b\w/g, (c) => c.toUpperCase());
}

function scenarioClass(run){
  const raw = String(run?.scenario_id || run?.environment || '').toLowerCase();
  if (raw.includes('escape')) return 'escape';
  if (raw.includes('office')) return 'office';
  if (raw.includes('cafe')) return 'cafe';
  return 'other';
}

function teamLabel(team){
  const raw = String(team || '').toLowerCase();
  const labels = {
    smooth: 'Smooth Team',
    tension: 'Tension Team',
    pressure: 'Pressure Team',
    creative: 'Creative Team',
  };
  return labels[raw] || (team ? String(team).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : '—');
}

function modeLabel(run){
  return isInteractionRun(run) ? 'Live Interaction' : 'Watch Mode';
}

function outcomeRank(run){
  const label = outcomeLabel(run);
  const ranks = {
    'Success': 5,
    'Partial Success': 4,
    'In Progress': 3,
    'Incomplete': 2,
    'Interrupted': 1,
    'Deadlock': 0,
    'Failed': -1,
  };
  return ranks[label] ?? 0;
}

function outcomeInfo(run){
  const raw = String(run?.outcome || '').toLowerCase();
  const status = String(run?.status || '').toLowerCase();

  if (raw === 'success') return { cls: 'success', label: 'Success' };
  if (raw === 'partial' || raw === 'partial_success') return { cls: 'partial', label: 'Partial Success' };
  if (raw === 'failure' || raw === 'failed' || raw === 'meltdown') return { cls: 'failure', label: 'Failed' };
  if (raw === 'deadlock') return { cls: 'deadlock', label: 'Deadlock' };
  if (raw === 'interrupted' || status === 'interrupted' || status === 'cancelled' || status === 'stopped') {
    return { cls: 'interrupted', label: 'Interrupted' };
  }
  if (status === 'running' || status === 'paused' || status === 'idle' || status === 'auto_running') {
    return { cls: 'progress', label: 'In Progress' };
  }
  return { cls: 'incomplete', label: 'Incomplete' };
}

function outcomeClass(run){
  return outcomeInfo(run).cls;
}

function outcomeLabel(run){
  return outcomeInfo(run).label;
}

function formatDate(value){
  if (!value) return '—';
  try{
    const date = new Date(value);
    return date.toLocaleString('en-GB', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
  }catch{
    return '—';
  }
}

function cleanMessage(text){
  if (!text) return '';
  return String(text).replace(/\s+/g, ' ').trim();
}

function isInteractionRun(run){
  const src = String(run?.config?.source || '').toLowerCase();
  // Explicit new-run sources (set since the run_mode field was added to the API)
  if (src === 'watch') return false;
  if (src === 'live_interactive') return true;
  // Legacy runs (source = "interactive" or missing): fall back to intervention count.
  // A run with interventions was definitely Live Interaction; without, assume Watch Mode.
  return Number(run?.intervention_count ?? run?.event_counts?.interventions_used ?? 0) > 0;
}

function eventLabel(type){
  const raw = String(type || 'update').replace(/_/g, ' ').trim();
  return raw ? raw.replace(/\b\w/g, (c) => c.toUpperCase()) : 'Update';
}

function itemLabel(value){
  const raw = String(value || '').trim();
  if (!raw) return '—';
  const labels = {
    map: 'Room Map',
    lock: 'Lock Pattern',
    pattern: 'Lock Pattern',
    key: 'Key Location',
    code: 'Door Code',
    door: 'Door Code',
    unlock: 'Exit Lock',
    dietary_constraint: 'Dietary Constraint',
    budget_constraint: 'Budget',
    location_constraint: 'Location',
    location: 'Location',
    decision: 'Final Decision',
    choose_restaurant: 'Final Choice',
    requirements: 'Requirements',
    design: 'Design Plan',
    tech_specs: 'Technical Specs',
    budget: 'Budget',
    spec_doc: 'Spec Doc',
  };
  return labels[raw] || raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function interventionTypeLabel(raw) {
  const map = {
    force_meeting:    'Force Meeting',
    reveal_info:      'Reveal Info',
    nudge_strategy:   'Nudge Strategy',
    boost_urgency:    'Boost Pressure',
    ease_pressure:    'Ease Pressure',
    inject_tension:   'Inject Tension',
    inject_emotion:   'Emotion Input',
    emotion_injection:'Emotion Input',
  };
  const key = String(raw || '').toLowerCase();
  return map[key] || eventLabel(raw);
}

function extractConversation(history){
  const out = [];
  for (const tick of history || []) {
    // Agent conversation events
    for (const event of tick.events || []) {
      if (!event?.text) continue;
      const isEmotionInjection = String(event.type || '').toLowerCase() === 'emotion_injection';
      out.push({
        tick: tick.tick,
        actor:  isEmotionInjection ? 'You' : (event.actor || 'Agent'),
        target: isEmotionInjection ? 'Group' : (event.target || ''),
        type:   isEmotionInjection ? 'Emotion Input' : eventLabel(event.type),
        text:   cleanMessage(event.text),
        isUser: isEmotionInjection || String(event.actor || '').toUpperCase() === 'USER',
        isIntervention: isEmotionInjection,
      });
    }
    // User intervention events — include in the log so the full run is visible.
    // Skip inject_emotion: the emotion_injection event in tick.events already
    // represents it with the actual typed text (marked isIntervention: true
    // above). Including the tick.interventions entry too would double-count it
    // in the intervention total and show a duplicate Run Log row.
    for (const iv of tick.interventions || []) {
      if (String(iv.type || '').toLowerCase() === 'inject_emotion') continue;
      const label = interventionTypeLabel(iv.type);
      const detail = cleanMessage(iv.message || iv.label || iv.result?.message || '');
      out.push({
        tick: tick.tick,
        actor: 'User',
        target: '',
        type: label,
        text: detail || label,
        isUser: true,
        isIntervention: true,
      });
    }
  }
  // Sort by tick, then within the same tick put interventions FIRST so the Run Log
  // order matches Live Simulation: user intervention → agent response it caused.
  out.sort((a, b) => {
    const tickDiff = (a.tick || 0) - (b.tick || 0);
    if (tickDiff !== 0) return tickDiff;
    // Interventions before agent events within the same tick
    if (a.isIntervention && !b.isIntervention) return -1;
    if (!a.isIntervention && b.isIntervention) return 1;
    return 0;
  });
  return out;
}

// Collapse an array of type-label strings so repeated types become "Type ×N".
// Preserves first-occurrence order (Map iterates in insertion order).
function collapseInterventionLabels(types) {
  const seen = new Map();
  for (const t of types) seen.set(t, (seen.get(t) || 0) + 1);
  return Array.from(seen.entries()).map(([t, n]) => n > 1 ? `${t} \u00d7${n}` : t);
}

function extractInterventionMessages(run, conversation){
  // Prefer interventions already in the conversation log (from tick.interventions)
  const fromLog = conversation
    .filter((entry) => entry.isIntervention)
    .map((entry) => entry.type)
    .filter(Boolean);
  if (fromLog.length) return fromLog;
  // Fallback: top-level interventions list (backward-compat with older saves)
  return (run.interventions || [])
    .map((entry) => cleanMessage(interventionTypeLabel(entry?.type) || entry?.message || entry?.summary))
    .filter(Boolean);
}

// Modal and status helpers for run details and page-level feedback.
function openModal(){
  $('historyModal').hidden = false;
}

function closeModal(){
  $('historyModal').hidden = true;
}

function setSort(key){
  if (sortKey === key) {
    sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  } else {
    sortKey = key;
    sortDir = key === 'date' ? 'desc' : 'asc';
  }
  currentPage = 1;
  renderTable();
}

function updateSortIndicators(){
  const indicators = {
    steps: $('sortStepsIndicator'),
    outcome: $('sortOutcomeIndicator'),
    date: $('sortDateIndicator'),
  };
  Object.entries(indicators).forEach(([key, el]) => {
    if (!el) return;
    el.textContent = sortKey === key ? (sortDir === 'asc' ? '↑' : '↓') : '↕';
  });
}

function setSelectionStatus(message, kind = 'info'){
  const el = $('selectionStatus');
  if (!el) return;
  if (selectionStatusTimer) {
    clearTimeout(selectionStatusTimer);
    selectionStatusTimer = null;
  }
  el.textContent = message;
  el.className = `selection-status ${kind}`;
}

function flashSelectionStatus(message, kind = 'success', fallbackMessage = 'Select runs to replay, inspect, or delete from Run History.'){
  setSelectionStatus(message, kind);
  selectionStatusTimer = window.setTimeout(() => {
    setSelectionStatus(fallbackMessage, 'info');
    selectionStatusTimer = null;
  }, 4200);
}

function setOfflineBanner(message, kind = 'error'){
  const banner = $('offlineBanner');
  const msg = $('offlineBannerMsg');
  if (!banner || !msg) return;
  if (!message) {
    banner.classList.remove('show', 'error', 'warn', 'success');
    return;
  }
  msg.textContent = message;
  banner.className = `offline-banner show ${kind}`;
}

function showLoadingSkeleton(){
  const tbody = $('runsTableBody');
  if (!tbody) return;
  _lastRenderedKey = ':loading';
  tbody.innerHTML = Array.from({ length: 4 }, () => `
    <tr class="skeleton-row">
      <td class="select-cell"></td>
      <td><div class="skeleton-cell short"></div></td>
      <td><div class="skeleton-cell wide"></div></td>
      <td><div class="skeleton-cell short"></div></td>
      <td><div class="skeleton-cell tag"></div></td>
      <td><div class="skeleton-cell" style="width:32px"></div></td>
      <td><div class="skeleton-cell tag"></div></td>
      <td><div class="skeleton-cell short"></div></td>
      <td></td>
    </tr>
  `).join('');
}

async function parseApiError(response){
  const text = await response.text();
  if (!text) return `HTTP ${response.status}`;
  try{
    const data = JSON.parse(text);
    return data.detail || data.message || `HTTP ${response.status}`;
  }catch{
    return text;
  }
}

async function deleteRun(runId){
  const confirmed = window.confirm(`Delete saved run "${runId}" from history? This cannot be undone.`);
  if (!confirmed) return;

  try{
    const response = await fetch(`${API}/history/runs/${encodeURIComponent(runId)}`, {
      method: 'DELETE',
      headers: authHeader(),
    });
    if (!response.ok) throw new Error(await parseApiError(response));

    allRuns = allRuns.filter((run) => run.run_id !== runId);
    selectedRunIds.delete(runId);
    currentPage = 1;
    renderStats();
    renderFilter();
    renderTable();

    isReloadingAfterDelete = true;
    await loadRuns({ showSkeleton: false });
    flashSelectionStatus(`✓ Run ${runId} was deleted from history.`, 'success');

    if (!$('historyModal').hidden && $('historyModalTitle').textContent.includes(runId)) {
      closeModal();
    }
  }catch(error){
    setSelectionStatus(`Could not delete run ${runId}. ${error.message || String(error)}`, 'error');
  } finally {
    isReloadingAfterDelete = false;
  }
}

async function deleteSelectedRuns(){
  const runIds = Array.from(selectedRunIds);
  if (!runIds.length) return;

  const confirmed = window.confirm(`Delete ${runIds.length} selected run${runIds.length === 1 ? '' : 's'} from history? This cannot be undone.`);
  if (!confirmed) return;

  const failed = [];
  for (const runId of runIds) {
    try{
      const response = await fetch(`${API}/history/runs/${encodeURIComponent(runId)}`, {
        method: 'DELETE',
        headers: authHeader(),
      });
      if (!response.ok) throw new Error(await parseApiError(response));
      allRuns = allRuns.filter((run) => run.run_id !== runId);
      selectedRunIds.delete(runId);
      if (!$('historyModal').hidden && $('historyModalTitle').textContent.includes(runId)) {
        closeModal();
      }
    }catch(error){
      failed.push(`${runId} (${error.message || String(error)})`);
    }
  }

  renderStats();
  renderFilter();
  renderTable();

  if (runIds.length !== failed.length) {
    isReloadingAfterDelete = true;
    try {
      await loadRuns({ showSkeleton: false });
    } finally {
      isReloadingAfterDelete = false;
    }
  }

  if (failed.length) {
    setSelectionStatus(`Some runs could not be deleted: ${failed.join(' · ')}`, 'error');
  } else {
    flashSelectionStatus(`✓ Deleted ${runIds.length} selected run${runIds.length === 1 ? '' : 's'}.`, 'success');
  }
}

async function clearHistory(){
  if (!allRuns.length) {
    setSelectionStatus('There are no saved runs to clear.', 'info');
    return;
  }

  const confirmed = window.confirm(`Clear all ${allRuns.length} saved run${allRuns.length === 1 ? '' : 's'} from history? This cannot be undone.`);
  if (!confirmed) return;

  try{
    const response = await fetch(`${API}/history/runs`, {
      method: 'DELETE',
      headers: authHeader(),
    });
    if (!response.ok) throw new Error(await parseApiError(response));
    const data = await response.json();
    allRuns = [];
    selectedRunIds.clear();
    currentPage = 1;
    closeModal();
    renderStats();
    renderFilter();
    renderTable();

    isReloadingAfterDelete = true;
    await loadRuns({ showSkeleton: false });
    flashSelectionStatus(`✓ ${data.message || 'Saved history was cleared.'}`, 'success');
  }catch(error){
    setSelectionStatus(`Could not clear saved history. ${error.message || String(error)}`, 'error');
  } finally {
    isReloadingAfterDelete = false;
  }
}

// Build one clean export payload from the saved run JSON.
/**
 * Build a canonical payload for SimuVerseReport.generate() from a saved history run object.
 * Matches the shape produced by buildPdfPayload() / buildInteractionPdfPayload().
 */
function buildHistoryPdfPayload(run) {
  const ticks = Number(run.ticks || 0);
  const teamStr = run.team_type || run.team_preset || run.config?.team_type || '';
  const scenId  = String(run.scenario_id || run.environment || '').toLowerCase();
  const src = String(run.config?.source || '').toLowerCase();
  let mode = 'Watch Mode';
  if (src === 'live_interactive') mode = 'Live Interaction';
  else if (src === 'watch') mode = 'Watch Mode';
  else if (Number(run.intervention_count ?? run.event_counts?.interventions_used ?? 0) > 0) {
    mode = 'Live Interaction';
  }

  /* Final progress */
  const progressRaw = Number(run.final_progress || 0);
  const progressFraction = progressRaw <= 1 ? progressRaw : progressRaw / 100;

  /* Final metrics */
  const lastTick = (run.history || []).slice(-1)[0] || {};
  const lastM = lastTick.metrics || {};
  const peakStress = run.metric_trajectory?.stress_peak
    ?? run.peak_tension
    ?? Number(lastM.avg_stress || lastM.stress || 0);

  const finalMetrics = {
    progress: progressFraction,
    trust:    Number(lastM.avg_trust    || lastM.trust    || 0),
    stress:   Number(lastM.avg_stress   || lastM.stress   || peakStress),
    conflict: Number(lastM.conflict     || 0),
    cohesion: Number(lastM.cohesion     || 0),
  };

  /* Metrics history from per-tick data */
  const metricsHistory = (run.history || [])
    .filter((t) => t?.metrics)
    .map((t) => {
      const m = t.metrics || {};
      const scenTasks = t.scenario?.tasks || {};
      const vals = Object.values(scenTasks);
      const prog = vals.length ? vals.filter(Boolean).length / vals.length : 0;
      return {
        tick:     Number(t.tick || 0),
        progress: prog,
        trust:    Number(m.avg_trust    || m.trust    || 0),
        stress:   Number(m.avg_stress   || m.stress   || 0),
        conflict: Number(m.conflict     || 0),
        cohesion: Number(m.cohesion     || 0),
      };
    });

  /* Tasks: derive from the last tick's scenario.tasks */
  const lastScenTasks = lastTick.scenario?.tasks || {};
  const taskLabels = {
    requirements: 'Requirements', design: 'Design Plan',
    tech_specs: 'Technical Specs', budget: 'Budget Sign-off',
    dietary_constraint: 'Dietary Constraint', budget_constraint: 'Budget',
    location_constraint: 'Location', choose_restaurant: 'Final Choice',
    map: 'Room Map', lock: 'Lock Pattern', key: 'Key Location', code: 'Door Code',
  };
  const tasks = Object.entries(lastScenTasks).map(([k, done]) => ({
    label: taskLabels[k] || k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    done: Boolean(done),
  }));

  /* Timeline from history ticks */
  const evTypeLabel = (type) => {
    const map = {
      ask_info: 'Request Information', share_info: 'Share Information',
      trust_shift: 'Trust Change', conflict: 'Agent Conflict',
      complete_task: 'Task Completed', task_resolved: 'Task Resolved',
      force_meeting: 'Forced Meeting', reveal_info: 'Information Revealed',
      inject_tension: 'Inject Tension', boost_urgency: 'Boost Urgency',
      ease_pressure: 'Ease Pressure', nudge_strategy: 'Nudge Cooperation',
      inject_emotion: 'Inject Mood', block: 'Blocked', deadlock: 'Deadlock',
    };
    const raw = String(type || '').toLowerCase().replace(/-/g, '_');
    return map[raw] || String(type || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) || 'Interaction';
  };

  const timeline = (run.history || [])
    .filter((t) => Number(t.tick || 0) > 0)
    .map((t) => {
      const evs = t.events || [];
      const mainEv = evs.find((e) => {
        const et = String(e.type || '').toLowerCase();
        return !et.startsWith('trust') && !et.startsWith('group') && !et.startsWith('metric');
      }) || evs[0] || {};
      const actor  = String(mainEv.actor  || mainEv.actor_id  || '');
      const target = String(mainEv.target || mainEv.target_id || '');
      const isIv = evs.some((e) => {
        const et = String(e.type || '').toLowerCase();
        return et.includes('inject') || et.includes('reveal') || et.includes('force') ||
               et.includes('nudge') || et.includes('boost') || et.includes('ease');
      });
      const ivEv = isIv ? evs.find((e) => {
        const et = String(e.type || '').toLowerCase();
        return et.includes('inject') || et.includes('reveal') || et.includes('force') ||
               et.includes('nudge') || et.includes('boost') || et.includes('ease');
      }) : null;
      const title = evTypeLabel((ivEv || mainEv).type);
      const messages = evs.map((e) => e.text || e.message || '').filter(Boolean);
      return {
        tick:         Number(t.tick || 0),
        title,
        eventType:    (mainEv.type || ''),
        actorName:    actor,
        targetName:   target,
        summary:      messages[0] || '',
        message:      messages[0] || '',
        actionDetails: messages.slice(0, 2),
        effects:      [],
        hasEvent:     evs.length > 0,
      };
    });

  /* Interventions from per-tick data */
  const interventions = [];
  (run.history || []).forEach((t) => {
    for (const iv of (t.interventions || [])) {
      interventions.push({
        tick:    Number(t.tick || 0),
        label:   interventionTypeLabel(iv.type) || iv.label || 'Intervention',
        type:    iv.type || '',
        stressChange: null,
        trustChange:  null,
        verdict: '',
      });
    }
  });

  const doneTasks = tasks.filter((t) => t.done).length;
  const pct = tasks.length ? Math.round((doneTasks / tasks.length) * 100) : 0;
  const outcomeSummary =
    `The ${scenarioLabel(run)} scenario ran for ${ticks} steps using the ` +
    `${teamLabel(teamStr)} preset. ` +
    `${doneTasks} of ${tasks.length} tasks were completed (${pct}%). ` +
    `Final trust was ${finalMetrics.trust.toFixed(2)} and stress was ${finalMetrics.stress.toFixed(2)}.`;

  return {
    runId:      run.run_id || 'unknown',
    seed:       run.config?.seed ?? run.seed ?? 'Not recorded',
    exportedAt: new Date().toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }),
    scenario: {
      id:    scenId,
      label: scenarioLabel(run),
      title: scenarioLabel(run) + ' Simulation',
    },
    team:   { key: teamStr, label: teamLabel(teamStr) },
    mode,
    outcome:    outcomeLabel(run),
    totalSteps: ticks,
    agents:     [],   /* agent-level data not stored in history summary */
    tasks,
    finalMetrics,
    metricsHistory,
    timeline,
    interventions,
    outcomeSummary,
  };
}

// Modal renderers for one run and for side-by-side comparison.
async function openInteractionSummary(runId){
  $('historyModalTitle').textContent = 'Run Summary';
  $('historyModalSubtitle').textContent = 'Loading…';
  $('historyModalBody').innerHTML = '<div class="modal-empty">Loading saved run…</div>';
  openModal();

  try{
    const response = await fetch(`${API}/history/runs/${runId}`, { headers: authHeader() });
    if (!response.ok) throw new Error(await parseApiError(response));
    const run = await response.json();
    const conversation = extractConversation(run.history || []);
    const interventionMessages = extractInterventionMessages(run, conversation);
    // Resolve blocker label — for a completed escape run the bottleneck is null
    // (all clues resolved), so show a meaningful completion label instead of "—".
    const rawBlocker = itemLabel(run.group_state?.bottleneck_item);
    const scenId = String(run.scenario_id || '').toLowerCase();
    const isEscapeRun = scenId.includes('escape');
    const isOfficeRun = scenId.includes('office');
    // For failed/partial runs, rawBlocker may be empty (the run ended without a
    // live bottleneck_item).  Fall back to the first unresolved task from run.tasks
    // so the "Final blocker state" line is never blank for incomplete runs.
    const _firstUnresolved = run.tasks
      ? (Object.entries(run.tasks).find(([, done]) => !done)?.[0] ?? null)
      : null;
    const blocker = rawBlocker !== '—' ? rawBlocker
      : outcomeLabel(run) === 'Success'
        ? (isEscapeRun ? 'Escape complete — all clues resolved'
           : isOfficeRun ? 'All tasks completed'
           : 'All items resolved')
        : _firstUnresolved
          ? `${itemLabel(_firstUnresolved)} — not confirmed before step limit`
          : 'All blockers resolved';

    // Use null-safe check so 0 interventions stays 0 (not overridden by message scan).
    // Also prefer event_counts.interventions_used (scanned from full history) over the
    // top-level intervention_count (which previously only read the last-tick diff).
    const interventionCount = run.event_counts?.interventions_used != null
      ? run.event_counts.interventions_used
      : (run.intervention_count != null ? run.intervention_count : (interventionMessages.length || 0));
    // Peak tension priority — must match what the live completion modal shows.
    // The live modal reads metric_trajectory.stress_peak (avg_stress running max,
    // server-computed). run.peak_tension is group_tension max — a different metric.
    // Fallback: compute avg_stress running max from tick history if no trajectory saved.
    const peakTension = (() => {
      if (run.metric_trajectory?.stress_peak != null) return run.metric_trajectory.stress_peak;
      if (run.peak_tension != null) return run.peak_tension;
      // Compute from per-tick avg_stress (same source as peakStressThroughIndex in dashboard)
      const maxFromHistory = (run.history || []).reduce((mx, tick) => {
        const s = tick?.metrics?.avg_stress;
        return typeof s === 'number' ? Math.max(mx, s) : mx;
      }, 0);
      return maxFromHistory > 0 ? maxFromHistory : (run.group_state?.tension || 0);
    })();
    // team_preset is the top-level field saved by the backend; team_type lives inside config
    const teamStr = run.team_type || run.team_preset || run.config?.team_type;

    $('historyModalTitle').textContent = `${scenarioLabel(run)} · Run ${run.run_id}`;
    $('historyModalSubtitle').textContent = `${teamLabel(teamStr)} · ${outcomeLabel(run)} · ${run.ticks || 0} steps`;

    // ── Stat strip ──────────────────────────────────────────────────────────
    // "Peak Stress" = metric_trajectory.stress_peak (avg_stress running max) —
    //   the same value shown as "Peak team stress" in the live completion card.
    // "Peak Tension" = run.peak_tension (group_tension max) — stored separately,
    //   not surfaced in the live card but meaningful context in the inspect view.
    const rawPeakTension = run.peak_tension != null ? Number(run.peak_tension).toFixed(2) : null;
    const statChips = [
      ['Scenario',     scenarioLabel(run)],
      ['Team',         teamLabel(teamStr)],
      ['Mode',         modeLabel(run)],
      ['Outcome',      outcomeLabel(run)],
      ['Steps',        String(run.ticks || 0)],
      ['Progress',     Math.round(Number(run.final_progress || 0) * 100) + '%'],
      ['Peak Stress',  Number(peakTension).toFixed(2)],
      ...(rawPeakTension != null ? [['Peak Tension', rawPeakTension]] : []),
    ];
    const statStripHtml = `<div class="insp-stat-strip">${
      statChips.map(([lbl, val]) =>
        `<div class="insp-stat-chip">
          <span class="insp-chip-label">${escapeHtml(lbl)}</span>
          <span class="insp-chip-val">${escapeHtml(val)}</span>
        </div>`
      ).join('')
    }</div>`;

    // ── What Happened card ───────────────────────────────────────────────────
    const whatHtml = `
      <div class="insp-card">
        <div class="insp-card-title">What Happened</div>
        <ul class="what-list">
          <li>Ended as <strong>${escapeHtml(outcomeLabel(run))}</strong> after ${escapeHtml(String(run.ticks || 0))} steps.</li>
          <li>Final blocker state: <strong>${escapeHtml(blocker)}</strong>.</li>
          <li>${escapeHtml(String(interventionCount))} intervention${interventionCount === 1 ? '' : 's'} used${interventionMessages.length ? ': ' + escapeHtml(collapseInterventionLabels(interventionMessages).join(' · ')) : ''}.</li>
        </ul>
      </div>`;

    // ── Behaviour Counts card ────────────────────────────────────────────────
    const ec = run.event_counts;
    let countsCardHtml = '';
    if (ec) {
      // For incomplete escape runs, ec.blockers_total may be set to the resolved-so-far
      // count (e.g. 1) rather than the true scenario total (e.g. 5).
      // Defensively correct it using run.tasks, which always contains all task keys.
      const taskKeyCount = run.tasks ? Object.keys(run.tasks).length : 0;
      const blockersTotal = (taskKeyCount > (ec.blockers_total ?? 0))
        ? taskKeyCount
        : (ec.blockers_total ?? '?');

      const countRows = [
        ['Messages exchanged',    ec.messages_exchanged],
        ['Clues shared',          ec.clues_shared],
        ['Questions asked',       ec.questions_asked],
        ['Agreements',            ec.agreements],
        ['Challenges / refusals', ec.challenges],
        [isEscapeRun ? 'Clues resolved' : 'Items resolved', `${ec.blockers_resolved ?? '?'}/${blockersTotal}`],
        ['Interventions used',    ec.interventions_used],
      ];
      countsCardHtml = `
        <div class="insp-card">
          <div class="insp-card-title">Behaviour Counts</div>
          <div class="insp-counts">${
            countRows.map(([lbl, val]) =>
              `<div class="insp-count-row">
                <span class="insp-count-label">${escapeHtml(lbl)}</span>
                <strong class="insp-count-val">${escapeHtml(String(val ?? '—'))}</strong>
              </div>`
            ).join('')
          }</div>
        </div>`;
    }

    const infoGridHtml = `<div class="insp-info-grid${countsCardHtml ? '' : ' single-col'}">${whatHtml}${countsCardHtml}</div>`;

    // ── Memory Impressions ───────────────────────────────────────────────────
    const mem = run.memory_summary;
    let memSectionHtml = '';
    if (mem && mem.total_impressions != null) {
      let inner = '';
      if (mem.total_impressions === 0) {
        inner = `<p class="insp-note">${escapeHtml(mem.no_impression_reason || 'No impressions formed during this run.')}</p>`;
      } else {
        inner = `<p class="insp-mem-summary">${mem.total_impressions} impression${mem.total_impressions === 1 ? '' : 's'} formed — ${mem.positive_count} positive, ${mem.conflict_prone_count} conflict-prone.</p>`;
        for (const imp of [mem.strongest_positive, mem.strongest_conflict]) {
          if (!imp) continue;
          const count = imp.interaction_count || 0;
          const impLabel = 'positive' in (imp.patterns || {}) ? 'positive' : 'conflict-prone';
          let pairHtml = `<div class="insp-mem-pair">
            <p class="insp-mem-pair-header">${escapeHtml(imp.observer)} → ${escapeHtml(imp.target)} · ${impLabel} · ${count} interaction${count === 1 ? '' : 's'}</p>`;
          if (imp.evidence && imp.evidence.length) {
            pairHtml += `<ul class="insp-mem-evidence">${
              imp.evidence.map(ev =>
                `<li>${ev.tick != null ? `<strong>Step ${ev.tick}:</strong> ` : ''}${escapeHtml(ev.text || '')}</li>`
              ).join('')
            }</ul>`;
          }
          if (imp.effect) {
            pairHtml += `<p class="insp-mem-effect">Effect: ${escapeHtml(imp.effect)}</p>`;
          }
          pairHtml += `</div>`;
          inner += pairHtml;
        }
      }
      memSectionHtml = `<div class="insp-section"><div class="insp-section-title">Memory Impressions</div>${inner}</div>`;
    }

    // ── Emotion Effects ──────────────────────────────────────────────────────
    const emo = run.emotion_summary;
    let emoSectionHtml = '';
    if (emo && emo.emotion_inputs != null) {
      let inner = '';
      if (!emo.emotion_inputs) {
        inner = `<p class="insp-note">${escapeHtml(emo.interpretation || 'No emotion input was applied during this run.')}</p>`;
      } else {
        const dominant = emo.dominant_emotion || 'neutral';
        const valence  = emo.valence_label  || (emo.average_valence > 0.1 ? 'mildly positive' : emo.average_valence < -0.1 ? 'mildly negative' : 'neutral');
        const arousal  = emo.arousal_label  || (emo.average_arousal > 0.5 ? 'high' : 'low');
        const effect   = emo.effect_label   || 'minimal';
        inner = `<p class="insp-emo-headline">Dominant emotion: <strong>${escapeHtml(dominant)}</strong></p>
          <div class="insp-emo-pills">
            <span class="insp-emo-pill">valence: ${escapeHtml(valence)}</span>
            <span class="insp-emo-pill">arousal: ${escapeHtml(arousal)}</span>
            <span class="insp-emo-pill">effect: ${escapeHtml(effect)}</span>
          </div>`;
        if (effect === 'minimal' && emo.zero_reason) {
          inner += `<p class="insp-emo-note"><strong>Reason:</strong> ${escapeHtml(emo.zero_reason)}</p>`;
        } else if (effect !== 'minimal') {
          inner += `<p class="insp-emo-impacts">Stress impact: <strong>${escapeHtml(emo.stress_impact || '+0.00')}</strong> · Trust impact: <strong>${escapeHtml(emo.trust_impact || '+0.00')}</strong></p>`;
        }
      }
      emoSectionHtml = `<div class="insp-section"><div class="insp-section-title">Emotion Effects</div>${inner}</div>`;
    }

    const extraHtml = (memSectionHtml || emoSectionHtml)
      ? `<div class="insp-extra-sections">${memSectionHtml}${emoSectionHtml}</div>`
      : '';

    // ── Conversation Log (agent messages + user interventions) ───────────────
    const agentCount        = conversation.filter((e) => !e.isIntervention).length;
    const interventionCount2 = conversation.filter((e) => e.isIntervention).length;
    const logCountLabel = conversation.length
      ? `<span class="insp-log-count">${agentCount} message${agentCount === 1 ? '' : 's'}${interventionCount2 ? ` · ${interventionCount2} intervention${interventionCount2 === 1 ? '' : 's'}` : ''}</span>`
      : '';
    const logEntriesHtml = conversation.length
      ? conversation.map((entry) =>
          `<article class="log-card ${entry.isIntervention ? 'intervention' : entry.isUser ? 'user' : ''}">
            <div class="log-meta">
              <span>Step ${escapeHtml(String(entry.tick || 0))}</span>
              <span class="log-actor">${escapeHtml(entry.actor)}</span>
              ${entry.target ? `<span>→</span><span class="log-target">${escapeHtml(entry.target)}</span>` : ''}
              <span class="log-type">${escapeHtml(entry.type)}</span>
            </div>
            <div class="log-text">${escapeHtml(entry.text)}</div>
          </article>`
        ).join('')
      : '<div class="modal-empty">No saved conversation events were found for this run.</div>';

    const exportBarHtml = window.SimuVerseReport
      ? `<div class="insp-export-bar">
           <button class="insp-export-pdf-btn" id="historyExportPdfBtn" type="button">Export PDF</button>
         </div>`
      : '';

    $('historyModalBody').innerHTML =
      exportBarHtml +
      statStripHtml +
      infoGridHtml +
      extraHtml +
      `<div class="insp-log-head"><span class="insp-log-label">Run Log</span>${logCountLabel}</div>` +
      `<div class="insp-log">${logEntriesHtml}</div>`;

    /* Wire Export PDF button (run is still in scope here) */
    const exportBtn = $('historyExportPdfBtn');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        try {
          const payload = buildHistoryPdfPayload(run);
          if (window.SimuVersePDF) {
            window.SimuVersePDF.generate(payload);
            return;
          }
          if (window.SimuVerseReport) {
            window.SimuVerseReport.generate(payload);
            return;
          }
          throw new Error('Structured PDF generator not loaded.');
        } catch (err) {
          console.error('[History] PDF export error:', err);
          alert('PDF export failed. Check the browser console for details.');
        }
      });
    }

  } catch(error) {
    $('historyModalBody').innerHTML =
      `<div class="modal-empty">Could not load this run. ${escapeHtml(error.message || String(error))}</div>`;
  }
}

/**
 * Canonical peak-stress lookup — mirrors the logic in openInteractionSummary.
 * Priority: metric_trajectory.stress_peak → run.peak_tension → history scan → group_state fallback.
 * Returns a Number (never null).
 */
function _comparePeakStress(run) {
  if (run.metric_trajectory?.stress_peak != null) return Number(run.metric_trajectory.stress_peak);
  if (run.peak_tension != null) return Number(run.peak_tension);
  const maxFromHistory = (run.history || []).reduce((mx, tick) => {
    const s = tick?.metrics?.avg_stress;
    return typeof s === 'number' ? Math.max(mx, s) : mx;
  }, 0);
  return maxFromHistory > 0 ? maxFromHistory : Number(run.group_state?.tension || 0);
}

function openCompareSummary(){
  const selected = allRuns.filter((run) => selectedRunIds.has(run.run_id));
  if (selected.length < 2) return;

  // Determine whether any run has a distinct group-tension value to show.
  // "Peak Stress" = avg_stress running max (same as Inspect stat strip).
  // "Peak Tension" = group_tension max (run.peak_tension), only shown when present.
  const anyHasPeakTension = selected.some((run) => run.peak_tension != null);

  $('historyModalTitle').textContent = 'Compare Selected Runs';
  $('historyModalSubtitle').textContent = `${selected.length} runs selected`;

  $('historyModalBody').innerHTML = `
    <div style="padding:20px 28px 28px;display:flex;flex-direction:column;gap:16px;">
      <div class="compare-table-wrap">
        <table class="compare-table">
          <thead>
            <tr>
              <th>Run</th>
              <th>Scenario</th>
              <th>Team</th>
              <th>Mode</th>
              <th>Steps</th>
              <th>Outcome</th>
              <th>Peak Stress</th>
              ${anyHasPeakTension ? '<th>Peak Tension</th>' : ''}
            </tr>
          </thead>
          <tbody>
            ${selected.map((run) => {
              const teamStr = run.team_type || run.team_preset || run.config?.team_type;
              const peakStress = _comparePeakStress(run).toFixed(2);
              const peakTensionCell = anyHasPeakTension
                ? `<td>${escapeHtml(run.peak_tension != null ? Number(run.peak_tension).toFixed(2) : '—')}</td>`
                : '';
              return `
              <tr>
                <td>${escapeHtml(run.run_id)}</td>
                <td>${escapeHtml(scenarioLabel(run))}</td>
                <td>${escapeHtml(teamLabel(teamStr))}</td>
                <td>${escapeHtml(modeLabel(run))}</td>
                <td>${escapeHtml(String(run.ticks || 0))}</td>
                <td>${escapeHtml(outcomeLabel(run))}</td>
                <td>${escapeHtml(peakStress)}</td>
                ${peakTensionCell}
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>
      <p class="modal-empty" style="padding:8px 0;">Use Replay on any run to inspect the full sequence step by step.</p>
    </div>
  `;
  openModal();
}

function currentRuns(){
  const query = ($('searchInput').value || '').trim().toLowerCase();
  const scenario = $('scenarioFilter').value || 'all';
  const team = $('teamFilter').value || 'all';
  const outcome = $('outcomeFilter').value || 'all';
  const from = $('dateFrom').value || '';
  const to = $('dateTo').value || '';
  const filtered = allRuns.filter((run) => {
    if (scenario !== 'all' && scenarioLabel(run) !== scenario) return false;
    if (team !== 'all' && teamLabel(run.team_type || run.config?.team_type) !== team) return false;
    if (outcome !== 'all' && outcomeLabel(run) !== outcome) return false;
    if (from || to) {
      const runDate = run.timestamp ? new Date(run.timestamp) : null;
      if (!runDate || Number.isNaN(runDate.getTime())) return false;
      if (from) {
        const start = new Date(`${from}T00:00:00`);
        if (runDate < start) return false;
      }
      if (to) {
        const end = new Date(`${to}T23:59:59`);
        if (runDate > end) return false;
      }
    }
    if (!query) return true;
    return [
      run.run_id,
      run.scenario_id,
      run.scenario_name,
      run.team_type,
      run.environment,
    ].some((part) => String(part || '').toLowerCase().includes(query));
  });
  return filtered.sort((a, b) => {
    let delta = 0;
    if (sortKey === 'steps') {
      delta = Number(a.ticks || 0) - Number(b.ticks || 0);
    } else if (sortKey === 'outcome') {
      delta = outcomeRank(a) - outcomeRank(b);
    } else {
      delta = new Date(a.timestamp || 0).getTime() - new Date(b.timestamp || 0).getTime();
    }
    return sortDir === 'asc' ? delta : -delta;
  });
}

function renderStats(){
  $('statTotalRuns').textContent = allRuns.length;
  const successCount = allRuns.filter((run) => outcomeLabel(run) === 'Success').length;
  $('statSuccessRate').textContent = allRuns.length ? `${Math.round((successCount / allRuns.length) * 100)}%` : '—';
  $('statLastScenario').textContent = allRuns.length ? scenarioLabel(allRuns[0]) : '—';
  const avgSteps = allRuns.length
    ? allRuns.reduce((sum, run) => sum + Number(run.ticks || 0), 0) / allRuns.length
    : 0;
  $('statAverageSteps').textContent = allRuns.length ? avgSteps.toFixed(1) : '—';
}

function renderFilter(){
  const scenarios = [...new Set(allRuns.map((run) => scenarioLabel(run)).filter(Boolean))];
  const teams = [...new Set(allRuns.map((run) => teamLabel(run.team_type || run.config?.team_type)).filter((value) => value && value !== '—'))];
  const outcomes = [...new Set(allRuns.map((run) => outcomeLabel(run)).filter(Boolean))];
  const currentScenario = $('scenarioFilter').value || 'all';
  const currentTeam = $('teamFilter').value || 'all';
  const currentOutcome = $('outcomeFilter').value || 'all';
  $('scenarioFilter').innerHTML = ['<option value="all">All Scenarios</option>']
    .concat(scenarios.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`))
    .join('');
  $('scenarioFilter').value = scenarios.includes(currentScenario) || currentScenario === 'all' ? currentScenario : 'all';

  $('teamFilter').innerHTML = ['<option value="all">All Teams</option>']
    .concat(teams.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`))
    .join('');
  $('teamFilter').value = teams.includes(currentTeam) || currentTeam === 'all' ? currentTeam : 'all';

  $('outcomeFilter').innerHTML = ['<option value="all">All Outcomes</option>']
    .concat(outcomes.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`))
    .join('');
  $('outcomeFilter').value = outcomes.includes(currentOutcome) || currentOutcome === 'all' ? currentOutcome : 'all';
}

// Tracks the run IDs rendered in the last tbody write so we can skip
// an identical repaint (e.g. background refresh with no new data).
let _lastRenderedKey = '';

function renderTable(){
  const tbody = $('runsTableBody');
  const runs = currentRuns();
  const pageCount = Math.max(1, Math.ceil(runs.length / PAGE_SIZE));
  if (currentPage > pageCount) currentPage = pageCount;
  const start = (currentPage - 1) * PAGE_SIZE;
  const pageRuns = runs.slice(start, start + PAGE_SIZE);
  const visibleRunIds = pageRuns.map((run) => run.run_id);
  const selectedVisibleCount = visibleRunIds.filter((runId) => selectedRunIds.has(runId)).length;
  const totalSelected = selectedRunIds.size;
  const end = Math.min(start + pageRuns.length, runs.length);

  $('pageStatus').textContent = runs.length
    ? `Showing ${start + 1}–${end} of ${runs.length} runs · Page ${currentPage} of ${pageCount}`
    : 'Showing 0 of 0 runs';
  $('prevBtn').disabled = currentPage <= 1;
  $('nextBtn').disabled = currentPage >= pageCount;
  $('clearHistoryBtn').disabled = allRuns.length === 0;
  $('deleteSelectedBtn').disabled = totalSelected === 0;
  $('compareSelectedBtn').disabled = totalSelected < 2;
  updateSortIndicators();
  if (!$('selectionStatus').classList.contains('error') && !$('selectionStatus').classList.contains('success')) {
    const defaultSelectionMessage = totalSelected === 0
      ? 'Select 2 or more runs to compare, or choose a run to replay, inspect, or delete.'
      : totalSelected === 1
        ? '1 run selected. Select one more run to compare.'
        : `${totalSelected} runs selected. Compare or delete them from Run History.`;
    setSelectionStatus(defaultSelectionMessage, 'info');
  }
  $('selectAllRuns').checked = !!visibleRunIds.length && selectedVisibleCount === visibleRunIds.length;
  $('selectAllRuns').indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < visibleRunIds.length;

  // Build a stable cache key: the ordered run IDs plus their selection state.
  // Including selection avoids stale checkboxes after a select-all / deselect.
  const renderKey = visibleRunIds.map((id) => id + (selectedRunIds.has(id) ? '+' : '')).join(',')
    + (pageRuns.length ? '' : ':empty');

  if (!pageRuns.length) {
    if (_lastRenderedKey !== ':empty') {
      _lastRenderedKey = ':empty';
      const emptyMsg = allRuns.length === 0
      ? 'No saved runs yet. Start a simulation to create your first run.'
        : 'No saved runs match this filter.';
      tbody.innerHTML = `<tr><td colspan="9" class="empty-table">${emptyMsg}</td></tr>`;
    }
    return;
  }

  // Skip the DOM write entirely when the visible page is unchanged.
  // This prevents the repaint flicker on background auto-refreshes where
  // the run list hasn't actually changed.
  if (renderKey === _lastRenderedKey) return;
  _lastRenderedKey = renderKey;

  // Suppress row transitions during the swap so newly inserted rows don't
  // flash through the hover/box-shadow transition on first paint.
  tbody.classList.add('is-updating');

  tbody.innerHTML = pageRuns.map((run) => `
    <tr class="${isInteractionRun(run) ? 'interactive-row' : ''}" ${isInteractionRun(run) ? `data-summary-run="${escapeHtml(run.run_id)}"` : ''}>
      <td class="select-cell">
        <input class="run-select" type="checkbox" data-run="${escapeHtml(run.run_id)}" ${selectedRunIds.has(run.run_id) ? 'checked' : ''} aria-label="Select run ${escapeHtml(run.run_id)}" />
      </td>
      <td><span class="run-id">${escapeHtml(run.run_id)}</span></td>
      <td>
        <div class="scenario-cell">
          <span class="scenario-dot ${scenarioClass(run)}"></span>
          <span>${escapeHtml(scenarioLabel(run))}</span>
        </div>
      </td>
      <td>${escapeHtml(teamLabel(run.team_type || run.config?.team_type))}</td>
      <td><span class="mode-badge">${escapeHtml(modeLabel(run))}</span></td>
      <td>${escapeHtml(String(run.ticks || 0))}</td>
      <td><span class="badge ${outcomeClass(run)}">${escapeHtml(outcomeLabel(run))}</span></td>
      <td>${escapeHtml(formatDate(run.timestamp))}</td>
      <td>
        <div class="action-group">
          <button class="inspect-btn" data-run="${escapeHtml(run.run_id)}">Inspect</button>
          <button class="replay-btn" data-run="${escapeHtml(run.run_id)}">▶ Replay</button>
          <button class="delete-btn" data-run="${escapeHtml(run.run_id)}">Delete</button>
        </div>
      </td>
    </tr>
  `).join('');

  // Re-enable transitions after the browser has committed the new layout.
  requestAnimationFrame(() => tbody.classList.remove('is-updating'));

  document.querySelectorAll('.replay-btn').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      const run = allRuns.find((r) => r.run_id === button.dataset.run);
      // Route each mode to its correct page:
      //   watch_replay       → dashboard.html  (Watch Mode timeline/results view)
      //   interactive_replay → interactive.html (Live Interactive read-only replay view)
      // Never open a modal here — the Inspect button handles the static modal.
      const isInteractive = Boolean(run && isInteractionRun(run));
      const targetPage = isInteractive ? 'interactive.html' : 'dashboard.html';
      const replayMode = isInteractive ? 'interactive_replay' : 'watch_replay';
      const target = new URL(targetPage, window.location.href);
      target.searchParams.set('run_id', button.dataset.run);
      target.searchParams.set('mode', replayMode);
      window.location.href = target.toString();
    });
  });

  document.querySelectorAll('.inspect-btn').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      openInteractionSummary(button.dataset.run);
    });
  });

  document.querySelectorAll('.delete-btn').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      deleteRun(button.dataset.run);
    });
  });

  document.querySelectorAll('.run-select').forEach((checkbox) => {
    checkbox.addEventListener('click', (event) => {
      event.stopPropagation();
    });
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) selectedRunIds.add(checkbox.dataset.run);
      else selectedRunIds.delete(checkbox.dataset.run);
      renderTable();
    });
  });

  document.querySelectorAll('#runsTableBody tr[data-summary-run]').forEach((row) => {
    row.addEventListener('click', () => openInteractionSummary(row.dataset.summaryRun));
  });

}

async function loadRuns({ showSkeleton = allRuns.length === 0 && !isReloadingAfterDelete } = {}){
  // Only show the shimmer skeleton on the very first load when the table is
  // empty. Background auto-refreshes silently update the data so the user
  // never sees a flash of skeleton rows replacing real content.
  if (showSkeleton) showLoadingSkeleton();
  const response = await fetch(`${API}/history/runs`, { headers: authHeader(), signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error(await parseApiError(response));
  const data = await response.json();
  allRuns = Array.isArray(data.runs) ? data.runs : [];
  selectedRunIds = new Set(Array.from(selectedRunIds).filter((runId) => allRuns.some((run) => run.run_id === runId)));
  renderStats();
  renderFilter();
  renderTable();
  const ss = $('selectionStatus');
  if (ss && !ss.classList.contains('success')) {
    setSelectionStatus('Select 2 or more runs to compare, or choose a run to replay, inspect, or delete.', 'info');
  }
}

async function refreshHistoryFromBackend(){
  const wasOnline = backendOnline;
  try {
    await loadRuns();
    backendOnline = true;
    if (wasOnline === false) {
      setOfflineBanner('Backend is back online — history refreshed.', 'success');
      setTimeout(() => setOfflineBanner(''), 4000);
    } else {
      setOfflineBanner('');
    }
  } catch(error) {
    backendOnline = false;
    if (wasOnline !== false) {
      // First detected failure — show the banner and update the table if empty.
      setOfflineBanner('Backend is offline. Showing last known data. Will retry automatically.', 'error');
      setSelectionStatus('Backend went offline. History will refresh when it comes back.', 'error');
      if (allRuns.length === 0) {
        const isTimeout = error.name === 'TimeoutError' || error.name === 'AbortError';
        const msg = isTimeout ? 'Request timed out — backend may be slow or offline.' : (error.message || String(error));
        const tbody = $('runsTableBody');
        if (tbody) tbody.innerHTML = `<tr><td colspan="9" class="empty-table">Could not load saved runs. ${escapeHtml(msg)}</td></tr>`;
      }
    }
  }
}

function startAutoRefresh(){
  if (refreshTimer) window.clearInterval(refreshTimer);
  refreshTimer = window.setInterval(() => {
    if (document.hidden) return;
    refreshHistoryFromBackend();
  }, REFRESH_INTERVAL_MS);
}

// Debounce search so rapid keystrokes don't trigger a full re-render on every
// character — 150 ms is fast enough to feel instant while avoiding flicker.
let _searchDebounceTimer = null;
$('searchInput').addEventListener('input', () => {
  clearTimeout(_searchDebounceTimer);
  _searchDebounceTimer = setTimeout(() => {
    currentPage = 1;
    renderTable();
  }, 150);
});

$('scenarioFilter').addEventListener('change', () => {
  currentPage = 1;
  renderTable();
});

$('teamFilter').addEventListener('change', () => {
  currentPage = 1;
  renderTable();
});

$('outcomeFilter').addEventListener('change', () => {
  currentPage = 1;
  renderTable();
});

$('dateFrom').addEventListener('change', () => {
  currentPage = 1;
  renderTable();
});

$('dateTo').addEventListener('change', () => {
  currentPage = 1;
  renderTable();
});

$('selectAllRuns').addEventListener('change', () => {
  const runs = currentRuns();
  const start = (currentPage - 1) * PAGE_SIZE;
  const pageRuns = runs.slice(start, start + PAGE_SIZE);
  pageRuns.forEach((run) => {
    if ($('selectAllRuns').checked) selectedRunIds.add(run.run_id);
    else selectedRunIds.delete(run.run_id);
  });
  renderTable();
});

$('deleteSelectedBtn').addEventListener('click', deleteSelectedRuns);
$('compareSelectedBtn').addEventListener('click', openCompareSummary);
$('clearHistoryBtn').addEventListener('click', clearHistory);

$('sortStepsBtn').addEventListener('click', () => setSort('steps'));
$('sortOutcomeBtn').addEventListener('click', () => setSort('outcome'));
$('sortDateBtn').addEventListener('click', () => setSort('date'));

$('prevBtn').addEventListener('click', () => {
  if (currentPage > 1) {
    currentPage -= 1;
    renderTable();
  }
});

$('nextBtn').addEventListener('click', () => {
  const pageCount = Math.max(1, Math.ceil(currentRuns().length / PAGE_SIZE));
  if (currentPage < pageCount) {
    currentPage += 1;
    renderTable();
  }
});

$('historyModalClose').addEventListener('click', closeModal);
$('historyModal').addEventListener('click', (event) => {
  if (event.target === $('historyModal')) closeModal();
});
window.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && !$('historyModal').hidden) closeModal();
});

refreshHistoryFromBackend();
startAutoRefresh();

window.addEventListener('focus', refreshHistoryFromBackend);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) refreshHistoryFromBackend();
});
