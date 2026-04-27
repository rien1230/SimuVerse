// History page logic for loading runs, filtering them, and paging the results.
const API = window.SimuVerseAPI.API_BASE;
const PAGE_SIZE = 4;
const REFRESH_INTERVAL_MS = 8000;

let allRuns = [];
let currentPage = 1;
let selectedRunIds = new Set();
let refreshTimer = null;
let backendOnline = null;

function $(id){ return document.getElementById(id); }

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

function outcomeClass(outcome){
  const raw = String(outcome || '').toLowerCase();
  if (raw === 'success') return 'success';
  if (raw === 'partial' || raw === 'partial_success') return 'partial';
  if (raw === 'failure' || raw === 'failed' || raw === 'meltdown') return 'failure';
  if (raw === 'deadlock') return 'deadlock';
  return 'unknown';
}

function outcomeLabel(outcome){
  const raw = String(outcome || '').toLowerCase();
  if (raw === 'partial_success') return 'Partial Success';
  if (raw === 'failure') return 'Failed';
  return raw ? raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : 'Unknown';
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
  return run?.config?.source === "interactive" || Number(run?.intervention_count || 0) > 0;
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

function extractConversation(history){
  const out = [];
  for (const tick of history || []) {
    for (const event of tick.events || []) {
      if (!event?.text) continue;
      out.push({
        tick: tick.tick,
        actor: event.actor || 'Agent',
        target: event.target || '',
        type: eventLabel(event.type),
        text: cleanMessage(event.text),
        isUser: String(event.actor || '').toUpperCase() === 'USER'
      });
    }
  }
  return out;
}

function extractInterventionMessages(run, conversation){
  const fromHistory = conversation
    .filter((entry) => entry.isUser)
    .map((entry) => entry.text)
    .filter(Boolean);
  if (fromHistory.length) return fromHistory;
  return (run.interventions || [])
    .map((entry) => cleanMessage(entry?.message || entry?.summary || entry?.type))
    .filter(Boolean);
}

function openModal(){
  $('historyModal').hidden = false;
}

function closeModal(){
  $('historyModal').hidden = true;
}

function setSelectionStatus(message, kind = 'info'){
  const el = $('selectionStatus');
  if (!el) return;
  el.textContent = message;
  el.className = `selection-status ${kind}`;
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
  tbody.innerHTML = Array.from({ length: 4 }, () => `
    <tr class="skeleton-row">
      <td class="select-cell"></td>
      <td><div class="skeleton-cell short"></div></td>
      <td><div class="skeleton-cell wide"></div></td>
      <td><div class="skeleton-cell short"></div></td>
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
    });
    if (!response.ok) throw new Error(await parseApiError(response));

    allRuns = allRuns.filter((run) => run.run_id !== runId);
    renderStats();
    renderFilter();
    renderTable();
    setSelectionStatus(`Run ${runId} was deleted from history.`, 'success');

    if (!$('historyModal').hidden && $('historyModalTitle').textContent.includes(runId)) {
      closeModal();
    }
  }catch(error){
    setSelectionStatus(`Could not delete run ${runId}. ${error.message || String(error)}`, 'error');
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

  if (failed.length) {
    setSelectionStatus(`Some runs could not be deleted: ${failed.join(' · ')}`, 'error');
  } else {
    setSelectionStatus(`Deleted ${runIds.length} selected run${runIds.length === 1 ? '' : 's'}.`, 'success');
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
    setSelectionStatus(data.message || 'Saved history was cleared.', 'success');
  }catch(error){
    setSelectionStatus(`Could not clear saved history. ${error.message || String(error)}`, 'error');
  }
}

async function openInteractionSummary(runId){
  $('historyModalTitle').textContent = 'Interactive Run Summary';
  $('historyModalSubtitle').textContent = 'Loading the saved conversation log…';
  $('historyModalSummary').innerHTML = '';
  $('historyModalLog').innerHTML = '<div class="modal-empty">Loading saved interaction history…</div>';
  openModal();

  try{
    const response = await fetch(`${API}/history/runs/${runId}`);
    if (!response.ok) throw new Error(await parseApiError(response));
    const run = await response.json();
    const conversation = extractConversation(run.history || []);
    const interventionMessages = extractInterventionMessages(run, conversation);
    const blocker = itemLabel(run.group_state?.bottleneck_item);

    $('historyModalTitle').textContent = `${scenarioLabel(run)} · Run ${run.run_id}`;
    $('historyModalSubtitle').textContent = `${teamLabel(run.team_type || run.config?.team_type)} · ${outcomeLabel(run.outcome)} · ${run.ticks || 0} steps`;

    $('historyModalSummary').innerHTML = `
      <section class="modal-card">
        <h4>What Happened</h4>
        <ul class="what-list">
          <li>This run used ${escapeHtml(String(run.intervention_count || interventionMessages.length || 0))} intervention${(run.intervention_count || interventionMessages.length || 0) === 1 ? '' : 's'}.</li>
          <li>It ended as <strong>${escapeHtml(outcomeLabel(run.outcome))}</strong> after ${escapeHtml(String(run.ticks || 0))} steps.</li>
          <li>The final blocker state was <strong>${escapeHtml(blocker)}</strong>.</li>
          ${interventionMessages.length ? `<li>Interventions used: ${escapeHtml(interventionMessages.slice(0, 4).join(' · '))}</li>` : ''}
        </ul>
      </section>
      <section class="modal-card">
        <h4>Run Snapshot</h4>
        <div class="modal-stats">
          <div class="modal-stat">
            <div class="modal-stat-label">Scenario</div>
            <div class="modal-stat-value">${escapeHtml(scenarioLabel(run))}</div>
          </div>
          <div class="modal-stat">
            <div class="modal-stat-label">Team</div>
            <div class="modal-stat-value">${escapeHtml(teamLabel(run.team_type || run.config?.team_type))}</div>
          </div>
          <div class="modal-stat">
            <div class="modal-stat-label">Final Progress</div>
            <div class="modal-stat-value">${escapeHtml(String(Math.round(Number(run.final_progress || 0) * 100)))}%</div>
          </div>
          <div class="modal-stat">
            <div class="modal-stat-label">Peak Tension</div>
            <div class="modal-stat-value">${escapeHtml(Number(run.peak_tension || run.group_state?.tension || 0).toFixed(2))}</div>
          </div>
        </div>
      </section>
    `;

    $('historyModalLog').innerHTML = conversation.length
      ? conversation.map((entry) => `
        <article class="log-card ${entry.isUser ? 'user' : ''}">
          <div class="log-meta">
            <span>Step ${escapeHtml(String(entry.tick || 0))}</span>
            <span class="log-actor">${escapeHtml(entry.actor)}</span>
            ${entry.target ? '<span>→</span><span class="log-target">' + escapeHtml(entry.target) + '</span>' : ''}
            <span class="log-type">${escapeHtml(entry.type)}</span>
          </div>
          <div class="log-text">${escapeHtml(entry.text)}</div>
        </article>
      `).join('')
      : '<div class="modal-empty">No saved conversation events were found for this run.</div>';
  }catch(error){
    $('historyModalSummary').innerHTML = '';
    $('historyModalLog').innerHTML = `<div class="modal-empty">Could not load this interactive run summary. ${escapeHtml(error.message || String(error))}</div>`;
  }
}

function currentRuns(){
  const query = ($('searchInput').value || '').trim().toLowerCase();
  const scenario = $('scenarioFilter').value || 'all';
  const team = $('teamFilter').value || 'all';
  const from = $('dateFrom').value || '';
  const to = $('dateTo').value || '';
  const filtered = allRuns.filter((run) => {
    if (scenario !== 'all' && scenarioLabel(run) !== scenario) return false;
    if (team !== 'all' && teamLabel(run.team_type || run.config?.team_type) !== team) return false;
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
  return filtered;
}

function renderStats(){
  $('statTotalRuns').textContent = allRuns.length;
  $('statSavedReplays').textContent = allRuns.length;
  $('statLastScenario').textContent = allRuns.length ? scenarioLabel(allRuns[0]) : '—';
}

function renderFilter(){
  const scenarios = [...new Set(allRuns.map((run) => scenarioLabel(run)).filter(Boolean))];
  const teams = [...new Set(allRuns.map((run) => teamLabel(run.team_type || run.config?.team_type)).filter((value) => value && value !== '—'))];
  const currentScenario = $('scenarioFilter').value || 'all';
  const currentTeam = $('teamFilter').value || 'all';
  $('scenarioFilter').innerHTML = ['<option value="all">All Scenarios</option>']
    .concat(scenarios.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`))
    .join('');
  $('scenarioFilter').value = scenarios.includes(currentScenario) || currentScenario === 'all' ? currentScenario : 'all';

  $('teamFilter').innerHTML = ['<option value="all">All Teams</option>']
    .concat(teams.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`))
    .join('');
  $('teamFilter').value = teams.includes(currentTeam) || currentTeam === 'all' ? currentTeam : 'all';
}

function renderTable(){
  const runs = currentRuns();
  const pageCount = Math.max(1, Math.ceil(runs.length / PAGE_SIZE));
  if (currentPage > pageCount) currentPage = pageCount;
  const start = (currentPage - 1) * PAGE_SIZE;
  const pageRuns = runs.slice(start, start + PAGE_SIZE);
  const visibleRunIds = pageRuns.map((run) => run.run_id);
  const selectedVisibleCount = visibleRunIds.filter((runId) => selectedRunIds.has(runId)).length;
  const totalSelected = selectedRunIds.size;

  $('pageStatus').textContent = `Page ${currentPage} of ${pageCount}`;
  $('prevBtn').disabled = currentPage <= 1;
  $('nextBtn').disabled = currentPage >= pageCount;
  $('clearHistoryBtn').disabled = allRuns.length === 0;
  $('deleteSelectedBtn').disabled = totalSelected === 0;
  if (!$('selectionStatus').classList.contains('error') && !$('selectionStatus').classList.contains('success')) {
    setSelectionStatus(
      totalSelected
        ? `${totalSelected} run${totalSelected === 1 ? '' : 's'} selected.`
        : 'No runs selected.',
      'info'
    );
  }
  $('selectAllRuns').checked = !!visibleRunIds.length && selectedVisibleCount === visibleRunIds.length;
  $('selectAllRuns').indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < visibleRunIds.length;

  if (!pageRuns.length) {
    $('runsTableBody').innerHTML = '<tr><td colspan="8" class="empty-table">No saved runs match this filter.</td></tr>';
    return;
  }

  $('runsTableBody').innerHTML = pageRuns.map((run) => `
    <tr class="${isInteractionRun(run) ? 'interactive-row' : ''}" ${isInteractionRun(run) ? `data-summary-run="${escapeHtml(run.run_id)}"` : ''}>
      <td class="select-cell">
        <input class="run-select" type="checkbox" data-run="${escapeHtml(run.run_id)}" ${selectedRunIds.has(run.run_id) ? 'checked' : ''} aria-label="Select run ${escapeHtml(run.run_id)}" />
      </td>
      <td>${escapeHtml(run.run_id)}</td>
      <td>
        <div class="scenario-cell">
          <span class="scenario-dot ${scenarioClass(run)}"></span>
          <span>${escapeHtml(scenarioLabel(run))}</span>
        </div>
      </td>
      <td>${escapeHtml(teamLabel(run.team_type || run.config?.team_type))}</td>
      <td>${escapeHtml(String(run.ticks || 0))}</td>
      <td><span class="badge ${outcomeClass(run.outcome)}">${escapeHtml(outcomeLabel(run.outcome))}</span></td>
      <td>${escapeHtml(formatDate(run.timestamp))}</td>
      <td>
        <div class="action-group">
          <button class="replay-btn" data-run="${escapeHtml(run.run_id)}">▶ Replay</button>
          <button class="delete-btn" data-run="${escapeHtml(run.run_id)}">Delete</button>
        </div>
      </td>
    </tr>
  `).join('');

  document.querySelectorAll('.replay-btn').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      const run = allRuns.find((r) => r.run_id === button.dataset.run);
      if (run && isInteractionRun(run)) {
        openInteractionSummary(button.dataset.run);
      } else {
        const target = new URL('dashboard.html', window.location.href);
        target.searchParams.set('run_id', button.dataset.run);
        target.searchParams.set('mode', 'step');
        window.location.href = target.toString();
      }
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

async function checkHealth(){
  try{
    const response = await fetch(`${API}/health`, { signal: AbortSignal.timeout(4000) });
    if (!response.ok) throw new Error('offline');
    backendOnline = true;
  }catch{
    backendOnline = false;
  }
}

async function loadRuns(){
  showLoadingSkeleton();
  try{
    const response = await fetch(`${API}/history/runs`, { signal: AbortSignal.timeout(10000) });
    if (!response.ok) throw new Error(await parseApiError(response));
    const data = await response.json();
    allRuns = Array.isArray(data.runs) ? data.runs : [];
    selectedRunIds = new Set(Array.from(selectedRunIds).filter((runId) => allRuns.some((run) => run.run_id === runId)));
    setOfflineBanner('');
    renderStats();
    renderFilter();
    renderTable();
    const ss = $('selectionStatus');
    if (ss && !ss.classList.contains('success')) {
      setSelectionStatus('Select runs to replay or delete them from saved history.', 'info');
    }
  }catch(error){
    const isTimeout = error.name === 'TimeoutError' || error.name === 'AbortError';
    const msg = isTimeout ? 'Request timed out — backend may be slow or offline.' : (error.message || String(error));
    const tbody = $('runsTableBody');
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-table">Could not load saved runs. ${escapeHtml(msg)}</td></tr>`;
    }
    setSelectionStatus(`Could not load saved history. ${msg}`, 'error');
  }
}

async function refreshHistoryFromBackend(){
  const wasOnline = backendOnline;
  await checkHealth();
  if (backendOnline) {
    await loadRuns();
    if (wasOnline === false) {
      setOfflineBanner('Backend is back online — history refreshed.', 'success');
      setTimeout(() => setOfflineBanner(''), 4000);
    } else {
      setOfflineBanner('');
    }
  } else {
    if (wasOnline !== false) {
      setOfflineBanner('Backend is offline. Showing last known data. Will retry automatically.', 'error');
      setSelectionStatus('Backend went offline. History will refresh when it comes back.', 'error');
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

$('searchInput').addEventListener('input', () => {
  currentPage = 1;
  renderTable();
});

$('scenarioFilter').addEventListener('change', () => {
  currentPage = 1;
  renderTable();
});

$('teamFilter').addEventListener('change', () => {
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
$('clearHistoryBtn').addEventListener('click', clearHistory);

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
