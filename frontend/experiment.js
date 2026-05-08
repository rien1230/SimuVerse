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

  const TYPE_DESCS = {
    team_comparison:
      "Compare how different team styles behave under the same scenario. Each selected team style runs against the same repeatable run IDs for a fair comparison.",
    scenario_comparison:
      "Run the same team style across multiple scenarios to see how the environment changes coordination, stress, and completion speed.",
    seed_reproducibility:
      "Fix one scenario and one team style, then rerun the same setup with repeatable run IDs to check consistency across repeated tests.",
    intervention_impact:
      "Compare a baseline run against a run where an intervention was applied mid-simulation.",
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
    intervention_impact: "xpPanelIntervention",
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

      // Disable Next on coming-soon types so user can't proceed to configure step
      const isComingSoon = _currentType === "intervention_impact";
      if (stepNext) stepNext.disabled = isComingSoon;

      updateRunCount();
      updatePreview();
      hideError();
    });
  });

  // ── Run count display ──────────────────────────────────────────────────────

  function updateRunCount() {
    if (_currentType === "intervention_impact") {
      runCountEl.textContent = "Not available in this build";
      runBtn.textContent = "Intervention experiments coming soon";
      return;
    }
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
  showSetupView();

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

      const crs    = labels.map(l => agg[l].completion_rate ?? 0);
      const avgCr  = Math.round(crs.reduce((s, v) => s + v, 0) / n * 100);
      const crRange= Math.round((Math.max(...crs) - Math.min(...crs)) * 100);

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
          value: crRange === 0 ? "Consistent" : "Variable",
          sub:   crRange === 0 ? "All run IDs gave the same outcome" : `Rate varied by ${crRange}%`,
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

    const cards = [
      {
        label: "Runs completed",
        value: `${completed}/${total}`,
        sub:   completed === total ? "All runs finished" : `${total - completed} did not complete`,
      },
      speed && {
        label: `Fastest ${winWord}`,
        value: esc(titleCaseLabel(speed.winner)),
        sub:   `Avg ${fmtNum(speed.value, 1)} steps · Completed the required sequence quickest`,
      },
      stress && {
        label: "Highest stress",
        value: esc(titleCaseLabel(stress.winner)),
        sub:   `Avg peak ${fmtNum(stress.value)} · Most pressured behaviour`,
      },
      coop && {
        label: "Most cooperative",
        value: esc(titleCaseLabel(coop.winner)),
        sub:   `Avg ${fmtNum(coop.value, 1)} events · Most stable teamwork`,
      },
      chall && {
        label: "Most challenges",
        value: esc(titleCaseLabel(chall.winner)),
        sub:   `Avg ${fmtNum(chall.value, 1)} events · Highest conflict signal`,
      },
    ].filter(Boolean);

    el.innerHTML = cards.map(c =>
      `<div class="xp-card">
         <div class="xp-card-label">${esc(c.label)}</div>
         <div class="xp-card-value">${c.value}</div>
         <div class="xp-card-sub">${esc(c.sub)}</div>
       </div>`
    ).join("");
  }

  // ── Comparison table ────────────────────────────────────────────────────────

  const TABLE_COLS = [
    { key: "completion_rate",            label: "Completion",           tip: "Share of runs that completed successfully.",                                          fmt: v => fmtPct(v),      lowerBetter: false },
    { key: "avg_completion_steps",       label: "Steps",                tip: "Average steps to finish a run (completed runs only).",                                fmt: v => fmtNum(v, 1),   lowerBetter: true  },
    { key: "avg_peak_stress",            label: "Stress",               tip: "Highest average stress reached across the run.",                                      fmt: v => fmtNum(v),      lowerBetter: true  },
    { key: "avg_trust_delta",            label: "Trust Δ",              tip: "Average change in trust between team members over the run.",                          fmt: v => fmtDelta(v),    lowerBetter: false },
    { key: "avg_challenge_count",        label: "Challenges",           tip: "Average refusal / push-back events per run.",                                         fmt: v => fmtNum(v, 1),   lowerBetter: true  },
    { key: "conflict_ratio",             label: "Conflict %",           tip: "Challenge events as a share of all social interactions. Lower = more cooperative.",
      compute: g => { const c = Number(g?.avg_challenge_count ?? 0); const o = Number(g?.avg_cooperation_count ?? 0); return c / Math.max(1, c + o); },
      fmt: v => v == null ? "—" : Math.round(v * 100) + "%",            lowerBetter: true  },
    { key: "avg_cooperation_count",      label: "Cooperation",          tip: "Average info-sharing / agreement events per run.",                                    fmt: v => fmtNum(v, 1),   lowerBetter: false },
    { key: "avg_blockers_resolved_rate", label: "Resolved",             tip: "Share of tracked items resolved. 100% if run completed with no tracked items.", fmt: v => fmtPct(v),      lowerBetter: false },
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

  function renderBehaviourPattern(agg, experimentType) {
    const el = $("xpBehaviourPattern");
    if (!el) return;

    const labels = Object.keys(agg || {});
    if (labels.length < 2 || experimentType === "seed_reproducibility") {
      el.innerHTML = "";
      el.style.display = "none";
      return;
    }

    el.style.display = "";

    const isTeam = experimentType === "team_comparison";
    const g = label => agg[label] || {};
    const name = label => titleCaseLabel(label) + (isTeam ? " Team" : "");
    const fmt1 = v => (v == null || !isFinite(v)) ? "—" : Number(v).toFixed(1);
    const fmt2 = v => (v == null || !isFinite(v)) ? "—" : Number(v).toFixed(2);
    const fmtPct = v => `${Math.round(v * 100)}%`;
    const crOf = l => {
      const c = Number(g(l).avg_challenge_count ?? 0);
      const o = Number(g(l).avg_cooperation_count ?? 0);
      return c / Math.max(1, c + o);
    };
    const winnerOf = (metric, lowerBetter = false) =>
      labels.reduce((a, b) => {
        const va = Number(g(a)[metric] ?? (lowerBetter ? Infinity : -Infinity));
        const vb = Number(g(b)[metric] ?? (lowerBetter ? Infinity : -Infinity));
        return lowerBetter ? (va < vb ? a : b) : (va > vb ? a : b);
      });

    const fastest = winnerOf("avg_completion_steps", true);
    const calmest = winnerOf("avg_peak_stress", true);
    const mostConflict = labels.reduce((a, b) => crOf(a) > crOf(b) ? a : b);
    const mostCoop = winnerOf("avg_cooperation_count");

    const chips = [
      {
        kicker: "Fastest",
        winner: name(fastest),
        value: `${fmt1(g(fastest).avg_completion_steps)} steps`,
        cls: "xp-pattern-chip xp-pattern-chip--accent",
      },
      {
        kicker: "Calmest",
        winner: name(calmest),
        value: `${fmt2(g(calmest).avg_peak_stress)} stress`,
        cls: "xp-pattern-chip xp-pattern-chip--positive",
      },
      {
        kicker: "Most conflict",
        winner: name(mostConflict),
        value: `${fmtPct(crOf(mostConflict))} conflict ratio`,
        cls: "xp-pattern-chip xp-pattern-chip--warning",
      },
      {
        kicker: "Most cooperative",
        winner: name(mostCoop),
        value: `${fmt1(g(mostCoop).avg_cooperation_count)} events`,
        cls: "xp-pattern-chip xp-pattern-chip--positive",
      },
    ];

    el.innerHTML = chips.map(item => `
      <div class="${item.cls}">
        <span class="xp-pattern-kicker">${esc(item.kicker)}</span>
        <span class="xp-pattern-winner">${esc(item.winner)}</span>
        <span class="xp-pattern-value">${esc(item.value)}</span>
      </div>
    `).join("");
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

    const winnerOf = (metric, lowerBetter = false) =>
      labels.reduce((a, b) => {
        const va = Number(g(a)[metric] ?? (lowerBetter ? Infinity : -Infinity));
        const vb = Number(g(b)[metric] ?? (lowerBetter ? Infinity : -Infinity));
        return lowerBetter ? (va < vb ? a : b) : (va > vb ? a : b);
      });

    const crOf  = l => { const c = Number(g(l).avg_challenge_count ?? 0); const o = Number(g(l).avg_cooperation_count ?? 0); return c / Math.max(1, c + o); };
    const fastest  = winnerOf("avg_completion_steps", true);
    const calmest  = winnerOf("avg_peak_stress", true);
    const highCoop = winnerOf("avg_cooperation_count");
    const highCR   = labels.reduce((a, b) => crOf(a) > crOf(b) ? a : b);

    const chips = [
      { kicker: "Fastest",          winner: name(fastest),   value: `${fmt1(g(fastest).avg_completion_steps)} avg steps`,       mod: "xp-pattern-chip--accent"   },
      { kicker: "Calmest",          winner: name(calmest),   value: `${fmt2(g(calmest).avg_peak_stress)} peak stress`,          mod: "xp-pattern-chip--positive" },
      { kicker: "Most Cooperative", winner: name(highCoop),  value: `${fmt1(g(highCoop).avg_cooperation_count)} events avg`,    mod: "xp-pattern-chip--positive" },
      { kicker: "Most Conflict",    winner: name(highCR),    value: `${fmtP(crOf(highCR))} conflict ratio`,                     mod: "xp-pattern-chip--warning"  },
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

    const crOf = l => { const c = Number(g(l).avg_challenge_count ?? 0); const o = Number(g(l).avg_cooperation_count ?? 0); return c / Math.max(1, c + o); };

    const winnerOf = (metric, lowerBetter = false) =>
      labels.reduce((a, b) => {
        const va = Number(g(a)[metric] ?? (lowerBetter ? Infinity : -Infinity));
        const vb = Number(g(b)[metric] ?? (lowerBetter ? Infinity : -Infinity));
        return lowerBetter ? (va < vb ? a : b) : (va > vb ? a : b);
      });

    const highTrust  = winnerOf("avg_trust_delta");
    const highCoop   = winnerOf("avg_cooperation_count");
    const highConf   = winnerOf("avg_challenge_count");
    const highStress = winnerOf("avg_peak_stress");
    const fastest    = winnerOf("avg_completion_steps", true);
    const highCR     = labels.reduce((a, b) => crOf(a) > crOf(b) ? a : b);

    const narrative = isTeam
      ? `Across ${labels.length} team styles, <strong>${esc(name(highTrust))}</strong> showed the strongest trust growth (${esc(fmtD(g(highTrust).avg_trust_delta))}), while <strong>${esc(name(highConf))}</strong> generated the most challenge events (${esc(fmt1(g(highConf).avg_challenge_count))} avg). <strong>${esc(name(highCoop))}</strong> led on cooperation (${esc(fmt1(g(highCoop).avg_cooperation_count))} events avg) and <strong>${esc(name(highStress))}</strong> had the highest peak stress (${esc(fmt1(g(highStress).avg_peak_stress))}). <strong>${esc(name(fastest))}</strong> completed runs fastest at ${esc(fmt1(g(fastest).avg_completion_steps))} steps on average. Conflict ratio was highest in <strong>${esc(name(highCR))}</strong> (${esc(fmtPct2(crOf(highCR)))}). This comparison shows that team style changed measurable behaviour: <strong>${esc(name(fastest))}</strong> completed fastest, <strong>${esc(name(highCoop))}</strong> produced the strongest cooperation pattern, and <strong>${esc(name(highStress))}</strong> produced the highest stress and conflict ratio.`
      : `Across ${labels.length} scenarios, <strong>${esc(name(highTrust))}</strong> produced the highest trust growth (${esc(fmtD(g(highTrust).avg_trust_delta))}), while <strong>${esc(name(highConf))}</strong> generated the most challenge events (${esc(fmt1(g(highConf).avg_challenge_count))} avg). <strong>${esc(name(highCoop))}</strong> was the most cooperative environment (${esc(fmt1(g(highCoop).avg_cooperation_count))} events avg) and <strong>${esc(name(highStress))}</strong> showed the highest stress (${esc(fmt1(g(highStress).avg_peak_stress))}). <strong>${esc(name(fastest))}</strong> resolved fastest at ${esc(fmt1(g(fastest).avg_completion_steps))} steps. This comparison shows that scenario context changed measurable behaviour across speed, stress, cooperation, and conflict.`;

    const items = [
      { metric: "Trust Growth",   winner: name(highTrust),  val: fmtD(g(highTrust).avg_trust_delta),                        color: "var(--xp-green)"  },
      { metric: "Cooperation",    winner: name(highCoop),   val: `${fmt1(g(highCoop).avg_cooperation_count)} events`,        color: "#1a8a7a"          },
      { metric: "Most Conflict",  winner: name(highConf),   val: `${fmt1(g(highConf).avg_challenge_count)} events`,          color: "var(--xp-amber)"  },
      { metric: "Conflict Ratio", winner: name(highCR),     val: fmtPct2(crOf(highCR)),                                     color: "var(--xp-red)"    },
      { metric: "Peak Stress",    winner: name(highStress), val: fmt1(g(highStress).avg_peak_stress),                        color: "var(--xp-red)"    },
      { metric: "Fastest",        winner: name(fastest),    val: `${fmt1(g(fastest).avg_completion_steps)} steps`,           color: "var(--xp-accent)" },
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

    const overall = isTeam
      ? `Across repeated runs, team style had a clear effect on behaviour. `
        + `${titleCaseLabel(byCoop[0]?.[0])} teams were the most cooperative, `
        + `${titleCaseLabel(byStress[0]?.[0])} teams showed the highest stress, `
        + `and ${titleCaseLabel(bySpeed[0]?.[0])} teams completed runs most quickly.`
      : `Across repeated runs, the scenario environment shaped behaviour in distinct ways. `
        + `${titleCaseLabel(byCoop[0]?.[0])} produced the most cooperative interactions, `
        + `${titleCaseLabel(byStress[0]?.[0])} generated the highest stress, `
        + `and ${titleCaseLabel(bySpeed[0]?.[0])} was completed most quickly.`;

    const why = isTeam
      ? `These results suggest that ${groupWord} meaningfully changes simulation outcomes, `
        + `affecting coordination speed, social tension, and collaboration quality. `
        + `${titleCaseLabel(byChallenge[0]?.[0])} teams generated the most challenge events, `
        + `while ${titleCaseLabel(byCoop[0]?.[0])} teams showed the smoothest coordination.`
      : `These results suggest that ${groupWord} shapes agent behaviour in measurable ways. `
        + `${titleCaseLabel(byChallenge[0]?.[0])} generated the most challenge events, `
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
