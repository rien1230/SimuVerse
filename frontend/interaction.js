// Live run page logic: websocket updates, interventions, and on-screen state.
 const API_BASE = window.SimuVerseAPI.API_BASE;
    const WS_BASE = window.SimuVerseAPI.WS_BASE;
    const PARAMS = new URLSearchParams(window.location.search);

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
      // urgencyValue tracks env.urgency_modifier (not in group_state).
      // Seeded at 1.0 (backend default); updated from intervention POST replies.
      urgencyValue: 1.0,
      lastIntervention: null,       // {type, params, label, before, atTick, postUrgency}
      interventionLog: [],          // completed interventions with before + afterMetrics

      // ── Metrics & Analysis ────────────────────────────────────────────
      metricsHistory: [],           // [{tick, stress, trust, cohesion, conflict}] per step
      peakTension: 0,               // running max of group_state.tension across all ticks

      // ── UI view state ─────────────────────────────────────────────────
      currentView: "live",          // "live" | "metrics" | "impact"
      mainChart: null,              // Chart.js instance for Metrics & Analysis view
    };

    // ── DOM refs ───────────────────────────────────────────────────────
    const $ = (id) => document.getElementById(id);
    const banner = $("banner");
    const fallbackMissing = $("fallbackMissing");
    const fallbackStale = $("fallbackStale");
    const liveSession = $("liveSession");
    const agentList = $("agentList");
    const eventLog = $("eventLog");
    const btnStep = $("btnStep");
    const btnReset = $("btnReset");
    const ivButtons = {
      boost_urgency: document.querySelector('[data-iv="boost_urgency"]'),
      reveal_info: document.querySelector('[data-iv="reveal_info"]'),
      force_meeting: document.querySelector('[data-iv="force_meeting"]'),
      nudge_strategy: document.querySelector('[data-iv="nudge_strategy"]'),
      inject_tension: document.querySelector('[data-iv="inject_tension"]'),
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
        _bannerTimer = setTimeout(hideBanner, 6000);
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

    function showEndModal() {
      const modal = $("endRunModal");
      if (!modal) return;
      const title = $("endRunTitle");
      const text = $("endRunText");
      const dashboardLink = $("endRunDashboardLink");
      if (title) title.textContent = "This run has ended.";
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

      if (state.ended) {
        const env = String(state.environment || state.scenarioHint || "").toLowerCase();
        const outcomeWord = env === "office" ? "Proposal Accepted"
                          : env === "cafe"   ? "Decision Reached"
                          : "Escaped";
        if (label) label.textContent = "Outcome";
        badge.className = "sc-blocker is-clear";
        textEl.textContent = outcomeWord;
        if (sub) { sub.textContent = "Completed"; sub.style.color = "var(--teal)"; }
        return;
      }

      const blocker = currentBlocker();
      if (label) label.textContent = "Blocked By";
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
      const blocker = currentBlocker();
      if (!blocker) {
        el.textContent = "No active blocker — watch for the final resolution";
        el.style.color = "var(--teal)";
        return;
      }
      el.style.color = "";
      const anyMissing = state.agents.some(
        a => Array.isArray(a.known_items) && !a.known_items.includes(blocker)
      );
      el.textContent = anyMissing
        ? `Blocker: ${itemLabel(blocker)} — Recommended: Reveal Info`
        : `Blocker: ${itemLabel(blocker)} — Recommended: Force Meeting`;
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
        summary: "Summary", finalise: "Finalise",
        compliment: "Praise", clue: "Clue",
        coord: "Coordinate", enter: "Enter",
        open: "Open", doubt: "Doubt",
        reassure: "Reassure", insult: "Clash",
        ignore: "Ignore", pressure: "Pressure",
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

    function itemLabel(item) {
      const raw = String(item || "");
      const labels = {
        map: "Room Map",
        pattern: "Lock Pattern",
        lock_pattern: "Lock Pattern",
        lock_combination: "Lock Pattern",
        combination: "Lock Pattern",
        key: "Key Location",
        key_location: "Key Location",
        code: "Door Code",
        door_code: "Door Code",
        door: "Door Code",
        unlock: "Exit Lock",
        lock: "Lock Pattern",
        requirements: "Requirements",
        design: "Design Plans",
        budget: "Budget",
        tech_specs: "Spec Doc",
        dietary_constraint: "Dietary Constraint",
        budget_constraint: "Budget",
        location_constraint: "Location"
      };
      if (labels[raw]) return labels[raw];
      return raw
        .replace(/_/g, " ")
        .replace(/\b\w/g, (char) => char.toUpperCase());
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
      return `${agent.public_id || agent.id} — ${agentRoleLabel(agent)}`;
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
        user_inject_tension: "Response to your tension injection",
        user_reveal_info:    "Follow-through on your reveal",
      };
      return labels[reason] || "User-triggered";
    }

    // Keep the intervention copy a bit cleaner than the raw backend strings so
    // the timeline reads like a person wrote it, not like a debug log.
    // ── Intervention message formatting ────────────────────────────────
    function formatInterventionMessage(type, params, rawMessage) {
      const message = String(rawMessage || "").trim();
      const blocker = currentBlocker();
      const blockerText = blocker ? itemLabel(blocker) : null;

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
            return blockerText
              ? `Reinforced ${agentId}'s ${newStrategy} approach on ${blockerText}.`
              : `Reinforced ${agentId}'s ${newStrategy} approach.`;
          }
          return blockerText
            ? `Asked ${agentId} to take a more ${newStrategy} line on ${blockerText}.`
            : `Asked ${agentId} to take a more ${newStrategy} line.`;
        }
        return blockerText
          ? `Nudged ${params.agent_id} toward cooperation on ${blockerText}.`
          : `Nudged ${params.agent_id} toward cooperation.`;
      }

      if (type === "inject_tension") {
        const match = message.match(/^Group tension raised by ([0-9.]+)\./);
        if (match) {
          return blockerText
            ? `Group tension increased by +${toFixedSafe(match[1])} around ${blockerText}.`
            : `Group tension increased by +${toFixedSafe(match[1])}.`;
        }
        const amount = Number(params && params.amount);
        if (Number.isFinite(amount) && amount > 0) {
          return blockerText
            ? `Group tension increased by +${toFixedSafe(amount)} around ${blockerText}.`
            : `Group tension increased by +${toFixedSafe(amount)}.`;
        }
        return "Group tension increased for the next step.";
      }

      if (type === "boost_urgency") {
        const match = message.match(/^Urgency boosted by ([0-9.]+)\./);
        if (match) {
          return blockerText
            ? `Urgency increased by +${toFixedSafe(match[1])} on ${blockerText}.`
            : `Urgency increased by +${toFixedSafe(match[1])}.`;
        }
        const amount = Number(params && params.amount);
        if (Number.isFinite(amount) && amount > 0) {
          return blockerText
            ? `Urgency increased by +${toFixedSafe(amount)} on ${blockerText}.`
            : `Urgency increased by +${toFixedSafe(amount)}.`;
        }
        return "Urgency increased for the next step.";
      }

      return message || "Intervention applied.";
    }

    function buildLocalInterventionEvent(type, params, rawMessage) {
      // Add a local event immediately so the UI responds before the websocket
      // round-trip comes back with the backend-confirmed version.
      let target;
      if (type === "force_meeting" && params.agent_a_id && params.agent_b_id) {
        target = `${params.agent_a_id} & ${params.agent_b_id}`;
      } else {
        target = params.agent_id || params.agent_a_id || params.agent_b_id || "GROUP";
      }
      return {
        tick: Number(state.tick || 0) + 1,
        type: "intervention",
        actor: "USER",
        target,
        text: rawMessage,
        displayText: formatInterventionMessage(type, params, rawMessage),
        reason: type,
        params: { ...params },
      };
    }

    function massageEventText(ev) {
      if (ev.displayText) return ev.displayText;

      if (String(ev.actor || "").toUpperCase() === "USER" && ev.type === "intervention") {
        return formatInterventionMessage(ev.reason, ev.params || {}, ev.text);
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
          "We need movement this tick.",
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

      return text;
    }

    function displayPriority(ev) {
      if (String(ev.actor || "").toUpperCase() === "USER" || ev.type === "intervention") return 0;
      if (String(ev.reason || "").startsWith("user_")) return 1;
      return 2;
    }

    // ── Controls enable/disable ────────────────────────────────────────
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

      if (ivButtons.boost_urgency) ivButtons.boost_urgency.disabled = !canUse;
      if (ivButtons.inject_tension) ivButtons.inject_tension.disabled = !canUse;
      if (ivButtons.reveal_info) ivButtons.reveal_info.disabled = !(revealValid && revealOptions.length > 0);
      if (ivButtons.force_meeting) ivButtons.force_meeting.disabled = !forceValid;
      if (ivButtons.nudge_strategy) {
        ivButtons.nudge_strategy.disabled = !(canUse && nudgeAgentId);
        ivButtons.nudge_strategy.textContent = alreadyCooperative ? "✓ Reinforce" : "✓ Nudge";
      }
    }

    function setRunControlsEnabled(attached, ended) {
      const canAdvance = attached && state.wsReady && !ended && !state.actionPending && !state.autoRunning;
      btnStep.disabled = !canAdvance;
      btnReset.disabled = state.actionPending || !state.config;
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
    }

    function eventKey(ev) {
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
          : "No fixed item";

        const stress  = a.stress != null ? Number(a.stress).toFixed(2) : "—";
        const valenceNum = (a.mood?.valence != null) ? Number(a.mood.valence) : (a.valence != null ? Number(a.valence) : NaN);
        const valence = Number.isFinite(valenceNum) ? valenceNum.toFixed(2) : "—";
        const thought = cleanThought(a.last_thought || "");
        const stressWidth = `${Math.round(clamp01(a.stress) * 100)}%`;
        const valenceWidth = `${Math.round(clamp01((valenceNum + 1) / 2) * 100)}%`;
        const mood = moodLabel(valenceNum);
        const valenceClass = moodBarClass(valenceNum);

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
          ? rawEmotion.charAt(0).toUpperCase() + rawEmotion.slice(1)
          : null;

        card.className = "agent-card";
        card.style.borderLeftColor = color.bg;
        card.innerHTML = `
          <div class="agent-top">
            <div class="agent-avatar" style="background: ${color.labelBg}; color: ${color.label};">${escapeHtml(initials)}</div>
            <div class="agent-info">
              <div class="agent-name">${escapeHtml(id)}</div>
              <div class="agent-role">${escapeHtml(role)}</div>
            </div>
            <div class="agent-strategy-label" style="color: ${color.label}; background: ${color.labelBg};">${escapeHtml(strategy.toUpperCase())}</div>
          </div>
          <div class="agent-chip-row">
            <span class="agent-owner-chip">Holds: ${escapeHtml(ownedLabel)}</span>
            ${emotionLabel ? `<span class="agent-emotion-chip">${emotionEmoji} ${escapeHtml(emotionLabel)}</span>` : ""}
          </div>
          <div class="agent-metrics">
            <div class="metric">
              <div class="metric-topline">
                <span class="metric-label">Stress</span>
                <span class="metric-value">${escapeHtml(String(stress))}</span>
              </div>
              <div class="mini-bar stress"><span style="width:${escapeHtml(stressWidth)};"></span></div>
            </div>
          </div>
          ${thought ? `<div class="agent-thought">${escapeHtml(thought)}</div>` : ""}
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

    function appendEvents(events) {
      if (!Array.isArray(events) || !events.length) return [];
      const placeholder = eventLog.querySelector("[data-placeholder]");
      if (placeholder) placeholder.remove();

      const appended = [];
      const orderedEvents = [...events].sort((a, b) => displayPriority(a) - displayPriority(b));
      orderedEvents.forEach(ev => {
        const key = eventKey(ev);
        if (state.eventsSeen.has(key)) return;
        state.eventsSeen.add(key);
        appended.push(ev);

        const node = document.createElement("article");
        const isUser        = String(ev.actor || "").toUpperCase() === "USER" || ev.type === "intervention";
        const isTriggered   = String(ev.reason || "").startsWith("user_");
        node.className      = "event";
        if (isUser || isTriggered) node.setAttribute("data-origin", "user");

        const visibleText = massageEventText(ev);
        // Map real tick numbers to sequential visible step labels so empty ticks
        // (ticks the model advanced through but produced no events) don't create
        // confusing gaps like "Step 4 … Step 6" in the log.
        let tickStr = "";
        if (ev.tick != null) {
          if (!state.tickToDisplayStep.has(ev.tick)) {
            state.nextDisplayStep += 1;
            state.tickToDisplayStep.set(ev.tick, state.nextDisplayStep);
          }
          tickStr = `Step ${state.tickToDisplayStep.get(ev.tick)}`;
        }

        if (isUser) {
          const blocker = currentBlocker();
          const target  = ev.target && String(ev.target).toUpperCase() !== "GROUP"
            ? actorLabel(ev.target) : "Group";
          node.innerHTML = `
            <div class="ev-header">
              <div class="ev-actors">
                <span class="ev-you">You</span>
                <span class="ev-arrow">→</span>
                <span class="ev-target">${escapeHtml(target)}</span>
                <span class="ev-type" data-etype="intervention">Intervention</span>
              </div>
              <span class="ev-tick">${escapeHtml(tickStr)}</span>
            </div>
            <div class="ev-body-iv">${escapeHtml(visibleText)}</div>
            ${blocker ? `<div class="ev-triggered">↳ Current blocker: ${escapeHtml(itemLabel(blocker))}</div>` : ""}
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
          const effectText = eventEffectText(ev);

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
        eventLog.appendChild(node);
      });

      const scroll = $("eventLogScroll");
      const shouldStickToBottom = scroll
        ? (scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight) < 56
        : false;
      const toggleBtn = $("timelineToggle");
      if (toggleBtn) toggleBtn.remove();
      if (scroll && shouldStickToBottom) scroll.scrollTop = scroll.scrollHeight;
      return appended;
    }

    // ── Intervention picker population ─────────────────────────────────
    function refreshInterventionPickers() {
      const agentIds = state.agents.map(a => a.public_id || a.id).filter(Boolean);
      fillSelect($("revealAgent"), agentIds);
      fillSelect($("revealItem"), revealableItemsForAgent($("revealAgent").value));
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
          opt.textContent = itemLabel(v);
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
      if (gs.bottleneck_item) {
        const tasksMap = state.tasks || {};
        if (typeof tasksMap[gs.bottleneck_item] === "boolean" && !tasksMap[gs.bottleneck_item]) {
          return gs.bottleneck_item;
        }
        if (tasksMap[gs.bottleneck_item] === undefined) {
          return gs.bottleneck_item;
        }
      }
      const tasks = state.tasks || {};
      for (const [name, done] of Object.entries(tasks)) {
        if (!done && name !== "unlock") return name;
      }
      return null;
    }

    function unsolvedTaskNames() {
      const tasks = state.tasks || {};
      return Object.entries(tasks)
        .filter(([name, done]) => !done && name !== "unlock")
        .map(([name]) => name);
    }

    function revealableItemsForAgent(agentId) {
      const unsolved = unsolvedTaskNames();
      if (!agentId) return unsolved;
      const agent = state.agents.find((a) => (a.id || a.public_id) === agentId);
      if (!agent || !Array.isArray(agent.known_items)) return unsolved;
      const known = new Set(agent.known_items);
      return unsolved.filter((item) => !known.has(item));
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
          reason: `${holderLabel} holds ${blockerLabel} but has not shared it yet. Reveal it to surface the clue.`,
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
      if (!blocker) return "No active blocker — the team is closing the final outcome.";
      const known = taskKnowledgeCount(blocker);
      if (known === 0) {
        return `The team is blocked because ${itemLabel(blocker)} has not been surfaced yet.`;
      }
      if (known < (state.agents.length || 1)) {
        return `The team is blocked because ${itemLabel(blocker)} is only partially shared.`;
      }
      return `The team is blocked because ${itemLabel(blocker)} still needs to be confirmed or used.`;
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
    // Returns the raw key (e.g. "map", "pattern", "code") so itemLabel() can prettify it.
    function detectItemFromText(text) {
      const s = String(text || "").toLowerCase();
      // Door code / final entry — check before generic "code"
      if (s.includes("door code") || s.includes("4-2-7") || s.includes("final code") || s.includes("entering") || s.includes("entering now")) return "code";
      // Room map
      if (s.includes("room map") || s.includes("map clue") || s.includes("got the map") || s.includes("use the map")) return "map";
      // Lock pattern / combination
      if (s.includes("lock pattern") || s.includes("lock combination") || s.includes("combination") || s.includes("the pattern")) return "pattern";
      // Key location
      if (s.includes("key location") || s.includes("golden key") || s.includes("the key") || s.includes("exit panel")) return "key";
      // Exit / escape completion
      if (s.includes("through") || s.includes("we escaped") || s.includes("door open") || s.includes("move now")) return "unlock";
      // Generic code mention
      if (s.includes(" code")) return "code";
      return null;
    }

    function eventReasonText(ev, blockerOverride = null) {
      const blocker = blockerOverride || currentBlocker();
      const detectedItem = detectItemFromText(ev.text);
      const item = ev.item || detectedItem || blocker;
      const reason = String(ev.reason || "");
      const type = String(ev.type || "").toLowerCase();

      if (reason.startsWith("user_")) {
        // reveal_info: distinguish between "directly unblocking" and "storing for later"
        if (reason === "user_reveal_info") {
          const revealed = ev.item ? itemLabel(ev.item) : "the missing information";
          if (ev.item && blocker && ev.item !== blocker) {
            return `${userTriggerLabel(reason)} — ${revealed} is stored ahead of the active blocker (${itemLabel(blocker)}).`;
          }
          return `${userTriggerLabel(reason)} to surface ${revealed} for the team.`;
        }
        // Use the event's own item when set (e.g. forced-meeting share targets the blocker
        // that existed when the meeting was triggered, not the current live blocker which may
        // have already advanced by render time).
        const focus = item ? itemLabel(item) : (blocker ? itemLabel(blocker) : "the scenario objective");
        return `${userTriggerLabel(reason)} while ${focus} is the live focus.`;
      }
      if (type === "ask_info" || type === "ask") {
        const focus = item ? itemLabel(item) : "a missing detail";
        return `${actorLabel(ev.actor)} still needs ${focus} to move the team forward.`;
      }
      if (type === "share_info" || type === "share") {
        const focus = item ? itemLabel(item) : "a key clue";
        return `${actorLabel(ev.actor)} is surfacing ${focus} to unblock the team.`;
      }
      if (type === "challenge" || type === "doubt") {
        const focus = item ? itemLabel(item) : "the current answer";
        return `${actorLabel(ev.actor)} is rechecking ${focus} before the team commits.`;
      }
      if (type === "agree" || type === "confirm") {
        const focus = item ? itemLabel(item) : "the shared information";
        return `The team is validating and locking in ${focus}.`;
      }
      if (type === "suggest" || type === "say" || type === "coord") {
        if (state.ended) {
          const env = String(state.environment || state.scenarioHint || "").toLowerCase();
          if (env === "office") return "The team has submitted the proposal and the run is complete.";
          if (env === "cafe")   return "The group has reached a decision and the run is complete.";
          return "The team has cleared the final objective and the run is complete.";
        }
        const focus = item ? itemLabel(item) : "the next step";
        return `${actorLabel(ev.actor)} is coordinating progress on ${focus}.`;
      }
      // Praise / social events — do not attribute to a task blocker
      if (type === "compliment" || type === "reassure") {
        return "The team is maintaining morale and keeping relations positive.";
      }
      if (type === "refuse") {
        const focus = item ? itemLabel(item) : "the current request";
        return `${actorLabel(ev.actor)} is pushing back on ${focus} this step.`;
      }
      if (type === "ignore" || type === "insult") {
        return "A breakdown in communication is increasing friction this step.";
      }
      return blocker
        ? `${itemLabel(blocker)} is still the active dependency this step.`
        : "The team is closing in on the final objective.";
    }

    // Event types that can legitimately claim a task is "resolved."
    // Ask / praise / friction events must never trigger the "X is now resolved" path.
    const RESOLUTION_TYPES = new Set([
      "share_info", "share", "agree", "confirm",
      "suggest", "say", "coord", "open", "enter", "finalise", "summary",
    ]);

    function eventEffectText(ev, blockerOverride = null) {
      const blocker = blockerOverride || currentBlocker();
      const detectedItem = detectItemFromText(ev.text);
      const item = ev.item || detectedItem || blocker;
      const type = String(ev.type || "").toLowerCase();
      const tasks = state.tasks || {};

      // Praise / social events — generic, no task or blocker reference
      if (type === "compliment" || type === "reassure") {
        return "The team acknowledges progress and stays aligned.";
      }
      if (type === "ignore" || type === "insult") {
        return "The communication breakdown adds friction and may slow progress.";
      }
      if (type === "refuse") {
        const focus = item ? itemLabel(item) : "the current request";
        return `${actorLabel(ev.actor)} declining slows progress on ${focus} this step.`;
      }

      // Ask events: never claim resolution — always show "waiting for reply"
      if (type === "ask_info" || type === "ask") {
        const focus = item ? itemLabel(item) : "the missing detail";
        return `The question focuses the team on ${focus}. Progress waits on a reply.`;
      }

      // "Item just completed" — only for event types that actually resolve tasks
      if (item && tasks[item] && RESOLUTION_TYPES.has(type)) {
        const env = String(state.environment || state.scenarioHint || "").toLowerCase();
        const next = currentBlocker();
        if (!next) {
          if (env === "office") return `${itemLabel(item)} is confirmed. The team is ready to submit the proposal.`;
          if (env === "cafe")   return `${itemLabel(item)} is confirmed. The group can now finalise the decision.`;
          return `${itemLabel(item)} is confirmed. The team can now attempt the final escape.`;
        }
        return `${itemLabel(item)} is now resolved. The team moves on to ${itemLabel(next)}.`;
      }

      if (state.ended) {
        const env = String(state.environment || state.scenarioHint || "").toLowerCase();
        if (env === "office") return "The proposal is submitted and the team has completed the project.";
        if (env === "cafe")   return "The group has agreed on a venue and the decision is final.";
        return "The door code is entered and the team has successfully escaped.";
      }

      if (type === "share_info" || type === "share") {
        const focus = item ? itemLabel(item) : "the clue";
        return `${focus} is now in the conversation for the team to confirm and use.`;
      }
      if (type === "challenge" || type === "doubt") {
        const focus = item ? itemLabel(item) : "the current answer";
        return `The team pauses briefly to verify ${focus} before committing.`;
      }
      if (type === "agree" || type === "confirm") {
        const focus = item ? itemLabel(item) : "the shared information";
        return `Confidence rises around ${focus}. Confirmation is close.`;
      }
      if (type === "suggest" || type === "say" || type === "coord") {
        const focus = item ? itemLabel(item) : "the objective";
        return `The team stays aligned on ${focus} and readies the next move.`;
      }
      return "The conversation state advances, keeping the team on track.";
    }

    function latestUpdateFromEvents(events) {
      const visible = (events || []).filter((ev) => String(ev.actor || "").toUpperCase() !== "USER" && ev.type !== "intervention");
      if (!visible.length) {
        return {
          summary: "No simulation events yet.",
          note: "Press Next Step to let the agents act. The timeline will explain what happened and why.",
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
      const item = itemLabel(lead.item || detectItemFromText(lead.text) || blocker || "the objective");
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

      if (objective) objective.textContent = scenarioObjectiveText();

      // Current Situation card
      const blocker = currentBlocker();
      const holder = holderOfBlocker(blocker);
      const holderLabel = holder ? actorLabel(holder) : "An agent";
      const knowCount = blocker ? taskKnowledgeCount(blocker) : 0;
      const blockerLabel = blocker ? itemLabel(blocker) : null;
      const agentCount = state.agents.length || 1;

      if (currentProblem) {
        if (!blocker) {
          currentProblem.textContent = "No active blocker — the team is resolving the final outcome.";
        } else if (knowCount === 0) {
          currentProblem.textContent = `The team is blocked by ${blockerLabel}. ${holderLabel} holds the needed clue, but it has not been shared yet.`;
        } else if (knowCount < agentCount) {
          currentProblem.textContent = `The team is blocked by ${blockerLabel}. The clue is partially shared — not all agents have it yet.`;
        } else {
          currentProblem.textContent = `The team is blocked by ${blockerLabel}. All agents know the clue, but it has not been confirmed yet.`;
        }
      }

      if (nextExpected) nextExpected.textContent = nextExpectedText();

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
        } else {
          nextActionEl.classList.add("hidden");
        }
      }

      // Recommended action — show in both Intervention Lab and Latest Change card
      const rec = recommendedActionText();
      if (ivRecommend) {
        if (rec) {
          ivRecommend.innerHTML = `<span class="iv-rec-label">Suggested action:</span> <strong>${escapeHtml(rec.action)}</strong> — ${escapeHtml(rec.reason)}`;
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
      if (type === "reveal_info")    return `Reveal ${itemLabel(params.item)} → ${params.agent_id}`;
      if (type === "force_meeting")  return `Force meeting · ${params.agent_a_id} & ${params.agent_b_id}`;
      if (type === "nudge_strategy") return `Nudge ${params.agent_id} → ${params.strategy}`;
      if (type === "boost_urgency")  return `Boost urgency +${toFixedSafe(params.amount)}`;
      if (type === "inject_tension") return `Inject tension +${toFixedSafe(params.amount)}`;
      return type;
    }

    function expectedEffectFor(iv) {
      const { type, params, before } = iv;
      const blocker = before && before.blocker;
      if (type === "reveal_info") {
        if (blocker && blocker === params.item) {
          return `${params.agent_id} surfaces ${itemLabel(params.item)} next step.`;
        }
        return `${params.agent_id} carries ${itemLabel(params.item)} into the next blocker turn.`;
      }
      if (type === "force_meeting")  return `${params.agent_a_id} ↔ ${params.agent_b_id} on ${itemLabel(blocker || "blocker")}.`;
      if (type === "nudge_strategy") return blocker
        ? `${params.agent_id} speaks constructively on ${itemLabel(blocker)}.`
        : `${params.agent_id} speaks constructively (share/agree/ask).`;
      if (type === "boost_urgency")  return `Urgency rises, next line pushes ${itemLabel(blocker || "blocker")}.`;
      if (type === "inject_tension") return `Tension rises, next line sharpens on ${itemLabel(blocker || "blocker")}.`;
      return "";
    }

    function stateChangeLineFor(type, params, before, after) {
      if (type === "reveal_info") {
        return `${params.agent_id} now knows <b>${itemLabel(params.item)}</b>.`;
      }
      if (type === "force_meeting") {
        const blocker = before && before.blocker;
        return blocker
          ? `<b>${params.agent_a_id}</b> & <b>${params.agent_b_id}</b> on <b>${itemLabel(blocker)}</b>.`
          : `<b>${params.agent_a_id}</b> & <b>${params.agent_b_id}</b> paired.`;
      }
      if (type === "nudge_strategy") {
        const beforeStrat = (before && before.strategy) || "—";
        if (beforeStrat === params.strategy) {
          return `${params.agent_id} locked <b>${params.strategy}</b> (refreshed).`;
        }
        return `${params.agent_id}: <b>${beforeStrat}</b> → <b>${params.strategy}</b>.`;
      }
      if (type === "boost_urgency") {
        const beforeU = (before && before.urgency) || 1.0;
        const afterU  = (after && after.urgency) || beforeU;
        return `Urgency <b>${toFixedSafe(beforeU)}</b> → <b>${toFixedSafe(afterU)}</b>.`;
      }
      if (type === "inject_tension") {
        const beforeT = (before && before.tension) || 0;
        return `Tension queued +${toFixedSafe(params.amount)} (was <b>${toFixedSafe(beforeT)}</b>).`;
      }
      return "—";
    }

    function deltaSpan(label, before, after) {
      const b = Number(before);
      const a = Number(after);
      if (!Number.isFinite(b) || !Number.isFinite(a)) {
        return `<span class="delta-flat">${label}: —</span>`;
      }
      const diff = a - b;
      let cls = "delta-flat";
      let arrow = "→";
      if (diff > 0.001) { cls = "delta-up"; arrow = "↑"; }
      else if (diff < -0.001) { cls = "delta-down"; arrow = "↓"; }
      return `<span class="${cls}">${label}: ${b.toFixed(2)} ${arrow} ${a.toFixed(2)}</span>`;
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

      $("ivTickStamp").textContent = `applied at step ${iv.atTick}`;
      $("ivButton").textContent = iv.label;
      $("ivStateChange").innerHTML = stateChangeLineFor(
        iv.type, iv.params, iv.before, { urgency: iv.postUrgency }
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
        urgency: Number(state.urgencyValue || 1.0),
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
                 consequence: "The forced pair did not visibly lead this tick." };
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
                   note: `Nudge registered: ${params.agent_id} is now ${agent.strategy}, but no visible action landed this tick yet.`,
                   consequence: "Strategy changed — follow-through expected next tick." };
        }
        if (strategyOk) {
          return { confirmed: false,
                   note: `Nudge registered: strategy is ${agent.strategy} but the next event was not clearly cooperative.`,
                   consequence: `${params.agent_id} strategy updated; full effect may land next tick.` };
        }
        return { confirmed: false,
                 note: "Nudge did not produce the expected strategy change this tick.",
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
                   note: `Tension injection raised tension ${before.toFixed(2)} → ${after.tension.toFixed(2)}, but no visible challenge event landed this tick.`,
                   consequence: `Tension rose to ${after.tension.toFixed(2)} — the disagreement may surface next tick.` };
        }
        return { confirmed: false,
                 note: "Tension injection registered but group tension did not visibly rise this tick.",
                 consequence: "No tension change observed — the effect may still propagate." };
      }

      if (iv.type === "boost_urgency") {
        const beforeU = Number(iv.before.urgency) || 1.0;
        const afterU = Number(iv.postUrgency || after.urgency) || beforeU;
        const urgencyUp = afterU > beforeU + 0.001;
        const blockerLine = postEvents.some(
          e => String(e.reason || "").startsWith("user_boost_urgency") &&
               (e.item === blocker || itemMatch(e.text, blocker))
        );
        const anyUrgencyLine = postEvents.some(e => String(e.reason || "").startsWith("user_boost_urgency"));
        if (urgencyUp && (blockerLine || anyUrgencyLine)) {
          return { confirmed: true,
                   note: `Your urgency boost worked — urgency rose ${beforeU.toFixed(2)} → ${afterU.toFixed(2)} and agents pushed faster.`,
                   consequence: `Boost urgency: urgency is now ${afterU.toFixed(2)}; agents accelerated progress on ${itemLabel(blocker || "the active item")}.` };
        }
        if (urgencyUp) {
          return { confirmed: false,
                   note: `Urgency boost registered — urgency rose ${beforeU.toFixed(2)} → ${afterU.toFixed(2)}, but no urgency-driven event was visible this tick.`,
                   consequence: `Urgency raised to ${afterU.toFixed(2)} — faster pacing expected next tick.` };
        }
        return { confirmed: false,
                 note: "Urgency boost registered but the urgency value did not rise this tick.",
                 consequence: "No urgency change observed — check if the backend applied it." };
      }

      return { confirmed: false, note: "Unknown intervention type.", consequence: "—" };
    }

    function applyConfirmationUpdate(iv, postEvents) {
      if (!$("ivConfirmBadge")) return;
      const result = evaluateInterventionConfirmation(iv, postEvents);
      const before = iv.before || {};
      const tensionAfter = Number(state.groupState.tension || 0);
      const cohesionAfter = Number(state.groupState.cohesion || 0);
      const urgencyAfter = Number(iv.postUrgency || state.urgencyValue || 1.0);

      let deltaParts = [];
      if (iv.type === "inject_tension" || iv.type === "force_meeting" || iv.type === "nudge_strategy") {
        deltaParts.push(deltaSpan("Tension", before.tension, tensionAfter));
      }
      if (iv.type === "force_meeting" || iv.type === "nudge_strategy" || iv.type === "reveal_info") {
        deltaParts.push(deltaSpan("Cohesion", before.cohesion, cohesionAfter));
      }
      if (iv.type === "boost_urgency") {
        deltaParts.push(deltaSpan("Urgency", before.urgency, urgencyAfter));
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
      state.tasks = scenario.tasks || state.tasks;
      state.knowledgeMap = scenario.knowledge_map || state.knowledgeMap;
      state.agents = Array.isArray(data.agents) ? data.agents : state.agents;
      state.groupState = data.group_state || state.groupState;
      // Seed peak tension from history (captures initial non-zero values that
      // may have dropped to 0 by the time the first tick snapshot is stored).
      if (data.group_state) {
        state.peakTension = Math.max(state.peakTension, data.group_state.tension || 0);
      }
      if (Array.isArray(data.history)) {
        data.history.forEach(h => {
          const t = h.group_state ? (h.group_state.tension || 0) : (h.metrics ? (h.metrics.group_tension || 0) : 0);
          if (t > state.peakTension) state.peakTension = t;
        });
      }

      setMeta("RunId", state.runId || "—");
      setMeta("Status", statusLabel(state.status, state.ended),
              state.ended ? "ended" : (state.autoRunning ? "running" : ""));
      setMeta("Tick", state.tick);
      setMeta("Env", environmentLabel(state.environment || "—"));
      setMeta("Team", teamLabel(data.team_type || state.teamHint || "—"));
      setMeta("Tension", toFixedSafe(state.groupState.tension));
      setMeta("Cohesion", toFixedSafe(state.groupState.cohesion));
      setMeta("Urgency", toFixedSafe(state.urgencyValue));

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
        if (done && taskKey !== "unlock") {
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
            conflict: Number(hm.conflict_rate ?? 0),
          });
        });
      }

      // Seed log from recent history on first attach
      if (!eventLog.querySelector(".event") && Array.isArray(data.history)) {
        const recent = [];
        data.history.slice(-8).forEach(h => {
          (h.events || []).forEach(ev => recent.push(Object.assign({ tick: h.tick }, ev)));
        });
        appendEvents(recent);
        const latestTick = recent.length ? Math.max(...recent.map((ev) => Number(ev.tick || 0))) : null;
        renderStoryPanels(latestTick == null ? [] : recent.filter((ev) => Number(ev.tick) === latestTick));
      } else {
        renderStoryPanels([]);
      }

      updateControlState();

      if (state.ended) {
        setModePill("Ended", "ended");
        showEndModal();
      } else {
        setModePill("Live Interactive");
        hideEndModal();
        showBanner("Live Interactive attached. Use <strong>▶ Next Step</strong> or an intervention to advance one step.", "info");
      }
    }

    function applyTickDiff(diff) {
      if (!diff) return;
      state.tick = diff.tick ?? state.tick;
      if (Array.isArray(diff.agents) && diff.agents.length) state.agents = diff.agents;
      if (diff.group_state) {
        state.groupState = diff.group_state;
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
        conflict: Number(m.cumulative_conflict_rate ?? m.conflict_rate ?? 0),
      });
      if (state.currentView === "metrics") refreshMetricsView();

      setMeta("Tick", state.tick);
      setMeta("Tension", toFixedSafe(state.groupState.tension));
      setMeta("Cohesion", toFixedSafe(state.groupState.cohesion));
      setMeta("Urgency", toFixedSafe(state.urgencyValue));
      updateBlockerBadge();
      renderAgents();
      refreshInterventionPickers();
      updateSuggestText();

      const events = (diff.events || []).map(e => Object.assign({ tick: state.tick }, e));
      appendEvents(events);
      renderStoryPanels(events);

      // Effect confirmation: evaluate the just-arrived tick against the
      // intervention applied at state.lastIntervention.atTick.
      if (state.lastIntervention && !state.lastIntervention.confirmed
          && state.tick > state.lastIntervention.atTick) {
        try {
          applyConfirmationUpdate(state.lastIntervention, events);
          const lastM = state.metricsHistory.length
            ? state.metricsHistory[state.metricsHistory.length - 1] : null;
          state.lastIntervention.afterMetrics = {
            stress:   lastM ? lastM.stress   : 0,
            trust:    lastM ? lastM.trust     : 0,
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

      // Phase dividers: insert a marker each time a new task becomes complete
      const tasks = state.tasks || {};
      Object.entries(tasks).forEach(([taskKey, done]) => {
        if (done && !state.completedPhases.has(taskKey) && taskKey !== "unlock") {
          state.completedPhases.add(taskKey);
          const divider = document.createElement("div");
          divider.className = "phase-divider";
          divider.innerHTML = `<span class="phase-label">✓ ${escapeHtml(itemLabel(taskKey))} resolved</span>`;
          eventLog.appendChild(divider);
        }
      });

      if (diff.ended) {
        state.ended = true;
        state.autoRunning = false;
        setMeta("Status", statusLabel("ended", true), "ended");
        setModePill("Ended", "ended");
        updateBlockerBadge();
        updateControlState();

        // Insert final run summary card into the log
        if (!$("runSummaryCard")) {
          const resolvedItems = Object.entries(tasks)
            .filter(([k, v]) => v && k !== "unlock")
            .map(([k]) => itemLabel(k));
          // Use peak tension (running max over all ticks) rather than the final value,
          // which is often near 0 after a successful run relieves team stress.
          const tension = toFixedSafe(state.peakTension);
          const cohesion = toFixedSafe(state.groupState.cohesion);

          const _env = String(state.environment || state.scenarioHint || "").toLowerCase();
          const _runTitle = _env === "office" ? "Run Complete — Proposal Accepted"
                          : _env === "cafe"   ? "Run Complete — Decision Reached"
                          : "Run Complete — Escape Successful";
          const summary = document.createElement("div");
          summary.id = "runSummaryCard";
          summary.className = "run-summary-card";
          summary.innerHTML = `
            <div class="rs-header">
              <span class="rs-icon">✓</span>
              <div>
                <div class="rs-title">${escapeHtml(_runTitle)}</div>
                <div class="rs-sub">Completed in ${state.tick} steps</div>
              </div>
            </div>
            <div class="rs-body">
              <div class="rs-row"><span class="rs-key">Blockers resolved</span><span class="rs-val">${escapeHtml(resolvedItems.join(" → "))}</span></div>
              <div class="rs-row"><span class="rs-key">Final cohesion</span><span class="rs-val">${cohesion}</span></div>
              <div class="rs-row"><span class="rs-key">Peak tension</span><span class="rs-val">${tension}</span></div>
            </div>
          `;
          eventLog.appendChild(summary);
        }

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
        return data.detail || data.message || `HTTP ${response.status}`;
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
        const detail = (data && (data.detail || data.message)) || (text || `HTTP ${r.status}`);
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

      const params = {};
      if (type === "boost_urgency") {
        params.amount = parseFloat($("pressureAmt").value);
      } else if (type === "inject_tension") {
        params.amount = parseFloat($("tensionAmt").value);
      } else if (type === "reveal_info") {
        params.agent_id = $("revealAgent").value;
        params.item = $("revealItem").value;
        if (!params.agent_id || !params.item) {
          showBanner("Pick an agent and an info item to reveal.", "error");
          return;
        }
        if (!revealableItemsForAgent(params.agent_id).includes(params.item)) {
          showBanner("That agent already has that unsolved item, or it is no longer relevant to reveal.", "error");
          return;
        }
      } else if (type === "force_meeting") {
        params.agent_a_id = $("forceAgentA").value;
        params.agent_b_id = $("forceAgentB").value;
        if (!params.agent_a_id || !params.agent_b_id) {
          showBanner("Pick two agents to force into a meeting.", "error");
          return;
        }
        if (params.agent_a_id === params.agent_b_id) {
          showBanner("Pick two different agents.", "error");
          return;
        }
      } else if (type === "nudge_strategy") {
        params.agent_id = $("nudgeAgent").value;
        if (!params.agent_id) {
          showBanner("Pick an agent to nudge.", "error");
          return;
        }
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
        urgency: Number(state.urgencyValue || 1.0),
        stress: _lastM ? _lastM.stress : 0,
        trust:  _lastM ? _lastM.trust  : 0,
        blocker: currentBlocker(),
        strategy: targetAgent ? targetAgent.strategy : null,
        knownItems: targetAgent && Array.isArray(targetAgent.known_items)
          ? [...targetAgent.known_items]
          : [],
      };

      state.actionPending = true;
      updateControlState();
      try {
        const result = await postJson(`${API_BASE}/interventions/apply`, {
          run_id: state.runId, type, params,
        });
        const rawMessage = result.message || "Intervention queued for the next step.";
        const label = formatInterventionMessage(type, params, rawMessage);

        // Parse env.urgency_modifier from boost_urgency response
        let postUrgency = state.urgencyValue;
        if (type === "boost_urgency") {
          const m = String(rawMessage).match(/Environment urgency now ([0-9.]+)/);
          if (m) {
            postUrgency = parseFloat(m[1]);
            if (Number.isFinite(params.amount)) {
              const derivedBefore = postUrgency - Number(params.amount);
              if (derivedBefore >= 0) beforeSnapshot.urgency = derivedBefore;
            }
            state.urgencyValue = postUrgency;
            setMeta("Urgency", toFixedSafe(state.urgencyValue));
          } else if (Number.isFinite(params.amount)) {
            postUrgency = state.urgencyValue + Number(params.amount);
            state.urgencyValue = postUrgency;
            setMeta("Urgency", toFixedSafe(state.urgencyValue));
          }
        }

        state.lastIntervention = {
          type,
          params: { ...params },
          label: buttonLabelFor(type, params),
          before: beforeSnapshot,
          atTick: state.tick,
          postUrgency,
          confirmed: false,
        };
        showInterventionCardImmediate(state.lastIntervention);

        appendEvents([buildLocalInterventionEvent(type, params, rawMessage)]);
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

    // ── Intervention more/less toggle ─────────────────────────────────
    const ivMoreToggle = $("ivMoreToggle");
    const ivMore = $("ivMore");
    if (ivMoreToggle && ivMore) {
      ivMoreToggle.addEventListener("click", () => {
        const collapsed = ivMore.classList.toggle("collapsed");
        ivMoreToggle.setAttribute("aria-expanded", String(!collapsed));
        ivMoreToggle.textContent = collapsed ? "All interventions ▾" : "Hide interventions ▴";
      });
    }

    // ── Wire buttons ───────────────────────────────────────────────────
    btnStep.addEventListener("click", stepRun);
    const btnStepInline = $("btnStepInline");
    if (btnStepInline) btnStepInline.addEventListener("click", stepRun);
    btnReset.addEventListener("click", resetRun);
    const btnDismissEndModal = $("btnDismissEndModal");
    if (btnDismissEndModal) btnDismissEndModal.addEventListener("click", hideEndModal);
    document.querySelectorAll("[data-iv]").forEach(btn => {
      btn.addEventListener("click", () => applyIntervention(btn.getAttribute("data-iv")));
    });
    // Listen for picker changes in the new iv-item-controls containers
    document.querySelectorAll(".iv-item-controls select, .iv-item-controls input").forEach((field) => {
      field.addEventListener("change", updateControlState);
      field.addEventListener("input", updateControlState);
    });
    $("revealAgent").addEventListener("change", () => {
      fillSelect($("revealItem"), revealableItemsForAgent($("revealAgent").value));
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
      if (name === "metrics") refreshMetricsView();
      if (name === "impact") renderImpactView();
    }

    // ── Metrics view ───────────────────────────────────────────────────
    function refreshMetricsView() {
      const h = state.metricsHistory;
      const last = h.length ? h[h.length - 1] : null;

      const set = (id, val) => { const el = $(id); if (el) el.textContent = val; };
      set("mvFinalStress",  last ? toFixedSafe(last.stress,  2) : "—");
      set("mvFinalTrust",   last ? toFixedSafe(last.trust,   2) : "—");
      set("mvCohesion",     last ? toFixedSafe(last.cohesion,2) : "—");
      set("mvConflict",     last ? toFixedSafe(last.conflict,2) : "—");
      set("mvTicks",        h.length ? String(h[h.length - 1].tick) : "—");

      renderMainChart();
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
              position: "top",
              labels: { color: "#c8d0e0", font: { size: 12 }, boxWidth: 14, padding: 16 },
            },
            tooltip: {
              backgroundColor: "#1e2434",
              borderColor: "#2e3650",
              borderWidth: 1,
              titleColor: "#8892aa",
              bodyColor: "#c8d0e0",
              callbacks: {
                label: ctx => ` ${ctx.dataset.label}: ${Number(ctx.parsed.y).toFixed(2)}`,
              },
            },
          },
          scales: {
            x: {
              title: { display: true, text: "Tick", color: "#8892aa", font: { size: 11 } },
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

    function _ivSummary(iv, analysis) {
      const improved = analysis.filter(m => m.good);
      const worsened = analysis.filter(m => m.bad);
      const listStr  = arr => arr.length > 1
        ? arr.slice(0, -1).map(m => m.label.toLowerCase()).join(", ") + " and " + arr[arr.length - 1].label.toLowerCase()
        : arr[0] ? arr[0].label.toLowerCase() : "";
      const label = (iv.label || iv.type).toLowerCase();

      if (improved.length === 4)
        return `This ${label} improved all four metrics — ${listStr(improved)} all moved in a better direction. The team is more stable after this intervention.`;
      if (improved.length >= 3)
        return `This ${label} improved ${listStr(improved)}${worsened.length ? `, though ${listStr(worsened)} worsened slightly` : ""}. Overall a positive effect on team dynamics.`;
      if (improved.length >= 1 && worsened.length >= 1)
        return `Mixed result: ${listStr(improved)} improved, but ${listStr(worsened)} moved in the wrong direction. This intervention involved trade-offs.`;
      if (worsened.length >= 3)
        return `This ${label} worsened ${listStr(worsened)}. The team was more destabilised after this step.`;
      return `This intervention had little measurable effect on team dynamics at this step.`;
    }

    function _ivBadge(improved, worsened) {
      const n = improved.length;
      if (n === 4)           return { cls: "is-positive", text: `Positive Impact · 4/4 metrics improved` };
      if (n === 3)           return { cls: "is-positive", text: `Positive Impact · 3/4 metrics improved` };
      if (n === 2 && worsened.length <= 1)
                             return { cls: "is-mixed",    text: `Mixed Impact · 2/4 metrics improved` };
      if (n >= 1)            return { cls: "is-mixed",    text: `Mixed Impact · ${n}/4 metrics improved` };
      if (worsened.length >= 3)
                             return { cls: "is-negative", text: `Negative Impact · ${worsened.length}/4 metrics worsened` };
      return                        { cls: "is-neutral",  text: `No Clear Impact` };
    }

    function renderImpactView() {
      const empty = $("ivImpactEmpty");
      const list  = $("ivImpactList");
      if (!empty || !list) return;

      if (!state.interventionLog.length) {
        empty.classList.remove("hidden");
        list.classList.add("hidden");
        list.innerHTML = "";
        return;
      }

      empty.classList.add("hidden");
      list.classList.remove("hidden");

      const METRICS = [
        { key: "stress",   label: "Stress"   },
        { key: "trust",    label: "Trust"    },
        { key: "tension",  label: "Tension"  },
        { key: "cohesion", label: "Cohesion" },
      ];

      list.innerHTML = state.interventionLog.map((iv, i) => {
        const b   = iv.before || {};
        const a   = iv.afterMetrics || {};
        const fix2 = v => Number(v).toFixed(2);

        const analysis = METRICS.map(({ key, label }) => {
          const bv  = Number(b[key] ?? 0);
          const av  = Number(a[key] ?? 0);
          const d   = av - bv;
          const cls = _ivDeltaClass(key, d);
          return {
            key, label, bv, av, d, cls,
            good: cls === "iv-delta-good",
            bad:  cls === "iv-delta-bad",
            arrow: d > 0.005 ? "▲" : d < -0.005 ? "▼" : "–",
          };
        });

        const improved = analysis.filter(m => m.good);
        const worsened = analysis.filter(m => m.bad);
        const badge    = _ivBadge(improved, worsened);
        const summary  = _ivSummary(iv, analysis);

        const rows = analysis.map(({ label, bv, av, d, cls, arrow, good, bad }) => {
          const verdict = good ? "Improved" : bad ? "Worsened" : "Unchanged";
          return `<tr>
            <td>${label}</td>
            <td>${fix2(bv)}</td>
            <td>${fix2(av)}</td>
            <td><span class="${cls}">${arrow} ${fix2(Math.abs(d))}</span></td>
            <td class="iv-verdict ${cls}">${verdict}</td>
          </tr>`;
        }).join("");

        return `
          <div class="iv-impact-card">
            <div class="iv-impact-head">
              <span class="iv-impact-step">#${i + 1}</span>
              <span class="iv-impact-title">${escapeHtml(iv.label || iv.type)}</span>
              <span class="iv-tick-tag">tick ${iv.atTick}</span>
              <span class="iv-impact-badge ${badge.cls}">${badge.text}</span>
            </div>
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

    // ── Boot ───────────────────────────────────────────────────────────
    async function boot() {
      if (!state.runId) {
        fallbackMissing.classList.remove("hidden");
        setModePill("Idle", "error");
        return;
      }

      try {
        const status = await fetchRunStatus(state.runId);
        liveSession.classList.remove("hidden");
        applyStatusSnapshot(status);
        if (state.ended) {
          syncDashboardLinks();
          return;
        }
        try {
          await openWebSocket(state.runId);
          syncDashboardLinks();
          if (state.autoRunning && !state.ended) {
            enforceManualMode();
          } else if (!state.ended) {
            showBanner("Live Interactive attached. Use <strong>▶ Next Step</strong> or an intervention to advance one step.", "info");
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
