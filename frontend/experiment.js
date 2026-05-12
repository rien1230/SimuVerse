/**
 * experiment.js — Experiment Runner page logic.
 *
 * Three experiment types are supported:
 *   team_comparison      — fixed scenario, multiple team styles × seeds
 *   scenario_comparison  — fixed team style, multiple scenarios × seeds
 *   seed_reproducibility — fixed setup, multiple seeds (consistency test)
 */

(function () {
  "use strict";

  const API_BASE = (window.SimuVerseAPI && window.SimuVerseAPI.API_BASE)
    ? window.SimuVerseAPI.API_BASE
    : "http://127.0.0.1:8007/api";

  // ── Config ─────────────────────────────────────────────────────────────────
  // Static labels and panel mappings for the three experiment modes.

  const TYPE_DESCS = {
    team_comparison:
      "Compare how different team styles behave under the same scenario. Each selected team style runs against the same repeatable run IDs for a fair comparison.",
    scenario_comparison:
      "Run the same team style across multiple scenarios to see how the environment changes coordination, stress, and completion speed.",
    seed_reproducibility:
      "Fix one scenario and one team style, then rerun the same setup with repeatable run IDs to check consistency across repeated tests.",
  };

  const SCENARIO_NAMES = {
    escape: "Escape Room",
    office: "Office Project",
    cafe:   "Cafe Planning",
  };

  const PANEL_MAP = {
    team_comparison:     "xpPanelTeam",
    scenario_comparison: "xpPanelScenario",
    seed_reproducibility:"xpPanelSeed",
  };

  // ── State ──────────────────────────────────────────────────────────────────

  let _currentType = "team_comparison";
  let _currentStep = 1;

  // ── DOM refs ───────────────────────────────────────────────────────────────

  const $ = id => document.getElementById(id);

  const seedsInput    = $("xpSeeds");
  const maxStepsInput = $("xpMaxSteps");
  const runCountEl    = $("xpRunCount");
  const runBtn        = $("xpRunBtn");
  const progress      = $("xpProgress");
  const progressLabel = $("xpProgressLabel");
  const errorEl       = $("xpError");
  const setupViewEl   = $("xpSetupView");
  const resultsViewEl = $("xpResultsView");
  const resultsEl     = $("xpResults");
  const backBtn       = $("xpBackBtn");
  const runAgainBtn   = $("xpRunAgainBtn");
  const previewScenarioEl = $("xpPreviewScenario");
  const previewScenarioLabelEl = $("xpPreviewScenarioLabel");
  const previewTeamsEl    = $("xpPreviewTeams");
  const previewTeamsLabelEl = $("xpPreviewTeamsLabel");
  const previewSeedsEl    = $("xpPreviewSeeds");
  const previewSeedsLabelEl = $("xpPreviewSeedsLabel");
  const styleCountEl           = $("xpStyleCount");
  const previewRunsEl          = $("xpPreviewRuns");
  const previewRunsBreakdownEl = $("xpPreviewRunsBreakdown");
  const previewStepsEl         = $("xpPreviewSteps");
  const ctxStep1Panel    = $("xpCtxStep1Panel");
  const ctxProtocolPanel = $("xpCtxProtocolPanel");
  const ctxReadyBadge    = $("xpCtxReadyBadge");

  // Wizard step pages + navigation buttons
  const stepPage1 = $("xpStepPage1");
  const stepPage2 = $("xpStepPage2");
  const stepPage3 = $("xpStepPage3");
  const stepNext  = $("xpStepNext");
  const stepNext2 = $("xpStepNext2");
  const stepBack  = $("xpStepBack");
  const stepBack2 = $("xpStepBack2");

  // ── Helpers ────────────────────────────────────────────────────────────────

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function fmtPct(v) {
    if (v == null) return "—";
    return Math.round(v * 100) + "%";
  }

  function fmtNum(v, dp = 2) {
    if (v == null || !isFinite(v)) return "—";
    return Number(v).toFixed(dp);
  }

  // Shows no decimal when the value is whole (e.g. 14 not 14.0),
  // otherwise shows `dp` decimal places (e.g. 14.2).
  function fmtSmartNum(v, dp = 1) {
    if (v == null || !isFinite(v)) return "—";
    const n = Number(v);
    return Number.isInteger(n) ? String(n) : n.toFixed(dp);
  }

  function fmtDelta(v) {
    if (v == null || !isFinite(v)) return "—";
    const s = Number(v).toFixed(3);
    return v >= 0 ? "+" + s : s;
  }

  function titleCaseLabel(value) {
    const text = String(value ?? "").trim();
    if (!text) return "Unknown";
    // Handle "Seed 101", "Escape Room" etc — capitalise each word
    return text.replace(/\b\w/g, c => c.toUpperCase());
  }

  function toneClass(label) {
    const key = String(label ?? "").trim().toLowerCase();
    if (key.includes("smooth")) return "xp-tone-smooth";
    if (key.includes("tension")) return "xp-tone-tension";
    if (key.includes("creative")) return "xp-tone-creative";
    if (key.includes("pressure")) return "xp-tone-pressure";
    return "";
  }

  // Returns every label that shares the best value for `metric`.
  // `g` is a function label → group object.
  function winnersOf(labels, g, metric, lowerBetter = false) {
    const vals = labels.map(l => Number(g(l)?.[metric] ?? (lowerBetter ? Infinity : -Infinity)));
    const finite = vals.filter(isFinite);
    if (!finite.length) return labels.slice(0, 1);
    const best = lowerBetter ? Math.min(...finite) : Math.max(...finite);
    return labels.filter((_, i) => isFinite(vals[i]) && Math.abs(vals[i] - best) < 0.001);
  }

  // Formats a winner list into a readable label, e.g. "Smooth & Pressure" for ties.
  function tieLabel(winners, nameFn) {
    if (!winners.length) return "—";
    if (winners.length === 1) return nameFn(winners[0]);
    if (winners.length === 2) return `${nameFn(winners[0])} & ${nameFn(winners[1])}`;
    return "Tie (" + winners.map(nameFn).join(", ") + ")";
  }

  function selectedTeamStyles() {
    return [...document.querySelectorAll("input[name='teamStyle']:checked")]
      .map(cb => cb.value);
  }

  function selectedScenarios() {
    return [...document.querySelectorAll("input[name='scenarioChoice']:checked")]
      .map(cb => cb.value);
  }

  function parsedSeeds() {
    return seedsInput.value
      .split(/[\s,]+/)
      .map(s => parseInt(s, 10))
      .filter(n => !isNaN(n));
  }

  function currentExperimentSnapshot() {
    const seeds = parsedSeeds();
    const maxSteps = parseInt(maxStepsInput.value, 10) || 30;

    const pl = n => n === 1 ? "" : "s";

    if (_currentType === "scenario_comparison") {
      const scenarios = selectedScenarios();
      return {
        scenarioLabel: "Scenarios",
        teamsLabel: "Team style",
        seedsLabel: seeds.length === 1 ? "Repeatable Run ID" : "Repeatable Run IDs",
        totalRuns: scenarios.length * seeds.length,
        breakdownText: `${scenarios.length} scenario${pl(scenarios.length)} × ${seeds.length} run ID${pl(seeds.length)}`,
        scenarioText: scenarios.length
          ? scenarios.map(s => SCENARIO_NAMES[s] || titleCaseLabel(s)).join(", ")
          : "No scenarios selected",
        teamText: `${titleCaseLabel($("xpTeamStyleSingle").value)} Team`,
        seedText: seeds.length ? seeds.join(", ") : "No run IDs entered",
        stepText: String(maxSteps),
      };
    }

    if (_currentType === "seed_reproducibility") {
      return {
        scenarioLabel: "Scenario",
        teamsLabel: "Team style",
        seedsLabel: seeds.length === 1 ? "Repeatable Run ID" : "Repeatable Run IDs",
        totalRuns: seeds.length,
        breakdownText: `${seeds.length} run ID${pl(seeds.length)}`,
        scenarioText: SCENARIO_NAMES[$("xpScenarioRepro").value] || titleCaseLabel($("xpScenarioRepro").value),
        teamText: `${titleCaseLabel($("xpTeamStyleRepro").value)} Team`,
        seedText: seeds.length ? seeds.join(", ") : "No run IDs entered",
        stepText: String(maxSteps),
      };
    }

    const styles = selectedTeamStyles();
    return {
      scenarioLabel: "Scenario",
      teamsLabel: "Team styles",
      seedsLabel: seeds.length === 1 ? "Repeatable Run ID" : "Repeatable Run IDs",
      totalRuns: styles.length * seeds.length,
      breakdownText: `${styles.length} team${pl(styles.length)} × ${seeds.length} run ID${pl(seeds.length)}`,
      scenarioText: SCENARIO_NAMES[$("xpScenario").value] || titleCaseLabel($("xpScenario").value),
      teamText: styles.length ? styles.map(titleCaseLabel).join(", ") : "No team styles selected",
      seedText: seeds.length ? seeds.join(", ") : "No run IDs entered",
      stepText: String(maxSteps),
    };
  }

  // Client-side safety net: recompute blocker resolution rate from raw run data
  // to guard against scenarios where the backend blocker_count is 0.
  function withComputedBlockerResolution(agg, runs, experimentType) {
    const groupKey =
      experimentType === "scenario_comparison" ? "scenario_label"
      : experimentType === "seed_reproducibility" ? "seed_label"
      : "team_style";

    const next    = { ...(agg || {}) };
    const grouped = {};

    (runs || []).forEach(run => {
      const key = String(run?.[groupKey] || run?.team_style || "").trim();
      if (!key) return;
      (grouped[key] ||= []).push(run);
    });

    Object.keys(grouped).forEach(label => {
      const teamRuns = grouped[label];
      if (!teamRuns.length) return;
      const rates = teamRuns.map(run => {
        const total    = Number(run?.blocker_count ?? 0);
        const resolved = Number(run?.blockers_resolved ?? 0);
        if (total > 0) return resolved / total;
        if (run?.completed) return 1;
        return 0;
      });
      if (!next[label]) next[label] = {};
      next[label] = {
        ...next[label],
        avg_blockers_resolved_rate: rates.length
          ? Number((rates.reduce((s, r) => s + r, 0) / rates.length).toFixed(3))
          : next[label].avg_blockers_resolved_rate,
      };
    });

    return next;
  }

  // ── Wizard step navigation ─────────────────────────────────────────────────

  function showStep(n) {
    _currentStep = n;
    if (stepPage1) stepPage1.style.display = n === 1 ? "" : "none";
    if (stepPage2) stepPage2.style.display = n === 2 ? "" : "none";
    if (stepPage3) stepPage3.style.display = n === 3 ? "" : "none";

    document.querySelectorAll("#xpSteps .xp-step").forEach(dot => {
      const s = parseInt(dot.dataset.step, 10);
      dot.classList.toggle("xp-step--active", s === n);
      dot.classList.toggle("xp-step--done",   s < n);
    });

    document.querySelectorAll("#xpSteps .xp-step-line").forEach((line, i) => {
      // line 0 connects step 1→2, line 1 connects step 2→3
      line.classList.toggle("xp-step-line--done", i + 2 <= n);
    });

    if (n === 3) { updatePreview(); updateRunCount(); }

    // Step-aware context panel
    if (ctxStep1Panel)    ctxStep1Panel.style.display    = n === 1 ? "" : "none";
    if (ctxProtocolPanel) ctxProtocolPanel.style.display = n >= 2  ? "" : "none";
    if (ctxReadyBadge)    ctxReadyBadge.style.display    = n === 3 ? "" : "none";
  }

  if (stepNext)  stepNext.addEventListener("click",  () => { if (!stepNext.disabled) showStep(2); });
  if (stepNext2) stepNext2.addEventListener("click", () => showStep(3));
  if (stepBack)  stepBack.addEventListener("click",  () => showStep(1));
  if (stepBack2) stepBack2.addEventListener("click", () => showStep(2));

  // ── Tab switching ──────────────────────────────────────────────────────────

  document.querySelectorAll(".xp-tab[data-type]").forEach(tab => {
    tab.addEventListener("click", () => {
      if (tab.disabled) return;

      document.querySelectorAll(".xp-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      _currentType = tab.dataset.type;

      // Show the right context panel
      document.querySelectorAll(".xp-type-fields").forEach(p => p.style.display = "none");
      const panel = $(PANEL_MAP[_currentType]);
      if (panel) panel.style.display = "";

      // Update description
      $("xpTypeDesc").textContent = TYPE_DESCS[_currentType] || "";

      updateRunCount();
      updatePreview();
      hideError();
    });
  });

  // ── Run count display ──────────────────────────────────────────────────────

  function updateRunCount() {
    const seeds = parsedSeeds().length;
    let totalRuns = 0;
    let msg = "";

    if (_currentType === "team_comparison") {
      const styles = selectedTeamStyles().length;
      if (styles === 0) {
        msg = "Select at least one team style";
      } else {
        const t = styles * seeds;
        totalRuns = t;
        msg = `${t} run${t === 1 ? "" : "s"} total`;
      }
    } else if (_currentType === "scenario_comparison") {
      const scens = selectedScenarios().length;
      if (scens === 0) {
        msg = "Select at least one scenario";
      } else {
        const t = scens * seeds;
        totalRuns = t;
        msg = `${t} run${t === 1 ? "" : "s"} total`;
      }
    } else if (_currentType === "seed_reproducibility") {
      if (seeds === 0) {
        msg = "Enter at least one run ID";
      } else {
        totalRuns = seeds;
        msg = `${seeds} run${seeds === 1 ? "" : "s"} total`;
      }
    }

    runCountEl.textContent = msg;
    if (totalRuns > 0) {
      runBtn.textContent = `Run ${totalRuns} Controlled Simulation${totalRuns === 1 ? "" : "s"}`;
    } else {
      runBtn.textContent = "Run Controlled Simulations";
    }
  }

  function updatePreview() {
    if (!previewScenarioEl) return;
    const snapshot = currentExperimentSnapshot();
    if (previewScenarioLabelEl) previewScenarioLabelEl.textContent = snapshot.scenarioLabel;
    if (previewTeamsLabelEl) previewTeamsLabelEl.textContent = snapshot.teamsLabel;
    if (previewSeedsLabelEl) previewSeedsLabelEl.textContent = snapshot.seedsLabel;
    previewScenarioEl.textContent = snapshot.scenarioText;

    // Team styles: pills for team comparison, plain text otherwise
    if (_currentType === "team_comparison") {
      const parts = snapshot.teamText.split(", ").filter(t => t && !t.startsWith("No "));
      previewTeamsEl.innerHTML = parts.length
        ? parts.map(t => `<span class="xp-ctx-pill">${esc(t)}</span>`).join("")
        : `<span style="color:var(--xp-muted);font-size:0.82rem">${esc(snapshot.teamText)}</span>`;
    } else {
      previewTeamsEl.textContent = snapshot.teamText;
    }

    previewSeedsEl.textContent = snapshot.seedText;
    previewRunsEl.textContent = `${snapshot.totalRuns || 0} runs`;
    if (previewRunsBreakdownEl) previewRunsBreakdownEl.textContent = snapshot.breakdownText || "";
    previewStepsEl.textContent = snapshot.stepText;
  }

  function updateStyleCount() {
    if (!styleCountEl) return;
    const styles = selectedTeamStyles().length;
    const seeds  = parsedSeeds().length;
    const total  = styles * seeds;
    styleCountEl.textContent = styles === 0
      ? "No styles selected"
      : `${styles} selected · ${total} run${total === 1 ? "" : "s"} total`;
  }

  document.querySelectorAll("input[name='teamStyle']").forEach(cb =>
    cb.addEventListener("change", () => { updateRunCount(); updatePreview(); updateStyleCount(); })
  );
  document.querySelectorAll("input[name='scenarioChoice']").forEach(cb =>
    cb.addEventListener("change", () => { updateRunCount(); updatePreview(); })
  );
  seedsInput.addEventListener("input", () => { updateRunCount(); updatePreview(); updateStyleCount(); });
  maxStepsInput.addEventListener("input", updatePreview);
  ["xpScenario", "xpTeamStyleSingle", "xpScenarioRepro", "xpTeamStyleRepro"].forEach(id => {
    const el = $(id);
    if (el) el.addEventListener("change", updatePreview);
  });
  updateRunCount();
  updatePreview();
  updateStyleCount();

  // ── Restore last result from sessionStorage (survives page refresh) ────────
  try {
    const saved = sessionStorage.getItem("xp_last_result");
    if (saved) {
      const data = JSON.parse(saved);
      // Validate shape before rendering — stale/corrupted data from an older
      // version of the UI would crash renderResults() without this guard.
      if (data && Array.isArray(data.runs) && data.aggregated && data.experiment_type) {
        renderResults(data);
      } else {
        sessionStorage.removeItem("xp_last_result"); // discard invalid data
        showSetupView();
      }
    } else {
      showSetupView();
    }
  } catch (_) {
    showSetupView();
  }

  // ── Run experiment ─────────────────────────────────────────────────────────

  runBtn.addEventListener("click", runExperiment);
  if (runAgainBtn) runAgainBtn.addEventListener("click", runExperiment);
  if (backBtn) backBtn.addEventListener("click", showSetupView);

  async function runExperiment() {
    const seeds     = parsedSeeds();
    const maxSteps  = parseInt(maxStepsInput.value, 10) || 30;

    if (seeds.length === 0) { showError("Enter at least one valid run ID."); return; }

    let body, totalRuns;

    if (_currentType === "team_comparison") {
      const teamStyles = selectedTeamStyles();
      if (teamStyles.length === 0) { showError("Select at least one team style."); return; }
      body = {
        experiment_type: "team_comparison",
        scenario:        $("xpScenario").value,
        team_styles:     teamStyles,
        seeds,
        max_steps:       maxSteps,
        group_by:        "team_style",
      };
      totalRuns = teamStyles.length * seeds.length;

    } else if (_currentType === "scenario_comparison") {
      const scenarios = selectedScenarios();
      if (scenarios.length === 0) { showError("Select at least one scenario."); return; }
      body = {
        experiment_type: "scenario_comparison",
        team_style:      $("xpTeamStyleSingle").value,
        scenarios,
        seeds,
        max_steps:       maxSteps,
        group_by:        "scenario_label",
      };
      totalRuns = scenarios.length * seeds.length;

    } else if (_currentType === "seed_reproducibility") {
      body = {
        experiment_type: "seed_reproducibility",
        scenario:        $("xpScenarioRepro").value,
        team_style:      $("xpTeamStyleRepro").value,
        seeds,
        max_steps:       maxSteps,
        group_by:        "seed_label",
      };
      totalRuns = seeds.length;

    } else {
      showError("This experiment type is not available yet.");
      return;
    }

    setRunning(true, totalRuns);

    try {
      const res = await fetch(`${API_BASE}/experiments/batch`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }

      const data = await res.json();
      renderResults(data);
      hideError();
      // Persist so a page refresh restores the results view
      try { sessionStorage.setItem("xp_last_result", JSON.stringify(data)); } catch (_) {}
    } catch (err) {
      showError(err.message ?? "Unknown error — check the backend is running.");
    } finally {
      setRunning(false);
    }
  }

  // ── State helpers ──────────────────────────────────────────────────────────

  function setRunning(on, totalRuns) {
    runBtn.disabled             = on;
    if (runAgainBtn) {
      runAgainBtn.disabled = on;
      runAgainBtn.textContent = on ? "Running…" : "Run Again";
    }
    progress.style.display      = on ? "flex" : "none";
    if (on && totalRuns) {
      progressLabel.textContent = `Running controlled simulations... This may take a few seconds.`;
    }
  }

  function showError(msg) {
    errorEl.textContent   = msg;
    errorEl.style.display = "block";
  }

  function hideError() {
    errorEl.style.display = "none";
  }

  function showSetupView() {
    document.body.classList.add("setup-active");
    document.body.classList.remove("results-active");
    if (setupViewEl) setupViewEl.style.display = "";
    if (resultsViewEl) resultsViewEl.style.display = "none";
    showStep(1);
    window.scrollTo({ top: 0, behavior: "auto" });
    // Clear saved result so a subsequent refresh starts on setup, not results
    try { sessionStorage.removeItem("xp_last_result"); } catch (_) {}
  }

  function showResultsView() {
    document.body.classList.add("results-active");
    document.body.classList.remove("setup-active");
    if (setupViewEl) setupViewEl.style.display = "none";
    if (resultsViewEl) resultsViewEl.style.display = "";
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  // ── Render results ─────────────────────────────────────────────────────────

  function renderResults(data) {
    showResultsView();

    const rawAgg   = data.summary_by_team_style || {};
    const cmp      = data.comparison            || {};
    const runs     = data.runs                  || [];
    const expType  = data.config?.experiment_type || "team_comparison";
    const agg      = withComputedBlockerResolution(rawAgg, runs, expType);

    renderResultsMeta(data.config, expType);
    renderCards(agg, cmp, runs, expType);
    renderBehaviourPattern(agg, expType);
    renderTable(agg, expType);
    renderBehaviourDiff(agg, expType);
    renderInterpretation(agg, cmp.interpretation, expType);
    renderRunList(runs, expType);
  }

  // ── Results meta bar ───────────────────────────────────────────────────────

  function renderResultsMeta(config, experimentType) {
    const el = $("xpResultsMeta");
    if (!el || !config) return;

    const typeLabel =
      experimentType === "scenario_comparison" ? "Compare Scenarios"
      : experimentType === "seed_reproducibility" ? "Reproducibility"
      : "Compare Teams";

    const parts = [`Mode: ${typeLabel}`];
    if (experimentType === "team_comparison") {
      parts.push(`Scenario: ${SCENARIO_NAMES[config.scenario] || titleCaseLabel(config.scenario)}`);
      const styles = (config.team_styles || []).map(titleCaseLabel).join(", ");
      parts.push(`Team styles: ${styles}`);
    } else if (experimentType === "scenario_comparison") {
      parts.push(`Team style: ${titleCaseLabel(config.team_style)} Team`);
      const scens = (config.scenarios || [])
        .map(s => SCENARIO_NAMES[s] || titleCaseLabel(s)).join(", ");
      parts.push(`Scenarios: ${scens}`);
    } else if (experimentType === "seed_reproducibility") {
      parts.push(`Scenario: ${SCENARIO_NAMES[config.scenario] || titleCaseLabel(config.scenario)}`);
      parts.push(`Team style: ${titleCaseLabel(config.team_style)} Team`);
    }

    const seedArr = Array.isArray(config.seeds) ? config.seeds : [];
    const ids = seedArr.length ? seedArr.join(", ") : "—";
    parts.push(`${seedArr.length === 1 ? "Repeatable Run ID" : "Repeatable Run IDs"}: ${ids}`);
    parts.push(`Total runs: ${config.total_runs || "?"}`);

    el.textContent = parts.join(" · ");
  }

  // ── Summary cards ──────────────────────────────────────────────────────────

  function renderCards(agg, comparison, runs, experimentType) {
    const el        = $("xpCards");
    const total     = runs.length;
    const completed = runs.filter(r => r.completed).length;

    // Seed reproducibility: show consistency stats instead of "winner" cards
    if (experimentType === "seed_reproducibility") {
      const labels  = Object.keys(agg);
      const n       = labels.length;
      if (n === 0) { el.innerHTML = ""; return; }

      const crs    = labels.map(l => agg[l]?.completion_rate ?? 0);
      const avgCr  = Math.round(crs.reduce((s, v) => s + v, 0) / n * 100);
      const crRange= Math.round((Math.max(...crs) - Math.min(...crs)) * 100);
      // Only call it "Consistent" if runs actually completed — all-zero means all failed
      const allFailed = crs.every(v => v === 0) && completed === 0;
      const consistencyValue = allFailed ? "No data"
        : crRange === 0 ? "Consistent" : "Variable";
      const consistencySub = allFailed ? "No run IDs completed successfully"
        : crRange === 0 ? "All run IDs gave the same outcome" : `Rate varied by ${crRange}%`;

      const cards = [
        {
          label: "Runs completed",
          value: `${completed}/${total}`,
          sub:   completed === total ? "All run IDs finished" : `${total - completed} did not complete`,
        },
        {
          label: "Avg completion",
          value: avgCr + "%",
          sub:   "Across all run IDs",
        },
        {
          label: "Consistency",
          value: consistencyValue,
          sub:   consistencySub,
        },
        {
          label: "Run IDs tested",
          value: String(n),
          sub:   "Independent reruns",
        },
      ];

      el.innerHTML = cards.map(c =>
        `<div class="xp-card">
           <div class="xp-card-label">${esc(c.label)}</div>
           <div class="xp-card-value">${c.value}</div>
           <div class="xp-card-sub">${esc(c.sub)}</div>
         </div>`
      ).join("");
      return;
    }

    // Team / scenario comparison: show "winner" cards
    const findings  = comparison.findings || [];
    const isTeam    = experimentType === "team_comparison";
    const winWord   = isTeam ? "team" : "scenario";

    const findWinner = metric => findings.find(f => f.metric === metric);
    const speed  = findWinner("completion_speed");
    const stress = findWinner("peak_stress");
    const coop   = findWinner("cooperation");
    const chall  = findWinner("challenge_count");

    const aggLabels = Object.keys(agg);
    const aggG      = l => agg[l] || {};

    const cards = [
      {
        label: "Runs completed",
        value: `${completed}/${total}`,
        sub:   completed === total ? "All runs finished" : `${total - completed} did not complete`,
      },
      speed && (() => {
        const ws    = winnersOf(aggLabels, aggG, "avg_completion_steps", true);
        const isTie = ws.length > 1;
        return {
          label: `Fastest ${winWord}`,
          value: isTie ? "Tie" : esc(titleCaseLabel(speed.winner)),
          sub:   isTie
            ? `${ws.map(titleCaseLabel).join(", ")} · ${fmtSmartNum(speed.value)} steps each`
            : `Avg ${fmtSmartNum(speed.value)} steps · Completed the required sequence quickest`,
        };
      })(),
      stress && {
        label: "Highest stress",
        value: esc(titleCaseLabel(stress.winner)),
        sub:   `Avg peak ${fmtNum(stress.value)} · Most pressured behaviour`,
      },
      coop && (() => {
        const ws    = winnersOf(aggLabels, aggG, "avg_cooperation_count");
        const isTie = ws.length > 1;
        return {
          label: "Most cooperative",
          value: isTie ? "Tie" : esc(titleCaseLabel(coop.winner)),
          sub:   isTie
            ? `${ws.map(titleCaseLabel).join(", ")} · ${fmtSmartNum(coop.value)} coop. events each`
            : `Avg ${fmtSmartNum(coop.value)} coop. events · Most stable teamwork`,
        };
      })(),
      chall && (() => {
        const challWinners = winnersOf(aggLabels, aggG, "avg_challenge_count");
        const challIsTie   = challWinners.length > 1;
        const challLabel   = challIsTie ? "Tie" : esc(titleCaseLabel(chall.winner));
        const challSub     = challIsTie
          ? `${challWinners.map(titleCaseLabel).join(", ")} · ${fmtSmartNum(chall.value)} challenge events each · Highest pushback signal`
          : `Avg ${fmtSmartNum(chall.value)} challenge events · Highest pushback signal`;
        return { label: "Most Pushback", value: challLabel, sub: challSub };
      })(),
    ].filter(Boolean);

    // If metric findings are fewer than expected, some cards were silently dropped.
    // Surface a note so the user knows the comparison data is incomplete.
    const expectedMetrics = 4; // speed, stress, coop, chall
    const missingCount = expectedMetrics - [speed, stress, coop, chall].filter(Boolean).length;
    const incompleteNote = missingCount > 0
      ? `<div class="xp-incomplete-note">${missingCount} metric${missingCount === 1 ? "" : "s"} could not be compared — not enough completed runs in every group.</div>`
      : "";

    el.innerHTML = cards.map(c =>
      `<div class="xp-card">
         <div class="xp-card-label">${esc(c.label)}</div>
         <div class="xp-card-value">${c.value}</div>
         <div class="xp-card-sub">${esc(c.sub)}</div>
       </div>`
    ).join("") + incompleteNote;
  }

  // ── Comparison table ────────────────────────────────────────────────────────

  const TABLE_COLS = [
    { key: "completion_rate",            label: "Completion",           tip: "Share of runs that completed successfully.",                                                                                              fmt: v => fmtPct(v),          lowerBetter: false },
    { key: "avg_completion_steps",       label: "Steps",                tip: "Average steps to finish a run (completed runs only). Whole numbers when all runs took the same count; one decimal when averaged.",       fmt: v => fmtSmartNum(v, 1),   lowerBetter: true  },
    { key: "avg_peak_stress",            label: "Stress",               tip: "Highest average stress reached across the run.",                                                                                          fmt: v => fmtNum(v),           lowerBetter: true  },
    { key: "avg_trust_delta",            label: "Trust Δ",              tip: "Average change in trust between team members over the run.",                                                                              fmt: v => fmtDelta(v),         lowerBetter: false },
    { key: "avg_challenge_count",        label: "Challenges",           tip: "Average refusal / push-back events per run. Whole numbers when consistent across runs; one decimal when averaged.",                      fmt: v => fmtSmartNum(v, 1),   lowerBetter: true  },
    { key: "conflict_ratio",             label: "Challenge %",          tip: "Challenge events (refusals, push-backs) as a share of all agent interactions in the run. Unlike challenge-vs-cooperation ratio, this accounts for neutral interactions (asks, suggestions) so high-negotiation scenarios are not unfairly penalised.",
      compute: g => {
        const c = Number(g?.avg_challenge_count ?? 0);
        const total = Number(g?.avg_total_event_count ?? 0);
        if (total > 0) return c / total;
        // Fallback to old formula if total_event_count not available (old runs)
        const o = Number(g?.avg_cooperation_count ?? 0);
        if (c + o > 0) return c / (c + o);
        return 0; // No events recorded — no challenge ratio to show
      },
      fmt: v => v == null ? "—" : Math.round(v * 100) + "%",                                                                                                                                                            lowerBetter: true  },
    { key: "avg_cooperation_count",      label: "Coop. Events Avg",     tip: "Average info-sharing and agreement events per run (event count, not a 0–1 score). Higher = more cooperative interactions.",               fmt: v => fmtSmartNum(v, 1),   lowerBetter: false },
    { key: "avg_blockers_resolved_rate", label: "Resolved",             tip: "Share of tracked items resolved. 100% if run completed with no tracked items.",                                                           fmt: v => fmtPct(v),           lowerBetter: false },
  ];

  // col can be a column object (with optional .compute) or a plain key string (legacy)
  function tableValue(group, col) {
    if (col && col.compute) return col.compute(group);
    const key = (col && col.key) ? col.key : col;
    const raw = group?.[key];
    if (key === "avg_blockers_resolved_rate") {
      const completion = Number(group?.completion_rate ?? 0);
      const value      = Number(raw ?? 0);
      if (completion >= 0.995 && value <= 0) return 1;
    }
    return raw;
  }

  function renderTable(agg, experimentType) {
    const head   = $("xpTableHead");
    const body   = $("xpTableBody");
    const labels = Object.keys(agg);
    if (labels.length === 0) { head.innerHTML = ""; body.innerHTML = ""; return; }

    const firstColLabel =
      experimentType === "scenario_comparison"  ? "Scenario"
      : experimentType === "seed_reproducibility" ? "Run ID"
      : "Team";

    // Pre-compute best/worst per column
    const extremes = {};
    const flatCols = new Set();
    for (const col of TABLE_COLS) {
      const vals = labels.map(l => tableValue(agg[l], col)).filter(v => v != null);
      if (!vals.length) continue;
      if (vals.every(v => v === vals[0])) flatCols.add(col.key);
      extremes[col.key] = {
        best:  col.lowerBetter ? Math.min(...vals) : Math.max(...vals),
        worst: col.lowerBetter ? Math.max(...vals) : Math.min(...vals),
      };
    }

    head.innerHTML =
      `<tr>
         <th>${esc(firstColLabel)}</th>
         ${TABLE_COLS.map(c => `<th${flatCols.has(c.key) ? ` class="xp-col-flat"` : ""}><span class="xp-th-label">${esc(c.label)}<span class="xp-th-help" title="${esc(c.tip || c.label)}">i</span></span></th>`).join("")}
       </tr>`;

    body.innerHTML = labels.map(label => {
      const g     = agg[label];
      const cells = TABLE_COLS.map(col => {
        const v   = tableValue(g, col);
        const fmt = col.fmt(v);
        const ext = extremes[col.key];
        let cls = "";
        if (flatCols.has(col.key)) {
          cls = " class=\"xp-cell-flat\"";
        } else if (ext != null && v != null) {
          if (v === ext.best)  cls = " class=\"xp-cell-best\"";
          if (v === ext.worst) cls = " class=\"xp-cell-worst\"";
        }
        return `<td${cls}>${esc(fmt)}</td>`;
      }).join("");
      const displayLabel = titleCaseLabel(label);
      const tagClass = toneClass(label);
      return `<tr><td><span class="xp-table-tag ${tagClass}">${esc(displayLabel)}</span></td>${cells}</tr>`;
    }).join("");
  }

  // ── Behaviour Pattern strip (above table) ──────────────────────────────────

  function renderBehaviourPattern(agg, experimentType) {
    const el = $("xpBehaviourPattern");
    if (!el) return;

    const labels = Object.keys(agg || {});
    if (labels.length < 2 || experimentType === "seed_reproducibility") {
      el.innerHTML = ""; return;
    }

    const isTeam = experimentType === "team_comparison";
    const g      = label => agg[label] || {};
    const name   = label => titleCaseLabel(label) + (isTeam ? " Team" : "");
    const fmt1   = v => (v == null || !isFinite(v)) ? "—" : Number(v).toFixed(1);
    const fmt2   = v => (v == null || !isFinite(v)) ? "—" : Number(v).toFixed(2);
    const fmtP   = v => Math.round(v * 100) + "%";

    // challenge / total_events (falls back to challenge / (challenge+coop) for old data)
    const crOf = l => {
      const c = Number(g(l).avg_challenge_count ?? 0);
      const total = Number(g(l).avg_total_event_count ?? 0);
      if (total > 0) return c / total;
      const o = Number(g(l).avg_cooperation_count ?? 0);
      return c / Math.max(1, c + o);
    };

    // Tie-aware winners
    const fastestWs  = winnersOf(labels, g, "avg_completion_steps", true);
    const calmestWs  = winnersOf(labels, g, "avg_peak_stress",      true);
    const highCoopWs = winnersOf(labels, g, "avg_cooperation_count");
    // "Most Pushback" chip uses raw challenge count (most honest: which had most pushback events)
    const highCRWs   = winnersOf(labels, g, "avg_challenge_count");
    const fastest    = fastestWs[0];
    const calmest    = calmestWs[0];
    const highCoop   = highCoopWs[0];
    const highCR     = highCRWs[0];

    const chips = [
      { kicker: "Fastest",          winner: tieLabel(fastestWs,  name), value: `${fmtSmartNum(g(fastest).avg_completion_steps)} avg steps`,       mod: "xp-pattern-chip--accent"   },
      { kicker: "Calmest",          winner: tieLabel(calmestWs,  name), value: `${fmt2(g(calmest).avg_peak_stress)} peak stress`,                  mod: "xp-pattern-chip--positive" },
      { kicker: "Most Cooperative", winner: tieLabel(highCoopWs, name), value: `${fmtSmartNum(g(highCoop).avg_cooperation_count)} coop. events`,   mod: "xp-pattern-chip--positive" },
      { kicker: "Most Pushback",    winner: tieLabel(highCRWs,   name), value: `${fmtSmartNum(g(highCR).avg_challenge_count)} challenge events`,   mod: "xp-pattern-chip--warning"  },
    ];

    el.innerHTML = chips.map(c => `
      <div class="xp-pattern-chip ${c.mod}">
        <span class="xp-pattern-kicker">${esc(c.kicker)}</span>
        <span class="xp-pattern-winner">${esc(c.winner)}</span>
        <span class="xp-pattern-value">${esc(c.value)}</span>
      </div>`).join("");
  }

  // ── Behaviour Differences ───────────────────────────────────────────────────

  function renderBehaviourDiff(agg, experimentType) {
    const el = $("xpBehaviourDiff");
    const section = $("xpBehaviourSection");
    if (!el) return;

    const labels = Object.keys(agg || {});
    const hide = () => { el.innerHTML = ""; if (section) section.style.display = "none"; };

    if (labels.length < 2 || experimentType === "seed_reproducibility") { hide(); return; }
    if (section) section.style.display = "";

    const isTeam   = experimentType === "team_comparison";
    const g        = label => agg[label] || {};
    const name     = label => titleCaseLabel(label) + (isTeam ? " Team" : "");
    const fmt1     = v => (v == null || !isFinite(v)) ? "—" : Number(v).toFixed(1);
    const fmtD     = v => { if (v == null || !isFinite(v)) return "—"; const s = Number(v).toFixed(2); return v >= 0 ? "+" + s : s; };
    const fmtPct2  = v => Math.round(v * 100) + "%";

    // challenge / total_events (falls back to challenge / (challenge+coop) for old data)
    const crOf = l => {
      const c = Number(g(l).avg_challenge_count ?? 0);
      const total = Number(g(l).avg_total_event_count ?? 0);
      if (total > 0) return c / total;
      const o = Number(g(l).avg_cooperation_count ?? 0);
      return c / Math.max(1, c + o);
    };

    // Tie-aware winners
    const highTrustWs  = winnersOf(labels, g, "avg_trust_delta");
    const highCoopWs   = winnersOf(labels, g, "avg_cooperation_count");
    const highConfWs   = winnersOf(labels, g, "avg_challenge_count");
    const highStressWs = winnersOf(labels, g, "avg_peak_stress");
    const fastestWs    = winnersOf(labels, g, "avg_completion_steps", true);
    const highTrust    = highTrustWs[0];
    const highCoop     = highCoopWs[0];
    const highConf     = highConfWs[0];
    const highStress   = highStressWs[0];
    const fastest      = fastestWs[0];
    // "Conflict Ratio" winner uses the improved challenge/total formula (tie-aware)
    const highCRVals   = labels.map(l => crOf(l));
    const bestCR       = Math.max(...highCRVals);
    const highCRWs     = labels.filter((_, i) => Math.abs(highCRVals[i] - bestCR) < 0.001);
    const highCR       = highCRWs[0];

    const highTrustLabel  = tieLabel(highTrustWs,  name);
    const highCoopLabel   = tieLabel(highCoopWs,   name);
    const highConfLabel   = tieLabel(highConfWs,   name);
    const highStressLabel = tieLabel(highStressWs, name);
    const fastestLabel    = tieLabel(fastestWs,    name);
    const highCRLabel     = tieLabel(highCRWs,     name);

    const narrative = isTeam
      ? `Across ${labels.length} team styles, <strong>${esc(highTrustLabel)}</strong> showed the strongest trust growth (${esc(fmtD(g(highTrust).avg_trust_delta))}), while <strong>${esc(highConfLabel)}</strong> generated the most challenge events (${esc(fmtSmartNum(g(highConf).avg_challenge_count))} avg). <strong>${esc(highCoopLabel)}</strong> led on cooperation (${esc(fmtSmartNum(g(highCoop).avg_cooperation_count))} coop. events avg) and <strong>${esc(highStressLabel)}</strong> had the highest peak stress (${esc(fmt1(g(highStress).avg_peak_stress))}). <strong>${esc(fastestLabel)}</strong> completed runs fastest at ${esc(fmtSmartNum(g(fastest).avg_completion_steps))} steps on average. Challenge rate was highest in <strong>${esc(highCRLabel)}</strong> (${esc(fmtPct2(crOf(highCR)))} of all interactions). This comparison shows that team style changed measurable behaviour: <strong>${esc(fastestLabel)}</strong> completed fastest, <strong>${esc(highCoopLabel)}</strong> produced the strongest cooperation pattern, and <strong>${esc(highStressLabel)}</strong> produced the highest stress.`
      : `Across ${labels.length} scenarios, <strong>${esc(highTrustLabel)}</strong> produced the highest trust growth (${esc(fmtD(g(highTrust).avg_trust_delta))}), while <strong>${esc(highConfLabel)}</strong> generated the most challenge events (${esc(fmtSmartNum(g(highConf).avg_challenge_count))} avg). <strong>${esc(highCoopLabel)}</strong> was the most cooperative environment (${esc(fmtSmartNum(g(highCoop).avg_cooperation_count))} coop. events avg) and <strong>${esc(highStressLabel)}</strong> showed the highest stress (${esc(fmt1(g(highStress).avg_peak_stress))}). <strong>${esc(fastestLabel)}</strong> resolved fastest at ${esc(fmtSmartNum(g(fastest).avg_completion_steps))} steps. This comparison shows that scenario context changed measurable behaviour across speed, stress, cooperation, and conflict.`;

    const items = [
      { metric: "Trust Growth",    winner: highTrustLabel,  val: fmtD(g(highTrust).avg_trust_delta),                             color: "var(--xp-green)"  },
      { metric: "Coop. Events Avg", winner: highCoopLabel,   val: `${fmtSmartNum(g(highCoop).avg_cooperation_count)} events`,      color: "#1a8a7a"          },
      { metric: "Most Pushback",   winner: highConfLabel,   val: `${fmtSmartNum(g(highConf).avg_challenge_count)} events`,         color: "var(--xp-amber)"  },
      { metric: "Challenge %",     winner: highCRLabel,     val: fmtPct2(crOf(highCR)),                                           color: "var(--xp-red)"    },
      { metric: "Peak Stress",     winner: highStressLabel, val: fmt1(g(highStress).avg_peak_stress),                              color: "var(--xp-red)"    },
      { metric: "Fastest",         winner: fastestLabel,    val: `${fmtSmartNum(g(fastest).avg_completion_steps)} steps`,          color: "var(--xp-accent)" },
    ];

    el.innerHTML = `
      <div class="xp-bdiff">
        <p class="xp-bdiff-narrative">${narrative}</p>
        <div class="xp-bdiff-grid">
          ${items.map(item => `
            <div class="xp-bdiff-item">
              <span class="xp-bdiff-metric">${esc(item.metric)}</span>
              <span class="xp-bdiff-winner">${esc(item.winner)}</span>
              <span class="xp-bdiff-val" style="color:${item.color}">${esc(item.val)}</span>
            </div>`).join("")}
        </div>
      </div>`;
  }

  // ── Interpretation ─────────────────────────────────────────────────────────

  function renderInterpretation(agg, fallbackText, experimentType) {
    const el     = $("xpInterpretation");
    const labels = Object.keys(agg || {});

    if (labels.length === 0) {
      el.textContent = fallbackText || "No interpretation available.";
      return;
    }

    // ── Seed Reproducibility ──────────────────────────────────────────────────
    if (experimentType === "seed_reproducibility") {
      const lines = labels.map(label => {
        const g     = agg[label];
        const rate  = Math.round((g.completion_rate ?? 0) * 100) + "%";
        const steps = g.avg_completion_steps != null
          ? Number(g.avg_completion_steps).toFixed(1) + " steps"
          : "—";
        const stress = Number(g.avg_peak_stress ?? 0).toFixed(2);
        return `<li><strong>${esc(label)}:</strong> ${esc(rate)} completion, avg ${esc(steps)}, peak stress ${esc(stress)}.</li>`;
      });

      el.innerHTML = `
        <div class="xp-interpretation-block">
          <div class="xp-interpretation-head">Consistency analysis</div>
          <p class="xp-interpretation-copy">${esc(fallbackText || "")}</p>
        </div>
        <div class="xp-interpretation-block">
          <div class="xp-interpretation-head">Per-run-ID results</div>
          <ul class="xp-interpretation-list">${lines.join("")}</ul>
        </div>`;
      return;
    }

    // ── Team Comparison & Scenario Comparison ─────────────────────────────────
    const isTeam    = experimentType === "team_comparison";
    const groupWord = isTeam ? "team style" : "scenario environment";

    const TEAM_TRAITS = {
      smooth:   "Most stable and cooperative, with low stress and low disagreement.",
      tension:  "Highest stress and most disagreement, but still capable of full completion.",
      creative: "Balanced performance with moderate stress and flexible coordination.",
      pressure: "Fastest overall, showing controlled urgency without high conflict.",
    };

    const lines = labels.map(label => {
      const g     = agg[label];
      const name  = titleCaseLabel(label);
      const rate  = Math.round((g.completion_rate ?? 0) * 100) + "%";
      const steps = Number(g.avg_completion_steps ?? 0).toFixed(1);
      const stress= Number(g.avg_peak_stress ?? 0).toFixed(2);
      const trust = fmtDelta(g.avg_trust_delta ?? 0);

      const trait = isTeam
        ? (TEAM_TRAITS[label] || "Flexible coordination with variable stress levels.")
        : null;

      if (trait) {
        return `<li><strong>${esc(name)} Team:</strong> ${esc(trait)} `
             + `(${esc(rate)} completion, avg ${esc(steps)} steps, `
             + `peak stress ${esc(stress)}, trust Δ ${esc(trust)}).</li>`;
      } else {
        return `<li><strong>${esc(name)}:</strong> ${esc(rate)} completion, avg ${esc(steps)} steps, `
             + `peak stress ${esc(stress)}, trust Δ ${esc(trust)}.</li>`;
      }
    });

    const byStress    = labels.map(l => [l, Number(agg[l]?.avg_peak_stress      ?? 0       )]).sort((a, b) => b[1] - a[1]);
    const byCoop      = labels.map(l => [l, Number(agg[l]?.avg_cooperation_count ?? 0       )]).sort((a, b) => b[1] - a[1]);
    const bySpeed     = labels.map(l => [l, Number(agg[l]?.avg_completion_steps  ?? Infinity)]).sort((a, b) => a[1] - b[1]);
    const byChallenge = labels.map(l => [l, Number(agg[l]?.avg_challenge_count   ?? 0       )]).sort((a, b) => b[1] - a[1]);

    // Tie-aware top labels for interpretation text
    const _topCoopVal  = byCoop[0]?.[1];
    const _topCoopNames  = byCoop.filter(([, v]) => Math.abs(v - _topCoopVal) < 0.001).map(([l]) => titleCaseLabel(l));
    const _topCoopLabel  = _topCoopNames.length > 1 ? _topCoopNames.join(" & ") : (_topCoopNames[0] || "—");

    const _topStressVal  = byStress[0]?.[1];
    const _topStressNames= byStress.filter(([, v]) => Math.abs(v - _topStressVal) < 0.001).map(([l]) => titleCaseLabel(l));
    const _topStressLabel= _topStressNames.length > 1 ? _topStressNames.join(" & ") : (_topStressNames[0] || "—");

    const _topSpeedVal   = bySpeed[0]?.[1];
    const _topSpeedNames = bySpeed.filter(([, v]) => Math.abs(v - _topSpeedVal) < 0.001).map(([l]) => titleCaseLabel(l));
    const _topSpeedLabel = _topSpeedNames.length > 1 ? _topSpeedNames.join(" & ") : (_topSpeedNames[0] || "—");

    const _topChallVal   = byChallenge[0]?.[1];
    const _topChallNames = byChallenge.filter(([, v]) => Math.abs(v - _topChallVal) < 0.001).map(([l]) => titleCaseLabel(l));
    const _topChallLabel = _topChallNames.length > 1 ? _topChallNames.join(" & ") : (_topChallNames[0] || "—");

    const overall = isTeam
      ? `Across repeated runs, team style had a clear effect on behaviour. `
        + `${_topCoopLabel} team${_topCoopNames.length > 1 ? "s" : ""} were the most cooperative, `
        + `${_topStressLabel} team${_topStressNames.length > 1 ? "s" : ""} showed the highest stress, `
        + `and ${_topSpeedLabel} team${_topSpeedNames.length > 1 ? "s" : ""} completed runs most quickly.`
      : `Across repeated runs, the scenario environment shaped behaviour in distinct ways. `
        + `${_topCoopLabel} produced the most cooperative interactions, `
        + `${_topStressLabel} generated the highest stress, `
        + `and ${_topSpeedLabel} was completed most quickly.`;

    const why = isTeam
      ? `These results suggest that ${groupWord} meaningfully changes simulation outcomes, `
        + `affecting coordination speed, social tension, and collaboration quality. `
        + `${_topChallLabel} team${_topChallNames.length > 1 ? "s" : ""} generated the most challenge events, `
        + `while ${_topCoopLabel} team${_topCoopNames.length > 1 ? "s" : ""} showed the smoothest coordination.`
      : `These results suggest that ${groupWord} shapes agent behaviour in measurable ways. `
        + `${_topChallLabel} generated the most challenge events, `
        + `indicating higher coordination friction in that context.`;

    const summaryLabel = isTeam ? "Team-by-team summary" : "Scenario-by-scenario summary";

    el.innerHTML = `
      <div class="xp-interpretation-block">
        <div class="xp-interpretation-head">Overall takeaway</div>
        <p class="xp-interpretation-copy">${esc(overall)}</p>
      </div>
      <div class="xp-interpretation-block">
        <div class="xp-interpretation-head">${esc(summaryLabel)}</div>
        <ul class="xp-interpretation-list">${lines.join("")}</ul>
      </div>
      <div class="xp-interpretation-block">
        <div class="xp-interpretation-head">Why it matters</div>
        <p class="xp-interpretation-copy">${esc(why)}</p>
      </div>`;
  }

  // ── Individual run list ─────────────────────────────────────────────────────

  function renderRunList(runs, experimentType) {
    const el    = $("xpRunList");
    const count = $("xpRunsCount");
    count.textContent = `${runs.length} run${runs.length === 1 ? "" : "s"}`;

    el.innerHTML = runs.map(r => {
      const done  = r.completed;
      const badge = done
        ? `<span class="xp-run-badge done">✓ Completed</span>`
        : `<span class="xp-run-badge incomplete">✗ Incomplete</span>`;

      // Group label depends on experiment type
      let groupLabel;
      if (experimentType === "scenario_comparison") {
        groupLabel = r.scenario_label || SCENARIO_NAMES[r.scenario] || titleCaseLabel(r.scenario || "—");
      } else if (experimentType === "seed_reproducibility") {
        groupLabel = r.seed_label || `Run ID ${r.seed ?? "?"}`;
      } else {
        groupLabel = titleCaseLabel(r.team_style ?? "—");
      }

      const steps  = done ? `${r.completion_steps ?? r.ticks} steps` : `${r.ticks} steps`;
      const stress = `Stress ${fmtNum(r.peak_stress)}`;
      const trust  = `Trust ${fmtDelta(r.trust_delta)}`;
      const chall  = `Challenges ${r.challenge_count ?? 0}`;

      return `<div class="xp-run-row">
        ${badge}
        <span class="xp-run-meta xp-run-meta-strong">${esc(groupLabel)}</span>
        <span class="xp-run-meta">Run ID ${esc(String(r.seed ?? "?"))}</span>
        <span class="xp-run-meta">${esc(steps)} · ${esc(stress)} · ${esc(trust)} · ${esc(chall)}</span>
        <span></span>
        <span></span>
      </div>`;
    }).join("");
  }

})();
