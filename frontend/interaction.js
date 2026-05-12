// Live run page logic: websocket updates, interventions, and on-screen state.
 const API_BASE = window.SimuVerseAPI.API_BASE;
    const WS_BASE = window.SimuVerseAPI.WS_BASE;
    const PARAMS = new URLSearchParams(window.location.search);

    // True when opened from History → Replay for a Live Interactive saved run.
    // In this mode the page is read-only: no WebSocket, no interventions, no steps.
    const IS_REPLAY_MODE = PARAMS.get("mode") === "interactive_replay";

    // Main page state for the current run, replay mode, and intervention tracking.
    const state = {
      // ── Run identity ──────────────────────────────────────────────────
      runId: PARAMS.get("run_id") || "",
      scenarioHint: PARAMS.get("scenario") || "",
      teamHint: PARAMS.get("team") || "",

      // ── Simulation state (updated from backend diffs) ─────────────────
      environment: "",
      ended: false,
      tick: 0,
      status: "idle",
      config: null,
      agents: [],
      tasks: {},
      knowledgeMap: {},
      groupState: {},
      historySnapshots: [],

      // ── WebSocket ─────────────────────────────────────────────────────
      ws: null,
      wsReady: false,
      autoRunning: false,

      // ── Step-tracking ─────────────────────────────────────────────────
      completedPhases: new Set(),   // tasks already marked with a phase divider
      eventsSeen: new Set(),
      tickToDisplayStep: new Map(), // real tick → sequential visible step label
      nextDisplayStep: 0,           // increments each time a new tick has visible events
      actionPending: false,
      pendingAdvance: null,

      // ── Interventions ─────────────────────────────────────────────────
      // urgencyValue mirrors env.urgency_modifier. Seeded from scenario type on
      // first snapshot (Café=0.00, Office=0.25, Escape=0.80); updated from
      // pressure intervention POST replies and shown as a real numeric pressure value.
      urgencyValue: 0,
      urgencySeeded: false,
      lastIntervention: null,       // {type, params, label, before, atTick, postUrgency}
      interventionLog: [],          // completed interventions with before + afterMetrics
      // Tracks "agentA|agentB|blocker" keys for Force Meeting repetition detection.
      // Cleared automatically when the active blocker advances.
      recentForceMeetings: new Set(),
      // Tracks focus items where a non-owner pair has already been tried.
      // Used to escalate warnings after the first ineffective attempt.
      // Cleared automatically when the active blocker advances.
      nonOwnerAttempts: new Set(),
      _lastSeenBlocker: null,       // used to detect blocker transitions for cache-clearing

      // ── Metrics & Analysis ────────────────────────────────────────────
      metricsHistory: [],           // [{tick, stress, trust, cohesion, conflict}] per step
      peakTension: 0,               // running max of group_state.tension across all ticks

      // ── UI view state ─────────────────────────────────────────────────
      currentView: "live",          // "live" | "metrics" | "impact"
      mainChart: null,              // Chart.js instance for Metrics & Analysis view

      // ── Replay navigation (only used when IS_REPLAY_MODE = true) ──────
      replayIndex: -1,              // which historySnapshot is currently shown in panels
    };

    // ── DOM refs ───────────────────────────────────────────────────────
    // Cache key elements once so the render/update code stays simpler.
    const $ = (id) => document.getElementById(id);
    const banner = $("banner");
    const fallbackMissing = $("fallbackMissing");
    const fallbackStale = $("fallbackStale");
    const liveSession = $("liveSession");
    const agentList = $("agentList");
    const eventLog = $("eventLog");
    const btnStep = $("btnStep");
    const btnStepLabel = $("btnStepLabel");
    const btnReset = $("btnReset");
    const ivButtons = {
      boost_urgency: document.querySelector('[data-iv="boost_urgency"]'),
      ease_pressure: document.querySelector('[data-iv="ease_pressure"]'),
      reveal_info: document.querySelector('[data-iv="reveal_info"]'),
      force_meeting: document.querySelector('[data-iv="force_meeting"]'),
      nudge_strategy: document.querySelector('[data-iv="nudge_strategy"]'),
      inject_tension: document.querySelector('[data-iv="inject_tension"]'),
      inject_emotion: document.querySelector('[data-iv="inject_emotion"]'),
    };

    // ── Banner (floating toast, auto-dismisses info/good) ──────────────
    let _bannerTimer = null;
    function showBanner(message, kind = "info") {
      if (_bannerTimer) { clearTimeout(_bannerTimer); _bannerTimer = null; }
      const dismissible = kind === "error" || kind === "warn";
      banner.innerHTML = message + (dismissible
        ? `<button onclick="this.closest('.banner').className='banner info hidden';" aria-label="Dismiss" style="margin-left:12px;background:none;border:none;cursor:pointer;font-size:1rem;font-weight:900;opacity:0.6;line-height:1;">✕</button>`
        : "");
      banner.className = "banner " + kind;
      if (kind === "info" || kind === "good") {
        _bannerTimer = setTimeout(hideBanner, kind === "good" ? 2600 : 6000);
      } else if (kind === "warn") {
        _bannerTimer = setTimeout(hideBanner, 12000);
      }
      // "error" persists until dismissed or replaced
    }
    function hideBanner() {
      if (_bannerTimer) { clearTimeout(_bannerTimer); _bannerTimer = null; }
      banner.className = "banner info hidden";
    }

    // ── setMeta (supports both old "v" class and new "sm-v" class) ─────
    function setMeta(field, value, stateClass = "") {
      const node = $("s" + field);
      if (!node) return;
      node.textContent = value;
      const base = node.classList.contains("status-value")
        ? "status-value"
        : (node.classList.contains("sm-v") ? "sm-v" : "v");
      node.className = base + (stateClass ? " is-" + stateClass : "");
    }

    function setModePill(label, statusClass = "") {
      $("modeLabel").textContent = label;
      const dot = $("modeDot");
      dot.className = "mode-dot" + (statusClass ? " is-" + statusClass : "");
    }

    // Metric display helpers keep the top strip and analysis tab consistent.
    // Qualitative metric labels are scenario-aware because each scenario has different baseline expectations.
    // Each entry is [Low_max, Medium_max, High_max]; values ≥ High_max → "Very High".
    const METRIC_THRESHOLDS = {
      cafe: {
        tension:  [0.20, 0.40, 0.60],
        cohesion: [0.40, 0.65, 0.85],
      },
      office: {
        tension:  [0.25, 0.50, 0.75],
        cohesion: [0.30, 0.55, 0.78],
      },
      escape: {
        tension:  [0.30, 0.55, 0.80],
        cohesion: [0.25, 0.50, 0.75],
      },
    };

    const DISPLAY_PRESSURE_BASELINES = {
      cafe: 0.15,
      office: 0.45,
      escape: 0.70,
    };

    const DISPLAY_PRESSURE_THRESHOLDS = [0.25, 0.55, 0.80];
    const DISPLAY_PRESSURE_DELTA_SCALE = 0.6;
    const DISPLAY_PRESSURE_STEP = 0.05;
    const PRESSURE_INTERVENTION_AMOUNT = DISPLAY_PRESSURE_STEP / DISPLAY_PRESSURE_DELTA_SCALE;

    function scenarioKeyFromEnv(env) {
      const e = String(env || state.environment || state.scenarioHint || "").toLowerCase();
      if (e === "cafe" || e === "cafe_restaurant") return "cafe";
      if (e === "office") return "office";
      if (e === "escape" || e === "escape_room") return "escape";
      return "office"; // unknown → moderate defaults
    }

    function levelFromThresholds(thresholds, value) {
      const LABELS = ["Low", "Medium", "High", "Very High"];
      const n = Number(value);
      if (!Number.isFinite(n)) return "—";
      for (let i = 0; i < thresholds.length; i++) {
        if (n < thresholds[i]) return LABELS[i];
      }
      return LABELS[LABELS.length - 1];
    }

    function metricLevelLabel(field, value, env) {
      if (field === "Urgency") {
        return levelFromThresholds(DISPLAY_PRESSURE_THRESHOLDS, value);
      }
      const sk = scenarioKeyFromEnv(env);
      const row = METRIC_THRESHOLDS[sk] || METRIC_THRESHOLDS.office;
      const metricKey = field === "Tension"  ? "tension"
                      : field === "Cohesion" ? "cohesion" : null;
      if (!metricKey) return "";
      return levelFromThresholds(row[metricKey], value);
    }

    function metricDeltaClass(field, diff) {
      if (!Number.isFinite(diff) || Math.abs(diff) <= 0.001) return "is-empty";
      if (field === "Cohesion") return diff > 0 ? "is-positive" : "is-negative";
      if (field === "Tension") return diff > 0 ? "is-warning" : "is-calm";
      if (field === "Urgency") return diff > 0 ? "is-warning" : "is-calm";
      return diff > 0 ? "is-warning" : "is-calm";
    }

    function setTopStripMetric(field, value, previous = null) {
      const env = state.environment || state.scenarioHint;
      const actualCurrent = Number(value);
      const actualPrior = Number(previous);
      const displayCurrent = field === "Urgency"
        ? displayPressureValue(actualCurrent, env)
        : actualCurrent;
      const displayPrior = field === "Urgency"
        ? displayPressureValue(actualPrior, env)
        : actualPrior;
      const valueNode = $("s" + field);
      if (valueNode) valueNode.textContent = toFixedSafe(displayCurrent);
      const levelNode = $("s" + field + "Level");
      if (levelNode) levelNode.textContent = metricLevelLabel(field, displayCurrent, env);
      const deltaNode = $("s" + field + "Delta");
      if (!deltaNode) return;
      // After the run completes, show clean final values with no delta noise.
      if (state.ended) {
        deltaNode.textContent = "";
        deltaNode.className = "sc-sub metric-delta is-empty";
        return;
      }
      if (!Number.isFinite(displayCurrent) || !Number.isFinite(displayPrior) || Math.abs(displayCurrent - displayPrior) <= 0.001) {
        deltaNode.textContent = "";
        deltaNode.className = "sc-sub metric-delta is-empty";
        return;
      }
      const diff = displayCurrent - displayPrior;
      const sign = diff > 0 ? "+" : "";
      deltaNode.textContent = `${sign}${diff.toFixed(2)}`;
      deltaNode.className = `sc-sub metric-delta ${metricDeltaClass(field, diff)}`;
    }

    function updateMetricStripLabels() {
      const urgencyLabel = $("sUrgencyLabel");
      const tensionLabel = $("sTensionLabel");
      const cohesionLabel = $("sCohesionLabel");
      if (urgencyLabel) {
        urgencyLabel.textContent = state.ended ? "Final Pressure" : "Pressure";
        urgencyLabel.title = "Final/latest environment pressure value";
      }
      if (tensionLabel) {
        tensionLabel.textContent = state.ended ? "Final Tension" : "Tension";
        tensionLabel.title = state.ended
          ? "Final group-level tension at the end of the run"
          : "Current group-level tension";
      }
      if (cohesionLabel) {
        cohesionLabel.textContent = state.ended ? "Final Cohesion" : "Cohesion";
        cohesionLabel.title = state.ended
          ? "Final group alignment at the end of the run"
          : "Current group alignment";
      }
    }

    function readPressureValue(source) {
      const group = source?.group_state || source || {};
      const scenario = source?.scenario || {};
      const metrics = source?.metrics || {};
      const candidates = [
        group.pressure,
        group.urgency_modifier,
        scenario.pressure,
        scenario.urgency_modifier,
        metrics.pressure,
      ];
      for (const value of candidates) {
        const n = Number(value);
        if (Number.isFinite(n)) return n;
      }
      return null;
    }

    function displayPressureBaseline(env) {
      const sk = scenarioKeyFromEnv(env);
      return DISPLAY_PRESSURE_BASELINES[sk] ?? DISPLAY_PRESSURE_BASELINES.office;
    }

    function displayPressureValue(actual, env) {
      const actualValue = Number(actual);
      if (!Number.isFinite(actualValue)) return actualValue;
      const actualBase = scenarioBaseUrgency(env);
      const displayBase = displayPressureBaseline(env);
      const normalized = displayBase + ((actualValue - actualBase) * DISPLAY_PRESSURE_DELTA_SCALE);
      return Math.max(0, Math.min(1, normalized));
    }

    function showEndModal() {
      const modal = $("endRunModal");
      if (!modal) return;
      const title = $("endRunTitle");
      const text = $("endRunText");
      const dashboardLink = $("endRunDashboardLink");
      if (title) title.textContent = "Run complete";
      if (text) {
        text.textContent = "Interventions are disabled. Start a new live run from Setup, or keep reviewing the full log from this page.";
      }
      if (dashboardLink && state.runId) {
        const dashLink = new URL("dashboard.html", window.location.href);
        dashLink.searchParams.set("run_id", state.runId);
        if (state.scenarioHint) dashLink.searchParams.set("scenario", state.scenarioHint);
        if (state.teamHint) dashLink.searchParams.set("team", state.teamHint);
        dashboardLink.href = dashLink.toString();
      }
      modal.classList.remove("hidden");
    }

    function hideEndModal() {
      const modal = $("endRunModal");
      if (modal) modal.classList.add("hidden");
    }

    function syncDashboardLinks() {
      if (!state.runId) return;
      const dashLink = new URL("dashboard.html", window.location.href);
      dashLink.searchParams.set("run_id", state.runId);
      if (state.scenarioHint) dashLink.searchParams.set("scenario", state.scenarioHint);
      if (state.teamHint) dashLink.searchParams.set("team", state.teamHint);
      $("dashboardLink").href = dashLink.toString();
      $("fallbackReplayLink").href = dashLink.toString();
      const endRunLink = $("endRunDashboardLink");
      if (endRunLink) endRunLink.href = dashLink.toString();
    }

    // ── Blocker badge & suggest text ───────────────────────────────────
    function updateBlockerBadge() {
      const badge   = $("blockerBadge");
      const textEl  = $("sBlocker");
      const label   = $("blockerStripLabel");
      const sub     = $("blockerStripSub");
      const icon    = $("blockerStripIcon");
      if (!badge || !textEl) return;

      // Clear the force-meeting caches whenever the active blocker changes.
      // Both exact-pair repetitions and non-owner attempt records reset per focus.
      {
        const _newBlocker = state.ended ? null : currentBlocker();
        if (_newBlocker !== state._lastSeenBlocker) {
          state.recentForceMeetings.clear();
          state.nonOwnerAttempts.clear();
          state._lastSeenBlocker = _newBlocker;
        }
      }

      // ── Pre-run guard: before Step 1, show neutral "Ready" state ────────────
      // Knowledge map is already populated at tick 0, but surfacing internal
      // private knowledge (holder, partial share counts) before any agent has
      // acted would expose hidden simulation state to the user prematurely.
      if (state.tick === 0 && !state.ended) {
        if (label) label.textContent = "Focus";
        badge.className = "sc-blocker is-clear";
        textEl.textContent = "Ready to start";
        if (sub) { sub.textContent = "Awaiting first step"; sub.style.color = "var(--muted)"; }
        return;
      }

      if (state.ended) {
        const env = String(state.environment || state.scenarioHint || "").toLowerCase();
        // Determine whether the run actually succeeded — check canonical task order,
        // not just state.ended, which is true for both completed and failed runs.
        const _cfg   = scenarioConfig();
        const _order = Array.isArray(_cfg.order) ? _cfg.order : [];
        const _tasks = state.tasks || {};
        const _allDone = _order.length
          ? _order.every(item => Boolean(_tasks[item]))
          : Object.values(_tasks).every(v => Boolean(v));
        if (label) label.textContent = "Outcome";
        if (_allDone) {
          const outcomeWord = env === "office" ? "Proposal Accepted"
                            : env === "cafe"   ? "Decision Reached"
                            : "Escaped";
          badge.className = "sc-blocker is-clear";
          textEl.textContent = outcomeWord;
          if (sub) { sub.textContent = "Completed"; sub.style.color = "var(--teal)"; }
        } else {
          const failWord = env === "office" ? "Proposal Not Finalised"
                         : env === "cafe"   ? "Decision Not Reached"
                         : "Escape Failed";
          const firstUnresolved = _order.find(item => !Boolean(_tasks[item])) || null;
          badge.className = "sc-blocker";
          textEl.textContent = failWord;
          if (sub) {
            sub.textContent = firstUnresolved ? `Unresolved: ${itemLabel(firstUnresolved)}` : "Run ended";
            sub.style.color = "var(--red, #e05c5c)";
          }
        }
        return;
      }

      const blocker = currentBlocker();
      if (label) label.textContent = "Current focus";
      if (sub) { sub.textContent = "In progress"; sub.style.color = ""; }
      if (!blocker) {
        badge.className = "sc-blocker is-clear";
        textEl.textContent = "All complete";
      } else {
        badge.className = "sc-blocker";
        textEl.textContent = itemLabel(blocker);
      }
    }

    function updateSuggestText() {
      const el = $("suggestText");
      if (!el) return;
      // ── Pre-run guard ─────────────────────────────────────────────────────────
      if (state.tick === 0 && !state.ended) {
        el.textContent = "";
        el.style.display = "none";
        return;
      }
      el.style.display = "";
      if (state.ended) {
        const env = String(state.environment || state.scenarioHint || "").toLowerCase();
        const _cfg2   = scenarioConfig();
        const _order2 = Array.isArray(_cfg2.order) ? _cfg2.order : [];
        const _tasks2 = state.tasks || {};
        const _allDone2 = _order2.length
          ? _order2.every(item => Boolean(_tasks2[item]))
          : Object.values(_tasks2).every(v => Boolean(v));
        if (_allDone2) {
          if (env === "office") {
            el.textContent = "Run complete — all required proposal steps have been resolved.";
          } else if (env === "cafe") {
            el.textContent = "Run complete — the group has reached its final decision.";
          } else {
            el.textContent = "Run complete — all required escape steps have been resolved.";
          }
          el.style.color = "var(--teal)";
        } else {
          const firstUnresolved2 = _order2.find(item => !Boolean(_tasks2[item])) || null;
          el.textContent = firstUnresolved2
            ? `Run ended — ${itemLabel(firstUnresolved2)} was not confirmed before the step limit.`
            : "Run ended — not all required steps were completed.";
          el.style.color = "var(--red, #e05c5c)";
        }
        return;
      }
      const blocker = currentBlocker();
      if (!blocker) {
        el.textContent = "No active focus — watch for the final resolution";
        el.style.color = "var(--teal)";
        return;
      }
      el.style.color = "";
      // Final-stage blockers: no info left to reveal, steer toward completion
      const env = String(state.environment || state.scenarioHint || "").toLowerCase();
      const isFinalUnlock   = (env === "escape" || env === "escape_room") && blocker === "unlock";
      const isFinalDecision = (env === "cafe"   || env === "cafe_restaurant") && (blocker === "decision" || blocker === "final_decision");
      if (isFinalUnlock) {
        el.textContent = "Suggested: Verify the exit code and open it — this is the final step.";
        return;
      }
      if (isFinalDecision) {
        el.textContent = "Suggested: Bring the team together to confirm the final decision.";
        return;
      }
      const anyMissing = state.agents.some(
        a => Array.isArray(a.known_items) && !a.known_items.includes(blocker)
      );
      el.textContent = anyMissing
        ? `Suggested: Reveal Info`
        : `Suggested: Force Meeting`;
    }

    function shortItemLabel(item) {
      const raw = String(item || "");
      const labels = {
        dietary_constraint: "Dietary",
        budget_constraint: "Budget",
        location_constraint: "Location",
        final_decision: "Decision",
        decision: "Decision",
        requirements: "Requirements",
        design: "Design",
        budget: "Budget",
        tech_specs: "Specs",
        map: "Map",
        pattern: "Pattern",
        code: "Code",
        key: "Key",
        unlock: "Unlock",
      };
      return labels[raw] || itemLabel(item);
    }

    function updateStepStrip() {
      const labelEl = $("sTickLabel");
      const valueEl = $("sTick");
      if (!labelEl || !valueEl) return;
      if (state.ended) {
        labelEl.textContent = "Final Step";
        valueEl.textContent = String(state.tick || state.nextDisplayStep || 0);
        return;
      }
      labelEl.textContent = "Next Step";
      valueEl.textContent = String(Math.max(1, Number(state.tick || 0) + 1));
    }

    // ── Event type / actor labels ──────────────────────────────────────
    function labelForEventType(type) {
      const key = String(type || "").toLowerCase();
      const labels = {
        intervention: "Intervention",
        ask: "Ask", ask_info: "Ask",
        share: "Share", share_info: "Share",
        agree: "Agree", confirm: "Confirm",
        say: "Say", refuse: "Refuse",
        challenge: "Challenge", suggest: "Suggest",
        summary: "Summary", finalise: "Finalise", resolve: "Resolve",
        compliment: "Praise", clue: "Clue",
        coord: "Coordinate", enter: "Enter",
        open: "Open", doubt: "Doubt",
        reassure: "Reassure", insult: "Clash",
        ignore: "Ignore", pressure: "Pressure",
        emotion_injection: "Emotion Input",
      };
      if (labels[key]) return labels[key];
      if (!key || key.includes("_") || key.includes("fallback") || key.includes("micro")) {
        return "Update";
      }
      return key.charAt(0).toUpperCase() + key.slice(1);
    }

    function actorLabel(actor) {
      const raw = String(actor || "");
      if (raw.toUpperCase() === "USER") return "You";
      if (raw.toUpperCase() === "GROUP") return "Team";
      return raw || "?";
    }

    function normalizeScenarioItemKey(item) {
      const raw = String(item || "").trim().toLowerCase().replace(/[.\s]+$/g, "");
      const normalized = raw.replace(/\s+/g, "_");
      const aliases = {
        final_decision: "decision",
        finalise: "decision",
        finalize: "decision",
      };
      return aliases[normalized] || normalized;
    }

    function itemLabel(item) {
      const raw = normalizeScenarioItemKey(item);
      // Check every scenario's label map first so the canonical names are always used.
      for (const cfg of Object.values(SCENARIO_CONFIG)) {
        if (cfg.labels && cfg.labels[raw]) return cfg.labels[raw];
      }
      // Alias / legacy keys that don't appear directly in canonical orders.
      const aliases = {
        pattern:          "Lock Pattern",
        lock_pattern:     "Lock Pattern",
        lock_combination: "Lock Pattern",
        combination:      "Lock Pattern",
        key_location:     "Key Location",
        code:             "Door Code",
        door_code:        "Door Code",
        lock:             "Lock Pattern",
      };
      if (aliases[raw]) return aliases[raw];
      return raw
        .replace(/_/g, " ")
        .replace(/\b\w/g, (char) => char.toUpperCase());
    }

    function eventEnvironment(ev) {
      return String(ev?.__environment || state.environment || state.scenarioHint || "").toLowerCase();
    }

    function stepActiveBlockerForEvent(ev) {
      // ALWAYS compute from a task snapshot using the canonical scenario order.
      // Never fall back to ev.__stepActiveBlocker or currentBlocker() — both can
      // reflect bottleneck_item which is set to the intervention's target item
      // (e.g. "budget") rather than the true first-unresolved blocker.
      // Use ev.__stepTasks when available; fall back to state.tasks as the best
      // available approximation (still canonical-order based, never bottleneck_item).
      const tasks = (ev?.__stepTasks != null) ? ev.__stepTasks : (state.tasks ?? {});
      const env = ev?.__environment || state.environment || state.scenarioHint || "";
      const order = scenarioBlockerOrder(env);
      return order.find(item => !tasks[item]) ?? null;
    }

    function stepNextBlockerForEvent(ev) {
      return ev?.__stepNextBlocker ?? currentBlocker();
    }

    // Given a just-resolved item, find the next unresolved item in the canonical
    // scenario chain.  This is the correct "moves on to" target — it is always
    // the item immediately after resolvedItem in the declared order that has not
    // yet been resolved.  Using blocker (the active blocker) would be wrong if
    // the task snapshot shows the resolved item still as false (same-tick lag).
    function nextBlockerInChain(resolvedItem, stepTasks, env) {
      const order = scenarioBlockerOrder(env);
      const idx = order.indexOf(resolvedItem);
      if (idx < 0) return null;
      for (let i = idx + 1; i < order.length; i++) {
        if (!stepTasks[order[i]]) return order[i];
      }
      return null;  // resolvedItem was the last in the chain
    }

    function stepTasksForEvent(ev) {
      return ev?.__stepTasks || state.tasks || {};
    }

    function stepResolvedItems(ev) {
      return Array.isArray(ev?.__resolvedItems) ? ev.__resolvedItems : [];
    }

    // ── Scenario timeline contract ─────────────────────────────────────────────
    // Single source of truth for per-scenario blocker order, labels, synthetic
    // finalisation text, and the completed-run summary chain.  ALL rendering
    // functions must read from this object; text detection is a fallback only.
    const SCENARIO_CONFIG = {
      cafe: {
        order: ["dietary_constraint", "budget_constraint", "location_constraint", "decision"],
        labels: {
          dietary_constraint: "Dietary Constraint",
          budget_constraint:  "Budget",
          location_constraint: "Location",
          decision:           "Decision",
        },
        finalisationText: {
          dietary_constraint: "The team confirmed the dietary requirement (vegan-friendly). The group can now work on the budget.",
          budget_constraint:  "The team confirmed the budget limit. The group can now agree on a location.",
          location_constraint: "The team confirmed the location — nearby and easy to reach. The group can now lock in the café choice.",
          decision:           "The team finalised the nearby vegan-friendly option within budget.",
        },
        evidenceShareText: {
          dietary_constraint: "We need something vegan-friendly — that's the dietary constraint we're working with.",
          budget_constraint:  "The budget is the key constraint here — we need an affordable option.",
          location_constraint: "Location matters — it needs to be nearby and easy for everyone to reach.",
          decision:           "We've covered all the constraints. Time to lock in the final choice.",
        },
        summaryChain: "Dietary Constraint → Budget → Location → Decision",
      },
      office: {
        order: ["requirements", "design", "tech_specs", "budget"],
        labels: {
          requirements: "Requirements",
          design:       "Design Plans",
          tech_specs:   "Spec Doc",
          budget:       "Budget",
        },
        finalisationText: {
          requirements: "The requirements are confirmed: mobile access and offline mode support.",
          design:       "The design is confirmed: a flat, modern UI with a blue colour scheme.",
          tech_specs:   "The technical specification is confirmed: React frontend, Node backend, and PostgreSQL database.",
          budget:       "The budget is confirmed: $50k total with a 10% contingency buffer.",
        },
        evidenceShareText: {
          requirements: "The key requirements are mobile access and offline mode — that's what the client needs.",
          design:       "We're going with a flat, modern UI — blue colour scheme throughout.",
          tech_specs:   "The stack is React on the frontend, Node for the backend, PostgreSQL for the database.",
          budget:       "The budget is $50k total, with 10% held back as contingency.",
        },
        summaryChain: "Requirements → Design Plans → Spec Doc → Budget",
      },
      escape: {
        order: ["map", "lock", "key", "door", "unlock"],
        labels: {
          map:    "Room Map",
          lock:   "Lock Pattern",
          key:    "Key Location",
          door:   "Door Code",
          unlock: "Final Unlock",
        },
        finalisationText: {
          map:    "The room map was decoded. The team can now analyse the lock pattern.",
          lock:   "The lock pattern was confirmed as triangle, circle, square. The team can now locate the key.",
          key:    "The key was found. The team can now enter the door code.",
          door:   "The door code was entered. The team can now attempt the final unlock.",
          unlock: "The final lock was opened. The team has escaped the room.",
        },
        evidenceShareText: {
          map:    "The panel is on the east wall, behind the bookshelf — that's where we need to look.",
          lock:   "The lock sequence is triangle, then circle, then square — in that order.",
          key:    "The key is magnetic — it's attached to the metal panel on the east wall.",
          door:   "The door code is 4-2-7-1. Enter that to open the exit.",
          unlock: "We have everything. Enter the code and open the exit now.",
        },
        summaryChain: "Room Map → Lock Pattern → Key Location → Door Code → Final Unlock",
      },
    };

    // Return the SCENARIO_CONFIG entry for an environment string.
    // Defaults to escape (the 5-item chain) when the env is unrecognised.
    function scenarioConfig(environment = "") {
      const env = String(environment || state.environment || state.scenarioHint || "").toLowerCase();
      return SCENARIO_CONFIG[env] || SCENARIO_CONFIG.escape;
    }

    function scenarioBlockerOrder(environment = "") {
      return scenarioConfig(environment).order;
    }

    function resolvedBlockerLabelsFromTasks(tasks = {}, environment = "") {
      return scenarioBlockerOrder(environment)
        .filter((item) => Boolean(tasks[item]))
        .map((item) => itemLabel(item));
    }

    // ── Task-transition ground-truth helpers ────────────────────────────────
    /**
     * Derive the ordered list of task-resolution events by comparing consecutive
     * history snapshot tasks.  Each false→true transition becomes one entry.
     *
     * This is the most reliable source for "what resolved and when" —
     * it reads only from scenario.tasks, never from text detection or fallback
     * config strings, so it stays correct even if group_state lags.
     *
     * @param {Array}  history      — run history array (snapshots from backend)
     * @param {string} scenarioKey  — "cafe" | "office" | "escape"
     * @returns {Array<{item:string, tick:number, label:string}>}
     */
    function deriveResolvedPhasesFromHistory(history, scenarioKey) {
      const key = String(scenarioKey || "").toLowerCase();
      const cfg = SCENARIO_CONFIG[key] || SCENARIO_CONFIG.escape;
      const order = cfg.order;
      const prevTasks = {};
      order.forEach(item => { prevTasks[item] = false; });
      const transitions = [];
      (Array.isArray(history) ? history : []).forEach(snap => {
        const tasks = snap.scenario?.tasks || {};
        const tick  = Number(snap.tick || 0);
        order.forEach(item => {
          if (!prevTasks[item] && tasks[item]) {
            transitions.push({
              item,
              tick,
              label: (cfg.labels && cfg.labels[item]) || itemLabel(item),
            });
          }
          if (tasks[item]) prevTasks[item] = true;
        });
      });
      return transitions;
    }

    function deriveResolvedPhasesFromTaskTransition(previousTasks = {}, currentTasks = {}, scenarioKey = "") {
      const key = String(scenarioKey || "").toLowerCase();
      const cfg = SCENARIO_CONFIG[key] || SCENARIO_CONFIG.escape;
      return cfg.order
        .filter((item) => !previousTasks[item] && Boolean(currentTasks[item]))
        .map((item) => ({
          item,
          label: (cfg.labels && cfg.labels[item]) || itemLabel(item),
        }));
    }

    /**
     * Validate that a completed run's history records every blocker in the
     * canonical chain as both:
     *  (a) true in the final snapshot's scenario.tasks, AND
     *  (b) present as a false→true task-state transition.
     *
     * Returns a plain object the caller can log or use to gate "Escape Successful".
     */
    function validateCompletedScenario(history, scenarioKey) {
      const key = String(scenarioKey || "").toLowerCase();
      const cfg = SCENARIO_CONFIG[key] || SCENARIO_CONFIG.escape;
      const order = cfg.order;
      const transitions = deriveResolvedPhasesFromHistory(history, key);
      const resolvedSet = new Set(transitions.map(t => t.item));
      const lastSnap = Array.isArray(history) && history.length
        ? history[history.length - 1] : null;
      const finalTasks = lastSnap?.scenario?.tasks || {};
      const allTasksTrue           = order.every(item => Boolean(finalTasks[item]));
      const allTransitionsPresent  = order.every(item => resolvedSet.has(item));
      return {
        valid:                  allTasksTrue && allTransitionsPresent,
        allTasksTrue,
        allTransitionsPresent,
        resolvedTransitions:    transitions,
        missingFromTasks:       order.filter(item => !finalTasks[item]),
        missingFromTransitions: order.filter(item => !resolvedSet.has(item)),
      };
    }

    function eventItemFromContext(ev, blockerOverride = null) {
      const blocker = blockerOverride || stepActiveBlockerForEvent(ev);
      // Priority order (matches the scenario timeline contract):
      //   1. ev.item / ev.preference — explicitly tagged by the backend; most reliable
      //   2. blocker     — first-unresolved item from task snapshot in scenario order
      //   3. detectedItem — keyword scan; fallback only; can produce cross-scenario contamination
      //
      // Text detection is intentionally LAST so that e.g. an agree event whose body
      // mentions "vegan" (dietary text) while "decision" is the live blocker resolves
      // correctly to "decision", not "dietary_constraint".
      const detectedItem = detectItemFromText(ev?.text, eventEnvironment(ev));
      return normalizeScenarioItemKey(ev?.item || ev?.preference || blocker || detectedItem || null) || null;
    }

    function stepEventTitle(ev) {
      const rawBlocker = stepActiveBlockerForEvent(ev);
      const reason = String(ev?.reason || "");
      // For user-triggered events, use the tick-start blocker (ev.__stepActiveBlocker) as the
      // active context so the step title reflects what was actually happening when the
      // intervention was processed — not the end-of-tick blocker which may have advanced
      // (e.g. if Design Plans resolves in the same tick, end-of-tick blocker = "tech_specs"
      // which would wrongly title the step "Spec Doc Confirmed" instead of "Design Plans Confirmed").
      const activeBlocker = reason.startsWith("user_")
        ? (ev.__stepActiveBlocker || rawBlocker)
        : rawBlocker;
      const item = eventItemFromContext(ev, activeBlocker);
      const resolvedItems = stepResolvedItems(ev);
      const label = item ? itemLabel(item) : "Interaction";
      const type = String(ev?.type || "").toLowerCase();
      const env = eventEnvironment(ev);
      const _titleStepTasks = ev?.__stepTasks || {};
      // isFutureReveal: item is ahead of the active blocker in the chain, was not resolved
      // this tick, AND was not already resolved in a prior tick (already-resolved items
      // should not be labelled as "Revealed Early" — they are simply revisited).
      const isFutureReveal = Boolean(
        item && activeBlocker && item !== activeBlocker
        && !resolvedItems.includes(item)
        && !_titleStepTasks[item]
      );
      if (type === "resolve") {
        const firstResolved = (stepResolvedItems(ev))[0] || item;
        return firstResolved ? `${itemLabel(firstResolved)} Finalised` : "Decision Finalised";
      }
      if (type === "hold") {
        if (activeBlocker) {
          // If the step's task snapshot already shows the blocker resolved, don't label it as waiting.
          const stepTasks = ev?.__stepTasks || {};
          if (stepTasks[activeBlocker] === true) return "No New Exchange";
          return `${itemLabel(activeBlocker)} Waiting`;
        }
        return "No New Exchange";
      }
      if (type === "ask" || type === "ask_info") return `${label} Requested`;
      if ((type === "share" || type === "share_info") && reason === "quiet_share") {
        return `${label} — Evidence Note`;
      }
      if (type === "share" || type === "share_info") {
        if (resolvedItems.includes(item)) return `${label} Confirmed`;
        // Item was already resolved in a prior tick — don't treat as a new revelation
        if (item && _titleStepTasks[item] === true) return `${label} Revisited`;
        if (isFutureReveal) return `${label} Revealed Early`;
        return `${label} Shared`;
      }
      if (type === "agree" || type === "confirm") {
        // Only say "Confirmed" when this event actually seals the deal (item resolves this tick).
        // A partial agree/confirm that doesn't yet resolve the blocker gets "Endorsed" so the
        // title doesn't claim a resolution that hasn't landed yet.
        if (env === "cafe" && isFutureReveal) {
          if (activeBlocker === "dietary_constraint") return "Dietary Constraint Explored";
          if (activeBlocker === "decision") return "Decision Discussed";
        }
        if (env === "cafe" && activeBlocker === "location_constraint" && item === "budget_constraint" && isFutureReveal) {
          return "Budget Mentioned Again";
        }
        if (isFutureReveal) return `${label} Discussed Early`;
        return resolvedItems.includes(item) ? `${label} Confirmed` : `${label} Endorsed`;
      }
      if (type === "suggest") {
        // When an agent raises a future item (e.g. Budget) while a different
        // blocker is still active, "Budget Explored" is misleading because the
        // Why/Effect are about the live blocker, not Budget.  Label it as an
        // early discussion instead so the step is self-consistent.
        if (env === "cafe" && isFutureReveal) {
          if (activeBlocker === "dietary_constraint") return "Dietary Constraint Explored";
          if (activeBlocker === "decision") return "Decision Discussed";
        }
        if (env === "cafe" && activeBlocker === "location_constraint" && item === "budget_constraint" && isFutureReveal) {
          return "Budget Mentioned Again";
        }
        if (isFutureReveal) return `${label} Discussed Early`;
        return `${label} Explored`;
      }
      if (type === "challenge" || type === "refuse" || type === "doubt") return `${label} Challenged`;
      if (type === "intervention") return "User Intervention Applied";
      if (type === "pressure") return `${label} Under Pressure`;
      return `${label} Updated`;
    }

    function environmentLabel(name) {
      const raw = String(name || "").toLowerCase();
      const labels = {
        office: "Office",
        cafe: "Cafe",
        escape: "Escape",
        escape_room: "Escape",
      };
      return labels[raw] || formatRoleLabel(name);
    }

    function teamLabel(name) {
      const raw = String(name || "").toLowerCase();
      const labels = {
        smooth: "Smooth Team",
        tension: "Tension Team",
        pressure: "Pressure Team",
        creative: "Creative Team",
      };
      return labels[raw] || formatRoleLabel(name);
    }

    function formatRoleLabel(role) {
      const raw = String(role || "").trim();
      if (!raw) return "Active participant";
      return raw
        .replace(/_/g, " ")
        .replace(/\b\w/g, (char) => char.toUpperCase());
    }

    function statusLabel(status, ended = false) {
      if (ended || status === "ended") return "Completed";
      const labels = {
        idle: "Ready for your action",
        paused: "Ready for your action",
        auto_stopped: "Ready for your action",
        stopped: "Stopped",
        running: "Auto running",
        auto_running: "Auto running",
      };
      return labels[String(status || "").toLowerCase()] || formatRoleLabel(status || "idle");
    }

    function wsLabel(status) {
      const labels = {
        open: "Open",
        closed: "Closed",
        connecting: "Connecting",
        error: "Error",
      };
      return labels[String(status || "").toLowerCase()] || formatRoleLabel(status || "closed");
    }

    function clamp01(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return 0;
      return Math.max(0, Math.min(1, n));
    }

    function knownTaskTotal() {
      const tasks = state.tasks || {};
      const core = Object.keys(tasks).filter((name) => name !== "unlock");
      return core.length || 1;
    }

    function ownedItemsForAgent(agentId) {
      const knowledge = state.knowledgeMap || {};
      const items = knowledge[agentId] || [];
      return Array.isArray(items) ? items : [];
    }

    function knownItemCount(agent) {
      return Array.isArray(agent?.known_items)
        ? agent.known_items.length
        : Number(agent?.known || 0);
    }

    function moodLabel(valence) {
      const n = Number(valence);
      if (!Number.isFinite(n)) return "Unavailable";
      if (n >= 0.25) return "Positive";
      if (n <= -0.25) return "Negative";
      return "Neutral";
    }

    function moodBarClass(valence) {
      const n = Number(valence);
      if (!Number.isFinite(n)) return "valence-neutral";
      if (n >= 0.25) return "valence-positive";
      if (n <= -0.25) return "valence-negative";
      return "valence-neutral";
    }

    // Stress labels are scenario-aware because each scenario has different expected stress baselines.
    // Each entry is [Low_max, Moderate_max]; values >= Moderate_max → "High".
    const STRESS_THRESHOLDS = {
      cafe:   [0.20, 0.40],  // Café is calm — 0.25 already reads as Moderate
      office: [0.30, 0.55],  // Office is moderate — 0.30 Low, 0.55+ High
      escape: [0.40, 0.65],  // Escape is pressured — elevated stress is expected
    };

    // Returns { level: "low"|"moderate"|"high", label: "Low"|"Moderate"|"High" }
    function getStressLevel(stress, env) {
      const n = Number(stress);
      if (!Number.isFinite(n)) return { level: "low", label: "—" };
      const sk = scenarioKeyFromEnv(env);
      const [lowMax, modMax] = STRESS_THRESHOLDS[sk] || STRESS_THRESHOLDS.office;
      if (n < lowMax) return { level: "low",      label: "Low" };
      if (n < modMax) return { level: "moderate",  label: "Moderate" };
      return                  { level: "high",     label: "High" };
    }

    function findAgent(agentId) {
      return state.agents.find((agent) => (agent.public_id || agent.id) === agentId);
    }

    function agentRoleLabel(agent) {
      return formatRoleLabel(
        agent.role || agent.personality || agent.personality_type || agent.title || ""
      );
    }

    function agentOptionLabel(agentId) {
      const agent = findAgent(agentId);
      if (!agent) return agentId;
      return `${agent.public_id || agent.id} · ${agentRoleLabel(agent)}`;
    }

    function pickVariant(seed, options) {
      if (!options.length) return "";
      let hash = 0;
      for (let i = 0; i < seed.length; i += 1) {
        hash = ((hash << 5) - hash + seed.charCodeAt(i)) | 0;
      }
      return options[Math.abs(hash) % options.length];
    }

    function userTriggerLabel(reason) {
      const labels = {
        user_nudge_strategy: "Response to your nudge",
        user_force_meeting:  "Response to your forced meeting",
        user_boost_urgency:  "Response to your urgency boost",
        user_ease_pressure:  "Response to easing pressure",
        user_inject_tension: "Response to your tension injection",
        user_reveal_info:    "Follow-through on your reveal",
      };
      return labels[reason] || "User-triggered";
    }

    function pressureDisplayChangeText(beforePressure, afterPressure, direction) {
      const env = state.environment || state.scenarioHint;
      const beforeDisplay = displayPressureValue(beforePressure, env);
      const afterDisplay = displayPressureValue(afterPressure, env);
      if (!Number.isFinite(beforeDisplay) || !Number.isFinite(afterDisplay)) {
        return direction === "down"
          ? "Pressure decreased slightly."
          : "Pressure increased slightly.";
      }
      const delta = afterDisplay - beforeDisplay;
      if (Math.abs(delta) < 0.001) {
        return direction === "down"
          ? "Pressure is already at the scenario baseline."
          : "Pressure is already at maximum.";
      }
      const signedDelta = `${delta > 0 ? "+" : ""}${delta.toFixed(2)}`;
      return `Pressure ${beforeDisplay.toFixed(2)} → ${afterDisplay.toFixed(2)} (${signedDelta}).`;
    }

    // Keep the intervention copy a bit cleaner than the raw backend strings so
    // the timeline reads like a person wrote it, not like a debug log.
    // ── Intervention message formatting ────────────────────────────────
    function formatInterventionMessage(type, params, rawMessage, blockerOverride = undefined) {
      const message = String(rawMessage || "").trim();
      // Always use the canonical task-order blocker when provided — currentBlocker()
      // can return bottleneck_item which is backend-influenced and may point to a
      // future/intervention-target item rather than the true first-unresolved task.
      const blocker = blockerOverride !== undefined ? blockerOverride : currentBlocker();
      const blockerText = blocker ? itemLabel(blocker) : null;
      const targetItem = normalizeScenarioItemKey(params?.item || null);
      const targetText = targetItem ? itemLabel(targetItem) : null;
      const targetDiffers = Boolean(targetText && blockerText && targetItem !== blocker);

      if (type === "reveal_info") {
        if (message.includes("task marked complete")) {
          return `Revealed ${itemLabel(params.item)} to ${params.agent_id} and marked it complete.`;
        }
        return `Revealed ${itemLabel(params.item)} to ${params.agent_id}.`;
      }

      if (type === "force_meeting") {
        return blockerText
          ? `Called ${params.agent_a_id} and ${params.agent_b_id} into a direct conversation about ${blockerText}.`
          : `Called ${params.agent_a_id} and ${params.agent_b_id} into a direct conversation.`;
      }

      if (type === "nudge_strategy") {
        const reinforced = message.match(/^(.+?) reinforced as ([^.]+)\.$/);
        if (reinforced) {
          const [, agentId, strategy] = reinforced;
          return blockerText
            ? `Reinforced ${agentId}'s ${strategy} approach on ${blockerText}.`
            : `Reinforced ${agentId}'s ${strategy} approach.`;
        }
        const match = message.match(/^(.+?) strategy changed: ([^ ]+) → ([^.]+)\.$/);
        if (match) {
          const [, agentId, oldStrategy, newStrategy] = match;
          if (oldStrategy === newStrategy) {
            if (targetDiffers) {
              return `Reinforced ${agentId}'s ${newStrategy} approach while ${blockerText} remains the current focus.`;
            }
            return blockerText
              ? `Reinforced ${agentId}'s ${newStrategy} approach on ${blockerText}.`
              : `Reinforced ${agentId}'s ${newStrategy} approach.`;
          }
          if (targetDiffers) {
            return `Asked ${agentId} to take a more ${newStrategy} line while ${blockerText} remains the current focus.`;
          }
          return blockerText
            ? `Asked ${agentId} to take a more ${newStrategy} line on ${blockerText}.`
            : `Asked ${agentId} to take a more ${newStrategy} line.`;
        }
        if (targetDiffers) {
          return `Nudged ${params.agent_id} toward cooperation while ${blockerText} remains the current focus.`;
        }
        return blockerText
          ? `Nudged ${params.agent_id} toward cooperation on ${blockerText}.`
          : `Nudged ${params.agent_id} toward cooperation.`;
      }

      if (type === "inject_tension") {
        if (targetDiffers) {
          return `A short tension spike was introduced while ${blockerText} remains the current focus.`;
        }
        if (blockerText) return `A short tension spike was introduced around ${blockerText}.`;
        return "A short tension spike was introduced for the next step.";
      }

      if (type === "boost_urgency") {
        const beforePressure = Number(
          state.urgencySeeded
            ? state.urgencyValue
            : scenarioBaseUrgency(state.environment || state.scenarioHint)
        );
        const matched = String(message || "").match(/Environment urgency now ([0-9.]+)/);
        const afterPressure = matched
          ? Number.parseFloat(matched[1])
          : (beforePressure + Number(params?.amount || PRESSURE_INTERVENTION_AMOUNT));
        return pressureDisplayChangeText(beforePressure, afterPressure, "up");
      }

      if (type === "ease_pressure") {
        if (blockerText) return `You eased pressure around ${blockerText}.`;
        return "You eased pressure for the team.";
      }

      return message || "Intervention applied.";
    }

    function buildLocalInterventionEvent(type, params, rawMessage, displayTextOverride = null) {
      // Add a local event immediately so the UI responds before the websocket
      // round-trip comes back with the backend-confirmed version.
      // displayTextOverride must be passed for pressure interventions so the text uses the
      // correct pre-update pressure value — formatInterventionMessage reads
      // state.urgencyValue which has already been updated by this point.
      let target;
      if (type === "force_meeting" && params.agent_a_id && params.agent_b_id) {
        target = `${params.agent_a_id} & ${params.agent_b_id}`;
      } else {
        target = params.agent_id || params.agent_a_id || params.agent_b_id || "GROUP";
      }

      // Compute the canonical blocker from the task snapshot using scenario order —
      // the same logic stepActiveBlockerForEvent uses.  currentBlocker() can return
      // bottleneck_item (the backend's intervention-influenced focus) which may point
      // to a future item, causing body text and the "↳ Current focus:" footer to disagree.
      const _localEnv   = state.environment || state.scenarioHint || "";
      const _localOrder = scenarioBlockerOrder(_localEnv);
      const _localTasks = state.tasks || {};
      const canonicalBlockerNow = _localOrder.find(item => !_localTasks[item]) ?? null;

      return {
        tick: Number(state.tick || 0) + 1,
        type: "intervention",
        actor: "USER",
        target,
        text: rawMessage,
        displayText: displayTextOverride || formatInterventionMessage(type, params, rawMessage, canonicalBlockerNow),
        reason: type,
        params: { ...params },
        __stepActiveBlocker: canonicalBlockerNow,
        // Snapshot the task state at the moment the intervention fires so that
        // stepActiveBlockerForEvent() can recompute the correct blocker even
        // if this event is rendered after a subsequent resolution.
        __stepTasks: { ..._localTasks },
        __environment: _localEnv,
      };
    }

    function massageEventText(ev) {
      if (ev.displayText) return ev.displayText;

      if (String(ev.actor || "").toUpperCase() === "USER" && ev.type === "intervention") {
        // Use the same canonical-task-order blocker that the footer derives from
        // stepActiveBlockerForEvent so the body text and "↳ Current focus:" always agree.
        const canonicalBlocker = stepActiveBlockerForEvent(ev);
        return formatInterventionMessage(ev.reason, ev.params || {}, ev.text, canonicalBlocker);
      }

      // A few intervention follow-up lines get softened here so the live feed
      // stays consistent with the rest of the page copy.
      const text = String(ev.text || "").trim();
      if (!text) return "";

      if (ev.reason === "user_inject_tension" && text === "Something about this is starting to feel tense.") {
        return pickVariant(`${ev.tick}|${ev.actor}|${ev.target}|${ev.reason}`, [
          "This is starting to feel tense.",
          "Something's getting tense here.",
          "This is getting tense now.",
        ]);
      }

      if (ev.reason === "user_boost_urgency" && text === "Let's move faster — we need progress this tick.") {
        return pickVariant(`${ev.tick}|${ev.actor}|${ev.target}|${ev.reason}`, [
          "We need movement this step.",
          "Faster now — we need progress.",
          "Pick it up — we need progress now.",
        ]);
      }

      if (ev.reason === "user_boost_urgency" && text === "Quick pace now — let's keep momentum up.") {
        return pickVariant(`${ev.tick}|${ev.actor}|${ev.target}|${ev.reason}`, [
          "Keep the pace up now.",
          "Quick push — keep the momentum going.",
          "Stay sharp — keep it moving.",
        ]);
      }

      // Office: replace a known vague requirements-reveal phrase with concrete text
      // so the timeline shows the actual content rather than a future-budget hint.
      if (/I've got requirements lined up[^.]*budget is closed/i.test(text)) {
        return "I've got the requirements ready: mobile access and offline support.";
      }

      // Office: agents sometimes count remaining tasks using "one left", "one more",
      // or "one thing left" in the same tick that Budget resolves.  Budget IS the
      // final item, so any counting phrase is misleading — replace with outcome-focused language.
      const rItems = Array.isArray(ev.__resolvedItems) ? ev.__resolvedItems : [];
      const env = state.environment || state.scenarioHint || "";
      if (env === "office" && rItems.includes("budget") &&
          /\bone\s+(?:thing\s+)?left\b|\bone\s+more\b/i.test(text)) {
        return "Good — budget is locked. The proposal can go forward.";
      }

      return text;
    }

    function displayPriority(ev) {
      if (String(ev.actor || "").toUpperCase() === "USER" || ev.type === "intervention" || ev.type === "emotion_injection") return 0;
      if (String(ev.reason || "").startsWith("user_")) return 1;
      // Elevate events whose item/preference matches a resolved item in this tick so the
      // step group title reflects the actual resolution (e.g. "Requirements Confirmed")
      // rather than a co-occurring future-blocker event (e.g. "Design Plans Confirmed").
      const resolvedItems = Array.isArray(ev.__resolvedItems) ? ev.__resolvedItems : [];
      if (String(ev.type || "").toLowerCase() === "resolve") return 2.8;
      if (resolvedItems.length > 0) {
        const item = normalizeScenarioItemKey(ev.item || ev.preference || "");
        // Evidence / share / agree for the item resolving this tick: before the resolve event.
        if (item && resolvedItems.includes(item)) return 1.5;
        // Events about the NEXT focus (item not resolved this tick) must appear AFTER
        // the Team Resolve event.  This prevents "A4 asks for Budget" appearing before
        // "Spec Doc resolved" in the same step — the reader must see resolution first.
        if (item && !resolvedItems.includes(item)) return 3.5;
      }
      return 2;
    }

    // ── Controls enable/disable ────────────────────────────────────────
    // Show/clear small inline messages inside intervention cards.
    // These replace banner pop-ups for normal validation feedback.
    function setIvInline(id, msg) {
      const el = $(id);
      if (!el) return;
      if (msg) { el.textContent = msg; el.classList.remove("hidden"); }
      else        { el.textContent = ""; el.classList.add("hidden"); }
    }

    function setInterventionsEnabled(enabled) {
      const canUse = enabled && state.wsReady && !state.actionPending && !state.autoRunning;
      const revealAgentId = $("revealAgent").value;
      const revealOptions = revealableItemsForAgent(revealAgentId);
      const revealValid = canUse && revealAgentId && $("revealItem").value;
      const forceA = $("forceAgentA").value;
      const forceB = $("forceAgentB").value;
      const forceValid = canUse && forceA && forceB && forceA !== forceB;
      const nudgeAgentId = $("nudgeAgent").value;
      const nudgeAgent = state.agents.find((agent) => (agent.public_id || agent.id) === nudgeAgentId);
      const alreadyCooperative = nudgeAgent && nudgeAgent.strategy === "cooperative";

      const currentPressure = state.urgencySeeded
        ? state.urgencyValue
        : scenarioBaseUrgency(state.environment || state.scenarioHint);
      const currentDisplayPressure = displayPressureValue(currentPressure, state.environment || state.scenarioHint);
      const pressureBaseline = displayPressureBaseline(state.environment || state.scenarioHint);
      const pressureAtMax = Number.isFinite(currentDisplayPressure) && currentDisplayPressure >= 0.999;
      // pressureAtMin: display has reached the scenario baseline (not absolute zero).
      // Ease Pressure cannot reduce displayed pressure below its scenario baseline.
      const pressureAtMin = Number.isFinite(currentDisplayPressure) && currentDisplayPressure <= pressureBaseline + 0.001;

      if (ivButtons.boost_urgency) ivButtons.boost_urgency.disabled = !canUse || pressureAtMax;
      if (ivButtons.ease_pressure) ivButtons.ease_pressure.disabled = !canUse || pressureAtMin;
      setIvInline("ivNoteBoostPressure", canUse && pressureAtMax ? "Pressure is already at maximum." : null);
      setIvInline("ivNoteEasePressure", canUse && pressureAtMin ? "Pressure is already at the scenario baseline." : null);
      if (ivButtons.inject_tension) ivButtons.inject_tension.disabled = !canUse;
      const emotionTextEl = document.getElementById("emotionText");
      const emotionHasText = emotionTextEl && emotionTextEl.value.trim().length > 0;
      if (ivButtons.inject_emotion) ivButtons.inject_emotion.disabled = !(canUse && emotionHasText);
      if (ivButtons.reveal_info) ivButtons.reveal_info.disabled = !(revealValid && revealOptions.length > 0);
      // Force Meeting: multi-tier ownership + repetition validation
      {
        const fmBlocker = currentBlocker();
        const fmKey = forceValid
          ? [forceA, forceB].sort().join("|") + "|" + (fmBlocker || "")
          : null;
        const exactRepeat    = Boolean(fmKey && state.recentForceMeetings.has(fmKey));
        const ownership      = (forceValid && fmBlocker) ? pairHoldsBlocker(forceA, forceB, fmBlocker) : null;
        const isNonOwner     = ownership === false;  // null = unknown (no data) — no warning
        const nonOwnerRepeat = isNonOwner && state.nonOwnerAttempts.has(fmBlocker || "");

        // Disable when: pair invalid, exact pair repeated, or non-owner pair already tried
        if (ivButtons.force_meeting) {
          ivButtons.force_meeting.disabled = !forceValid || exactRepeat || nonOwnerRepeat;
        }

        // Same-agent selection (highest priority — clear note)
        if (canUse && forceA && forceB && forceA === forceB) {
          setIvInline("ivErrorForce", "Choose two different agents.");
          setIvInline("ivNoteForce", null);

        // Exact same pair tried on this focus already — hard block
        } else if (exactRepeat) {
          const bLabel = fmBlocker ? itemLabel(fmBlocker) : "this focus";
          setIvInline("ivErrorForce",
            `You already tried this meeting for ${bLabel}. Try Reveal Info or choose a different pair.`);
          setIvInline("ivNoteForce", null);

        // Non-owner pair tried before on this focus — escalate to hard block
        } else if (nonOwnerRepeat) {
          const bLabel = fmBlocker ? itemLabel(fmBlocker) : "this focus";
          setIvInline("ivErrorForce",
            `This meeting is unlikely to resolve ${bLabel}. Try Reveal Info or choose an agent with the relevant clue.`);
          setIvInline("ivNoteForce", null);

        // Non-owner pair, first attempt — allow but warn with holder name if known
        } else if (isNonOwner && fmBlocker) {
          const holder     = holderOfBlocker(fmBlocker);
          const holderName = holder ? actorLabel(holder) : null;
          const bLabel     = itemLabel(fmBlocker);
          const hint       = holderName
            ? ` Try including ${holderName} or use Reveal Info.`
            : " Try Reveal Info.";
          setIvInline("ivErrorForce", null);
          setIvInline("ivNoteForce", `These agents may not hold the ${bLabel} clue.${hint}`);

        // Valid pair or unknown ownership — clear all messages
        } else {
          setIvInline("ivErrorForce", null);
          setIvInline("ivNoteForce", null);
        }
      }

      if (ivButtons.nudge_strategy) {
        ivButtons.nudge_strategy.disabled = !(canUse && nudgeAgentId);
        ivButtons.nudge_strategy.textContent = alreadyCooperative ? "✓ Reinforce" : "✓ Nudge";
      }

      // Nudge Cooperation: agent already cooperating — informational, not a block
      setIvInline("ivNoteNudge",
        canUse && nudgeAgentId && alreadyCooperative
          ? "This agent is already cooperating." : null);

      // Reveal Info: agent selected but nothing revealable — reuse existing element
      // (revealEmptyMsg is also managed by syncRevealCard; this covers the live state)
      setIvInline("revealEmptyMsg",
        canUse && revealAgentId && revealOptions.length === 0
          ? "No revealable clue is available right now." : null);
    }

    function setRunControlsEnabled(attached, ended) {
      const canAdvance = attached && state.wsReady && !ended && !state.actionPending && !state.autoRunning;
      const canRestart = Boolean(ended);
      btnStep.disabled = !(canAdvance || canRestart);
      btnReset.disabled = state.actionPending || !state.config;
    }

    function advanceActionLabel() {
      if (state.ended) return "Start New Run";
      const hasStarted = Number(state.tick || 0) > 0 || Boolean(eventLog && eventLog.querySelector(".event"));
      return hasStarted ? "Next Step" : "Start First Step";
    }

    function updateStepButtonLabel() {
      if (!btnStep || !btnStepLabel) return;
      btnStepLabel.textContent = advanceActionLabel();
      btnStep.setAttribute("aria-label", btnStepLabel.textContent);
      // Pulse ring only on the very first action before any step has run
      const isPreRun = !state.ended && Number(state.tick || 0) === 0;
      btnStep.classList.toggle("is-start-action", isPreRun);
    }

    function clearPendingAdvance() {
      if (!state.pendingAdvance) return;
      clearTimeout(state.pendingAdvance.timer);
      state.pendingAdvance = null;
    }

    function resolvePendingAdvance() {
      if (!state.pendingAdvance) return;
      const pending = state.pendingAdvance;
      clearPendingAdvance();
      pending.resolve();
    }

    function rejectPendingAdvance(message) {
      if (!state.pendingAdvance) return;
      const pending = state.pendingAdvance;
      clearPendingAdvance();
      pending.reject(new Error(message));
    }

    function waitForNextTick(startTick) {
      clearPendingAdvance();
      return new Promise((resolve, reject) => {
        const timer = window.setTimeout(() => {
          if (state.pendingAdvance && state.pendingAdvance.timer === timer) {
            rejectPendingAdvance("Timed out waiting for the next step.");
          }
        }, 7000);
        state.pendingAdvance = { startTick, resolve, reject, timer };
      });
    }

    function updateControlState() {
      setRunControlsEnabled(Boolean(state.runId), state.ended);
      setInterventionsEnabled(Boolean(state.runId) && !state.ended);
      updateStepButtonLabel();
      const ivConsole = $("ivConsole");
      const ivCompleteNote = $("ivCompleteNote");
      const ivSectionLabel = $("ivSectionLabel");
      const ivRecommend = $("ivRecommend");
      if (ivConsole) ivConsole.classList.toggle("is-ended", Boolean(state.ended));
      if (ivCompleteNote) ivCompleteNote.classList.toggle("hidden", !state.ended);
      if (ivSectionLabel) ivSectionLabel.classList.toggle("hidden", Boolean(state.ended));
      if (ivRecommend && state.ended) ivRecommend.classList.add("hidden");
      const ivPreRunNote = $("ivPreRunNote");
      if (ivPreRunNote) ivPreRunNote.classList.toggle("hidden", state.ended || Number(state.tick || 0) > 0);
      const agentPanelSub = $("agentPanelSub");
      if (agentPanelSub) {
        if (state.ended) agentPanelSub.textContent = "Final agent states";
        else if (Number(state.tick || 0) > 0) agentPanelSub.textContent = "Private knowledge, style, mood and stress";
        else agentPanelSub.textContent = "Private knowledge, style, mood and stress";
      }
    }

    function eventKey(ev) {
      if ((String(ev.type || "").toLowerCase() === "intervention") || String(ev.actor || "").toUpperCase() === "USER") {
        return [
          ev.tick ?? state.tick,
          "intervention",
          ev.reason || ev.type || "",
          JSON.stringify(ev.params || {}),
        ].join("|");
      }
      return [ev.tick ?? state.tick, ev.type, ev.actor, ev.target, ev.text].join("|");
    }

    function escapeHtml(s) {
      return String(s == null ? "" : s).replace(/[&<>"']/g, c =>
        ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])
      );
    }

    // ── Render agents (compact, strategy-coloured) ─────────────────────
    const STRAT_SHORT = {
      cooperative: "coop", assertive: "assert",
      defensive: "defense", confrontational: "tense",
      avoidant: "avoid", neutral: "neutral",
    };

    function cleanThought(raw) {
      if (!raw) return "";
      // Strip backend debug parentheticals: (key:val, ...) or (key:val)
      let s = raw.replace(/\s*\([^)]*:[^)]*\)/g, "").trim();
      // Strip pure state-transition lines like "Strategy → avoidant"
      if (/^strategy\s*→/i.test(s)) return "";
      // Trim trailing punctuation fragments left after stripping
      return s.replace(/[,·\s]+$/, "").trim();
    }

    const STRATEGY_COLOR = {
      cooperative:    { bg: "#1fa84a", text: "#fff", label: "#0d6b30", labelBg: "rgba(31,168,74,0.10)" },
      assertive:      { bg: "#1fa84a", text: "#fff", label: "#0d6b30", labelBg: "rgba(31,168,74,0.10)" },
      defensive:      { bg: "#2196F3", text: "#fff", label: "#1060b0", labelBg: "rgba(33,150,243,0.10)" },
      confrontational:{ bg: "#F44336", text: "#fff", label: "#a02020", labelBg: "rgba(244,67,54,0.10)" },
      avoidant:       { bg: "#FF9800", text: "#fff", label: "#b06000", labelBg: "rgba(255,152,0,0.10)" },
      neutral:        { bg: "#9C27B0", text: "#fff", label: "#6a1a80", labelBg: "rgba(156,39,176,0.10)" },
    };

    function getAgentColor(strategy) {
      return STRATEGY_COLOR[strategy] || STRATEGY_COLOR.neutral;
    }

    function renderAgents() {
      agentList.innerHTML = "";
      if (!state.agents.length) {
        agentList.innerHTML = '<div class="empty-state">Waiting for first step…</div>';
        return;
      }
      state.agents.forEach((a) => {
        const card = document.createElement("article");
        const id       = a.id || a.public_id || "?";
        const role     = agentRoleLabel(a);
        const strategy = a.strategy || "neutral";
        const color    = getAgentColor(strategy);
        const initials = id.substring(0, 2).toUpperCase();
        const ownedItems = ownedItemsForAgent(id);
        const ownedLabel = ownedItems.length
          ? ownedItems.map((item) => itemLabel(item)).join(", ")
          : "";

        const stress  = a.stress != null ? Number(a.stress).toFixed(2) : "—";
        const stressWidth = `${Math.round(clamp01(a.stress) * 100)}%`;
        const stressInfo  = getStressLevel(a.stress, state.environment || state.scenarioHint);
        const stressLabel = stressInfo.label;
        const stressClass = `stress-${stressInfo.level}`; // stress-low | stress-moderate | stress-high

        // Avg trust toward other agents (trust is a dict {agentId: float})
        const trustVals = Object.values(a.trust || {}).map(Number).filter(isFinite);
        const trustAvg  = trustVals.length ? trustVals.reduce((s, v) => s + v, 0) / trustVals.length : null;
        const trustStr  = trustAvg != null ? trustAvg.toFixed(2) : "—";
        const trustWidth = trustAvg != null ? `${Math.round(clamp01(trustAvg) * 100)}%` : "0%";
        const trustLevel = trustAvg == null ? "neutral"
          : trustAvg >= 0.7 ? "high" : trustAvg >= 0.4 ? "moderate" : "low";

        // Live detected emotion from NLP backend field
        const rawEmotion = String(a.last_detected_emotion || a.emotion || "").toLowerCase();
        const emotionEmoji = {
          joy: "😊", approval: "👍", optimism: "🌟", excitement: "⚡",
          neutral: "😐", surprise: "😮",
          anxiety: "😰", fear: "😨", nervousness: "😬",
          disapproval: "😒", disappointment: "😔", sadness: "😞",
          anger: "😠", annoyance: "😤", frustration: "😤",
          confusion: "🤔", curiosity: "🔍",
          none: "", "": "",
        }[rawEmotion] ?? "💭";
        const emotionLabel = rawEmotion && rawEmotion !== "none"
          ? "Mood: " + rawEmotion.charAt(0).toUpperCase() + rawEmotion.slice(1)
          : null;
        // Display-only label variation for avoidant strategy so a full tension
        // team doesn't show four identical "Style: Avoidant" chips.
        // Underlying strategy value is unchanged — this is purely cosmetic.
        const _AVOIDANT_DISPLAY = ["Avoidant", "Cautious", "Defensive", "Reserved"];
        const _agentOrdinal = Math.max(0, parseInt(String(id).replace(/\D/g, ""), 10) - 1);
        const strategyBase = strategy.toLowerCase() === "neutral"
          ? "Balanced"
          : strategy.toLowerCase() === "avoidant"
            ? _AVOIDANT_DISPLAY[_agentOrdinal % _AVOIDANT_DISPLAY.length]
            : strategy.charAt(0).toUpperCase() + strategy.slice(1);
        const strategyLabel = "Style: " + strategyBase;

        card.className = "agent-card";
        card.style.borderLeftColor = color.bg;
        card.innerHTML = `
          <div class="agent-top">
            <div class="agent-avatar" style="background: ${color.labelBg}; color: ${color.label};">${escapeHtml(initials)}</div>
            <div class="agent-info">
              <div class="agent-name-row">
                <div class="agent-name">${escapeHtml(id)} · ${escapeHtml(role)}</div>
                <div class="agent-strategy-label" style="color: ${color.label}; background: ${color.labelBg};">${escapeHtml(strategyLabel)}</div>
              </div>
              ${ownedLabel ? `<div class="agent-role">Knows: <span class="agent-held-item">${escapeHtml(ownedLabel)}</span></div>` : ""}
            </div>
          </div>
          <div class="agent-meta-row">
            ${emotionLabel ? `<span class="agent-emotion-chip">${emotionEmoji} ${escapeHtml(emotionLabel)}</span>` : ""}
          </div>
          <div class="agent-metrics">
            <div class="metric">
              <div class="metric-topline">
                <span class="metric-label">Stress</span>
                <span class="metric-value">${escapeHtml(String(stress))} · ${escapeHtml(stressLabel)}</span>
              </div>
              <div class="mini-bar stress ${escapeHtml(stressClass)}"><span style="width:${escapeHtml(stressWidth)};"></span></div>
            </div>
            <div class="metric">
              <div class="metric-topline">
                <span class="metric-label">Avg Trust</span>
                <span class="metric-value">${escapeHtml(trustStr)}${trustAvg != null ? ` · ${escapeHtml(trustLevel.charAt(0).toUpperCase() + trustLevel.slice(1))}` : ""}</span>
              </div>
              <div class="mini-bar trust trust-${escapeHtml(trustLevel)}"><span style="width:${escapeHtml(trustWidth)};"></span></div>
            </div>
          </div>
        `;
        agentList.appendChild(card);
      });
    }

    // ── Render events (narrative, quoted dialogue) ─────────────────────
    // Event types that represent speech and should appear in quotes.
    const QUOTED_TYPES = new Set([
      "say","share","share_info","ask","ask_info","agree","confirm",
      "refuse","challenge","suggest","compliment","reassure",
      "pressure","coord","doubt","insult",
    ]);

    function stepGroupIdForEvent(ev, fallbackIndex = 0) {
      if (ev && ev.tick != null) return `tick-${ev.tick}`;
      return `floating-${fallbackIndex}`;
    }

    function stepGroupForId(stepId) {
      return Array.from(eventLog.querySelectorAll(".step-group")).find(
        (group) => group.dataset.stepId === String(stepId)
      ) || null;
    }

    function ensureStepGroup(stepId, stepMarker) {
      let group = stepGroupForId(stepId);
      if (group) return group;

      group = document.createElement("section");
      group.className = "step-group";
      group.dataset.stepId = String(stepId);
      if (stepMarker) group.id = `step-${stepMarker}`;
      if (stepMarker) group.setAttribute("data-step-marker", stepMarker);
      group.innerHTML = `
        <div class="step-group-head">
          <span class="step-group-kicker">Step ${escapeHtml(stepMarker || "—")}</span>
          <span class="step-group-title">Interaction in progress</span>
          <span class="step-group-count">1 interaction in this step</span>
        </div>
        <div class="step-group-events"></div>
      `;
      eventLog.appendChild(group);
      return group;
    }

    function upsertTimelineRangeNote(message) {
      let note = eventLog.querySelector(".timeline-range-note");
      if (!message) {
        if (note) note.remove();
        return;
      }
      if (!note) {
        note = document.createElement("div");
        note.className = "timeline-range-note";
        eventLog.prepend(note);
      }
      note.textContent = message;
    }

    // ── Substantive-evidence helpers ──────────────────────────────────────────
    // A "substantive" resolving event is one whose text actually describes the
    // item's content, not just a generic acknowledgement ("Yeah, that's fine.",
    // "Sounds good.", "Got it.").  Weak-text events are ignored for injection
    // purposes so the synthetic finalisation still fires and the user sees
    // concrete content before the ✓ divider.
    //
    // Patterns are derived directly from ITEM_INFO_TEMPLATES in scenario_data.py.
    const _SUBSTANTIVE_PATTERNS = {
      // Office items
      requirements: /mobile|offline/i,
      design:       /flat|blue|modern|colour|color|layout/i,
      tech_specs:   /react|node|postgresql|stack/i,
      budget:       /\$50|\b50k\b|contingency|sign.?off/i,
      // Café items
      dietary_constraint: /vegan|vegetarian|allergen|dietary/i,
      budget_constraint:  /budget|affordable|per\s+person|cheap/i,
      location_constraint:/nearby|close|walking|distance|easy\s+to\s+(get|reach)/i,
      decision:           /finalised?|confirmed|locked\s+in|let.?s\s+go/i,
      // Escape items — explicit patterns prevent a Door Code message from validating
      // Key Location evidence, or a Map clue from validating Lock Pattern, etc.
      map:  /bookshelf|east.*wall|panel.*wall|wall.*panel|room.*section|section.*room|hidden.*panel/i,
      lock: /triangle|circle|square/i,
      key:  /magnetic|loose.*tile|tile.*door|metal.*panel|panel.*metal|key.*under|under.*tile/i,
      door: /4-2-7-1|four.*two.*seven.*one|code.*\d|digit|\b4271\b/i,
    };

    const _RESOLVING_EVIDENCE_TYPES = new Set([
      "share_info", "share", "agree", "confirm", "open", "enter",
    ]);

    // Returns true only when at least one resolving event for resolvedItem
    // has content-specific text (matching _SUBSTANTIVE_PATTERNS).
    // When a pattern is not defined for the item, ANY matching event is accepted.
    function hasSubstantiveItemEvidence(events, resolvedItem) {
      const pattern = _SUBSTANTIVE_PATTERNS[resolvedItem] || null;
      return events.some(ev => {
        const evType = String(ev.type || "").toLowerCase();
        if (!_RESOLVING_EVIDENCE_TYPES.has(evType)) return false;
        if (String(ev.item || "") !== resolvedItem) return false;
        if (!pattern) return true;                         // no content requirement for this item
        return pattern.test(String(ev.text || ""));
      });
    }
    // ── End substantive-evidence helpers ─────────────────────────────────────

    // forceItem: when set, build a synthetic resolution event for that specific item
    // even if the tick's resolved_items list refers to a different item (e.g. Spec Doc
    // resolved on a tick that only has Budget share evidence — forceItem = "tech_specs").
    //
    // Returns an ARRAY of events (1 or 2) so callers must spread the result.
    // When a blocker resolved without a substantive share event visible in the same
    // tick, a synthetic share is prepended before the resolve event so the marker
    // can see what clue was confirmed and why the blocker closed.
    function buildQuietTickEvent(snapshot, environmentHint = "", forceItem = null) {
      const activeBlocker = snapshot.group_state?.active_blocker || snapshot.group_state?.bottleneck_item || null;
      const stepTasks = snapshot.scenario?.tasks || {};
      const resolvedItems = snapshot.scenario?.resolved_items || [];
      const environment = snapshot.scenario?.environment || environmentHint || state.environment || state.scenarioHint || "";

      // If a blocker resolved on a quiet tick, or we're forcing a specific item's event,
      // render it as a resolution event so the user sees "X Finalised" not "No new exchange".
      if (resolvedItems.length || forceItem) {
        const firstResolved = forceItem || resolvedItems[0];
        const env = String(environment || "").toLowerCase();
        // All finalisation text is owned by SCENARIO_CONFIG so every scenario's
        // quiet-tick resolve messages are consistent with the rest of the timeline.
        const cfgEntry = SCENARIO_CONFIG[env] || SCENARIO_CONFIG.escape;
        const resolveText = (firstResolved && cfgEntry.finalisationText && cfgEntry.finalisationText[firstResolved])
          || (firstResolved ? `The team locked in ${itemLabel(firstResolved)} from the agreed constraints.`
                            : "The team locked in the required step from the agreed constraints.");

        const meta = {
          tick: snapshot.tick,
          __stepActiveBlocker: activeBlocker,
          __stepNextBlocker: snapshot.group_state?.bottleneck_item || null,
          __stepTasks: stepTasks,
          __resolvedItems: resolvedItems,
          __environment: environment,
        };

        const resolveEvent = {
          ...meta,
          type: "resolve",
          actor: "GROUP",
          target: null,
          item: firstResolved || null,
          text: resolveText,
          displayText: resolveText,
          reason: "quiet_resolve",
        };

        // Prepend a synthetic share event when the clue content isn't already visible
        // in the same tick.  This ensures every resolution has traceable evidence in
        // the timeline — the marker can follow: Share → Resolve without a gap.
        const shareText = firstResolved && cfgEntry.evidenceShareText
          ? cfgEntry.evidenceShareText[firstResolved]
          : null;
        if (shareText) {
          const shareEvent = {
            ...meta,
            type: "share_info",
            actor: "GROUP",
            target: null,
            item: firstResolved || null,
            text: shareText,
            displayText: shareText,
            reason: "quiet_share",
          };
          return [shareEvent, resolveEvent];
        }

        return [resolveEvent];
      }

      return [{
        tick: snapshot.tick,
        type: "hold",
        actor: "GROUP",
        target: null,
        text: "",
        displayText: "No new agent message was recorded this step.",
        reason: "quiet_tick",
        __stepActiveBlocker: activeBlocker,
        __stepNextBlocker: snapshot.group_state?.bottleneck_item || null,
        __stepTasks: stepTasks,
        __resolvedItems: resolvedItems,
        __environment: environment,
      }];
    }

    function historyEventsForTimeline(history = [], options = {}) {
      const includeAllCompleted = Boolean(options.includeAllCompleted);
      const ended = Boolean(options.ended);
      const environmentHint = options.environment || "";
      const allSnapshots = Array.isArray(history) ? history : [];
      let snapshots = allSnapshots;
      if (!includeAllCompleted && !ended && allSnapshots.length > 8) {
        snapshots = allSnapshots.slice(-8);
      }
      upsertTimelineRangeNote(null);

      const events = [];
      snapshots.forEach((h) => {
        const stepActiveBlocker = h.group_state?.active_blocker || null;
        const stepNextBlocker = h.group_state?.bottleneck_item || null;
        const stepTasks = h.scenario?.tasks || {};
        const resolvedItems = h.scenario?.resolved_items || [];
        const environment = h.scenario?.environment || environmentHint || state.environment || state.scenarioHint || "";
        if (Array.isArray(h.events) && h.events.length) {
          h.events.forEach((ev) => events.push(Object.assign({
            tick: h.tick,
            __stepActiveBlocker: stepActiveBlocker,
            __stepNextBlocker: stepNextBlocker,
            __stepTasks: stepTasks,
            __resolvedItems: resolvedItems,
            __environment: environment,
          }, ev)));
          // Per-item evidence check: for each resolved item, inject a concrete
          // synthetic finalisation event unless the tick already has a resolving
          // event whose text is substantive (i.e. actually describes the item's
          // content, not just "Yeah, that's fine." or "Sounds good.").
          // A Budget share event does NOT explain Spec Doc resolving, and a
          // generic agree ("Got it.") does not explain Requirements resolving.
          resolvedItems.forEach(resolvedItem => {
            if (!hasSubstantiveItemEvidence(h.events, resolvedItem)) {
              events.push(...buildQuietTickEvent(h, environment, resolvedItem));
            }
          });
        } else {
          events.push(...buildQuietTickEvent(h, environment));
        }
      });
      return events;
    }

    /**
     * Inject phase-divider elements into the already-rendered event log at the
     * tick boundary where each focus item was resolved.  Called once after
     * appendEvents() finishes for a completed (ended) run loaded from history.
     *
     * For live runs, applyTickDiff handles dividers incrementally.  This
     * function only fires for the history-load path so that a completed run
     * opened from a URL shows the full progression:
     *   ✓ Room Map resolved  ✓ Lock Pattern resolved  …  ✓ Final Unlock resolved
     */
    function injectHistoryPhaseDividers(history, environment) {
      if (!Array.isArray(history) || !history.length) return;

      // Derive canonical scenario key from environment string
      const envLower = String(environment || state.environment || "").toLowerCase();
      const scenarioKey = envLower === "cafe" ? "cafe"
                        : envLower === "office" ? "office"
                        : "escape";

      // Clear any existing dividers before re-injecting from clean ground truth
      eventLog.querySelectorAll(".phase-divider").forEach(node => node.remove());

      // Use the task-transition helper — reads directly from scenario.tasks diffs,
      // not from text detection, group_state, or config fallbacks.
      const transitions = deriveResolvedPhasesFromHistory(history, scenarioKey);

      transitions.forEach(({ item, tick, label }) => {
        const visibleStep = state.tickToDisplayStep.get(tick);
        if (visibleStep == null) return;
        const stepEl = document.getElementById(`step-${visibleStep}`);
        if (!stepEl || !stepEl.parentNode) return;
        const div = document.createElement("div");
        div.className = "phase-divider";
        div.innerHTML = `<span class="phase-label">&#10003; ${escapeHtml(label)} resolved</span>`;
        stepEl.after(div);
      });
    }

    function shouldRenderPhaseDivider(taskKey, environment = "") {
      const env = String(environment || state.environment || state.scenarioHint || "").toLowerCase();
      if (env === "escape") return ["map", "lock", "key", "door", "unlock"].includes(taskKey);
      if (env === "cafe") return ["dietary_constraint", "budget_constraint", "location_constraint", "decision"].includes(taskKey);
      if (env === "office") return ["requirements", "design", "tech_specs", "budget"].includes(taskKey);
      return taskKey !== "unlock";
    }

    function appendRunSummaryCard(totalSteps = state.tick, finalTasksOverride = null, history = null) {
      if ($("runSummaryCard")) return;
      const env = String(state.environment || state.scenarioHint || "").toLowerCase();
      const scenarioKey = env === "cafe" ? "cafe" : env === "office" ? "office" : "escape";
      const cfg = SCENARIO_CONFIG[scenarioKey] || SCENARIO_CONFIG.escape;
      const order = cfg.order;
      const validation = Array.isArray(history) && history.length
        ? validateCompletedScenario(history, scenarioKey)
        : null;

      // Source priority for the resolved-sequence chain:
      //  1. finalTasksOverride — last history snapshot tasks (most complete)
      //  2. state.tasks — current run tasks (may be stale for replays)
      //  3. state.completedPhases — accumulated from live tick diffs
      //  4. deriveResolvedPhasesFromHistory — task-transition scan of history
      // SCENARIO_CONFIG.summaryChain is only used if source 1/2 confirm every
      // item in the chain is true — it is never used as a blind fallback.

      const tasks = finalTasksOverride || state.tasks || {};
      let resolvedItems = order.filter(item => Boolean(tasks[item]))
        .map(item => (cfg.labels && cfg.labels[item]) || itemLabel(item));

      if (!resolvedItems.length && state.tasks && state.tasks !== tasks) {
        resolvedItems = order.filter(item => Boolean(state.tasks[item]))
          .map(item => (cfg.labels && cfg.labels[item]) || itemLabel(item));
      }

      if (!resolvedItems.length && state.completedPhases.size) {
        resolvedItems = order
          .filter(item => state.completedPhases.has(item))
          .map(item => (cfg.labels && cfg.labels[item]) || itemLabel(item));
      }

      // If history is available, re-derive from task transitions — this is the
      // ground truth and cannot be spoofed by stale state.
      if (validation && validation.resolvedTransitions.length) {
        resolvedItems = validation.resolvedTransitions.map(t => t.label);
      } else if (!resolvedItems.length && Array.isArray(history) && history.length) {
        resolvedItems = deriveResolvedPhasesFromHistory(history, scenarioKey).map(t => t.label);
      }

      // Use summaryChain ONLY when final tasks confirm every required item is complete.
      // This prevents the chain from appearing when data is genuinely missing.
      const allTasksConfirmed = order.every(item => Boolean(tasks[item]));
      const allTasksTrue      = validation ? validation.allTasksTrue      : allTasksConfirmed;
      const allTransitionsPresent = validation ? validation.allTransitionsPresent : allTasksConfirmed;
      const missingItems      = validation ? validation.missingFromTasks
        : order.filter(item => !Boolean(tasks[item]));

      // Three-way outcome:
      //  isSuccess         — all tasks complete AND event history confirms all transitions
      //  isGenuineFailure  — at least one task was never completed (team didn't finish)
      //  isDataInconsistent — tasks all true but history transitions are missing (data gap)
      const isSuccess          = allTasksTrue && allTransitionsPresent;
      const isGenuineFailure   = !allTasksTrue;
      // isDataInconsistent is the remaining case (allTasksTrue && !allTransitionsPresent)

      const canUseSummaryFallback = allTasksConfirmed && isSuccess;
      // Final tension = current group_state value (last recorded step).
      // Peak tension  = running max across all ticks, guaranteed >= finalTension by guard.
      const finalTension = Number(state.groupState.tension || 0);
      const peakTension  = Math.max(state.peakTension, finalTension);
      const tensionFinal = toFixedSafe(finalTension);
      const tensionPeak  = toFixedSafe(peakTension);
      const cohesion     = toFixedSafe(state.groupState.cohesion);
      const steps     = escapeHtml(String(totalSteps || state.tick || 0));

      // ── Titles ──────────────────────────────────────────────────────────
      const successTitle = env === "office" ? "Run Complete — Proposal Accepted"
                         : env === "cafe"   ? "Run Complete — Decision Reached"
                         : "Run Complete — Escape Successful";
      const failTitle    = env === "office" ? "Run Ended — Proposal Not Finalised"
                         : env === "cafe"   ? "Run Ended — Decision Not Reached"
                         : "Run Ended — Escape Failed";
      const runTitle     = isSuccess ? successTitle
                         : isGenuineFailure ? failTitle
                         : "Run Ended — Completion Not Verified";

      // ── Icon / card class ────────────────────────────────────────────────
      const iconChar = isSuccess ? "&#10003;" : isGenuineFailure ? "&#10007;" : "&#9888;";
      const cardClass = isSuccess ? "run-summary-card"
                      : isGenuineFailure ? "run-summary-card is-failure"
                      : "run-summary-card is-uncertain";

      // ── Chain text (success / uncertain paths) ───────────────────────────
      const chainText = resolvedItems.length
        ? resolvedItems.join(" → ")
        : (canUseSummaryFallback ? cfg.summaryChain : "—");

      // ── Failure-path specifics ───────────────────────────────────────────
      const unresolvedLabels = missingItems
        .map(item => (cfg.labels && cfg.labels[item]) || itemLabel(item));
      const unresolvedText = unresolvedLabels.join(", ") || "Unknown";

      // Detect whether unresolved items were surfaced in the timeline (share_info events
      // mentioning the item) vs never mentioned at all, so the failure explanation is
      // specific rather than generic.
      const _histEvents = (Array.isArray(history) ? history : [])
        .flatMap(h => Array.isArray(h.events) ? h.events.map(ev => ({ ...ev, _tick: h.tick })) : []);
      const _lastTick = _histEvents.reduce((mx, ev) => Math.max(mx, Number(ev._tick || 0)), 0);
      const _shareTypes = new Set(["share_info", "share"]);
      const _surfacedItems = new Set(
        _histEvents
          .filter(ev => _shareTypes.has(String(ev.type || "").toLowerCase()) && ev.item)
          .map(ev => ev.item)
      );
      const _surfacedLate = new Set(
        _histEvents
          .filter(ev => _shareTypes.has(String(ev.type || "").toLowerCase()) && ev.item
                     && Number(ev._tick || 0) >= _lastTick - 1)
          .map(ev => ev.item)
      );

      // Per-item: classify each unresolved item's status
      const _itemStatus = (item) => {
        if (_surfacedLate.has(item)) return "late";   // shared at/near the last step
        if (_surfacedItems.has(item)) return "unconfirmed"; // shared earlier but not confirmed
        return "never";  // never surfaced at all
      };

      // Build a specific failure description for the primary unresolved item
      const primaryUnresolved = missingItems[0] || null;
      const primaryLabel      = primaryUnresolved ? ((cfg.labels && cfg.labels[primaryUnresolved]) || itemLabel(primaryUnresolved)) : null;
      let failDesc, suggestionText;

      if (primaryUnresolved) {
        const status = _itemStatus(primaryUnresolved);
        if (status === "late") {
          failDesc       = `${primaryLabel} was surfaced too late and was not confirmed before the step limit.`;
          suggestionText = `Try surfacing and confirming ${primaryLabel} earlier, or use Force Meeting before the final step.`;
        } else if (status === "unconfirmed") {
          failDesc       = `${primaryLabel} was mentioned during the run but was never fully confirmed by the team.`;
          suggestionText = `Use Force Meeting or Nudge to build consensus around ${primaryLabel} before the step limit.`;
        } else {
          const failDescByScenario = {
            cafe:   "The team discussed the issue but did not surface the required information before reaching the step limit.",
            office: "The team worked on the proposal but could not finalise all required items before the step limit.",
            escape: "The team attempted the escape but did not complete the required steps before running out of time.",
          };
          failDesc       = failDescByScenario[scenarioKey] || failDescByScenario.escape;
          suggestionText = `Try Reveal Info to surface ${primaryLabel}, or use Force Meeting to push the team toward it.`;
        }
      } else {
        const failDescByScenario = {
          cafe:   "The team discussed the issue but did not surface the required information before reaching the step limit.",
          office: "The team worked on the proposal but could not finalise all required items before the step limit.",
          escape: "The team attempted the escape but did not complete the required steps before running out of time.",
        };
        failDesc       = failDescByScenario[scenarioKey] || failDescByScenario.escape;
        suggestionText = "Try Reveal Info on the active focus, or use Force Meeting with a different agent pair.";
      }

      // ── Shared metric rows ──────────────────────────────────────────────
      // Always show Final tension and Peak tension as separate rows so the user can
      // see whether tension spiked mid-run and then dropped, or stayed elevated.
      // Peak tension is guaranteed >= Final tension by the guard applied above.
      const tensionRows = `
          <div class="rs-row"><span class="rs-key">Final tension</span><span class="rs-val">${tensionFinal}</span></div>
          <div class="rs-row"><span class="rs-key">Peak tension</span><span class="rs-val">${tensionPeak}</span></div>
      `;

      // ── Build HTML for each outcome ──────────────────────────────────────
      let bodyHtml;
      if (isSuccess) {
        bodyHtml = `
          <div class="rs-row rs-row--chain">
            <span class="rs-key">Resolved sequence</span>
            <span class="rs-val rs-chain">${escapeHtml(chainText)}</span>
          </div>
          <div class="rs-row"><span class="rs-key">Final cohesion</span><span class="rs-val">${cohesion}</span></div>
          ${tensionRows}
        `;
      } else if (isGenuineFailure) {
        bodyHtml = `
          <div class="rs-row rs-unresolved">
            <span class="rs-key">Unresolved items</span>
            <span class="rs-val">${escapeHtml(unresolvedText)}</span>
          </div>
          <div class="rs-fail-desc">${escapeHtml(failDesc)}</div>
          <div class="rs-suggestion">${escapeHtml(suggestionText)}</div>
          <div class="rs-row"><span class="rs-key">Final cohesion</span><span class="rs-val">${cohesion}</span></div>
          ${tensionRows}
        `;
      } else {
        // isDataInconsistent: tasks complete, but history is missing some transitions
        bodyHtml = `
          <div class="rs-row rs-row--chain">
            <span class="rs-key">Resolved sequence</span>
            <span class="rs-val rs-chain">${escapeHtml(chainText)}</span>
          </div>
          <div class="rs-warning">Completion state inconsistent: task records are complete but the event history is missing some resolved steps.</div>
          <div class="rs-row"><span class="rs-key">Final cohesion</span><span class="rs-val">${cohesion}</span></div>
          ${tensionRows}
        `;
      }

      const subLabel = isSuccess ? `Completed in ${steps} steps` : `Ended at step ${steps}`;

      const summary = document.createElement("div");
      summary.id = "runSummaryCard";
      summary.className = cardClass;
      summary.innerHTML = `
        <div class="rs-header">
          <span class="rs-icon">${iconChar}</span>
          <div>
            <div class="rs-title">${escapeHtml(runTitle)}</div>
            <div class="rs-sub">${escapeHtml(subLabel)}</div>
          </div>
        </div>
        <div class="rs-body">${bodyHtml}</div>
      `;
      eventLog.appendChild(summary);
    }

    function refreshStepGroupMeta(group) {
      if (!group) return;
      const cards = Array.from(group.querySelectorAll(".event"));
      const count = cards.length;
      const countEl = group.querySelector(".step-group-count");
      const titleEl = group.querySelector(".step-group-title");
      const quietOnly = cards.length > 0 && cards.every((card) => card.dataset.quietTick === "1");
      if (countEl) {
        countEl.textContent = quietOnly
          ? "No new interaction in this step"
          : `${count} interaction${count === 1 ? "" : "s"} in this step`;
      }
      if (titleEl && cards.length) {
        // Prefer the most informative resolution title rather than always showing
        // the first card's title. If a step starts with "Budget Challenged" but
        // ends with "Budget Confirmed", the group header should show the resolution.
        // Priority: Confirmed/Resolved > Shared/Revealed > first card (default).
        const TITLE_PRIORITY = ["Confirmed", "Resolved", "Finalised", "Endorsed", "Shared", "Revealed Early"];
        let bestTitle = cards[0].dataset.stepTitle || "Interaction in progress";
        outer: for (const pattern of TITLE_PRIORITY) {
          for (const card of cards) {
            const t = card.dataset.stepTitle || "";
            if (t.includes(pattern)) { bestTitle = t; break outer; }
          }
        }
        titleEl.textContent = bestTitle;
      }
      cards.forEach((card) => card.classList.remove("is-latest-action"));
      cards.forEach((card, index) => {
        const tickChip = card.querySelector(".ev-tick");
        if (tickChip) {
          tickChip.textContent = `Action ${index + 1} of ${count}`;
          tickChip.classList.toggle("is-latest", index === cards.length - 1);
        }
      });
      if (cards.length) {
        cards[cards.length - 1].classList.add("is-latest-action");
      }
    }

    function scrollLogToStepGroup(group, options = {}) {
      const scroll = $("eventLogScroll");
      if (!scroll || !group) return;
      const behavior = options.smooth ? "smooth" : "auto";
      const targetTop = Math.max(0, group.offsetTop - 6);
      scroll.scrollTo({ top: targetTop, behavior });

      if (options.highlight) {
        group.classList.remove("step-highlight");
        void group.offsetWidth;
        group.classList.add("step-highlight");
        window.setTimeout(() => {
          group.classList.remove("step-highlight");
        }, 1800);
      }
    }

    function appendEvents(events, options = {}) {
      if (!Array.isArray(events) || !events.length) return [];
      const placeholder = eventLog.querySelector("[data-placeholder]");
      if (placeholder) placeholder.remove();

      const appended = [];
      const orderedEvents = [...events].sort((a, b) => {
        const tickDelta = Number(a.tick || 0) - Number(b.tick || 0);
        if (tickDelta !== 0) return tickDelta;
        return displayPriority(a) - displayPriority(b);
      });
      // Per-tick deduplication of resolution effect texts.  When a share_info and
      // an agree event for the same item land in the same step, both can produce an
      // identical "X is now resolved…" sentence.  The second occurrence is replaced
      // with a short corroboration note so the step doesn't repeat itself.
      const shownEffectsByTick = new Map();
      let latestGroup = null;
      orderedEvents.forEach((ev, index) => {
        const key = eventKey(ev);
        if (state.eventsSeen.has(key)) return;
        state.eventsSeen.add(key);
        appended.push(ev);

        const node = document.createElement("article");
        const isUser          = String(ev.actor || "").toUpperCase() === "USER" || ev.type === "intervention" || ev.type === "emotion_injection";
        const isTriggered     = String(ev.reason || "").startsWith("user_");
        // Frontend-only synthetic evidence notes must never render as agent dialogue.
        // Only backend-emitted events (escape_reminder_share, etc.) are real agent events.
        const isSyntheticNote = String(ev.reason || "") === "quiet_share";
        node.className      = "event";
        if (isUser || isTriggered) node.setAttribute("data-origin", "user");
        if (isSyntheticNote)       node.setAttribute("data-origin", "evidence-note");

        const visibleText = massageEventText(ev);
        node.dataset.stepTitle = stepEventTitle(ev);
        if (String(ev.type || "").toLowerCase() === "hold") {
          node.dataset.quietTick = "1";
        }
        // Map real tick numbers to sequential visible step labels so empty ticks
        // now-visible quiet ticks do not create confusing gaps like "Step 4 … Step 6" in the log.
        let tickStr = "";
        let stepMarker = "";
        if (ev.tick != null) {
          if (!state.tickToDisplayStep.has(ev.tick)) {
            state.nextDisplayStep += 1;
            state.tickToDisplayStep.set(ev.tick, state.nextDisplayStep);
          }
          const visibleStep = state.tickToDisplayStep.get(ev.tick);
          tickStr = `Step ${visibleStep}`;
          stepMarker = String(visibleStep);
        }
        const stepId = stepGroupIdForEvent(ev, index);
        const group = ensureStepGroup(stepId, stepMarker);
        const groupEvents = group.querySelector(".step-group-events");
        latestGroup = group;

        if (isUser) {
          const blocker = stepActiveBlockerForEvent(ev) || ev.__stepActiveBlocker || null;
          // Show the item the user explicitly targeted separately from the active
          // blocker.  Check both ev.params.item (local event) and ev.item (backend
          // event where params may not be preserved in the history).
          const targetedItem = normalizeScenarioItemKey(ev.params?.item || ev.item || ev.preference || null);
          const showTargetedItem = targetedItem && targetedItem !== blocker;
          const target  = ev.target && String(ev.target).toUpperCase() !== "GROUP"
            ? actorLabel(ev.target) : "Group";
          const isEmotionIv = ev.type === "emotion_injection";
          const ivEtype = isEmotionIv ? "emotion" : "intervention";
          const ivLabel = isEmotionIv ? "Emotion Input" : "Intervention";
          const rawEmotion = isEmotionIv && ev.detected_emotion ? ev.detected_emotion : null;
          const detectedEmotion = rawEmotion
            ? rawEmotion.charAt(0).toUpperCase() + rawEmotion.slice(1)
            : null;
          node.innerHTML = `
            <div class="ev-header">
              <div class="ev-actors">
                <span class="ev-you">You</span>
                <span class="ev-arrow">→</span>
                <span class="ev-target">${escapeHtml(target)}</span>
                <span class="ev-type" data-etype="${ivEtype}">${escapeHtml(ivLabel)}</span>
              </div>
              <span class="ev-tick">${escapeHtml(tickStr)}</span>
            </div>
            <div class="ev-body-iv">${escapeHtml(visibleText)}</div>
            ${detectedEmotion ? `<div class="ev-triggered">↳ Detected emotion: ${escapeHtml(detectedEmotion)}</div>` : ""}
            ${blocker ? `<div class="ev-triggered">↳ Current focus: ${escapeHtml(itemLabel(blocker))}</div>` : ""}
            ${showTargetedItem ? `<div class="ev-triggered">↳ Targeted item: ${escapeHtml(itemLabel(targetedItem))}</div>` : ""}
          `;
        } else if (isSyntheticNote) {
          // Frontend-generated evidence note: not agent dialogue, not simulation output.
          // Shown so every resolution has traceable clue content in the timeline, but
          // rendered as a system note — no actor name, no quote style, no Why/Effect rows.
          const itemNote = ev.item ? itemLabel(ev.item) : null;
          node.innerHTML = `
            <div class="ev-header">
              <div class="ev-actors">
                <span class="ev-type" data-etype="evidence">Evidence Note</span>
                ${itemNote ? `<span class="ev-target">${escapeHtml(itemNote)}</span>` : ""}
              </div>
              <span class="ev-tick">${escapeHtml(tickStr)}</span>
            </div>
            <div class="ev-body no-quote">Evidence note: ${escapeHtml(visibleText)}</div>
          `;
        } else {
          const actor     = actorLabel(ev.actor || "?");
          const target    = ev.target && String(ev.target).toUpperCase() !== "GROUP"
            ? actorLabel(ev.target) : null;
          const type      = labelForEventType(ev.type);
          const etype     = type.toLowerCase();
          const useQuotes = QUOTED_TYPES.has(String(ev.type || "").toLowerCase());
          const bodyClass = useQuotes ? "ev-body" : "ev-body no-quote";
          const triggerNote = isTriggered
            ? `<div class="ev-why">◆ ${escapeHtml(userTriggerLabel(ev.reason))}</div>` : "";
          const reasonText = eventReasonText(ev);
          const rawEffect  = eventEffectText(ev);
          // Suppress identical resolution sentences repeated within the same step
          // (e.g. share_info and agree for the same item both firing "X is now resolved…").
          // Only applies to resolution-type events — generic coordination events that happen
          // to share the same effect text should never be collapsed to "Corroborates".
          const rawType = String(ev.type || "").toLowerCase();
          const tickKey = ev.tick ?? "_";
          const seenThisTick = shownEffectsByTick.get(tickKey) || new Set();
          const effectText = (RESOLUTION_TYPES.has(rawType) && seenThisTick.has(rawEffect))
            ? "Corroborates the resolution already noted this step."
            : rawEffect;
          seenThisTick.add(rawEffect);
          shownEffectsByTick.set(tickKey, seenThisTick);

          node.innerHTML = `
            <div class="ev-header">
              <div class="ev-actors">
                <span class="ev-actor">${escapeHtml(actor)}</span>
                ${target ? `<span class="ev-arrow">→</span><span class="ev-target">${escapeHtml(target)}</span>` : ""}
                <span class="ev-type" data-etype="${etype}">${escapeHtml(type)}</span>
              </div>
              <span class="ev-tick">${escapeHtml(tickStr)}</span>
            </div>
            ${visibleText ? `<div class="${bodyClass}">${escapeHtml(visibleText)}</div>` : ""}
            ${triggerNote}
            <div class="ev-meta">
              <span class="ev-meta-label">Why</span>
              <span class="ev-meta-copy">${escapeHtml(reasonText)}</span>
            </div>
            <div class="ev-meta">
              <span class="ev-meta-label">Effect</span>
              <span class="ev-meta-copy">${escapeHtml(effectText)}</span>
            </div>
          `;
        }
        if (groupEvents) groupEvents.appendChild(node);
        refreshStepGroupMeta(group);
      });

      eventLog.querySelectorAll(".step-group.is-latest").forEach((group) => {
        group.classList.remove("is-latest");
      });
      if (latestGroup) latestGroup.classList.add("is-latest");

      const scroll = $("eventLogScroll");
      const shouldStickToBottom = scroll
        ? (scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight) < 56
        : false;
      const toggleBtn = $("timelineToggle");
      if (toggleBtn) toggleBtn.remove();
      if (latestGroup && options.focusLatest) {
        scrollLogToStepGroup(latestGroup, {
          smooth: options.smoothScroll !== false,
          highlight: options.highlightLatest !== false,
        });
      } else if (scroll && shouldStickToBottom) {
        scroll.scrollTop = scroll.scrollHeight;
      }
      return appended;
    }

    // ── Intervention picker population ─────────────────────────────────
    function refreshInterventionPickers() {
      const agentIds = state.agents.map(a => a.public_id || a.id).filter(Boolean);
      fillSelect($("revealAgent"), agentIds);
      syncRevealCard();
      fillSelect($("forceAgentA"), agentIds);
      fillSelect($("forceAgentB"), agentIds, 1);
      fillSelect($("nudgeAgent"), agentIds);
    }

    function fillSelect(select, values, defaultIndex = 0) {
      if (!select) return;
      const prev = select.value;
      select.innerHTML = "";
      values.forEach(v => {
        const opt = document.createElement("option");
        opt.value = v;
        if (select.id === "revealItem") {
          opt.textContent = shortItemLabel(v);
        } else if (select.id === "revealAgent" || select.id === "forceAgentA" ||
                   select.id === "forceAgentB" || select.id === "nudgeAgent") {
          opt.textContent = agentOptionLabel(v);
        } else {
          opt.textContent = v;
        }
        select.appendChild(opt);
      });
      if (prev && values.includes(prev)) {
        select.value = prev;
      } else if (values[defaultIndex]) {
        select.value = values[defaultIndex];
      }
    }

    function toFixedSafe(n) {
      const x = Number(n);
      return Number.isFinite(x) ? x.toFixed(2) : "—";
    }

    // ── Blocker / task helpers ─────────────────────────────────────────
    function currentBlocker() {
      const gs = state.groupState || {};
      const tasks = state.tasks || {};
      const config = scenarioConfig();
      const order = Array.isArray(config.order) ? config.order : [];
      if (gs.bottleneck_item) {
        if (order.length && order.includes(gs.bottleneck_item) && !Boolean(tasks[gs.bottleneck_item])) {
          return gs.bottleneck_item;
        }
        if (!order.length) {
          if (typeof tasks[gs.bottleneck_item] === "boolean" && !tasks[gs.bottleneck_item]) {
            return gs.bottleneck_item;
          }
          if (tasks[gs.bottleneck_item] === undefined) {
            return gs.bottleneck_item;
          }
        }
      }
      if (order.length) {
        return order.find((item) => !Boolean(tasks[item])) || null;
      }
      for (const [name, done] of Object.entries(tasks)) {
        if (!done && name !== "unlock") return name;
      }
      return null;
    }

    function unsolvedTaskNames() {
      const tasks = state.tasks || {};
      const config = scenarioConfig();
      const order = Array.isArray(config.order) ? config.order : [];
      if (order.length) {
        return order.filter((item) => !Boolean(tasks[item]));
      }
      return Object.entries(tasks)
        .filter(([name, done]) => !done && name !== "unlock")
        .map(([name]) => name);
    }

    function revealableItemsForAgent(agentId) {
      const unsolved = unsolvedTaskNames();
      const env = String(state.environment || state.scenarioHint || "").toLowerCase();
      const selectable = ((env === "cafe" || env === "cafe_restaurant")
        ? unsolved.filter((item) => item !== "decision")
        : (env === "escape" || env === "escape_room")
          ? unsolved.filter((item) => item !== "unlock")
          : unsolved);
      if (!agentId) return selectable;
      const agent = state.agents.find((a) => (a.id || a.public_id) === agentId);
      if (!agent || !Array.isArray(agent.known_items)) return selectable;
      const known = new Set(agent.known_items);
      return selectable.filter((item) => !known.has(item));
    }

    // Sync the revealItem dropdown for the currently selected agent.
    // If that agent has nothing to reveal, shows a disabled placeholder instead
    // of a blank select. Hides the whole card if nothing is globally revealable.
    function syncRevealCard() {
      const agentSel = $("revealAgent");
      const itemSel  = $("revealItem");
      const card     = $("revealInfoCard");
      const emptyMsg = $("revealEmptyMsg");
      if (!agentSel || !itemSel) return;

      // Global check: any revealable item at all (no agent filter)?
      const globalItems = revealableItemsForAgent("");
      const cardEmpty   = globalItems.length === 0;
      if (card)     card.classList.toggle("hidden", cardEmpty);
      if (emptyMsg) emptyMsg.classList.toggle("hidden", true); // reset
      if (cardEmpty) return; // card hidden — nothing more to do

      // Fill revealItem for selected agent
      const agentId   = agentSel.value;
      const agentItems = revealableItemsForAgent(agentId);
      fillSelect(itemSel, agentItems);

      // If this agent has nothing but others do, show a placeholder
      if (agentItems.length === 0) {
        const ph = document.createElement("option");
        ph.value = "";
        ph.textContent = "No items to reveal for this agent";
        ph.disabled = true;
        itemSel.appendChild(ph);
        itemSel.value = "";
        if (emptyMsg) emptyMsg.classList.toggle("hidden", false);
      }
    }

    function taskKnowledgeCount(item) {
      return state.agents.filter((agent) => Array.isArray(agent.known_items) && agent.known_items.includes(item)).length;
    }

    function taskStatusInfo(item) {
      const done = Boolean((state.tasks || {})[item]);
      if (done) return { label: "Confirmed", className: "is-complete" };

      // Determine whether this item is the current blocker or locked behind one
      const blocker = currentBlocker();
      const isBlocker = blocker === item;
      if (!isBlocker && blocker) return { label: "Locked", className: "is-locked" };

      // How many agents currently know this item?
      const knowCount = taskKnowledgeCount(item);
      const agentCount = state.agents.length || 1;
      if (knowCount === 0) return { label: "Not started", className: "is-missing" };
      if (knowCount >= agentCount) return { label: "Waiting for confirmation", className: "is-waiting" };
      // Active blocker partially known → "In progress" (amber accent)
      if (isBlocker) return { label: "In progress", className: "is-inprogress" };
      return { label: "Partially shared", className: "is-partial" };
    }

    function holderOfBlocker(item) {
      if (!item) return null;
      // First: check knowledgeMap (who originally holds this clue)
      const km = state.knowledgeMap || {};
      const originalHolder = Object.entries(km).find(([, items]) =>
        Array.isArray(items) && items.includes(item)
      );
      if (originalHolder) return originalHolder[0];
      // Fallback: first agent who knows it
      const knower = state.agents.find((a) => Array.isArray(a.known_items) && a.known_items.includes(item));
      return knower ? (knower.id || knower.public_id) : null;
    }

    // Returns true  if at least one agent in the pair holds or knows the focus item.
    // Returns false if the owner is determinable and neither agent is it.
    // Returns null  if knowledge data is absent (can't warn without evidence).
    function pairHoldsBlocker(agentA, agentB, item) {
      if (!item || !agentA || !agentB) return null;

      // 1. Runtime known_items: agents accumulate knowledge via reveal_info, so
      //    check this first — it beats the original assignment.
      const findAgent = (id) => state.agents.find((a) => (a.id || a.public_id) === id);
      const aObj = findAgent(agentA);
      const bObj = findAgent(agentB);
      const aKnows = aObj && Array.isArray(aObj.known_items) && aObj.known_items.includes(item);
      const bKnows = bObj && Array.isArray(bObj.known_items) && bObj.known_items.includes(item);
      if (aKnows || bKnows) return true;

      // 2. Original knowledge map (static assignment from scenario start).
      const km = state.knowledgeMap || {};
      const entries = Object.entries(km);
      if (!entries.length) return null; // no data — can't determine
      const originalOwner = entries.find(([, items]) => Array.isArray(items) && items.includes(item));
      if (!originalOwner) return null; // item not in any map entry — unknown
      const ownerId = originalOwner[0];
      return ownerId === agentA || ownerId === agentB;
    }

    function recommendedActionText() {
      const blocker = currentBlocker();
      if (!blocker) return null;
      const knowCount = taskKnowledgeCount(blocker);
      const agentCount = state.agents.length || 1;
      const holder = holderOfBlocker(blocker);
      const blockerLabel = itemLabel(blocker);
      const holderLabel = holder ? actorLabel(holder) : "an agent";

      if (knowCount === 0) {
        return {
          action: "Reveal Info",
          iv: "reveal_info",
          reason: `${holderLabel} holds the ${blockerLabel} clue but has not shared it yet. Reveal it to surface the clue.`,
        };
      }
      if (knowCount < agentCount) {
        return {
          action: "Force Meeting",
          iv: "force_meeting",
          reason: `${blockerLabel} is partially known. Force a direct conversation to spread it to the full team.`,
        };
      }
      return {
        action: "Nudge Cooperation",
        iv: "nudge_strategy",
        reason: `${blockerLabel} is known by all agents but hasn't been confirmed. Nudge cooperation to resolve it.`,
      };
    }

    function scenarioObjectiveText() {
      const env = String(state.environment || state.scenarioHint || "").toLowerCase();
      if (env === "office") {
        return "The office team must coordinate dependencies and finish the deliverable.";
      }
      if (env === "cafe") {
        return "The group must balance preferences and constraints to agree where to eat.";
      }
      return "The escape team must collect clues and solve the final door code.";
    }

    function currentProblemText() {
      const blocker = currentBlocker();
      if (!blocker) return "No current focus — the team is closing the final outcome.";
      const known = taskKnowledgeCount(blocker);
      if (known === 0) {
        return `The team is waiting because ${itemLabel(blocker)} has not been surfaced yet.`;
      }
      if (known < (state.agents.length || 1)) {
        return `The team is waiting because ${itemLabel(blocker)} is only partially shared.`;
      }
      return `The team is waiting because ${itemLabel(blocker)} still needs to be confirmed or used.`;
    }

    function nextExpectedText() {
      const blocker = currentBlocker();
      if (!blocker) return "Agents should confirm the final step and resolve the scenario.";
      const known = taskKnowledgeCount(blocker);
      if (known === 0) {
        return `Agents should ask for ${itemLabel(blocker)} or reveal missing information.`;
      }
      if (known < (state.agents.length || 1)) {
        return `Agents should discuss ${itemLabel(blocker)} and share the missing detail.`;
      }
      return `Agents should use ${itemLabel(blocker)} to move the team forward.`;
    }

    // Infer the scenario item from event text when ev.item is not set.
    // Keep this scenario-aware and conservative so one scenario's phrasing
    // cannot leak another scenario's focus vocabulary into the timeline.
    function detectItemFromText(text, environment = "") {
      const s = String(text || "").toLowerCase();
      const env = String(environment || state.environment || state.scenarioHint || "").toLowerCase();

      if (env === "cafe") {
        if (/(dietary|vegan|vegetarian|allergen|food requirement)/.test(s)) return "dietary_constraint";
        if (/(budget|affordable|cheap|price|cost|spend|£|per person)/.test(s)) return "budget_constraint";
        if (/(nearby|close|walking distance|walk|distance|location|proximity|easy to get)/.test(s)) return "location_constraint";
        if (/(let's go with|we're doing|decision|best fit|the pick|that'?s the one)/.test(s)) return "decision";
        return null;
      }

      if (env === "office") {
        if (/(requirements|offline|mobile access|specifications)/.test(s)) return "requirements";
        if (/(design|ui|layout|blue theme|colour scheme)/.test(s)) return "design";
        if (/(spec doc|tech specs|react|node|postgresql|stack)/.test(s)) return "tech_specs";
        if (/(budget|cost|50k|\$50,?000|sign-off)/.test(s)) return "budget";
        return null;
      }

      if (s.includes("door code") || s.includes("4-2-7") || s.includes("final code") || s.includes("entering now")) return "door";
      if (s.includes("room map") || s.includes("hidden panel east") || s.includes("bookshelf")) return "map";
      if (s.includes("lock pattern") || s.includes("ceiling symbols") || s.includes("triangle") || s.includes("circle") || s.includes("square")) return "lock";
      if (s.includes("key location") || s.includes("magnetic key") || s.includes("loose tile") || s.includes("metal panel")) return "key";
      if (s.includes("door open") || s.includes("we escaped") || s.includes("final unlock") || s.includes("exit lock")) return "unlock";
      return null;
    }

    function eventReasonText(ev, blockerOverride = null) {
      const blocker = blockerOverride || stepActiveBlockerForEvent(ev);
      const item = eventItemFromContext(ev, blocker);
      const resolvedItems = stepResolvedItems(ev);
      const resolvedFocus = resolvedItems[0] || null;
      const reason = String(ev.reason || "");
      const type = String(ev.type || "").toLowerCase();
      const _reasonStepTasks = ev?.__stepTasks || {};
      // isFutureReveal: item is ahead of the blocker and was not resolved this tick NOR in a
      // prior tick.  Items already confirmed in a prior tick must not be called "early".
      const isFutureReveal = Boolean(
        item && blocker && item !== blocker
        && !resolvedItems.includes(item)
        && !_reasonStepTasks[item]
      );

      if (reason.startsWith("user_")) {
        // For user-triggered events, the Why text must reflect the tick-START blocker
        // (ev.__stepActiveBlocker), not the end-of-tick blocker computed from __stepTasks
        // which may have already advanced when a blocker resolved in the same tick.
        // e.g. Key Location resolves in tick 8 → end-of-tick blocker = Door Code, but
        // the nudge response in that tick should say "while Key Location is the current focus."
        const liveBlocker = ev.__stepActiveBlocker || blocker || null;

        // reveal_info: distinguish between "directly unblocking" and "storing for later"
        if (reason === "user_reveal_info") {
          const revealed = ev.item ? itemLabel(ev.item) : "the missing information";
          if (ev.item && liveBlocker && ev.item !== liveBlocker) {
            return `${userTriggerLabel(reason)} — ${revealed} is stored ahead of the active focus (${itemLabel(liveBlocker)}).`;
          }
          return `${userTriggerLabel(reason)} to surface ${revealed} for the team.`;
        }

        // For all other intervention types (force_meeting, inject_tension, boost_urgency,
        // ease_pressure, nudge_strategy) — never show a "targeting X" clause.
        // These interventions apply to the current focus globally; ev.item captures
        // what the agent happened to say in their response, not the user's chosen target.
        // Showing "targeting Budget while Spec Doc is the current focus" makes the
        // intervention look inconsistent even though the user never targeted Budget.
        const focus = liveBlocker
          ? itemLabel(liveBlocker)
          : "the scenario objective";
        return `${userTriggerLabel(reason)} while ${focus} is the current focus.`;
      }
      if (type === "ask_info" || type === "ask") {
        const focus = item ? itemLabel(item) : "a missing detail";
        return `${actorLabel(ev.actor)} still needs ${focus} to move the team forward.`;
      }
      if (type === "resolve") {
        const resolvedItems = stepResolvedItems(ev);
        const firstResolved = resolvedItems[0] || item;
        const env = eventEnvironment(ev);
        if (env === "cafe" && firstResolved === "decision") {
          return "All required café constraints were already confirmed, so the final decision could be locked in.";
        }
        if (firstResolved) {
          // For escape: if a specific agent originally held this clue and it resolved
          // without a preceding visible share event, explain that the agent drew on
          // their private knowledge so the resolution is not opaque to the user.
          if ((env === "escape" || env === "escape_room") && firstResolved !== "unlock") {
            const holder = holderOfBlocker(firstResolved);
            if (holder) {
              return `${actorLabel(holder)}'s private ${itemLabel(firstResolved)} clue provided the evidence needed to confirm this step.`;
            }
          }
          return `All prerequisites for ${itemLabel(firstResolved)} were already confirmed, so it could be locked in without further dialogue.`;
        }
        return "All prerequisites were already confirmed, so this step completed automatically.";
      }
      if (type === "hold") {
        return blocker
          ? `${itemLabel(blocker)} is still the current focus, but no new message landed in this step.`
          : "No new message landed in this step while the team held its position.";
      }
      if (type === "share_info" || type === "share") {
        const focus = item ? itemLabel(item) : "a key clue";
        // Item is marked true in the end-of-tick snapshot — but we must distinguish:
        //   resolvedItems.includes(item) → resolves THIS step (share contributes to it)
        //   otherwise                   → resolved in a PRIOR step (genuinely already done)
        if (item && _reasonStepTasks[item] === true && blocker && item !== blocker) {
          if (resolvedItems.includes(item)) {
            return `${actorLabel(ev.actor)} reinforces the ${focus} clue as the team prepares to confirm it.`;
          }
          return `${actorLabel(ev.actor)} references ${focus}, which the team has already confirmed.`;
        }
        if (isFutureReveal) {
          return `${actorLabel(ev.actor)} is surfacing ${focus} early while ${itemLabel(blocker)} is the current focus.`;
        }
        return `${actorLabel(ev.actor)} is surfacing ${focus} to move the team forward.`;
      }
      if (type === "challenge" || type === "doubt") {
        // Use the event's own item first — the agent is challenging a specific claim,
        // which may differ from the active blocker (e.g. a Budget challenge while
        // Spec Doc is the active blocker).
        const focus = item ? itemLabel(item) : (blocker ? itemLabel(blocker) : "the current answer");
        return `${actorLabel(ev.actor)} is rechecking ${focus} before the team commits.`;
      }
      if (type === "agree" || type === "confirm") {
        const futureTagged = Boolean(item && blocker && item !== blocker && !resolvedItems.includes(item));
        const focusItem = resolvedFocus || (futureTagged ? blocker : (item || blocker || null));
        const focus = focusItem ? itemLabel(focusItem) : "the shared information";
        return `The team is validating and locking in ${focus}.`;
      }
      if (type === "suggest" || type === "say" || type === "coord") {
        if (state.ended && !blocker) {
          const env = eventEnvironment(ev);
          if (env === "office") return "The team has submitted the proposal and the run is complete.";
          if (env === "cafe")   return "The group has reached a decision and the run is complete.";
          return "The team has cleared the final objective and the run is complete.";
        }
        const focusItem = resolvedFocus || blocker || item || null;
        const focus = focusItem ? itemLabel(focusItem) : "the next step";
        return `${actorLabel(ev.actor)} is coordinating progress on ${focus}.`;
      }
      // Praise / social events — do not attribute to a task focus
      if (type === "compliment" || type === "reassure") {
        return "The team is maintaining morale and keeping relations positive.";
      }
      if (type === "refuse") {
        const focus = blocker ? itemLabel(blocker) : (item ? itemLabel(item) : "the current request");
        return `${actorLabel(ev.actor)} is pushing back on ${focus} this step.`;
      }
      if (type === "ignore" || type === "insult") {
        return "A breakdown in communication is increasing friction this step.";
      }
      return blocker
        ? `${itemLabel(blocker)} is still the current focus this step.`
        : "The team is closing in on the final objective.";
    }

    // Event types that can legitimately claim a task is "resolved" in the effect text.
    // agree/confirm are excluded: they get "Confidence locks in" text instead, so that
    // when both a share and an agree appear in the same tick, only the share says "resolved"
    // and the agree reads as supporting confirmation.  The ✓ divider handles the
    // visual resolution signal for agree-led resolution ticks.
    // Ask / praise / friction events must never trigger the "X is now resolved" path.
    const RESOLUTION_TYPES = new Set([
      "share_info", "share", "open", "enter", "resolve",
    ]);

    function eventEffectText(ev, blockerOverride = null) {
      const rawBlocker = blockerOverride || stepActiveBlockerForEvent(ev);
      const reason = String(ev.reason || "");
      // For user-triggered events, use the tick-start blocker so the effect text reflects
      // what was active when the intervention was processed, not the end-of-tick blocker
      // (which may have advanced if a blocker resolved in the same tick).
      // e.g. if Design Plans resolves in the same tick as a nudge response, end-of-tick
      // blocker = "tech_specs" → "Confidence rises around Spec Doc" (wrong).
      // With tick-start "design", item = "design", resolvedItems includes "design" →
      // "Confidence locks in around Design Plans. The team commits." (correct).
      const blocker = reason.startsWith("user_") ? (ev.__stepActiveBlocker || rawBlocker) : rawBlocker;
      const item = eventItemFromContext(ev, blocker);
      const type = String(ev.type || "").toLowerCase();
      const resolvedItems = stepResolvedItems(ev);
      const resolvedFocus = resolvedItems[0] || null;
      // `blocker` is already computed from __stepTasks (post-resolution state), so
      // after "requirements" resolves, blocker === "design" — use it directly as the
      // "moves on to" target instead of bottleneck_item which can point to a future item.
      const env = eventEnvironment(ev);

      // Praise / social events — generic, no task or focus reference
      if (type === "compliment" || type === "reassure") {
        return "The team acknowledges progress and stays aligned.";
      }
      if (type === "ignore" || type === "insult") {
        return "The communication breakdown adds friction and may slow progress.";
      }
      if (type === "refuse") {
        const futureTagged = Boolean(item && blocker && item !== blocker && !resolvedItems.includes(item));
        const focusItem = (env === "cafe" && futureTagged) ? blocker : (item || blocker || null);
        const focus = focusItem ? itemLabel(focusItem) : "the current request";
        return `${actorLabel(ev.actor)} declining slows progress on ${focus} this step.`;
      }

      // Ask events: never claim resolution — always show "waiting for reply"
      if (type === "ask_info" || type === "ask") {
        const focus = item ? itemLabel(item) : "the missing detail";
        return `The question focuses the team on ${focus}. Progress waits on a reply.`;
      }
      if (type === "hold") {
        if (blocker) {
          // If this step's task snapshot already shows the blocker as resolved (e.g. resolved
          // earlier in the same tick's events), don't contradict that with "remains unresolved."
          const stepTasks = ev?.__stepTasks || {};
          if (stepTasks[blocker] === true) {
            return "No new agent interaction in this step.";
          }
          return `${itemLabel(blocker)} remains unresolved. No new progress evidence surfaced in this step.`;
        }
        return "No new progress evidence surfaced in this step.";
      }

      // "Item just completed" — only for event types that actually resolve tasks
      if (item && resolvedItems.includes(item) && RESOLUTION_TYPES.has(type)) {
        // Use nextBlockerInChain to find the next target: it looks up resolvedItem's
        // position in the canonical order and returns the first unresolved item after
        // it.  This is correct even when __stepTasks still shows the resolved item
        // as false (same-tick lag) — unlike blocker which would then self-refer.
        const stepTasks = ev?.__stepTasks ?? {};
        const nextInChain = nextBlockerInChain(item, stepTasks, env);
        if (!nextInChain) {
          if (env === "office") return `${itemLabel(item)} is confirmed. The team is ready to submit the proposal.`;
          if (env === "cafe" && item === "decision") return "Decision is now resolved. The team completes the cafe plan.";
          if (env === "cafe")   return `${itemLabel(item)} is confirmed. The group can now finalise the decision.`;
          return "The final unlock is complete, and the team has escaped.";
        }
        if (env === "cafe" && item === "decision") {
          return "Decision is now resolved. The team completes the cafe plan.";
        }
        return `${itemLabel(item)} is now resolved. The team moves on to ${itemLabel(nextInChain)}.`;
      }

      if (state.ended && !blocker) {
        if (env === "office") return "The proposal is submitted and the team has completed the project.";
        if (env === "cafe")   return "The group has agreed on a venue and the decision is final.";
        return "The door code is entered and the team has successfully escaped.";
      }

      if (type === "share_info" || type === "share") {
        const focus = item ? itemLabel(item) : "the clue";
        if (item && blocker && item !== blocker) {
          // Check whether the item was already resolved in a prior tick.
          // If so, "stored for later" is wrong — it was already confirmed.
          const _effectStepTasks = ev?.__stepTasks || {};
          if (_effectStepTasks[item] === true) {
            return `${focus} was already confirmed. The team remains focused on ${itemLabel(blocker)}.`;
          }
          return `${focus} is stored for later. ${itemLabel(blocker)} still needs to be resolved first.`;
        }
        // Detect referral language ("go to X", "ask X", "talk to X", "straight to X"):
        // the agent is directing the team to someone who holds the clue, not sharing
        // the actual content.  Claiming the item is "in the conversation" would be wrong.
        const _evText = String(ev?.text || "").toLowerCase();
        const _isReferral = /\b(go to|go straight|ask |talk to|check with|speak to|speak with|find )\b/.test(_evText)
          && !/\b(the answer is|it is|code is|map shows|clue is|says|states|reads|found|it.s)\b/.test(_evText);
        if (_isReferral) {
          return `The team has identified who may hold ${focus}, but the detail still needs to be shared directly.`;
        }
        return `${focus} is now in the conversation for the team to confirm and use.`;
      }
      if (type === "challenge" || type === "doubt") {
        // Use the event's specific item first — the agent is challenging a particular claim.
        // Fall back to active blocker only if no item is tagged on the event.
        const focus = item ? itemLabel(item) : (blocker ? itemLabel(blocker) : "the current answer");
        return `The team pauses briefly to verify ${focus} before committing.`;
      }
      if (type === "agree" || type === "confirm") {
        const futureTagged = Boolean(item && blocker && item !== blocker && !resolvedItems.includes(item));
        const focusItem = resolvedFocus || (futureTagged ? blocker : (item || blocker || null));
        const focus = focusItem ? itemLabel(focusItem) : "the shared information";
        // If this tick already resolved the item (e.g. a share event appeared first in the
        // same step), the agree is supporting confirmation rather than the resolution trigger.
        if (item && resolvedItems.includes(item)) {
          return `Confidence locks in around ${itemLabel(item)}. The team commits.`;
        }
        if (resolvedFocus) {
          return `Confidence locks in around ${itemLabel(resolvedFocus)}. The team commits.`;
        }
        return `Confidence rises around ${focus}. Confirmation is close.`;
      }
      if (type === "suggest" || type === "say" || type === "coord") {
        const focusItem = resolvedFocus || blocker || item || null;
        const focus = focusItem ? itemLabel(focusItem) : "the objective";
        // Decision phase: say/coord events are narrowing down the final venue choice
        if (env === "cafe" && (blocker === "decision" || item === "decision")) {
          return "The group is narrowing down the venue based on all agreed constraints.";
        }
        return `The team stays aligned on ${focus} and readies the next move.`;
      }
      return "The conversation state advances, keeping the team on track.";
    }

    function latestUpdateFromEvents(events) {
      const visible = (events || []).filter((ev) => String(ev.actor || "").toUpperCase() !== "USER" && ev.type !== "intervention");
      if (!visible.length) {
        return {
          summary: "No simulation events yet.",
          note: `Press ${advanceActionLabel()} to let the agents act. The timeline will explain what happened and why.`,
        };
      }
      const blocker = currentBlocker();
      const lead = visible[0];
      const actor = actorLabel(lead.actor || "?");
      const target = lead.target && String(lead.target).toUpperCase() !== "GROUP"
        ? actorLabel(lead.target)
        : null;
      const verb = {
        ask: "asked",
        share: "shared",
        agree: "agreed with",
        confirm: "confirmed with",
        challenge: "challenged",
        suggest: "prompted",
        say: "updated",
        refuse: "pushed back on",
      }[labelForEventType(lead.type).toLowerCase()] || "acted with";
      const item = itemLabel(lead.item || detectItemFromText(lead.text, eventEnvironment(lead)) || blocker || "the objective");
      const pair = target ? `${actor} ${verb} ${target}` : `${actor} acted`;
      return {
        summary: `${pair} on ${item}.`,
        note: eventEffectText(lead, blocker),
      };
    }

    function renderStoryPanels(events = []) {
      const objective = $("objectiveText");
      const currentProblem = $("currentProblemText");
      const nextExpected = $("nextExpectedText");
      const latestSummary = $("latestSummaryText");
      const latestNote = $("latestSummaryNote");
      const latestSummaryRec = $("latestSummaryRec");
      const progressList = $("progressList");
      const nextActionEl = $("nextRequiredAction");
      const ivRecommend = $("ivRecommend");

      if (objective) {
        if (state.ended) {
          const env = String(state.environment || state.scenarioHint || "").toLowerCase();
          // Check actual task completion — state.ended is true for both success AND failure.
          const _oCfg   = scenarioConfig();
          const _oOrder = Array.isArray(_oCfg.order) ? _oCfg.order : [];
          const _oTasks = state.tasks || {};
          const _oAllDone = _oOrder.length
            ? _oOrder.every(item => Boolean(_oTasks[item]))
            : Object.values(_oTasks).every(v => Boolean(v));
          if (_oAllDone) {
            objective.textContent = env === "office"
              ? "Final outcome reached — the proposal workflow is complete."
              : env === "cafe"
                ? "Final outcome reached — the cafe plan is complete."
                : "Final outcome reached — the escape sequence is complete.";
          } else {
            const _oFirst = _oOrder.find(item => !Boolean(_oTasks[item])) || null;
            objective.textContent = _oFirst
              ? `Run ended — ${itemLabel(_oFirst)} was not confirmed before the step limit.`
              : "Run ended — not all required steps were completed before the step limit.";
          }
        } else {
          objective.textContent = scenarioObjectiveText();
        }
      }

      // ── Pre-run guard: suppress all internal-state wording before Step 1 ───
      // At tick 0 the knowledge map is populated but no agent has acted yet.
      // Showing "partially shared" or holder info here exposes private sim state.
      if (state.tick === 0 && !state.ended) {
        if (currentProblem) {
          const _env0 = String(state.environment || state.scenarioHint || "").toLowerCase();
          const _readyLine = _env0 === "office"
            ? "The office team is ready. Press Start First Step to begin the project."
            : _env0 === "cafe"
              ? "The group is ready. Press Start First Step to begin choosing a restaurant."
              : "The escape team is ready. Press Start First Step to begin solving the clues.";
          currentProblem.textContent = _readyLine;
        }
        // Override the objective sub-text (set above to scenarioObjectiveText) with nothing — the headline already has the action
        if (objective) objective.textContent = "";
        if (nextExpected) {
          nextExpected.textContent = "No interactions have occurred yet.";
        }
        // Latest Change: latestUpdateFromEvents([]) already returns the correct
        // "No simulation events yet." placeholder — no override needed here.
        const latest0 = latestUpdateFromEvents(events);
        if (latestSummary) latestSummary.textContent = latest0.summary;
        if (latestNote)    latestNote.textContent    = latest0.note;
        if (nextActionEl)     nextActionEl.classList.add("hidden");
        if (ivRecommend)      ivRecommend.classList.add("hidden");
        if (latestSummaryRec) latestSummaryRec.classList.add("hidden");
        // Progress list: render tasks as "not started" — no knowledge leakage
        if (progressList) {
          const _tasks0 = Object.keys(state.tasks || {});
          const _ord0 = _tasks0.filter(n => n !== "unlock");
          if (_tasks0.includes("unlock")) _ord0.push("unlock");
          progressList.innerHTML = _ord0.length
            ? _ord0.map(item => `
                <div class="progress-item">
                  <span class="progress-item-name">${escapeHtml(itemLabel(item))}</span>
                  <span class="progress-status is-missing">Not started</span>
                </div>`).join("")
            : '<div class="progress-empty">Waiting for scenario state…</div>';
        }
        return;
      }

      // Current Situation card
      const blocker = currentBlocker();
      const holder = holderOfBlocker(blocker);
      const holderLabel = holder ? actorLabel(holder) : "An agent";
      const knowCount = blocker ? taskKnowledgeCount(blocker) : 0;
      const blockerLabel = blocker ? itemLabel(blocker) : null;
      const agentCount = state.agents.length || 1;

      if (currentProblem) {
        if (state.ended) {
          const env = String(state.environment || state.scenarioHint || "").toLowerCase();
          const _cpCfg   = scenarioConfig();
          const _cpOrder = Array.isArray(_cpCfg.order) ? _cpCfg.order : [];
          const _cpTasks = state.tasks || {};
          const _cpAllDone = _cpOrder.length
            ? _cpOrder.every(item => Boolean(_cpTasks[item]))
            : Object.values(_cpTasks).every(v => Boolean(v));
          if (_cpAllDone) {
            currentProblem.textContent = env === "office"
              ? "Run complete — all required proposal steps have been resolved."
              : env === "cafe"
                ? "Run complete — the group has reached a final decision."
                : "Run complete — all required escape steps have been resolved.";
          } else {
            const _cpFirst = _cpOrder.find(item => !Boolean(_cpTasks[item])) || null;
            currentProblem.textContent = _cpFirst
              ? `Run ended — ${itemLabel(_cpFirst)} was not confirmed before the step limit.`
              : "Run ended — not all required steps were completed before the step limit.";
          }
        } else if (!blocker) {
          currentProblem.textContent = "No current focus — the team is resolving the final outcome.";
        } else if (knowCount === 0) {
          currentProblem.textContent = `Current focus: ${blockerLabel}. One agent holds the missing clue, but it has not been shared yet.`;
        } else if (knowCount < agentCount) {
          currentProblem.textContent = `Current focus: ${blockerLabel}. The clue is partially shared, but not everyone has it yet.`;
        } else {
          currentProblem.textContent = `Current focus: ${blockerLabel}. Everyone knows the clue, but it has not been confirmed yet.`;
        }
      }

      if (nextExpected) {
        nextExpected.textContent = state.ended
          ? "Review the full log below or open the dashboard for the complete summary."
          : nextExpectedText();
      }

      // Latest Change card
      const latest = latestUpdateFromEvents(events);
      if (latestSummary) latestSummary.textContent = latest.summary;
      if (latestNote) latestNote.textContent = latest.note;

      // Next Required Action
      if (nextActionEl) {
        if (blocker && holder) {
          nextActionEl.textContent = `${holderLabel} must share or confirm ${blockerLabel}.`;
          nextActionEl.classList.remove("hidden");
        } else if (blocker) {
          nextActionEl.textContent = `The team must share or confirm ${blockerLabel}.`;
          nextActionEl.classList.remove("hidden");
        } else if (state.ended) {
          nextActionEl.textContent = "The run is complete.";
          nextActionEl.classList.remove("hidden");
        } else {
          nextActionEl.classList.add("hidden");
        }
      }

      // Recommended action — show in both Intervention Lab and Latest Change card
      const rec = recommendedActionText();
      if (ivRecommend) {
        if (rec) {
          ivRecommend.innerHTML = `<span class="iv-rec-label">Suggested action</span><strong>${escapeHtml(rec.action)}</strong><span class="iv-rec-copy">${escapeHtml(rec.reason)}</span>`;
          ivRecommend.classList.remove("hidden");
        } else {
          ivRecommend.classList.add("hidden");
        }
      }
      if (latestSummaryRec) {
        if (rec) {
          latestSummaryRec.innerHTML = `<strong>→ ${escapeHtml(rec.action)}:</strong> ${escapeHtml(rec.reason)}`;
          latestSummaryRec.classList.remove("hidden");
        } else {
          latestSummaryRec.classList.add("hidden");
        }
      }

      // Progress list
      if (!progressList) return;
      const tasks = Object.keys(state.tasks || {});
      const ordered = tasks.filter((name) => name !== "unlock");
      if (tasks.includes("unlock")) ordered.push("unlock");
      if (!ordered.length) {
        progressList.innerHTML = '<div class="progress-empty">Waiting for scenario state…</div>';
        return;
      }
      progressList.innerHTML = ordered.map((item) => {
        const status = taskStatusInfo(item);
        const isBlocker = currentBlocker() === item;
        return `
          <div class="progress-item${isBlocker ? " is-active-blocker" : ""}">
            <span class="progress-item-name">${escapeHtml(itemLabel(item))}</span>
            <span class="progress-status ${escapeHtml(status.className)}">${escapeHtml(status.label)}</span>
          </div>
        `;
      }).join("");
    }

    // ── Last Intervention card (explain strip) ─────────────────────────
    function buttonLabelFor(type, params) {
      if (type === "reveal_info")    return `Reveal ${itemLabel(params.item)} to ${params.agent_id}`;
      if (type === "force_meeting")  return `Force Meeting: ${params.agent_a_id} & ${params.agent_b_id}`;
      if (type === "nudge_strategy") return `Nudge ${params.agent_id} Toward Cooperation`;
      if (type === "boost_urgency")  return "Boost Pressure";
      if (type === "ease_pressure")  return "Ease Pressure";
      if (type === "inject_tension") return "Inject Tension";
      if (type === "inject_emotion") return `Inject Mood`;
      return type;
    }

    function expectedEffectFor(iv) {
      const { type, params, before, apiResult } = iv;
      const ar = apiResult || {};
      const blocker = before && before.blocker;
      if (type === "reveal_info") {
        if (blocker && blocker === params.item) {
          return `${params.agent_id} surfaces ${itemLabel(params.item)} next step.`;
        }
        return `${params.agent_id} carries ${itemLabel(params.item)} into the next step of the sequence.`;
      }
      if (type === "force_meeting") {
        const trustNote = (ar.trust_before != null && ar.trust_after != null)
          ? ` Pair trust raised ${ar.trust_before.toFixed(2)} → ${ar.trust_after.toFixed(2)}.`
          : "";
        return `${params.agent_a_id} ↔ ${params.agent_b_id} on ${itemLabel(blocker || "focus")}.${trustNote}`;
      }
      if (type === "nudge_strategy") {
        const lockNote = ar.lock_duration != null ? ` Strategy locked for ~${ar.lock_duration} steps.` : "";
        return blocker
          ? `${params.agent_id} speaks constructively on ${itemLabel(blocker)}.${lockNote}`
          : `${params.agent_id} speaks constructively (share/agree/ask).${lockNote}`;
      }
      if (type === "boost_urgency") {
        const boostTicks = ar.share_boost_ticks || 3;
        return `Pressure rises. Share boost active for ~${boostTicks} steps; pressure elevation persists beyond that window.`;
      }
      if (type === "ease_pressure") {
        const beforeU = (before && before.urgency != null) ? before.urgency : null;
        const afterU  = ar.pressure_after != null ? ar.pressure_after : null;
        if (beforeU != null && afterU != null && Math.abs(afterU - beforeU) < 0.001) {
          return `Pressure was already at the scenario baseline — agent stress reduced only, no urgency change.`;
        }
        return `Pressure eases, giving ${itemLabel(blocker || "focus")} more breathing room.`;
      }
      if (type === "inject_tension") return `Tension rises, next line sharpens on ${itemLabel(blocker || "focus")}.`;
      if (type === "inject_emotion") {
        const dTicks = ar.decay_ticks || 5;
        const emotion = ar.detected_emotion ? `${ar.detected_emotion} signal` : "emotional signal";
        return `All agents perceive the ${emotion}. Stress and trust shift decay over ~${dTicks} steps.`;
      }
      return "";
    }

    function stateChangeLineFor(type, params, before, after, apiResult) {
      const ar = apiResult || {};
      if (type === "reveal_info") {
        let line = `${params.agent_id} now knows <b>${itemLabel(params.item)}</b>.`;
        if (ar.stress_before != null && ar.stress_after != null) {
          const delta = ar.stress_after - ar.stress_before;
          if (Math.abs(delta) > 0.001) {
            line += ` Stress ${delta < 0 ? "−" : "+"}${Math.abs(delta * 100).toFixed(0)}%.`;
          }
        }
        return line;
      }
      if (type === "force_meeting") {
        const blocker = before && before.blocker;
        let line = blocker
          ? `<b>${params.agent_a_id}</b> & <b>${params.agent_b_id}</b> on <b>${itemLabel(blocker)}</b>.`
          : `<b>${params.agent_a_id}</b> & <b>${params.agent_b_id}</b> paired.`;
        if (ar.trust_before != null && ar.trust_after != null) {
          line += ` Trust: ${ar.trust_before.toFixed(2)} → <b>${ar.trust_after.toFixed(2)}</b>.`;
        }
        return line;
      }
      if (type === "nudge_strategy") {
        const beforeStrat = ar.strategy_before || (before && before.strategy) || "—";
        const afterStrat  = ar.strategy_after  || params.strategy;
        const lockDur     = ar.lock_duration;
        const lockNote    = lockDur != null ? ` · locked ~${lockDur} steps` : "";
        if (beforeStrat === afterStrat) {
          return `${params.agent_id} locked <b>${afterStrat}</b> (refreshed)${lockNote}.`;
        }
        return `${params.agent_id}: <b>${beforeStrat}</b> → <b>${afterStrat}</b>${lockNote}.`;
      }
      if (type === "boost_urgency") {
        const beforeU = (before && before.urgency != null) ? before.urgency : scenarioBaseUrgency(state.environment || state.scenarioHint);
        const afterU  = (after && after.urgency != null) ? after.urgency : beforeU;
        let line = pressureDisplayChangeText(beforeU, afterU, "up").replace(/([0-9]+\.[0-9]{2})/g, "<b>$1</b>");
        const boostTicks = ar.share_boost_ticks;
        if (boostTicks != null) {
          line += ` Share boost active for ~${boostTicks} steps; pressure elevation persists.`;
        }
        return line;
      }
      if (type === "ease_pressure") {
        const beforeU = (before && before.urgency != null) ? before.urgency : scenarioBaseUrgency(state.environment || state.scenarioHint);
        const afterU  = (after && after.urgency != null) ? after.urgency : beforeU;
        if (Math.abs(afterU - beforeU) < 0.001) {
          return "Pressure was already at the scenario baseline — agent stress reduced only.";
        }
        return pressureDisplayChangeText(beforeU, afterU, "down").replace(/([0-9]+\.[0-9]{2})/g, "<b>$1</b>");
      }
      if (type === "inject_tension") {
        if (ar.tension_before != null && ar.tension_after != null) {
          return `Tension: <b>${ar.tension_before.toFixed(2)}</b> → <b>${ar.tension_after.toFixed(2)}</b>.`;
        }
        const beforeT = (before && before.tension) || 0;
        return `Tension queued +${toFixedSafe(params.amount)} (was <b>${toFixedSafe(beforeT)}</b>).`;
      }
      if (type === "inject_emotion") {
        let line = params.text ? `"${params.text.slice(0, 60)}${params.text.length > 60 ? "…" : ""}"` : "Emotion injected.";
        if (ar.detected_emotion) line += ` Detected: <b>${ar.detected_emotion}</b>.`;
        const dTicks = ar.decay_ticks || 5;
        line += ` Effect decays over ~${dTicks} steps.`;
        return line;
      }
      return "—";
    }

    function deltaSpan(label, before, after) {
      const b = Number(before);
      const a = Number(after);
      if (!Number.isFinite(b) || !Number.isFinite(a)) {
        return `<span class="delta-flat">${label}: —</span>`;
      }
      const displayBefore = label === "Pressure"
        ? displayPressureValue(b, state.environment || state.scenarioHint)
        : b;
      const displayAfter = label === "Pressure"
        ? displayPressureValue(a, state.environment || state.scenarioHint)
        : a;
      const diff = displayAfter - displayBefore;
      let cls = "delta-flat";
      let arrow = "→";
      if (diff > 0.001) { cls = "delta-up"; arrow = "↑"; }
      else if (diff < -0.001) { cls = "delta-down"; arrow = "↓"; }
      return `<span class="${cls}">${label}: ${displayBefore.toFixed(2)} ${arrow} ${displayAfter.toFixed(2)}</span>`;
    }

    function renderBlockerPill(blocker) {
      const pill = $("ivBlockerPill");
      if (!pill) return;
      if (!blocker) {
        pill.textContent = "All tasks complete";
        pill.className = "iv-blocker-pill is-clear";
      } else {
        pill.textContent = itemLabel(blocker);
        pill.className = "iv-blocker-pill";
      }
    }

    function showInterventionCardImmediate(iv) {
      const card = $("lastInterventionCard");
      if (!card) return;
      card.classList.remove("hidden");

      const _ivDisplayStep = state.tickToDisplayStep.get(iv.displayAtTick ?? iv.atTick)
        ?? iv.displayAtTick ?? iv.atTick;
      $("ivTickStamp").textContent = `Applied at Step ${_ivDisplayStep}`;
      $("ivButton").textContent = iv.label;
      $("ivStateChange").innerHTML = stateChangeLineFor(
        iv.type, iv.params, iv.before, { urgency: iv.postUrgency }, iv.apiResult
      );
      renderBlockerPill(iv.before.blocker);
      $("ivExpected").textContent = expectedEffectFor(iv);
      $("ivMetricDelta").innerHTML = `<span class="delta-flat">Awaiting next step…</span>`;
      $("ivConsequence").textContent = "Pending — visible after the next step lands.";

      const badge = $("ivConfirmBadge");
      badge.className = "iv-confirm is-pending";
      badge.textContent = "⏳ Pending";
      $("ivConfirmNote").textContent = "";
    }

    function evaluateInterventionConfirmation(iv, postEvents) {
      const params = iv.params || {};
      const after = {
        tension: Number(state.groupState.tension || 0),
        cohesion: Number(state.groupState.cohesion || 0),
        urgency: Number(state.urgencyValue),
        agents: state.agents,
      };
      const blocker = currentBlocker();
      const itemMatch = (txt, item) => {
        if (!txt || !item) return false;
        const needle = String(item).replace(/_/g, " ").toLowerCase();
        return String(txt).toLowerCase().includes(needle);
      };
      const dialogue = postEvents.filter(
        e => String(e.actor || "").toUpperCase() !== "USER" && e.type !== "intervention"
      );

      if (iv.type === "reveal_info") {
        const agent = state.agents.find(a => (a.id || a.public_id) === params.agent_id);
        const knows = agent && Array.isArray(agent.known_items) && agent.known_items.includes(params.item);
        const used = postEvents.some(
          e => String(e.actor) === params.agent_id &&
               (e.item === params.item || itemMatch(e.text, params.item))
        );
        if (knows && used) {
          return { confirmed: true,
                   note: `${params.agent_id} now knows ${itemLabel(params.item)} and surfaced it this step.`,
                   consequence: `${params.agent_id} shared/used ${itemLabel(params.item)}.` };
        }
        if (knows) {
          return { confirmed: false,
                   note: `${params.agent_id} learned ${itemLabel(params.item)}, but no visible follow-through landed on this step.`,
                   consequence: `${params.agent_id} learned ${itemLabel(params.item)} but did not surface it yet.` };
        }
        return { confirmed: false,
                 note: `${params.agent_id}'s known_items did not include ${itemLabel(params.item)} after the step.`,
                 consequence: "No state change observed." };
      }

      if (iv.type === "force_meeting") {
        const a = params.agent_a_id, b = params.agent_b_id;
        const reasonHit = postEvents.some(e => {
          const reason = String(e.reason || "");
          return reason.startsWith("user_force_meeting") || reason === "forced_meeting_followthrough";
        });
        const first2 = dialogue.slice(0, 2);
        const stayedOnPair = first2.length >= 1 && first2.every(
          e => [a, b].includes(e.actor) && (!e.target || [a, b].includes(e.target))
        );
        if (stayedOnPair && reasonHit) {
          return { confirmed: true,
                   note: `Your forced meeting worked — ${a} and ${b} led the next exchange.`,
                   consequence: `Forced meeting: ${a} ↔ ${b} discussed ${itemLabel(blocker || "the active item")}.` };
        }
        if (reasonHit) {
          return { confirmed: true,
                   note: `Your forced meeting triggered a follow-up between ${a} and ${b}.`,
                   consequence: `Forced meeting: ${a} and ${b} engaged on the next step.` };
        }
        return { confirmed: false,
                 note: `Forced meeting registered but ${a} ↔ ${b} did not lead the next exchange.`,
                 consequence: "The forced pair did not visibly lead this step." };
      }

      if (iv.type === "nudge_strategy") {
        const agent = state.agents.find(a => (a.id || a.public_id) === params.agent_id);
        const strategyOk = agent && agent.strategy === params.strategy;
        const negativeTypes = new Set(["challenge","refuse","doubt","insult","ignore"]);
        const constructiveTypes = new Set(["share_info","suggest","agree","ask_info","say","compliment","reassure"]);
        const agentEvents = dialogue.filter(e => String(e.actor) === params.agent_id);
        const constructive = agentEvents.length > 0 && agentEvents.some(
          e => constructiveTypes.has(String(e.type)) && !negativeTypes.has(String(e.type))
        );
        const negative = agentEvents.some(e => negativeTypes.has(String(e.type)));
        if (strategyOk && constructive && !negative) {
          return { confirmed: true,
                   note: `Your nudge worked — ${params.agent_id} shifted to ${agent.strategy} and acted cooperatively next.`,
                   consequence: `Nudge cooperation: ${params.agent_id} produced a ${agentEvents[0]?.type || "constructive"} event.` };
        }
        if (strategyOk && agentEvents.length === 0) {
          return { confirmed: false,
                   note: `Nudge registered: ${params.agent_id} is now ${agent.strategy}, but no visible action landed this step yet.`,
                   consequence: "Strategy changed — follow-through expected next step." };
        }
        if (strategyOk) {
          return { confirmed: false,
                   note: `Nudge registered: strategy is ${agent.strategy} but the next event was not clearly cooperative.`,
                   consequence: `${params.agent_id} strategy updated; full effect may land next step.` };
        }
        return { confirmed: false,
                 note: "Nudge did not produce the expected strategy change this step.",
                 consequence: "No strategy state change observed." };
      }

      if (iv.type === "inject_tension") {
        const before = Number(iv.before.tension) || 0;
        const tensionUp = after.tension > before + 0.001;
        const blockerLine = postEvents.some(
          e => String(e.reason || "").startsWith("user_inject_tension") &&
               (e.item === blocker || itemMatch(e.text, blocker))
        );
        const anyTensionLine = postEvents.some(e => String(e.reason || "").startsWith("user_inject_tension"));
        if (tensionUp && (blockerLine || anyTensionLine)) {
          return { confirmed: true,
                   note: `Your tension injection worked — group tension rose ${before.toFixed(2)} → ${after.tension.toFixed(2)} and a challenge event followed.`,
                   consequence: `Inject tension: group tension rose to ${after.tension.toFixed(2)}; agents challenged each other on ${itemLabel(blocker || "the active item")}.` };
        }
        if (tensionUp) {
          return { confirmed: false,
                   note: `Tension injection raised tension ${before.toFixed(2)} → ${after.tension.toFixed(2)}, but no visible challenge event landed this step.`,
                   consequence: `Tension rose to ${after.tension.toFixed(2)} — the disagreement may surface next step.` };
        }
        return { confirmed: false,
                 note: "Tension injection registered but group tension did not visibly rise this step.",
                 consequence: "No tension change observed — the effect may still propagate." };
      }

      if (iv.type === "boost_urgency") {
        const beforeU = (iv.before && iv.before.urgency != null) ? Number(iv.before.urgency) : scenarioBaseUrgency(state.environment || state.scenarioHint);
        const afterU = Number(iv.postUrgency || after.urgency) || beforeU;
        const beforeDisplay = displayPressureValue(beforeU, state.environment || state.scenarioHint);
        const afterDisplay = displayPressureValue(afterU, state.environment || state.scenarioHint);
        const urgencyUp = afterDisplay > beforeDisplay + 0.001;
        const blockerLine = postEvents.some(
          e => String(e.reason || "").startsWith("user_boost_urgency") &&
               (e.item === blocker || itemMatch(e.text, blocker))
        );
        const anyUrgencyLine = postEvents.some(e => String(e.reason || "").startsWith("user_boost_urgency"));
        const delta = afterDisplay - beforeDisplay;
        const deltaLabel = `${delta > 0 ? "+" : ""}${delta.toFixed(2)}`;
        if (urgencyUp && (blockerLine || anyUrgencyLine)) {
          return { confirmed: true,
                   note: `Pressure boost worked — ${beforeDisplay.toFixed(2)} → ${afterDisplay.toFixed(2)}. Agents pushed faster.`,
                   consequence: `Pressure increased by ${deltaLabel}. Agents accelerated progress on ${itemLabel(blocker || "the active item")}.` };
        }
        if (urgencyUp) {
          return { confirmed: false,
                   note: `Pressure boost registered — ${beforeDisplay.toFixed(2)} → ${afterDisplay.toFixed(2)}, but no urgency-driven event was visible this step.`,
                   consequence: `Pressure increased by ${deltaLabel} — faster pacing expected next step.` };
        }
        return { confirmed: false,
                 note: "Pressure is already at maximum.",
                 consequence: "No pressure change observed — check if the backend applied it." };
      }

      if (iv.type === "ease_pressure") {
        const beforeU = (iv.before && iv.before.urgency != null) ? Number(iv.before.urgency) : scenarioBaseUrgency(state.environment || state.scenarioHint);
        const afterU = Number(iv.postUrgency || after.urgency) || beforeU;
        const beforeDisplay = displayPressureValue(beforeU, state.environment || state.scenarioHint);
        const afterDisplay = displayPressureValue(afterU, state.environment || state.scenarioHint);
        const urgencyDown = afterDisplay < beforeDisplay - 0.001;
        const blockerLine = postEvents.some(
          e => String(e.reason || "").startsWith("user_ease_pressure") &&
               (e.item === blocker || itemMatch(e.text, blocker))
        );
        const anyEaseLine = postEvents.some(e => String(e.reason || "").startsWith("user_ease_pressure"));
        if (urgencyDown && (blockerLine || anyEaseLine)) {
          return { confirmed: true,
                   note: `Pressure easing worked — ${beforeDisplay.toFixed(2)} → ${afterDisplay.toFixed(2)}. Agents got more breathing room.`,
                   consequence: "Pressure decreased slightly. Agents may respond more carefully instead of rushing." };
        }
        if (urgencyDown) {
          return { confirmed: false,
                   note: `Pressure easing registered — ${beforeDisplay.toFixed(2)} → ${afterDisplay.toFixed(2)}, but no calmer response was visible this step.`,
                   consequence: "Pressure decreased slightly. A steadier response may surface next step." };
        }
        return { confirmed: false,
                 note: "Pressure is already at the scenario baseline.",
                 consequence: "No pressure change observed — the displayed pressure was already at the scenario baseline." };
      }

      if (iv.type === "inject_emotion") {
        const ar = iv.apiResult || {};
        const anyEmotionLine = postEvents.some(e => String(e.reason || "").startsWith("user_inject_emotion"));
        const emotionLabel = ar.detected_emotion || "emotional";
        const deltaStress = ar.stress_delta != null ? ` Avg stress Δ ${ar.stress_delta > 0 ? "+" : ""}${ar.stress_delta.toFixed(2)}.` : "";
        if (anyEmotionLine) {
          return {
            confirmed: true,
            note: `Emotion injection registered — agents responded to the ${emotionLabel} signal.${deltaStress}`,
            consequence: `Inject emotion (${emotionLabel}): agents perceive and react over ~${ar.decay_ticks || 5} steps.`,
          };
        }
        return {
          confirmed: false,
          note: `Emotion injection queued (${emotionLabel}) — visible agent response expected next step.${deltaStress}`,
          consequence: `Inject emotion: effect propagates over ~${ar.decay_ticks || 5} steps.`,
        };
      }

      return { confirmed: false, note: "Unknown intervention type.", consequence: "—" };
    }

    function applyConfirmationUpdate(iv, postEvents) {
      if (!$("ivConfirmBadge")) return;
      const result = evaluateInterventionConfirmation(iv, postEvents);
      // Store on iv so renderImpactView() can use the follow-through text
      // without re-evaluating confirmation logic.
      iv.confirmResult = {
        confirmed:   result.confirmed,
        note:        result.note,
        consequence: result.consequence,
      };
      const before = iv.before || {};
      const tensionAfter = Number(state.groupState.tension || 0);
      const cohesionAfter = Number(state.groupState.cohesion || 0);
      const urgencyAfter = Number(iv.postUrgency || state.urgencyValue || scenarioBaseUrgency(state.environment || state.scenarioHint));

      let deltaParts = [];
      if (iv.type === "inject_tension" || iv.type === "force_meeting" || iv.type === "nudge_strategy") {
        deltaParts.push(deltaSpan("Tension", before.tension, tensionAfter));
      }
      if (iv.type === "force_meeting" || iv.type === "nudge_strategy" || iv.type === "reveal_info") {
        deltaParts.push(deltaSpan("Cohesion", before.cohesion, cohesionAfter));
      }
      if (iv.type === "boost_urgency" || iv.type === "ease_pressure") {
        const _bU  = before.urgency != null ? before.urgency : scenarioBaseUrgency(state.environment || state.scenarioHint);
        deltaParts.push(deltaSpan("Pressure", _bU, urgencyAfter));
      }
      if (iv.type === "inject_tension") {
        deltaParts.push(deltaSpan("Cohesion", before.cohesion, cohesionAfter));
      }
      if (iv.type === "boost_urgency") {
        deltaParts.push(deltaSpan("Tension", before.tension, tensionAfter));
      }
      if (!deltaParts.length) {
        deltaParts.push(deltaSpan("Tension", before.tension, tensionAfter));
        deltaParts.push(deltaSpan("Cohesion", before.cohesion, cohesionAfter));
      }
      $("ivMetricDelta").innerHTML = deltaParts.join(" &nbsp;·&nbsp; ");
      $("ivConsequence").textContent = result.consequence || "—";

      renderBlockerPill(currentBlocker());

      const badge = $("ivConfirmBadge");
      if (result.confirmed) {
        badge.className = "iv-confirm is-yes";
        badge.textContent = "✓ Yes";
      } else {
        badge.className = "iv-confirm is-no";
        badge.textContent = "✗ No";
      }
      $("ivConfirmNote").textContent = result.note || "";
    }

    // ── Scenario pressure helpers ──────────────────────────────────────
    // Returns the real backend env.urgency_modifier baseline for each scenario.
    function scenarioBaseUrgency(env) {
      const e = String(env || "").toLowerCase();
      if (e === "cafe" || e === "cafe_restaurant") return 0.00;  // no time pressure
      if (e === "office") return 0.25;                           // moderate pressure
      if (e === "escape" || e === "escape_room") return 0.80;   // high time pressure
      return 0.25; // unknown → medium
    }

    // ── State snapshot application ─────────────────────────────────────
    function applyStatusSnapshot(data) {
      if (!data) return;
      state.tick = data.tick ?? state.tick;
      state.status = data.status ?? state.status;
      state.ended = Boolean(data.ended);
      state.autoRunning = state.status === "auto_running" || state.status === "running";
      state.config = data.config || state.config;
      const scenario = data.scenario || {};
      state.environment = scenario.environment || state.environment || state.scenarioHint;
      const lastHistorySnapshot = Array.isArray(data.history) && data.history.length
        ? data.history[data.history.length - 1]
        : null;
      const snapshotPressure = readPressureValue(lastHistorySnapshot)
        ?? readPressureValue({ group_state: data.group_state, scenario: data.scenario, metrics: data.metrics });
      if (Number.isFinite(snapshotPressure)) {
        state.urgencyValue = snapshotPressure;
        state.urgencySeeded = true;
      } else if (!state.urgencySeeded && state.environment) {
        // Only seed from scenario defaults when no real snapshot value exists yet.
        state.urgencyValue = scenarioBaseUrgency(state.environment);
        state.urgencySeeded = true;
      }
      state.tasks = scenario.tasks || state.tasks;
      state.knowledgeMap = scenario.knowledge_map || state.knowledgeMap;
      state.agents = Array.isArray(data.agents) ? data.agents : state.agents;
      state.groupState = (state.ended && lastHistorySnapshot?.group_state)
        ? lastHistorySnapshot.group_state
        : (data.group_state || state.groupState);
      // Seed peak tension from history (captures initial non-zero values that
      // may have dropped to 0 by the time the first tick snapshot is stored).
      if (data.group_state) {
        state.peakTension = Math.max(state.peakTension, data.group_state.tension || 0);
      }
      if (Array.isArray(data.history)) {
        state.historySnapshots = data.history.slice();
        data.history.forEach(h => {
          const t = h.group_state ? (h.group_state.tension || 0) : (h.metrics ? (h.metrics.group_tension || 0) : 0);
          if (t > state.peakTension) state.peakTension = t;
        });
      }
      // Safety guard: peak tension must be >= the final tension value in state.groupState.
      // This covers edge cases where the final tick's tension was not captured in the
      // history loop (e.g. structural differences in backend response shapes).
      state.peakTension = Math.max(state.peakTension, Number(state.groupState.tension || 0));

      setMeta("RunId", state.runId || "—");
      setMeta("Status", statusLabel(state.status, state.ended),
              state.ended ? "ended" : (state.autoRunning ? "running" : ""));
      setMeta("Tick", state.tick);
      updateStepStrip();
      updateMetricStripLabels();
      const _envLabel  = environmentLabel(state.environment || "");
      const _teamLabel = teamLabel(data.team_type || state.teamHint || "");
      const _envFull   = [_envLabel, _teamLabel].filter(v => v && v !== "—").join(" · ") || "—";
      setMeta("Env", _envFull);
      // sTeam hidden in strip; kept for any legacy references
      const _sTeamEl = document.getElementById("sTeam");
      if (_sTeamEl) _sTeamEl.style.display = "none";
      // Pass the same value as "previous" on initial load so no delta fires.
      const _initTension  = Number(state.groupState.tension  || 0);
      const _initCohesion = Number(state.groupState.cohesion || 0);
      const _initUrgency  = Number(state.urgencyValue);
      setTopStripMetric("Tension",  _initTension,  _initTension);
      setTopStripMetric("Cohesion", _initCohesion, _initCohesion);
      setTopStripMetric("Urgency",  _initUrgency,  _initUrgency);

      updateBlockerBadge();
      renderAgents();
      refreshInterventionPickers();
      updateSuggestText();
      syncDashboardLinks();

      // Sync completedPhases with all tasks that are already done in the initial snapshot.
      // This prevents the phase divider loop in applyTickDiff from retroactively marking
      // tasks that were completed in history ticks we didn't render.
      const initialTasks = state.tasks || {};
      Object.entries(initialTasks).forEach(([taskKey, done]) => {
        if (done && shouldRenderPhaseDivider(taskKey, state.environment)) {
          state.completedPhases.add(taskKey);
        }
      });

      // Seed metricsHistory from full history ticks
      if (state.metricsHistory.length === 0 && Array.isArray(data.history)) {
        data.history.forEach(h => {
          const hm = h.metrics || {};
          const hg = h.group_state || {};
          state.metricsHistory.push({
            tick:     Number(h.tick || 0),
            stress:   Number(hm.avg_stress    ?? 0),
            trust:    Number(hm.avg_trust     ?? 0),
            cohesion: Number(hg.cohesion      ?? 0),
            tension:  Number(hg.tension       ?? 0),
            conflict: Number(hm.conflict_rate ?? 0),
          });
        });
      }

      // Seed log from recent history on first attach
      if (!eventLog.querySelector(".event") && Array.isArray(data.history)) {
        const recent = historyEventsForTimeline(data.history, {
          includeAllCompleted: state.ended,
          ended: state.ended,
          environment: data.environment || data.scenarioHint || state.environment || "",
        });
        appendEvents(recent, { focusLatest: true, smoothScroll: false, highlightLatest: false });
        updateStepStrip();
        const latestTick = recent.length ? Math.max(...recent.map((ev) => Number(ev.tick || 0))) : null;
        renderStoryPanels(latestTick == null ? [] : recent.filter((ev) => Number(ev.tick) === latestTick));
        if (state.ended) {
          // Inject blocker-resolution dividers from the full history before the
          // summary card so the user sees the complete progression in the timeline.
          const _histEnv = data.environment || data.scenarioHint || state.environment || "";
          injectHistoryPhaseDividers(data.history, _histEnv);
          // Use the last history snapshot's tasks as the final task state.
          // state.tasks comes from the STATUS endpoint's last_diff; the history snapshot
          // is a deep copy made at end-of-tick, so it's more reliably populated
          // when the status endpoint's last_diff.scenario is partially
          // constructed (e.g. from the fallback branch in get_run_status).
          const _finalTasks = lastHistorySnapshot?.scenario?.tasks || null;
          // Pass full history so appendRunSummaryCard can use deriveResolvedPhasesFromHistory
          // as the final fallback — never relying on blind config strings.
          appendRunSummaryCard(state.nextDisplayStep || state.tick, _finalTasks, data.history);
        }
      } else {
        renderStoryPanels([]);
      }

      updateControlState();

      if (state.ended) {
        setModePill("Ended", "ended");
        updateMetricStripLabels();
        showEndModal();
      } else {
        setModePill("Live Interactive");
        hideEndModal();
      }
    }

    function applyTickDiff(diff) {
      if (!diff) return;
      const previousTasks = Object.assign({}, state.tasks || {});
      const previousTension = Number(state.groupState?.tension || 0);
      const previousCohesion = Number(state.groupState?.cohesion || 0);
      const previousUrgency = Number(state.urgencyValue);
      state.tick = diff.tick ?? state.tick;
      if (Array.isArray(diff.agents) && diff.agents.length) state.agents = diff.agents;
      if (diff.group_state) {
        state.groupState = diff.group_state;
        const diffPressure = readPressureValue({ group_state: diff.group_state, scenario: diff.scenario, metrics: diff.metrics });
        if (Number.isFinite(diffPressure)) {
          state.urgencyValue = diffPressure;
          state.urgencySeeded = true;
        }
        // Track peak tension as a running max so the summary card shows
        // the highest tension the team reached, not just the final (often near-0) value.
        state.peakTension = Math.max(state.peakTension, diff.group_state.tension || 0);
      }
      if (diff.scenario && diff.scenario.tasks) state.tasks = diff.scenario.tasks;
      if (diff.scenario && diff.scenario.knowledge_map) state.knowledgeMap = diff.scenario.knowledge_map;

      // Accumulate per-tick metrics for Metrics & Analysis view
      const m = diff.metrics || {};
      state.metricsHistory.push({
        tick:     Number(state.tick || 0),
        stress:   Number(m.avg_stress    ?? 0),
        trust:    Number(m.avg_trust     ?? 0),
        cohesion: Number(state.groupState.cohesion || 0),
        tension:  Number(state.groupState.tension  || 0),
        conflict: Number(m.cumulative_conflict_rate ?? m.conflict_rate ?? 0),
      });
      if (state.currentView === "metrics") refreshMetricsView();

      setMeta("Tick", state.tick);
      updateStepStrip();
      setTopStripMetric("Tension", Number(state.groupState.tension || 0), previousTension);
      setTopStripMetric("Cohesion", Number(state.groupState.cohesion || 0), previousCohesion);
      setTopStripMetric("Urgency", Number(state.urgencyValue), previousUrgency);
      updateBlockerBadge();
      renderAgents();
      refreshInterventionPickers();
      updateSuggestText();

      const stepActiveBlocker = diff.group_state?.active_blocker || null;
      const stepNextBlocker = diff.group_state?.bottleneck_item || null;
      const stepTasks = diff.scenario?.tasks || state.tasks || {};
      const resolvedItems = diff.scenario?.resolved_items || [];
      const environment = diff.scenario?.environment || state.environment || state.scenarioHint || "";
      let events = (diff.events || []).map(e => Object.assign({
        tick: state.tick,
        __stepActiveBlocker: stepActiveBlocker,
        __stepNextBlocker: stepNextBlocker,
        __stepTasks: stepTasks,
        __resolvedItems: resolvedItems,
        __environment: environment,
      }, e));
      if (!events.length) {
        events = buildQuietTickEvent({
          tick: state.tick,
          group_state: diff.group_state || {},
          scenario: diff.scenario || {},
        }, environment);
      } else if (resolvedItems.length) {
        // Per-item evidence check (live path): same substantive logic as history path.
        // Generic agree events ("Yeah, that's fine.") are not substantive — still inject
        // the concrete synthetic so the user sees real content before the ✓ divider.
        const _snap = { tick: state.tick, group_state: diff.group_state || {}, scenario: diff.scenario || {} };
        resolvedItems.forEach(resolvedItem => {
          if (!hasSubstantiveItemEvidence(events, resolvedItem)) {
            events.push(...buildQuietTickEvent(_snap, environment, resolvedItem));
          }
        });
      }
      appendEvents(events, { focusLatest: true, smoothScroll: true, highlightLatest: true });
      updateStepStrip();
      renderStoryPanels(events);

      state.historySnapshots.push({
        tick: state.tick,
        group_state: Object.assign({}, diff.group_state || {}),
        scenario: {
          environment,
          tasks: Object.assign({}, stepTasks || {}),
          resolved_items: Array.isArray(resolvedItems) ? [...resolvedItems] : [],
        },
        events: Array.isArray(diff.events) ? diff.events.map((ev) => Object.assign({}, ev)) : [],
      });

      // Effect confirmation: evaluate the just-arrived tick against the
      // intervention applied at state.lastIntervention.atTick.
      if (state.lastIntervention && !state.lastIntervention.confirmed
          && state.tick > state.lastIntervention.atTick) {
        try {
          applyConfirmationUpdate(state.lastIntervention, events);
          const lastM = state.metricsHistory.length
            ? state.metricsHistory[state.metricsHistory.length - 1] : null;
          state.lastIntervention.afterMetrics = {
            // Null when no metrics history exists — the display layer treats null
            // as "no after data" and shows "—" rather than a misleading 0.00.
            stress:   lastM ? lastM.stress : null,
            trust:    lastM ? lastM.trust  : null,
            tension:  Number(state.groupState.tension  || 0),
            cohesion: Number(state.groupState.cohesion || 0),
          };
          state.lastIntervention.confirmed = true;
          state.interventionLog.push(Object.assign({}, state.lastIntervention));
          if (state.currentView === "impact") renderImpactView();
        } catch (e) {
          console.warn("Intervention confirmation failed:", e);
        }
      }

      if (state.pendingAdvance && state.tick > state.pendingAdvance.startTick) {
        resolvePendingAdvance();
      }

      // Phase dividers: insert a marker each time a new task becomes complete.
      // Iterate in canonical scenario order so dividers always appear in chain order.
      // Prefer diff.scenario.resolved_items (what the backend says resolved THIS tick)
      // then fall back to task-state transition detection (prev false → now true).
      const tasks = state.tasks || {};
      const liveEnvKey = String(state.environment || state.scenarioHint || "").toLowerCase();
      const liveScenarioKey = liveEnvKey === "cafe" ? "cafe"
                            : liveEnvKey === "office" ? "office" : "escape";
      const diffResolvedItems = Array.isArray(diff.scenario?.resolved_items)
        ? diff.scenario.resolved_items : [];
      const derivedTransitionItems = deriveResolvedPhasesFromTaskTransition(
        previousTasks,
        tasks,
        liveScenarioKey
      ).map((entry) => entry.item);

      scenarioBlockerOrder(liveScenarioKey).forEach(taskKey => {
        if (!shouldRenderPhaseDivider(taskKey, state.environment)) return;
        // An item is newly resolved if: backend says so in resolved_items this tick,
        // OR its task state transitioned to true since our last completedPhases check.
        const resolvedThisTick = diffResolvedItems.includes(taskKey) || derivedTransitionItems.includes(taskKey);
        if (resolvedThisTick && !state.completedPhases.has(taskKey)) {
          state.completedPhases.add(taskKey);
          const cfg = SCENARIO_CONFIG[liveScenarioKey] || SCENARIO_CONFIG.escape;
          const label = (cfg.labels && cfg.labels[taskKey]) || itemLabel(taskKey);
          const divider = document.createElement("div");
          divider.className = "phase-divider";
          divider.innerHTML = `<span class="phase-label">✓ ${escapeHtml(label)} resolved</span>`;
          eventLog.appendChild(divider);
        }
      });

      if (diff.ended) {
        state.ended = true;
        state.autoRunning = false;
        setMeta("Status", statusLabel("ended", true), "ended");
        setModePill("Ended", "ended");
        updateStepStrip();
        updateMetricStripLabels();
        updateBlockerBadge();
        updateSuggestText();
        renderStoryPanels(events);
        updateControlState();

        // Insert final run summary card into the log
        appendRunSummaryCard(
          state.nextDisplayStep || state.tick,
          diff.scenario?.tasks || state.tasks || null,
          state.historySnapshots
        );
        requestAnimationFrame(() => {
          const scroll = $("eventLogScroll");
          if (scroll) scroll.scrollTo({ top: scroll.scrollHeight, behavior: "smooth" });
        });

        const _envB = String(state.environment || state.scenarioHint || "").toLowerCase();
        const _completionMsg = _envB === "office" ? "Run complete — the proposal was accepted!"
                             : _envB === "cafe"   ? "Run complete — the group reached a decision!"
                             : "Run complete — the team escaped!";
        showEndModal();
        showBanner(_completionMsg, "good");
      }
    }

    // ── Networking ─────────────────────────────────────────────────────
    async function fetchRunStatus(runId) {
      const r = await fetch(`${API_BASE}/runs/${runId}`);
      if (!r.ok) {
        const detail = await parseApiError(r);
        const err = new Error(detail);
        err.status = r.status;
        throw err;
      }
      return r.json();
    }

    async function parseApiError(response) {
      const text = await response.text();
      if (!text) return `HTTP ${response.status}`;
      try {
        const data = JSON.parse(text);
        let detail = data.detail || data.message || `HTTP ${response.status}`;
        if (Array.isArray(detail)) {
          detail = detail.map(e => (typeof e === "object" ? (e.msg || JSON.stringify(e)) : String(e))).join("; ");
        }
        return detail;
      } catch {
        return text;
      }
    }

    async function postJson(url, body) {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      const text = await r.text();
      let data;
      try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
      if (!r.ok) {
        let detail = (data && (data.detail || data.message)) || (text || `HTTP ${r.status}`);
        if (Array.isArray(detail)) {
          detail = detail.map(e => (typeof e === "object" ? (e.msg || JSON.stringify(e)) : String(e))).join("; ");
        }
        throw new Error(detail);
      }
      return data;
    }

    // Reconnect state: track attempts so we don't reconnect infinitely.
    let _wsReconnectAttempts = 0;
    const _WS_MAX_RECONNECT = 3;

    function _scheduleWsReconnect() {
      if (state.ended || !state.runId) return;
      if (_wsReconnectAttempts >= _WS_MAX_RECONNECT) {
        showBanner(
          "Live connection lost. Please <strong>refresh the page</strong> to reconnect.",
          "error",
        );
        return;
      }
      _wsReconnectAttempts += 1;
      const delay = _wsReconnectAttempts * 1500;
      setMeta("Ws", wsLabel("reconnecting"));
      setTimeout(() => {
        if (state.wsReady || state.ended) return; // already reconnected or ended
        openWebSocket(state.runId)
          .then(() => {
            _wsReconnectAttempts = 0;
            showBanner("Live connection restored — you can continue stepping.", "good");
          })
          .catch(() => _scheduleWsReconnect());
      }, delay);
    }

    function openWebSocket(runId) {
      return new Promise((resolve, reject) => {
        const ws = new WebSocket(`${WS_BASE}/runs/${runId}/ws`);
        state.ws = ws;
        state.wsReady = false;
        setMeta("Ws", wsLabel("connecting"));

        ws.addEventListener("open", () => {
          state.wsReady = true;
          _wsReconnectAttempts = 0;
          setMeta("Ws", wsLabel("open"), "running");
          updateControlState();
          resolve(ws);
        }, { once: true });

        ws.addEventListener("error", () => {
          setMeta("Ws", wsLabel("error"), "error");
          rejectPendingAdvance("WebSocket error — reconnecting…");
          reject(new Error("WebSocket error"));
        }, { once: true });

        ws.addEventListener("close", () => {
          state.wsReady = false;
          setMeta("Ws", wsLabel("closed"));
          rejectPendingAdvance("Live connection closed before the next step arrived.");
          // If auto-run was active, reset the flag so the UI doesn't freeze on
          // "Auto running" while the connection is down. The reconnect will
          // restore the correct state from the backend's next status message.
          if (state.autoRunning && !state.ended) {
            state.autoRunning = false;
            showBanner("Auto-run paused — live connection dropped. Reconnecting…", "warn");
          }
          updateControlState();
          // Auto-reconnect unless the run ended cleanly.
          if (!state.ended) _scheduleWsReconnect();
        });

        ws.addEventListener("message", (evt) => {
          let msg;
          try { msg = JSON.parse(evt.data); } catch { return; }
          if (msg.type === "tick") {
            applyTickDiff(msg.data || {});
          } else if (msg.type === "status") {
            if (msg.status === "auto_running") state.autoRunning = true;
            if (msg.status === "auto_stopped") {
              state.autoRunning = false;
              if (!state.ended) setMeta("Status", statusLabel("paused"));
            }
            if (msg.status === "ended" || msg.status === "stopped") {
              state.ended = true;
              state.autoRunning = false;
              setModePill(msg.status === "ended" ? "Ended" : "Stopped", "ended");
              showEndModal();
            }
            const nextStatus = msg.status === "auto_stopped" ? "paused" : msg.status;
            setMeta("Status", statusLabel(nextStatus, state.ended),
                    state.ended ? "ended" : (state.autoRunning ? "running" : ""));
            updateControlState();
            if (msg.status === "auto_running" && !state.ended) {
              enforceManualMode();
            }
          } else if (msg.type === "error") {
            rejectPendingAdvance(msg.message || "Backend rejected the requested action.");
            showBanner("Backend: " + escapeHtml(msg.message || "unknown error"), "error");
          }
        });
      });
    }

    function wsSend(payload) {
      if (!state.ws || !state.wsReady) return false;
      state.ws.send(JSON.stringify(payload));
      return true;
    }

    // ── Run control actions ────────────────────────────────────────────
    function enforceManualMode() {
      if (!state.wsReady || !state.autoRunning || state.ended) return;
      wsSend({ cmd: "auto_stop" });
      state.autoRunning = false;
      setMeta("Status", statusLabel("paused"));
      updateControlState();
      showBanner("Live Interactive stays manual. Auto-play was paused when this page attached.", "warn");
    }

    async function advanceOneTick(successMessage, options = {}) {
      const fromIntervention = Boolean(options.fromIntervention);
      if (!state.runId) {
        showBanner("No active run attached to this page.", "error");
        return false;
      }
      if (state.ended) {
        showEndModal();
        return false;
      }
      if ((state.actionPending && !fromIntervention) || state.pendingAdvance) {
        return false;
      }
      if (!state.wsReady) {
        showBanner("Live connection is not ready yet — wait a moment and try again.", "error");
        return false;
      }
      if (state.autoRunning) {
        enforceManualMode();
        return false;
      }

      state.actionPending = true;
      updateControlState();
      // Safety valve: if actionPending is somehow never cleared by the normal
      // finally path (e.g. an unhandled promise rejection in a browser extension),
      // force-reset it after 12 s so buttons don't stay permanently disabled.
      const _apStallTimer = setTimeout(() => {
        if (state.actionPending) {
          state.actionPending = false;
          updateControlState();
        }
      }, 12000);
      try {
        const waitForTick = waitForNextTick(Number(state.tick || 0));
        if (!wsSend({ cmd: "step" })) {
          throw new Error("Live connection is not ready. Try refreshing or wait for reconnect.");
        }
        await waitForTick;
        if (!state.ended && successMessage) {
          showBanner(successMessage, "good");
        }
        return true;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        showBanner(message, "error");
        return false;
      } finally {
        clearTimeout(_apStallTimer);
        state.actionPending = false;
        updateControlState();
      }
    }

    async function stepRun() {
      if (state.actionPending || state.pendingAdvance) return;
      if (state.ended) {
        window.location.href = "setup.html";
        return;
      }
      await advanceOneTick("Advanced one step.");
    }

    async function resetRun() {
      if (state.actionPending || state.pendingAdvance) return;
      if (!state.config) {
        showBanner("This run cannot be reset from here because its setup details are unavailable.", "error");
        return;
      }

      state.actionPending = true;
      updateControlState();
      try {
        const created = await postJson(`${API_BASE}/runs`, {
          environment: state.config.environment || state.environment || state.scenarioHint,
          goal: state.config.goal,
          team_type: state.config.resolved_team_type || state.config.team_type || state.teamHint,
        });
        const params = new URLSearchParams({
          run_id: created.run_id,
          mode: "live",
          scenario: created.requested_environment || state.scenarioHint || state.environment,
          team: created.resolved_team_type || state.teamHint || state.config.team_type || "",
        });
        window.location.href = `interactive.html?${params.toString()}`;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        showBanner(`Could not reset the run.\n${escapeHtml(message)}`, "error");
        state.actionPending = false;
        updateControlState();
      }
    }

    // ── Interventions ──────────────────────────────────────────────────
    async function applyIntervention(type) {
      if (state.actionPending || state.pendingAdvance) return;
      if (!state.runId) { showBanner("No active run attached to this page.", "error"); return; }
      if (state.ended) { showEndModal(); return; }
      setIvInline("ivNoteBoostPressure", null);
      setIvInline("ivNoteEasePressure", null);

      const params = {};
      if (type === "boost_urgency") {
        const currentPressure = state.urgencySeeded
          ? state.urgencyValue
          : scenarioBaseUrgency(state.environment || state.scenarioHint);
        const currentDisplayPressure = displayPressureValue(currentPressure, state.environment || state.scenarioHint);
        if (currentDisplayPressure >= 0.999) {
          setIvInline("ivNoteBoostPressure", "Pressure is already at maximum.");
          return;
        }
        params.amount = PRESSURE_INTERVENTION_AMOUNT;
      } else if (type === "ease_pressure") {
        const currentPressure = state.urgencySeeded
          ? state.urgencyValue
          : scenarioBaseUrgency(state.environment || state.scenarioHint);
        const currentDisplayPressure = displayPressureValue(currentPressure, state.environment || state.scenarioHint);
        const _easeBaseline = displayPressureBaseline(state.environment || state.scenarioHint);
        if (currentDisplayPressure <= _easeBaseline + 0.001) {
          setIvInline("ivNoteEasePressure", "Pressure is already at the scenario baseline.");
          return;
        }
        params.amount = PRESSURE_INTERVENTION_AMOUNT;
      } else if (type === "inject_tension") {
        params.amount = 0.05;
      } else if (type === "inject_emotion") {
        const _etEl = document.getElementById("emotionText");
        params.text = _etEl ? _etEl.value.trim() : "";
        // Button is already disabled when text is empty — silent guard only.
        if (!params.text) return;
      } else if (type === "reveal_info") {
        params.agent_id = $("revealAgent").value;
        params.item = $("revealItem").value;
        // Button is already disabled for invalid selections — silent guards only.
        if (!params.agent_id || !params.item) return;
        if (!revealableItemsForAgent(params.agent_id).includes(params.item)) return;
      } else if (type === "force_meeting") {
        params.agent_a_id = $("forceAgentA").value;
        params.agent_b_id = $("forceAgentB").value;
        // Button is already disabled for invalid/same-agent selections — silent guards.
        if (!params.agent_a_id || !params.agent_b_id) return;
        if (params.agent_a_id === params.agent_b_id) return;
      } else if (type === "nudge_strategy") {
        params.agent_id = $("nudgeAgent").value;
        // Button is already disabled when no agent is selected — silent guard only.
        if (!params.agent_id) return;
        params.strategy = "cooperative";
      }

      // Capture BEFORE snapshot synchronously for effect verification
      const targetAgentId = params.agent_id || params.agent_a_id || null;
      const targetAgent = targetAgentId
        ? state.agents.find(a => (a.id || a.public_id) === targetAgentId)
        : null;
      const _lastM = state.metricsHistory.length
        ? state.metricsHistory[state.metricsHistory.length - 1] : null;
      const beforeSnapshot = {
        tick: state.tick,
        tension: Number(state.groupState.tension || 0),
        cohesion: Number(state.groupState.cohesion || 0),
        urgency: Number(state.urgencySeeded ? state.urgencyValue : scenarioBaseUrgency(state.environment || state.scenarioHint)),
        // Use null (not 0) when no metrics history exists yet.
        // A null baseline means "no before data" — the display layer will
        // skip that row rather than show a fake 0.00 → real-value jump.
        stress: _lastM ? _lastM.stress : null,
        trust:  _lastM ? _lastM.trust  : null,
        blocker: currentBlocker(),
        strategy: targetAgent ? targetAgent.strategy : null,
        knownItems: targetAgent && Array.isArray(targetAgent.known_items)
          ? [...targetAgent.known_items]
          : [],
      };

      state.actionPending = true;
      updateControlState();
      try {
        console.log("[SimuVerse] Intervention payload", {
          actionType: type,
          targetItem: params.item || null,
          currentBlocker: currentBlocker(),
          scenario: String(state.environment || state.scenarioHint || ""),
          selectedDropdownValue: type === "reveal_info" ? $("revealItem").value : null,
          params,
        });
        const result = await postJson(`${API_BASE}/interventions/apply`, {
          run_id: state.runId, type, params,
        });
        const rawMessage = result.message || "Intervention queued for the next step.";
        const label = formatInterventionMessage(type, params, rawMessage);

        // Update the Pressure strip immediately after pressure interventions using the
        // explicit fields the backend now returns (pressure_before / pressure_after).
        // Falls back to message-text parsing, then to client-side arithmetic.
        let postUrgency = state.urgencyValue;
        // pressureEventDisplayText is computed here while we still hold both before
        // and after values, then passed through to the local timeline event.
        let pressureEventDisplayText = null;
        if (type === "boost_urgency" || type === "ease_pressure") {
          // 1. Prefer the explicit backend values — no string parsing needed.
          // 2. Fallback: regex-parse the legacy message text.
          // 3. Last resort: client-side arithmetic mirroring the backend action.
          const currentSeedValue = state.urgencySeeded
            ? state.urgencyValue
            : scenarioBaseUrgency(state.environment || state.scenarioHint);

          let newPressure = null;
          let previousPressure = currentSeedValue;

          if (Number.isFinite(result.pressure_after)) {
            // Explicit backend truth — most reliable.
            newPressure = result.pressure_after;
            if (Number.isFinite(result.pressure_before)) previousPressure = result.pressure_before;
          } else {
            // Legacy: parse from message text.
            const m = String(rawMessage).match(/Environment urgency now ([0-9.]+)/);
            if (m) {
              newPressure = parseFloat(m[1]);
              if (Number.isFinite(params.amount)) {
                const derivedBefore = type === "ease_pressure"
                  ? (newPressure + Number(params.amount))
                  : (newPressure - Number(params.amount));
                if (derivedBefore >= 0) previousPressure = derivedBefore;
              }
            } else if (Number.isFinite(params.amount)) {
              // Arithmetic fallback floor for ease_pressure uses the scenario base
              // (same constraint the backend applies) so the display never undershoots.
              const _easeFallbackBase = scenarioBaseUrgency(state.environment || state.scenarioHint);
              newPressure = type === "ease_pressure"
                ? Math.max(_easeFallbackBase, currentSeedValue - Number(params.amount))
                : Math.min(3.0, currentSeedValue + Number(params.amount));
            }
          }

          if (Number.isFinite(newPressure)) {
            // Sync the before-snapshot so the intervention card shows the right baseline.
            beforeSnapshot.urgency = previousPressure;
            state.urgencyValue  = newPressure;
            state.urgencySeeded = true;
            postUrgency = newPressure;
            setTopStripMetric("Urgency", newPressure, previousPressure);

            const previousDisplay = displayPressureValue(previousPressure, state.environment || state.scenarioHint);
            const newDisplay = displayPressureValue(newPressure, state.environment || state.scenarioHint);

            // Pre-compute the timeline event text while we hold both values.
            if (Math.abs(newDisplay - previousDisplay) < 0.001) {
              pressureEventDisplayText = type === "ease_pressure"
                ? "Pressure is already at the scenario baseline."
                : "Pressure is already at maximum.";
            } else {
              pressureEventDisplayText = type === "ease_pressure"
                ? `Pressure decreased: ${previousDisplay.toFixed(2)} → ${newDisplay.toFixed(2)}.`
                : `Pressure increased: ${previousDisplay.toFixed(2)} → ${newDisplay.toFixed(2)}.`;
            }
          }
        }

        state.lastIntervention = {
          type,
          params: { ...params },
          label: buttonLabelFor(type, params),
          before: beforeSnapshot,
          atTick: state.tick,
          // displayAtTick is the tick the intervention event appears in the Live Log
          // (state.tick + 1, because buildLocalInterventionEvent uses tick + 1).
          // atTick stays as state.tick so the confirmation check fires correctly.
          displayAtTick: state.tick + 1,
          postUrgency,
          confirmed: false,
          // Transparency fields returned by the backend for the Impact card
          apiResult: {
            stress_before:    result.stress_before    ?? null,
            stress_after:     result.stress_after     ?? null,
            stress_delta:     result.stress_delta     ?? null,
            strategy_before:  result.strategy_before  ?? null,
            strategy_after:   result.strategy_after   ?? null,
            lock_duration:    result.lock_duration     ?? null,
            tension_before:   result.tension_before   ?? null,
            tension_after:    result.tension_after    ?? null,
            trust_before:     result.trust_before     ?? null,
            trust_after:      result.trust_after      ?? null,
            trust_delta:      result.trust_delta      ?? null,
            detected_emotion: result.detected_emotion ?? null,
            decay_ticks:      result.decay_ticks      ?? null,
            share_boost_ticks: result.share_boost_ticks ?? null,
          },
        };

        // Track force-meeting attempts per focus for repetition detection.
        // recentForceMeetings (exact pair+focus) and nonOwnerAttempts (focus only)
        // are both cleared automatically when the active blocker advances.
        if (type === "force_meeting" && params.agent_a_id && params.agent_b_id) {
          const fmBlocker = currentBlocker() || "";
          const fmKey = [params.agent_a_id, params.agent_b_id].sort().join("|")
            + "|" + fmBlocker;
          state.recentForceMeetings.add(fmKey);
          // If neither agent holds the focus clue, record this focus as having had
          // a non-owner attempt so the next attempt escalates to a hard block.
          if (fmBlocker && pairHoldsBlocker(params.agent_a_id, params.agent_b_id, fmBlocker) === false) {
            state.nonOwnerAttempts.add(fmBlocker);
          }
        }

        showInterventionCardImmediate(state.lastIntervention);

        appendEvents([buildLocalInterventionEvent(type, params, rawMessage, pressureEventDisplayText)]);
        const advanced = await advanceOneTick("✓ " + escapeHtml(label), {
          fromIntervention: true,
        });
        if (!advanced && !state.ended) {
          // The intervention was queued on the backend but the WS step didn't fire.
          // Give the user a clear path forward instead of a vague warning.
          const wsOk = state.wsReady;
          const msg = wsOk
            ? "Intervention queued — press <strong>▶ Next Step</strong> to see the effect."
            : "Intervention queued, but the live connection dropped. Reconnecting… or press <strong>▶ Next Step</strong> once the connection is restored.";
          showBanner(msg, "warn");
        }
      } catch (err) {
        showBanner("Intervention failed: " + escapeHtml(err.message), "error");
      } finally {
        if (state.actionPending) {
          state.actionPending = false;
          updateControlState();
        }
      }
    }

    // ── Wire buttons ───────────────────────────────────────────────────
    btnStep.addEventListener("click", stepRun);
    btnReset.addEventListener("click", resetRun);
    const btnDismissEndModal = $("btnDismissEndModal");
    if (btnDismissEndModal) btnDismissEndModal.addEventListener("click", hideEndModal);
    const btnExportPdf = $("btnExportPdf");
    if (btnExportPdf) btnExportPdf.addEventListener("click", exportInteractionPdf);
    document.querySelectorAll("[data-iv]").forEach(btn => {
      btn.addEventListener("click", () => applyIntervention(btn.getAttribute("data-iv")));
    });

    // Live NLP preview for the Inject Mood textarea
    const _emotionTextarea = document.getElementById("emotionText");
    const _ivEmotionPreview = document.getElementById("ivEmotionPreview");
    const _ivEmotionBadge   = document.getElementById("ivEmotionBadge");
    const _ivEmotionLabel   = document.getElementById("ivEmotionLabel");
    const _ivEmotionConf    = document.getElementById("ivEmotionConf");
    const _ivEmotionEffect  = document.getElementById("ivEmotionEffect");

    const IV_EMOTION_HINT = {
      anger: "↑ stress  ↓ trust", annoyance: "↑ stress  ↓ trust",
      fear: "↑ stress  ↓ trust", nervousness: "↑ stress",
      disgust: "↑ stress  ↓ trust", disapproval: "↑ stress  ↓ trust",
      sadness: "↑ stress (mild)", disappointment: "↑ stress (mild)",
      remorse: "↑ stress (mild)", grief: "↑ stress (mild)",
      joy: "↓ stress  ↑ trust", gratitude: "↓ stress  ↑ trust",
      approval: "↓ stress  ↑ trust", admiration: "↓ stress  ↑ trust",
      optimism: "↓ stress  ↑ trust", relief: "↓ stress  ↑ trust",
      amusement: "↓ stress  ↑ trust", excitement: "↓ stress  ↑ trust",
      pride: "↓ stress  ↑ trust", neutral: "no change",
    };

    let _ivEmotionDebounce = null;

    async function _previewIvEmotion(text) {
      if (!text || !text.trim()) {
        if (_ivEmotionPreview) _ivEmotionPreview.style.display = "none";
        return;
      }
      try {
        const res = await window.SimuVerseAPI.apiPost(`/simulation/classify-emotion`, { text: text.trim() });
        if (!_ivEmotionPreview) return;
        const emotion = res.top_emotion || "neutral";
        const conf    = Math.round((res.confidence || 0) * 100);
        _ivEmotionLabel.textContent  = emotion.charAt(0).toUpperCase() + emotion.slice(1);
        _ivEmotionConf.textContent   = conf ? `${conf}%` : "";
        _ivEmotionEffect.textContent = IV_EMOTION_HINT[emotion] || "";
        const valence = res.valence || 0;
        const bg  = valence > 0.1 ? "#edfaf7" : valence < -0.1 ? "#fff4f4" : "#edf4fb";
        const bdr = valence > 0.1 ? "rgba(15,143,131,0.18)" : valence < -0.1 ? "rgba(200,74,74,0.18)" : "rgba(40,120,200,0.16)";
        _ivEmotionPreview.style.background = bg;
        _ivEmotionPreview.style.border = `1px solid ${bdr}`;
        if (_ivEmotionBadge) _ivEmotionBadge.style.color = valence > 0.1 ? "#0f8f83" : valence < -0.1 ? "#c84a4a" : "#2878c8";
        _ivEmotionPreview.style.display = "flex";
      } catch (_) {
        if (_ivEmotionPreview) _ivEmotionPreview.style.display = "none";
      }
    }

    if (_emotionTextarea) {
      _emotionTextarea.addEventListener("input", () => {
        updateControlState();
        clearTimeout(_ivEmotionDebounce);
        _ivEmotionDebounce = setTimeout(() => _previewIvEmotion(_emotionTextarea.value), 600);
      });
    }
    // Listen for picker changes in the new iv-item-controls containers
    document.querySelectorAll(".iv-item-controls select, .iv-item-controls input").forEach((field) => {
      field.addEventListener("change", updateControlState);
      field.addEventListener("input", updateControlState);
    });
    $("revealAgent").addEventListener("change", () => {
      syncRevealCard();
      updateControlState();
    });

    // ── View switching ─────────────────────────────────────────────────
    function setView(name) {
      state.currentView = name;
      document.querySelectorAll(".view-tab").forEach(btn => {
        btn.classList.toggle("is-active", btn.dataset.view === name);
      });
      const ids = { live: "liveView", metrics: "metricsView", impact: "impactView" };
      Object.entries(ids).forEach(([key, id]) => {
        const el = $(id);
        if (el) el.classList.toggle("hidden", key !== name);
      });
      // Show/hide view hints
      const hintLive   = $("viewHintLive");
      const hintImpact = $("viewHintImpact");
      if (hintLive)   hintLive.classList.toggle("hidden",   name !== "live");
      if (hintImpact) hintImpact.classList.toggle("hidden", name !== "impact");
      if (name === "metrics") refreshMetricsView();
      if (name === "impact") renderImpactView();
      scrollViewToTop(name, ids);
      if (name === "live") {
        const latestGroup = eventLog && eventLog.querySelector(".step-group.is-latest");
        if (latestGroup) {
          requestAnimationFrame(() => {
            scrollLogToStepGroup(latestGroup, { smooth: false, highlight: false });
          });
        }
      }
    }

    function scrollViewToTop(name, idsMap = { live: "liveView", metrics: "metricsView", impact: "impactView" }) {
      const activeView = $(idsMap[name]);
      if (!activeView) return;
      requestAnimationFrame(() => {
        activeView.scrollTop = 0;
        activeView.querySelectorAll(".panel-scroll, .log-scroll, .col-body").forEach((node) => {
          node.scrollTop = 0;
        });
      });
    }

    // ── Metrics view ───────────────────────────────────────────────────
    function countConflictEventsFromHistory() {
      const history = Array.isArray(state.historySnapshots) ? state.historySnapshots : [];
      let count = 0;
      history.forEach((tick) => {
        const events = Array.isArray(tick?.events) ? tick.events : [];
        events.forEach((ev) => {
          const type = String(ev?.type || "").toLowerCase();
          if (type === "challenge" || type === "refuse" || type === "doubt") {
            count += 1;
          }
        });
      });
      return count;
    }

    function refreshMetricsView() {
      const h = state.metricsHistory;
      const last = h.length ? h[h.length - 1] : null;
      const conflictEvents = countConflictEventsFromHistory();

      const set = (id, val) => { const el = $(id); if (el) el.textContent = val; };
      set("mvFinalStress",  last ? toFixedSafe(last.stress,  2) : "—");
      set("mvFinalTrust",   last ? toFixedSafe(last.trust,   2) : "—");
      set("mvCohesion",     last ? toFixedSafe(last.cohesion,2) : "—");
      set("mvConflict",     String(conflictEvents));
      const completedTicks = Number(state.tick || (h.length ? h[h.length - 1].tick : 0) || 0);
      set("mvTicks",        completedTicks ? String(completedTicks) : "0");
      const ticksSub = $("mvTicksSub");
      if (ticksSub) {
        if (!completedTicks) {
          ticksSub.textContent = "No completed steps yet";
        } else if (state.ended) {
          ticksSub.textContent = `Completed in ${completedTicks} steps`;
        } else {
          ticksSub.textContent = `${completedTicks} completed · next = ${completedTicks + 1}`;
        }
      }
      const insight = $("mvChartInsight");
      if (insight) insight.textContent = metricsInsightText(h);
      const interpretation = $("mvRunInterpretation");
      if (interpretation) interpretation.textContent = metricsRunInterpretation(h, conflictEvents, completedTicks);

      renderMainChart();
    }

    function metricsInsightText(history) {
      if (!Array.isArray(history) || history.length < 2) {
        return "Insight will appear once the run has enough history.";
      }
      const first = history[0];
      const last = history[history.length - 1];
      const peakStressPoint = history.reduce((best, point) => (point.stress > best.stress ? point : best), history[0]);
      const stressWord = last.stress <= first.stress ? "remained controlled" : "rose overall";
      const cohesionWord = last.cohesion >= first.cohesion ? "steadily increased" : "shifted unevenly";
      return `Insight: Cohesion ${cohesionWord}, while stress ${stressWord}. Stress peaked at Step ${peakStressPoint.tick} before the run settled at ${toFixedSafe(last.stress)}.`;
    }

    function metricsRunInterpretation(history, conflictEvents, completedTicks) {
      if (!Array.isArray(history) || history.length < 2) {
        return "Run interpretation will appear once the simulation has enough step history.";
      }
      const first = history[0];
      const last = history[history.length - 1];
      const peakStressPoint = history.reduce((best, point) => (point.stress > best.stress ? point : best), history[0]);
      const env = String(state.environment || state.scenarioHint || "").toLowerCase();
      const team = teamLabel(state.teamHint || "");
      const runLabel = team && team !== "—"
        ? `${team} in ${environmentLabel(env)}`
        : environmentLabel(env);
      let completionText;
      if (state.ended) {
        if ((env === "escape" || env === "escape_room") && !currentBlocker()) {
          completionText = `completed the escape in ${completedTicks} steps`;
        } else if ((env === "cafe" || env === "cafe_restaurant") && !currentBlocker()) {
          completionText = `completed the cafe decision in ${completedTicks} steps`;
        } else if (env === "office" && !currentBlocker()) {
          completionText = `completed the proposal in ${completedTicks} steps`;
        } else {
          completionText = `ended after ${completedTicks} steps`;
        }
      } else {
        completionText = `has reached ${completedTicks} steps so far`;
      }
      const trustDirection = last.trust >= first.trust ? "rose" : "softened";
      const cohesionDirection = last.cohesion >= first.cohesion ? "improved" : "shifted unevenly";
      const conflictText = conflictEvents === 1
        ? "1 conflict event recorded"
        : `${conflictEvents} conflict events recorded`;
      return `${runLabel} ${completionText}. Cohesion ${cohesionDirection} from ${toFixedSafe(first.cohesion)} to ${toFixedSafe(last.cohesion)}, while trust ${trustDirection} from ${toFixedSafe(first.trust)} to ${toFixedSafe(last.trust)}. Stress peaked at Step ${peakStressPoint.tick} (${toFixedSafe(peakStressPoint.stress)}), with ${conflictText}.`;
    }

    function renderMainChart() {
      const canvas = $("chartMainLine");
      if (!canvas) return;
      const h = state.metricsHistory;

      const labels   = h.map(p => String(p.tick));
      const stress   = h.map(p => p.stress);
      const trust    = h.map(p => p.trust);
      const cohesion = h.map(p => p.cohesion);

      if (state.mainChart) {
        state.mainChart.data.labels        = labels;
        state.mainChart.data.datasets[0].data = stress;
        state.mainChart.data.datasets[1].data = trust;
        state.mainChart.data.datasets[2].data = cohesion;
        state.mainChart.update("none");
        return;
      }

      if (typeof Chart === "undefined") return;

      state.mainChart = new Chart(canvas, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Avg Stress",
              data: stress,
              borderColor: "#e05c5c",
              backgroundColor: "rgba(224,92,92,0.08)",
              tension: 0.35,
              pointRadius: 2,
              borderWidth: 2,
            },
            {
              label: "Avg Trust",
              data: trust,
              borderColor: "#4caf8a",
              backgroundColor: "rgba(76,175,138,0.08)",
              tension: 0.35,
              pointRadius: 2,
              borderWidth: 2,
            },
            {
              label: "Group Cohesion",
              data: cohesion,
              borderColor: "#5b9bd5",
              backgroundColor: "rgba(91,155,213,0.08)",
              tension: 0.35,
              pointRadius: 2,
              borderWidth: 2,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: {
              display: false,
            },
            tooltip: {
              backgroundColor: "#1b2740",
              borderColor: "#314562",
              borderWidth: 1,
              titleColor: "#8892aa",
              bodyColor: "#c8d0e0",
              cornerRadius: 10,
              padding: 10,
              callbacks: {
                label: ctx => ` ${ctx.dataset.label}: ${Number(ctx.parsed.y).toFixed(2)}`,
              },
            },
          },
          scales: {
            x: {
              title: { display: true, text: "Step", color: "#8892aa", font: { size: 11 } },
              ticks: { color: "#8892aa", maxTicksLimit: 12 },
              grid:  { color: "rgba(255,255,255,0.04)" },
            },
            y: {
              min: 0,
              max: 1,
              title: { display: true, text: "Value (0–1)", color: "#8892aa", font: { size: 11 } },
              ticks: { color: "#8892aa", stepSize: 0.2 },
              grid:  { color: "rgba(255,255,255,0.06)" },
            },
          },
        },
      });
    }

    // ── Impact view ────────────────────────────────────────────────────
    // Metrics where a higher value is better (green on increase)
    const _HIGHER_BETTER = new Set(["trust", "cohesion"]);

    function _ivDeltaClass(key, d) {
      if (Math.abs(d) <= 0.005) return "iv-delta-flat";
      const good = _HIGHER_BETTER.has(key) ? d > 0 : d < 0;
      return good ? "iv-delta-good" : "iv-delta-bad";
    }

    function _ivListStr(arr) {
      return arr.length > 1
        ? arr.slice(0, -1).map(m => m.label.toLowerCase()).join(", ") + " and " + arr[arr.length - 1].label.toLowerCase()
        : arr[0] ? arr[0].label.toLowerCase() : "";
    }

    function _ivSubject(iv) {
      if (!iv) return "This intervention";
      if (iv.type === "reveal_info" && iv.params?.item) {
        return `Revealing ${itemLabel(iv.params.item)}`;
      }
      if (iv.type === "force_meeting") {
        return `Forcing a meeting between ${iv.params?.agent_a_id || "two agents"} and ${iv.params?.agent_b_id || "the key partner"}`;
      }
      if (iv.type === "nudge_strategy" && iv.params?.agent_id) {
        return `Nudging ${iv.params.agent_id} toward cooperation`;
      }
      if (iv.type === "inject_tension") {
        return "Injecting tension";
      }
      if (iv.type === "boost_urgency") {
        return "Boosting pressure";
      }
      if (iv.type === "ease_pressure") {
        return "Easing pressure";
      }
      if (iv.type === "inject_emotion") {
        return "Injecting emotion";
      }
      return "This intervention";
    }

    function _ivSummary(iv, analysis) {
      const subject = _ivSubject(iv);

      // Build direction-aware phrases per metric so the prose reads naturally.
      // Lower-is-better metrics (stress, tension, pressure): "decreased" = good, "increased" = bad.
      // Higher-is-better metrics (trust, cohesion): "improved" = good, "declined" = bad.
      const _goodVerb  = key => _HIGHER_BETTER.has(key) ? "improved"  : "decreased";
      const _badVerb   = key => _HIGHER_BETTER.has(key) ? "declined"  : "increased";
      const _joinArr   = arr => arr.length > 1
        ? arr.slice(0, -1).join(", ") + " and " + arr[arr.length - 1]
        : arr[0] || "";

      const good      = analysis.filter(m => m.good);
      const bad       = analysis.filter(m => m.bad);
      const unchanged = analysis.filter(m => !m.good && !m.bad);

      const goodPhrases = good.map(m => `${m.label.toLowerCase()} ${_goodVerb(m.key)}`);
      const badPhrases  = bad.map(m => `${m.label.toLowerCase()} ${_badVerb(m.key)}`);
      const unchangedText = _ivListStr(unchanged);

      if (!good.length && !bad.length) {
        return "This intervention had limited measurable effect at this step.";
      }

      // Special case: inject_tension where the observed outcome shows tension going down
      // (or metrics improving) — the injection directly raised tension, but agent responses
      // or task completion in the same step produced a net positive. Flag the contradiction.
      if (iv?.type === "inject_tension") {
        const tensionEntry = analysis.find(m => m.key === "tension");
        const tensionObservedDown = tensionEntry && tensionEntry.good; // tension decreased = good
        if (tensionObservedDown || (good.length > 0 && bad.length === 0)) {
          const allPhrases = [...goodPhrases, ...badPhrases];
          if (tensionObservedDown) {
            return `Observed after this step: tension settled after progress, despite the tension injection.`;
          }
          return `Observed after this step: ${_joinArr(allPhrases.length ? allPhrases : goodPhrases)}, despite the tension injection.`;
        }
      }

      if (good.length > 0 && bad.length === 0) {
        if (unchanged.length) {
          return `Observed after this step: ${_joinArr(goodPhrases)}, while ${unchangedText} stayed unchanged.`;
        }
        return `Observed after this step: ${_joinArr(goodPhrases)}.`;
      }

      if (bad.length > 0 && good.length === 0) {
        if (unchanged.length) {
          return `${subject}: ${_joinArr(badPhrases)}, while ${unchangedText} stayed unchanged.`;
        }
        return `${subject}: ${_joinArr(badPhrases)}.`;
      }

      if (good.length > bad.length) {
        return `${subject}: ${_joinArr(goodPhrases)}, though ${_joinArr(badPhrases)}. Overall the team became more stable.`;
      }

      if (bad.length > good.length) {
        return `${subject}: ${_joinArr(badPhrases)}, even though ${_joinArr(goodPhrases)}. Overall the team became less stable.`;
      }

      return `${subject}: ${_joinArr(goodPhrases)}, but ${_joinArr(badPhrases)}. This intervention produced a mixed result.`;
    }

    function _ivBadge(improved, worsened, total) {
      const improvedCount = improved.length;
      const worsenedCount = worsened.length;
      const n = total || 4;

      if (!improvedCount && !worsenedCount) {
        return { cls: "is-neutral", text: "No Clear Impact" };
      }
      if (improvedCount > 0 && worsenedCount === 0) {
        if (improvedCount === 1) {
          return { cls: "is-positive", text: `Limited Positive Impact · 1/${n} metrics improved` };
        }
        return { cls: "is-positive", text: `Positive Impact · ${improvedCount}/${n} metrics improved` };
      }
      if (worsenedCount > 0 && improvedCount === 0) {
        if (worsenedCount === 1) {
          return { cls: "is-negative", text: `Limited Negative Impact · 1/${n} metrics worsened` };
        }
        return { cls: "is-negative", text: `Negative Impact · ${worsenedCount}/${n} metrics worsened` };
      }
      if (improvedCount > worsenedCount) {
        return { cls: "is-positive", text: `Positive Impact · ${improvedCount} improved, ${worsenedCount} worsened` };
      }
      if (worsenedCount > improvedCount) {
        return { cls: "is-negative", text: `Negative Impact · ${worsenedCount} worsened, ${improvedCount} improved` };
      }
      return { cls: "is-mixed", text: `Mixed Impact · ${improvedCount} improved, ${worsenedCount} worsened` };
    }

    function renderImpactView() {
      const empty = $("ivImpactEmpty");
      const list  = $("ivImpactList");
      const meta  = $("ivImpactMeta");
      if (!empty || !list) return;

      if (!state.interventionLog.length) {
        const ended = Boolean(state.ended);
        if (meta) meta.textContent = ended
          ? "No interventions were used in this run."
          : "No interventions applied yet.";
        empty.innerHTML = ended
          ? `<div class="iv-impact-empty-icon">⇄</div>
             <strong>No interventions were used in this run.</strong>
             <p>View the full step-by-step log in the <strong>Live Simulation</strong> tab.</p>`
          : `<div class="iv-impact-empty-icon">⇄</div>
             <strong>No intervention applied yet.</strong>
             <p>Apply an intervention in <strong>Live Simulation</strong> and advance one step to see the before/after impact here.</p>`;
        if (ended) {
          const btn = document.createElement("button");
          btn.className = "iv-link-btn";
          btn.textContent = "View Live Simulation Log";
          btn.addEventListener("click", () => setView("live"));
          empty.appendChild(btn);
        }
        empty.classList.remove("hidden");
        list.classList.add("hidden");
        list.innerHTML = "";
        return;
      }

      const latestIntervention = state.interventionLog[state.interventionLog.length - 1];
      if (meta) {
        const total = state.interventionLog.length;
        const noun = total === 1 ? "intervention" : "interventions";
        const _latestDisplayStep = state.tickToDisplayStep.get(
          latestIntervention.displayAtTick ?? latestIntervention.atTick
        ) ?? latestIntervention.displayAtTick ?? latestIntervention.atTick;
        meta.textContent = state.ended
          ? `${total} ${noun} used · Latest at Step ${_latestDisplayStep}`
          : `${total} ${noun} applied so far · Latest at Step ${_latestDisplayStep}`;
      }

      empty.classList.add("hidden");
      list.classList.remove("hidden");
      scrollViewToTop("impact");

      const BASE_METRICS = [
        { key: "stress",   label: "Stress"   },
        { key: "trust",    label: "Trust"    },
        { key: "tension",  label: "Tension"  },
        { key: "cohesion", label: "Cohesion" },
      ];

      list.innerHTML = state.interventionLog.map((iv, i) => {
        const b   = iv.before || {};
        const a   = iv.afterMetrics || {};
        const fix2 = v => Number(v).toFixed(2);
        const _env = state.environment || state.scenarioHint;

        // Pre-compute display pressure values so we can decide whether to show
        // the Pressure row before building the METRICS list.
        // iv.before.urgency = raw urgency_modifier before the intervention.
        // iv.postUrgency    = raw urgency_modifier immediately after.
        const _bRaw = Number(b.urgency ?? scenarioBaseUrgency(_env));
        const _aRaw = Number(iv.postUrgency ?? b.urgency ?? state.urgencyValue ?? scenarioBaseUrgency(_env));
        const _bPressure = displayPressureValue(_bRaw, _env);
        const _aPressure = displayPressureValue(_aRaw, _env);

        // Show Pressure row when:
        //   • the intervention type explicitly targets pressure (boost/ease), or
        //   • the displayed pressure value moved by ≥ 0.01 for any other reason
        //     (natural scenario drift captured in the before/after snapshots).
        const isPressureIv = iv.type === "boost_urgency" || iv.type === "ease_pressure";
        const showPressure = isPressureIv || Math.abs(_aPressure - _bPressure) >= 0.01;
        const METRICS = showPressure
          ? [{ key: "pressureDisplay", label: "Pressure" }, ...BASE_METRICS]
          : BASE_METRICS;

        const analysis = METRICS.map(({ key, label }) => {
          let bv, av;
          if (key === "pressureDisplay") {
            bv = _bPressure;
            av = _aPressure;
          } else {
            // Use null when the value is absent — never default to 0, because
            // 0 is indistinguishable from "genuinely zero" and creates fake
            // large deltas (e.g. Trust 0.00 → 0.59 when no before data exists).
            bv = b[key] != null ? Number(b[key]) : null;
            av = a[key] != null ? Number(a[key]) : null;
          }
          // If we have no before baseline, skip the delta computation entirely.
          // The row will render as "No baseline" rather than a misleading number.
          if (bv === null) {
            return { key, label, bv: null, av, d: null, cls: "iv-delta-flat",
                     good: false, bad: false, arrow: "—", noBaseline: true };
          }
          const d   = av != null ? av - bv : null;
          // Rounding guard: if before and after display identically at 2dp,
          // treat the change as flat — avoids "0.12 → 0.12 ▼ 0.01" contradiction.
          const visuallyFlat = av != null && Number(bv).toFixed(2) === Number(av).toFixed(2);
          const effectiveD   = visuallyFlat ? 0 : d;
          const cls = effectiveD != null ? _ivDeltaClass(key, effectiveD) : "iv-delta-flat";
          return {
            key, label, bv, av, d,
            effectiveD, visuallyFlat, cls,
            good: cls === "iv-delta-good",
            bad:  cls === "iv-delta-bad",
            arrow: effectiveD != null ? (effectiveD > 0.005 ? "▲" : effectiveD < -0.005 ? "▼" : "–") : "—",
          };
        });

        // Only count rows that have a real before baseline for badge/summary.
        const measurable = analysis.filter(m => !m.noBaseline);
        const improved = measurable.filter(m => m.good);
        const worsened = measurable.filter(m => m.bad);
        let badge   = _ivBadge(improved, worsened, measurable.length || METRICS.length);
        let summary = _ivSummary(iv, measurable);

        // inject_tension: the goal is disruption, not improvement — relabelling
        // "Positive Impact" (because e.g. stress or stall metrics improved after
        // the agent response) would confuse a marker reading the card.
        // Always use a disruption-specific label for this intervention type.
        if (iv.type === "inject_tension") {
          const tensionEntry = analysis.find(m => m.key === "tension");
          // "bad" on the tension entry means tension went up (lower-is-better direction)
          const tensionRose  = tensionEntry && tensionEntry.bad;
          if (tensionRose) {
            badge = { cls: "is-disruption", text: "Disruption recorded" };
          } else {
            // Tension didn't move (already high, or agent responses absorbed the spike)
            badge = { cls: "is-neutral", text: "Tension spike attempted — no shift recorded" };
          }
        }

        // reveal_info works through knowledge transfer, not immediate social metric
        // shifts. Always use a knowledge-specific label when knowledge was surfaced,
        // even if social metrics moved — labelling it "Negative Impact" because
        // tension ticked up after the next agent step would be misleading.
        if (iv.type === "reveal_info") {
          const cr = iv.confirmResult || {};
          // Build human-readable item/agent strings; fall back safely when params
          // are absent (runs saved before the params-persistence fix).
          const _riItem  = iv.params?.item || iv.params?.item_name || iv.params?.revealed_item || "";
          const _riAgent = iv.params?.agent_id || iv.params?.target_agent || "";
          const _riItemL  = _riItem  ? itemLabel(_riItem)    : "";
          const _riAgentL = _riAgent ? actorLabel(_riAgent)  : "An agent";
          const _riDetail = (_riItemL && _riAgentL !== "An agent")
            ? `${_riAgentL} surfaced ${_riItemL}.`
            : _riItemL
              ? `${_riItemL} was surfaced to the team.`
              : "Revealed information was surfaced to the team.";

          if (iv.confirmed || cr.confirmed) {
            badge = { cls: "is-positive", text: "Knowledge impact recorded" };
            // Only override the summary text when there is nothing social to describe;
            // if social metrics moved, _ivSummary already produced honest copy.
            if (!improved.length && !worsened.length) {
              summary = cr.consequence
                || `${_riDetail} Social metrics did not shift this step.`;
            }
          } else if (!improved.length && !worsened.length) {
            badge   = { cls: "is-neutral", text: "Information surfaced; social metrics unchanged" };
            summary = `${_riDetail} The knowledge carries forward into the next step.`;
          }
        }

        const rows = analysis.map(({ label, bv, av, d, effectiveD, visuallyFlat, cls, arrow, good, bad, noBaseline }) => {
          if (noBaseline) {
            return `<tr class="iv-no-baseline">
              <td>${label}</td>
              <td colspan="4" class="iv-no-baseline-note">No baseline — intervention applied before first step completed</td>
            </tr>`;
          }
          const verdict = good ? "Improved" : bad ? "Worsened" : "Unchanged";
          // When the change is visually flat (rounds to same 2dp), show "– 0.00"
          // rather than a non-zero arrow that contradicts the before/after columns.
          const changeHtml = effectiveD != null
            ? `${arrow} ${fix2(Math.abs(visuallyFlat ? 0 : d))}`
            : "—";
          return `<tr>
            <td>${label}</td>
            <td>${fix2(bv)}</td>
            <td>${av != null ? fix2(av) : "—"}</td>
            <td><span class="${cls}">${changeHtml}</span></td>
            <td class="iv-verdict ${cls}">${verdict}</td>
          </tr>`;
        }).join("");

        // Build the knowledge evidence panel for reveal_info cards.
        const knowledgeEvidence = (() => {
          if (iv.type !== "reveal_info") return "";
          const p     = iv.params || {};
          const rawItem  = p.item || p.item_name || p.revealed_item || p.target_item || "";
          const rawAgent = p.agent_id || p.target_agent || "";
          const item  = rawItem  ? itemLabel(rawItem)  : "";
          const agent = rawAgent || "";
          const cr    = iv.confirmResult || {};
          const ar    = iv.apiResult    || {};
          const wasBlocker = iv.before && iv.before.blocker === rawItem;

          // Old saved runs (pre-params-persistence) genuinely have no item/agent.
          // Show a safe, honest fallback rather than rendering "surfaced ." blanks.
          const hasDetail = Boolean(item || agent);

          const rows2 = [];
          if (hasDetail) {
            if (item)  rows2.push(`<div class="iv-ke-row"><span class="iv-ke-label">Item revealed</span><span class="iv-ke-value">${escapeHtml(item)}</span></div>`);
            if (agent) rows2.push(`<div class="iv-ke-row"><span class="iv-ke-label">Target agent</span><span class="iv-ke-value">${escapeHtml(actorLabel(agent))}</span></div>`);
          } else {
            rows2.push(`<div class="iv-ke-row"><span class="iv-ke-label iv-ke-muted">Detail</span><span class="iv-ke-value iv-ke-muted">Revealed information was surfaced to the team.</span></div>`);
          }
          if (wasBlocker) {
            rows2.push(`<div class="iv-ke-row"><span class="iv-ke-label">Context</span><span class="iv-ke-value">Active blocker — this item was blocking progress</span></div>`);
          }
          if (cr.consequence) {
            rows2.push(`<div class="iv-ke-row"><span class="iv-ke-label">Follow-through</span><span class="iv-ke-value">${escapeHtml(cr.consequence)}</span></div>`);
          } else if (cr.note && !iv.confirmed) {
            rows2.push(`<div class="iv-ke-row"><span class="iv-ke-label">Follow-through</span><span class="iv-ke-value iv-ke-muted">${escapeHtml(cr.note)}</span></div>`);
          } else if (!iv.confirmed) {
            rows2.push(`<div class="iv-ke-row"><span class="iv-ke-label">Follow-through</span><span class="iv-ke-value iv-ke-muted">Pending — check Live log for the next step</span></div>`);
          }
          if (ar.stress_delta != null && Math.abs(ar.stress_delta) > 0.001) {
            const sign = ar.stress_delta < 0 ? "−" : "+";
            const agentDisplay = agent ? actorLabel(agent) : "agent";
            rows2.push(`<div class="iv-ke-row"><span class="iv-ke-label">Stress on ${escapeHtml(agentDisplay)}</span><span class="iv-ke-value">${sign}${Math.abs(ar.stress_delta * 100).toFixed(0)}%</span></div>`);
          }
          return `<div class="iv-knowledge-evidence"><div class="iv-ke-head">Knowledge impact</div>${rows2.join("")}</div>`;
        })();

        const latestClass = i === state.interventionLog.length - 1 ? " is-latest" : "";
        return `
          <div class="iv-impact-card${latestClass}">
            <div class="iv-impact-head">
              <span class="iv-impact-step">#${i + 1}</span>
              <span class="iv-impact-title">${escapeHtml(iv.label || iv.type)}</span>
              <span class="iv-tick-tag">Step ${state.tickToDisplayStep.get(iv.displayAtTick ?? iv.atTick) ?? iv.displayAtTick ?? iv.atTick}</span>
              ${i === state.interventionLog.length - 1 ? '<span class="iv-impact-badge is-pending">Latest</span>' : ""}
              <span class="iv-impact-badge ${badge.cls}">${badge.text}</span>
            </div>
            ${knowledgeEvidence}
            <div class="iv-impact-body iv-two-col">
              <div class="iv-impact-summary">
                <p class="iv-summary-text">${escapeHtml(summary)}</p>
              </div>
              <div class="iv-table-wrap">
                <table class="iv-impact-table">
                  <thead><tr><th>Metric</th><th>Before</th><th>After</th><th>Change</th><th>Verdict</th></tr></thead>
                  <tbody>${rows}</tbody>
                </table>
              </div>
            </div>
          </div>`;
      }).join("");
    }

    // ── Tab wiring ─────────────────────────────────────────────────────
    document.querySelectorAll(".view-tab").forEach(btn => {
      btn.addEventListener("click", () => setView(btn.dataset.view));
    });

    // ── Interventions panel scroll hint ───────────────────────────────
    (function () {
      const scrollEl = $("ivPanelScroll");
      const hintEl   = $("ivScrollHint");
      if (!scrollEl || !hintEl) return;
      function sync() {
        const atBottom = scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight < 8;
        hintEl.classList.toggle("hidden", atBottom);
      }
      scrollEl.addEventListener("scroll", sync, { passive: true });
      // Re-check whenever content changes (new cards added, etc.)
      new ResizeObserver(sync).observe(scrollEl);
      sync();
    }());

    // ── Agents panel scroll hint ──────────────────────────────────────
    (function () {
      const scrollEl = agentList?.closest(".panel-scroll");
      const hintEl   = $("agentScrollHint");
      const panelEl  = agentList?.closest(".panel-agents");
      if (!scrollEl || !hintEl) return;
      function sync() {
        const canScroll = scrollEl.scrollHeight - scrollEl.clientHeight > 8;
        const atBottom = scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight < 8;
        hintEl.classList.toggle("hidden", !canScroll || atBottom);
        panelEl?.classList.toggle("show-scroll-cue", canScroll && !atBottom);
      }
      scrollEl.addEventListener("scroll", sync, { passive: true });
      new ResizeObserver(sync).observe(scrollEl);
      new ResizeObserver(sync).observe(agentList);
      sync();
    }());

    // ── Replay navigation (IS_REPLAY_MODE only) ────────────────────────

    // Move the sidebar panels (agents, metric strip, current focus) to reflect
    // the state at a specific history snapshot index.  The event log is NOT
    // re-rendered here — the full timeline is always visible; navigation just
    // updates the metric strip and agent panels, then scrolls the log to that tick.
    function replayGoTo(index) {
      const snaps = state.historySnapshots;
      if (!snaps || !snaps.length) return;
      const idx = Math.max(0, Math.min(index, snaps.length - 1));
      state.replayIndex = idx;
      const snap = snaps[idx];

      // Capture previous values so strip deltas render correctly
      const prevTension  = Number(state.groupState?.tension  || 0);
      const prevCohesion = Number(state.groupState?.cohesion || 0);
      const prevUrgency  = Number(state.urgencyValue);

      // ── REPLAY NAVIGATION RULE ────────────────────────────────────────────────
      // Only per-step visualisation state is updated here (agents, metric strip).
      // state.tick and state.tasks are intentionally NOT mutated: they hold the
      // saved final-run values and are the source of truth for the top summary
      // (Final Step, Status, Outcome badge, suggest text). Mutating them here was
      // the root cause of all four consistency bugs: the "Final Step" count
      // changing, "Escape Failed" contradicting "Run complete", and the failure
      // reason being recalculated from the selected replay step.
      // ─────────────────────────────────────────────────────────────────────────
      if (Array.isArray(snap.agents) && snap.agents.length) state.agents = snap.agents;
      if (snap.group_state) {
        state.groupState = snap.group_state;
        const p = readPressureValue({
          group_state: snap.group_state,
          scenario: snap.scenario,
          metrics: snap.metrics,
        });
        if (Number.isFinite(p)) { state.urgencyValue = p; state.urgencySeeded = true; }
        state.peakTension = Math.max(state.peakTension, snap.group_state.tension || 0);
      }
      // state.tasks is NOT updated from snap.scenario.tasks so that updateBlockerBadge()
      // and updateSuggestText() always reflect the saved final outcome, not the
      // in-progress state at the selected replay step.

      // Refresh per-snapshot panels only (metric strip values, agent portraits).
      // updateStepStrip() and updateBlockerBadge() read state.tick / state.tasks
      // which are the final-run values — so the summary stays stable.
      updateStepStrip();
      setTopStripMetric("Tension",  Number(state.groupState.tension  || 0), prevTension);
      setTopStripMetric("Cohesion", Number(state.groupState.cohesion || 0), prevCohesion);
      setTopStripMetric("Urgency",  Number(state.urgencyValue),              prevUrgency);
      updateBlockerBadge();
      renderAgents();
      refreshInterventionPickers();
      updateSuggestText();

      // Scroll the event log to the selected snapshot's tick (use snap.tick directly —
      // state.tick is now the final tick and must not drive the scroll in replay mode).
      const snapTick = snap.tick ?? idx;
      const stepGroup = eventLog.querySelector(
        `[data-step-tick="${snapTick}"], [data-tick="${snapTick}"]`
      );
      if (stepGroup) stepGroup.scrollIntoView({ behavior: "smooth", block: "start" });

      updateReplayNav();
    }

    function updateReplayNav() {
      const prevBtn  = $("replayPrevBtn");
      const nextBtn  = $("replayNextBtn");
      const stepLbl  = $("replayStepLabel");
      const snaps    = state.historySnapshots;
      if (!prevBtn || !nextBtn || !stepLbl) return;
      prevBtn.disabled = state.replayIndex <= 0;
      nextBtn.disabled = !snaps.length || state.replayIndex >= snaps.length - 1;
      if (!snaps.length) {
        stepLbl.textContent = "—";
        return;
      }
      // Show the snapshot's actual tick ("Viewing Step 3 of 11") rather than the
      // array index ("Step 3 of 11") so the label matches the event log entry the
      // user is looking at. state.tick is the saved final tick count.
      const snap = snaps[state.replayIndex];
      const viewTick  = snap?.tick ?? (state.replayIndex + 1);
      const finalTick = state.tick || snaps.length;
      stepLbl.textContent = `Viewing Step ${viewTick} of ${finalTick}`;
    }

    // Apply all read-only UI changes for replay mode.
    // Called once after applyStatusSnapshot() succeeds in bootReplay().
    function applyReplayUI() {
      // Mode pill
      setModePill("Live Interactive Replay", "ended");

      // Browser tab title
      document.title = "Live Interactive Replay — SimuVerse";

      // Header sub-label (shows "Live Interactive" by default)
      const modeLabel = $("modeLabel");
      if (modeLabel) modeLabel.textContent = "Live Interactive Replay";

      // Replace the "Run completed" note so it doesn't say "Start a new run"
      const ivCompleteNote = $("ivCompleteNote");
      if (ivCompleteNote) {
        ivCompleteNote.innerHTML =
          "<strong>Saved Interactive Run</strong>" +
          "<span>Read-only replay — no simulation is running.</span>" +
          "<a class=\"iv-complete-action\" href=\"history.html\">\u2190 Back to History</a>";
      }

      // Replace the step/reset buttons with replay nav controls in-place.
      // logHeadActions already has the correct flex layout — no new elements added.
      const logHeadActions = $("logHeadActions");
      if (logHeadActions && !$("replayPrevBtn")) {
        logHeadActions.innerHTML =
          "<button class=\"btn-reset\" id=\"replayPrevBtn\" disabled>\u2190 Prev</button>" +
          "<span id=\"replayStepLabel\" style=\"font-size:0.82rem;font-weight:600;" +
            "color:#1663f5;padding:0 4px;white-space:nowrap;\">\u2014</span>" +
          "<button class=\"btn-step\" id=\"replayNextBtn\" disabled>" +
            "<span class=\"btn-step-label\">Next</span>" +
            "<span class=\"btn-step-arrow\">\u203a</span>" +
          "</button>" +
          "<button class=\"btn-reset\" id=\"replayExportPdfBtn\" " +
            "title=\"Export this run as a PDF report\" " +
            "style=\"margin-left:8px;\">Export PDF</button>";
        $("replayPrevBtn").addEventListener("click", () => replayGoTo(state.replayIndex - 1));
        $("replayNextBtn").addEventListener("click", () => replayGoTo(state.replayIndex + 1));
        $("replayExportPdfBtn").addEventListener("click", exportInteractionPdf);
      }

      // Initialise nav button state
      updateReplayNav();
    }

    // ── PDF export ─────────────────────────────────────────────────────────────

    /**
     * Return a human-readable scenario label from the environment key.
     * Mirrors the labels in SCENARIOS in setup.js.
     */
    function _ivScenarioLabel(envKey) {
      const key = String(envKey || "").toLowerCase();
      const map = {
        office:          "Office Project",
        cafe:            "Cafe Planning",
        cafe_restaurant: "Cafe Planning",
        escape:          "Escape Room",
        escape_room:     "Escape Room",
      };
      return map[key] || environmentLabel(envKey) || "Simulation";
    }

    /**
     * Derive a human-readable outcome from the current state.
     */
    function _ivOutcomeLabel() {
      if (!state.ended) return "In progress";
      const env = String(state.environment || state.scenarioHint || "").toLowerCase();
      const tasks = state.tasks || {};
      const vals = Object.values(tasks);
      const allDone = vals.length > 0 && vals.every(Boolean);
      if (allDone) {
        if (env === "office")                        return "Proposal Accepted";
        if (env === "cafe" || env === "cafe_restaurant") return "Decision Reached";
        if (env === "escape" || env === "escape_room")   return "Escaped";
        return "Completed";
      }
      if (vals.some(Boolean)) return "Partial Completion";
      return "Incomplete";
    }

    /**
     * Convert state.tasks (dict) into [{label, done}] array using SCENARIO_CONFIG labels.
     */
    function _ivTasksArray() {
      const tasks  = state.tasks || {};
      const env    = String(state.environment || state.scenarioHint || "").toLowerCase();
      const cfg    = SCENARIO_CONFIG[env] || {};
      const order  = Array.isArray(cfg.order) ? cfg.order : Object.keys(tasks);
      const lblMap = cfg.labels || {};
      return order.map((key) => ({
        label: lblMap[key] || formatRoleLabel(key),
        done:  Boolean(tasks[key]),
      }));
    }

    /**
     * Build the structured payload consumed by window.SimuVersePDF.generate().
     * Reads only from `state.*` — always populated after boot(), refresh-safe.
     * Null-safe: every field has a fallback.
     */
    function buildInteractionPdfPayload() {
      const envKey     = state.environment || state.scenarioHint || "office";
      const teamKey    = state.teamHint || state.config?.team_type || "";
      const totalSteps = Number(state.tick || 0);

      /* ── Agents ── */
      const agents = (Array.isArray(state.agents) ? state.agents : []).map((a) => {
        const known = Array.isArray(a.known_items) && a.known_items.length
          ? String(a.known_items[0]).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
          : "—";
        return {
          id:          a.public_id || a.id || "",
          name:        a.public_id || a.id || "Agent", // always the ID (A1–A4), never a human name
          role:        a.role || "Agent",
          personality: a.personality || a.strategy || "",
          holds:       known,
          finalStress: typeof a.stress === "number" ? a.stress : null,
        };
      });

      /* ── Tasks ── */
      const tasks = _ivTasksArray();

      /* ── Build agent ID lookup — always resolves to the public_id (A1–A4), never a human name ── */
      const _agentNameMap = new Map();
      (Array.isArray(state.agents) ? state.agents : []).forEach((a) => {
        const id = a.public_id || a.id || "";
        if (id) _agentNameMap.set(id, id); // display the ID itself, not any name field
      });
      const _agentName = (id) => _agentNameMap.get(String(id || "")) || String(id || "");

      /* ── Map internal event type codes → human-readable labels ── */
      const _evLabel = (type) => {
        const map = {
          ask_info:       "Request Information",
          share_info:     "Share Information",
          trust_shift:    "Trust Change",
          conflict:       "Agent Conflict",
          complete_task:  "Task Completed",
          task_resolved:  "Task Resolved",
          force_meeting:  "Forced Meeting",
          reveal_info:    "Information Revealed",
          inject_tension: "Inject Tension",
          boost_urgency:  "Boost Urgency",
          ease_pressure:  "Ease Pressure",
          nudge_strategy: "Nudge Cooperation",
          inject_emotion: "Inject Mood",
          block:          "Blocked",
          deadlock:       "Deadlock",
          finalise:       "Task Finalised",
          unlock:         "Final Unlock",
          complete:       "Task Completed",
          task_complete:  "Task Completed",
          evidence_share: "Evidence Shared",
          query:          "Information Query",
          response:       "Information Response",
        };
        const raw = String(type || "").toLowerCase().replace(/-/g, "_");
        return map[raw] || String(type || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Interaction";
      };

      /* ── Build progress-by-tick from historySnapshots task state ── */
      const snaps = Array.isArray(state.historySnapshots) ? state.historySnapshots : [];
      const _progressByTick = new Map();
      snaps.forEach((s) => {
        const snapTasks = s.scenario?.tasks || {};
        const vals = Object.values(snapTasks);
        const prog = vals.length ? vals.filter(Boolean).length / vals.length : 0;
        _progressByTick.set(Number(s.tick || 0), prog);
      });

      /* ── Metrics history with real per-tick progress values ── */
      const metricsHistory = (Array.isArray(state.metricsHistory) ? state.metricsHistory : []).map((m) => ({
        tick:     Number(m.tick     || 0),
        progress: _progressByTick.get(Number(m.tick || 0)) ?? 0,
        trust:    Number(m.trust    || 0),
        stress:   Number(m.stress   || 0),
        conflict: Number(m.conflict || 0),
        cohesion: Number(m.cohesion || 0),
      }));

      /* ── Timeline from historySnapshots — human-readable entries ── */
      const timeline = snaps
        .filter((s) => Number(s.tick || 0) > 0)
        .map((s) => {
          const evs = Array.isArray(s.events) ? s.events : [];

          // Pick the most informative event for the title (prefer non-metric events)
          const mainEv = evs.find((ev) => {
            const t = String(ev.type || "").toLowerCase();
            return !t.startsWith("trust") && !t.startsWith("group") && !t.startsWith("metric");
          }) || evs[0] || {};

          // Resolve agent IDs to names
          const actorId  = mainEv.actor_id  || mainEv.actorId  || mainEv.source_id || "";
          const targetId = mainEv.target_id || mainEv.targetId || "";
          const actorName  = _agentName(actorId);
          const targetName = _agentName(targetId);

          // Human-readable title — prefer intervention events
          const ivEv = evs.find((ev) => {
            const t = String(ev.type || "").toLowerCase();
            return t.includes("inject") || t.includes("reveal") || t.includes("force") ||
                   t.includes("nudge") || t.includes("boost") || t.includes("ease");
          });
          const title = ivEv ? _evLabel(ivEv.type) : _evLabel(mainEv.type);

          // Build a readable summary from saved messages
          const messages = evs.map((ev) => ev.message || ev.summary || "").filter(Boolean);
          const summary = messages.length
            ? messages[0]
            : (evs.length
                ? `${title}${actorName ? " by " + actorName : ""}${targetName ? " involving " + targetName : ""}.`
                : "");

          // Per-event action detail lines (e.g. "Share Information: A1 → A2")
          const actionDetails = evs
            .map((ev) => {
              const lbl  = _evLabel(ev.type);
              const from = _agentName(ev.actor_id || ev.actorId || "");
              const to   = _agentName(ev.target_id || ev.targetId || "");
              const item = ev.item ? ` [${String(ev.item).replace(/_/g, " ")}]` : "";
              if (from && to) return `${lbl}: ${from} \u2192 ${to}${item}`;
              if (from)       return `${lbl}: ${from}${item}`;
              return item ? `${lbl}${item}` : "";
            })
            .filter(Boolean);

          return {
            tick:          Number(s.tick || 0),
            title,
            eventType:     mainEv.type || "",
            actorName,
            targetName,
            summary,
            message:       mainEv.message || messages[0] || "",
            actionDetails,
            effects:       [],
            whyTrigger:    "",
            whyReasoning:  "",
            whyImpact:     "",
            hasEvent:      evs.length > 0,
          };
        });

      /* ── Interventions from interventionLog ── */
      const interventions = (Array.isArray(state.interventionLog) ? state.interventionLog : [])
        .filter((iv) => iv.confirmed !== false)
        .map((iv) => {
          const stressChange = (iv.afterMetrics?.stress != null && iv.before?.stress != null)
            ? +(Number(iv.afterMetrics.stress) - Number(iv.before.stress)).toFixed(3)
            : null;
          const trustChange = (iv.afterMetrics?.trust != null && iv.before?.trust != null)
            ? +(Number(iv.afterMetrics.trust) - Number(iv.before.trust)).toFixed(3)
            : null;
          let verdict = "";
          if (stressChange != null || trustChange != null) {
            const positive = (stressChange != null && stressChange < -0.02)
                           || (trustChange  != null && trustChange  >  0.02);
            const negative = (stressChange != null && stressChange >  0.02)
                           || (trustChange  != null && trustChange  < -0.02);
            verdict = positive ? "Effective" : negative ? "Backfired" : "Neutral";
          }
          return {
            tick:           Number(iv.atTick || 0),
            label:          iv.label || iv.type || "Intervention",
            type:           iv.type  || "",
            stressChange,
            trustChange,
            conflictChange: null,
            verdict,
          };
        });

      /* ── Final metrics (last metricsHistory entry) ── */
      const lastM = metricsHistory.length ? metricsHistory[metricsHistory.length - 1] : {};
      const doneTasks = tasks.filter((t) => t.done).length;
      const progressFraction = tasks.length ? doneTasks / tasks.length : 0;

      /* ── Outcome summary ── */
      const scenarioLabel  = _ivScenarioLabel(envKey);
      const tLabel         = teamLabel(teamKey);
      const ivCount        = interventions.length;
      const outcomeSummary =
        `The ${scenarioLabel} scenario ran for ${totalSteps} step${totalSteps !== 1 ? "s" : ""} ` +
        `using the ${tLabel || "selected"} team preset. ` +
        (tasks.length
          ? `${doneTasks} of ${tasks.length} task${tasks.length !== 1 ? "s" : ""} were completed. `
          : "") +
        (lastM.trust != null
          ? `Final trust was ${Number(lastM.trust).toFixed(2)} and stress was ${Number(lastM.stress || 0).toFixed(2)}. `
          : "") +
        (ivCount
          ? `${ivCount} user intervention${ivCount !== 1 ? "s" : ""} were applied during the run.`
          : "No user interventions were applied — this was a fully autonomous run.");

      return {
        runId:        state.runId || "unknown-run",
        seed:         state.config?.seed ?? "Not recorded",
        exportedAt:   new Date().toLocaleString("en-GB", {
                        day: "2-digit", month: "short", year: "numeric",
                        hour: "2-digit", minute: "2-digit",
                      }),
        scenario:     { id: envKey, label: scenarioLabel, title: scenarioLabel },
        team:         { key: teamKey, label: tLabel || "Unknown team" },
        mode:         IS_REPLAY_MODE ? "Live Interactive Replay" : "Live Interaction",
        outcome:      _ivOutcomeLabel(),
        totalSteps,
        agents,
        tasks,
        finalMetrics: {
          progress: progressFraction,
          trust:    Number(lastM.trust    || 0),
          stress:   Number(lastM.stress   || 0),
          conflict: Number(lastM.conflict || 0),
          cohesion: Number(lastM.cohesion || 0),
        },
        metricsHistory,
        timeline,
        interventions,
        outcomeSummary,
      };
    }

    /**
     * Export the current interaction run as a PDF.
     * Works in live mode (after run ends) and replay mode.
     * Prefers the structured SimuVersePDF generator; only falls back if it is unavailable.
     */
    function exportInteractionPdf() {
      try {
        const payload = buildInteractionPdfPayload();

        if (window.SimuVersePDF) {
          const result = window.SimuVersePDF.generate(payload);
          if (result && !result.ok) console.warn("[IV-PDF] Legacy export non-ok:", result);
          return;
        }

        if (window.SimuVerseReport) {
          window.SimuVerseReport.generate(payload);
          return;
        }

        alert("PDF export is unavailable. The structured PDF generator did not load on this page.");
      } catch (err) {
        console.error("[IV-PDF] Export error:", err);
        alert("PDF export encountered an error. Check the browser console for details.");
      }
    }

    // Rebuild state.interventionLog from the saved per-tick history so that the
    // Intervention Impact tab is populated on every page load, including refresh.
    // Each entry is reconstructed from adjacent tick snapshots:
    //   before     = previous tick's metrics/group_state (what the team looked like
    //                one step before the intervention landed)
    //   afterMetrics = the tick that contains the intervention (what changed)
    // This is purely additive to state — nothing in the saved run is mutated.
    function reconstructInterventionLogFromHistory(history) {
      if (!Array.isArray(history) || !history.length) return;
      // Already populated (e.g. called twice) — skip
      if (state.interventionLog.length) return;

      // Human-readable labels for each type, without requiring live params
      const _label = (type) => {
        const map = {
          force_meeting:  "Force Meeting",
          reveal_info:    "Reveal Info",
          nudge_strategy: "Nudge Strategy",
          boost_urgency:  "Boost Pressure",
          ease_pressure:  "Ease Pressure",
          inject_tension: "Inject Tension",
          inject_emotion: "Emotion Input",
        };
        return map[String(type || "")] ||
          String(type || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
      };

      for (let i = 0; i < history.length; i++) {
        const snap    = history[i];
        const ivList  = Array.isArray(snap.interventions) ? snap.interventions : [];
        if (!ivList.length) continue;

        // "before" = the previous tick; fall back to first tick if this is tick 0
        const prevSnap   = i > 0 ? history[i - 1] : snap;
        const prevM      = prevSnap.metrics     || {};
        const prevGs     = prevSnap.group_state || {};
        const currM      = snap.metrics         || {};
        const currGs     = snap.group_state     || {};

        for (const iv of ivList) {
          // iv.params is present for runs saved after the params-persistence fix.
          // Old saved runs have no params — treat as empty and show safe fallback.
          const ivParams = (iv.params && typeof iv.params === "object") ? iv.params : {};

          // For reveal_info: synthesise a confirmResult so the badge/summary logic
          // fires correctly without a live applyConfirmationUpdate call.
          const confirmResult = (iv.type === "reveal_info")
            ? { confirmed: true, note: null, consequence: null }
            : undefined;

          state.interventionLog.push({
            type:   iv.type || "",
            params: ivParams,
            label:  _label(iv.type),
            before: {
              urgency:  Number(prevGs.pressure ?? currGs.pressure ?? 0),
              stress:   Number(prevM.avg_stress  ?? 0),
              trust:    Number(prevM.avg_trust   ?? 0),
              tension:  Number(prevGs.tension    ?? 0),
              cohesion: Number(prevGs.cohesion   ?? 0),
            },
            afterMetrics: {
              stress:   Number(currM.avg_stress  ?? 0),
              trust:    Number(currM.avg_trust   ?? 0),
              tension:  Number(currGs.tension    ?? 0),
              cohesion: Number(currGs.cohesion   ?? 0),
            },
            atTick:        Number(snap.tick ?? 0),
            displayAtTick: Number(snap.tick ?? 0),
            postUrgency:   Number(currGs.pressure ?? prevGs.pressure ?? 0),
            confirmed:     true,
            confirmResult,
          });
        }
      }
    }

    // Boot path for IS_REPLAY_MODE: loads from history endpoints, never touches
    // the live /runs/ endpoint and never opens a WebSocket.
    async function bootReplay() {
      if (!state.runId) {
        fallbackMissing.classList.remove("hidden");
        setModePill("Idle", "error");
        return;
      }

      try {
        const [summary, replayPayload] = await Promise.all([
          fetch(`${API_BASE}/history/runs/${encodeURIComponent(state.runId)}`)
            .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
          fetch(`${API_BASE}/history/runs/${encodeURIComponent(state.runId)}/replay`)
            .then((r) => r.ok ? r.json() : { history: [] })
            .catch(() => ({ history: [] })),
        ]);

        const history = Array.isArray(replayPayload?.history) ? replayPayload.history
                      : (Array.isArray(summary?.history) ? summary.history : []);
        const lastSnap = history.length ? history[history.length - 1] : {};

        // Build a status shape that applyStatusSnapshot() understands.
        // This is purely local — no backend state is mutated.
        const adaptedStatus = {
          run_id:      summary.run_id || state.runId,
          status:      "stopped",
          tick:        summary.ticks || lastSnap.tick || history.length || 0,
          config:      summary.config || {},
          ended:       true,
          agents:      (Array.isArray(lastSnap.agents) && lastSnap.agents.length)
                         ? lastSnap.agents
                         : (Array.isArray(summary.agents) ? summary.agents : []),
          ties:        lastSnap.ties        || [],
          events:      lastSnap.events      || [],
          metrics:     lastSnap.metrics     || summary.metrics     || {},
          group_state: lastSnap.group_state || summary.group_state || {},
          scenario: {
            environment:   summary.config?.environment
                           || lastSnap.scenario?.environment
                           || summary.scenario_id || "",
            tasks:         lastSnap.scenario?.tasks || summary.tasks || {},
            knowledge_map: lastSnap.scenario?.knowledge_map || {},
            progress:      typeof lastSnap.scenario?.progress === "number"
                             ? lastSnap.scenario.progress
                             : Number(summary.final_progress || 1),
            outcome:       summary.outcome || "",
          },
          history,
          team_type: summary.team_preset || summary.config?.team_type || "",
        };

        liveSession.classList.remove("hidden");
        applyStatusSnapshot(adaptedStatus);

        // Rebuild interventionLog from saved tick history so the Intervention
        // Impact tab shows correctly on any load — including browser refresh.
        // applyStatusSnapshot() never populates interventionLog (that is only
        // done by the live applyIntervention → applyConfirmationUpdate path),
        // so we reconstruct it here from before/after metrics in adjacent ticks.
        reconstructInterventionLogFromHistory(history);

        // If the run had no interventions and the current view is the Impact
        // tab (e.g. persisted from a previous session), switch to Live Simulation
        // so the page doesn't open on a blank empty-state.
        if (state.currentView === "impact" && !state.interventionLog.length) {
          setView("live");
        }

        // Point navigation to the last snapshot (most recent step shown by default)
        state.replayIndex = Math.max(0, history.length - 1);

        applyReplayUI();
        syncDashboardLinks();

      } catch (err) {
        fallbackStale.classList.remove("hidden");
        $("staleRunId").textContent = state.runId;
        syncDashboardLinks();
        setModePill("Not found", "error");
        console.error("[replay] Could not load saved run:", err);
      }
    }

    // ── Boot ───────────────────────────────────────────────────────────
    async function boot() {
      // Replay mode: load from history endpoints, never start a new simulation.
      if (IS_REPLAY_MODE) {
        await bootReplay();
        return;
      }

      if (!state.runId) {
        fallbackMissing.classList.remove("hidden");
        setModePill("Idle", "error");
        return;
      }

      try {
        const status = await fetchRunStatus(state.runId);
        liveSession.classList.remove("hidden");
        applyStatusSnapshot(status);

        // Restore Intervention Impact tab from the tick history included in the
        // GET /runs/{id} response.  This must run for BOTH ended and in-progress
        // runs — on a refresh the frontend starts with an empty interventionLog
        // regardless of run state, because the live WS only populates it in
        // real-time during the original session.
        // The guard inside reconstructInterventionLogFromHistory (length > 0) prevents
        // double-population if the WS later re-delivers ticks for the same run.
        reconstructInterventionLogFromHistory(status.history || []);

        if (state.ended) {
          if (state.currentView === "impact" && !state.interventionLog.length) {
            setView("live");
          }
          syncDashboardLinks();
          return;
        }
        try {
          await openWebSocket(state.runId);
          syncDashboardLinks();
          if (state.autoRunning && !state.ended) {
            enforceManualMode();
          }
        } catch (e) {
          showBanner("WebSocket could not open, so this live run cannot be controlled right now.", "error");
        }
      } catch (err) {
        fallbackStale.classList.remove("hidden");
        $("staleRunId").textContent = state.runId;
        syncDashboardLinks();
        setModePill("Not live", "error");
      }
    }

    boot();
