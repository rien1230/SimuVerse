// Setup page logic for presets, validation, and run creation.
const API_BASE = window.SimuVerseAPI.API_BASE;

// Static card content for the three setup choices.
const SCENARIOS = {
  office: {
    label: "Office Project",
    tag: "Structured",
    icon: "🏢",
    description: "A project team shares information and clears task dependencies to complete a proposal.",
    summary: "A project team must clear information dependencies before the work can move.",
    request: {
      environment: "office",
      goal: "complete_proposal"
    }
  },
  cafe: {
    label: "Cafe Planning",
    tag: "Social",
    icon: "☕",
    description: "Agents coordinate food, timing, and budget to agree on a restaurant choice.",
    summary: "A low-stakes planning task shows how social coordination changes behaviour.",
    request: {
      environment: "cafe",
      goal: "choose_restaurant"
    }
  },
  escape: {
    label: "Escape Room",
    tag: "High pressure",
    icon: "🔐",
    description: "Agents share clues under time pressure before using the final exit code.",
    summary: "A time-sensitive puzzle highlights pressure, urgency, and dependency handling.",
    request: {
      environment: "escape",
      goal: "solve_puzzle"
    }
  }
};

const TEAMS = {
  smooth: {
    label: "Smooth Team",
    tag: "Cooperative",
    icon: "🤝",
    description: "Agents trust each other from the start, share quickly, and keep friction low.",
    summary: "Cooperative personalities tend to share quickly and keep trust stable."
  },
  tension: {
    label: "Tension Team",
    tag: "Guarded",
    icon: "⚡",
    description: "Lower initial trust means delay and refusal become clearly visible.",
    summary: "Lower initial trust makes delay and refusal more visible."
  },
  creative: {
    label: "Creative Team",
    tag: "Exploratory",
    icon: "💡",
    description: "Curious personalities question the first answer and explore alternatives.",
    summary: "Curious personalities question the first answer and explore alternatives."
  },
  pressure: {
    label: "Pressure Team",
    tag: "Urgent",
    icon: "⏱",
    description: "Agents move fast and make urgent decisions — but the speed itself raises stress.",
    summary: "Urgent personalities move fast, but the speed itself raises pressure."
  }
};

const MODES = {
  step: {
    label: "Watch Mode",
    tag: "Observe",
    icon: "👁",
    description: "Step through the run automatically and observe how every agent decision unfolds.",
    summary: "The workspace will step through the backend run so you can observe each decision."
  },
  live: {
    label: "Live Interactive",
    tag: "Intervene",
    icon: "🎮",
    description: "Steer the run one tick at a time. Reveal clues, nudge cooperation, or raise urgency.",
    summary: "The workspace opens a manual live console attached to the backend run you just created."
  }
};

const STEPS = [
  { n: 1, label: "Scenario" },
  { n: 2, label: "Team style" },
  { n: 3, label: "Experience" }
];

const PARAMS = new URLSearchParams(window.location.search);

function prefillMode(value) {
  const lower = String(value || "").toLowerCase();
  if (lower === "live" || lower === "interactive") return "live";
  if (lower === "step" || lower === "manual" || lower === "auto") return "step";
  return null;
}

const state = {
  currentStep: 1,
  scenario: null,
  team: null,
  mode: prefillMode(PARAMS.get("mode")),
  launching: false
};

// Cached DOM refs used by the stepper, cards, and summary panel.
const stepperEl = document.getElementById("stepper");
const scenarioGrid = document.getElementById("scenarioGrid");
const teamGrid = document.getElementById("teamGrid");
const modeGrid = document.getElementById("modeGrid");

const summaryScenario = document.getElementById("summaryScenario");
const summaryTeam = document.getElementById("summaryTeam");
const summaryMode = document.getElementById("summaryMode");

const sumScenarioItem = document.getElementById("sumScenarioItem");
const sumTeamItem = document.getElementById("sumTeamItem");
const sumModeItem = document.getElementById("sumModeItem");

const launchBtn = document.getElementById("launchBtn");
const launchFromStep = document.getElementById("launchFromStep");
const launchFeedback = document.getElementById("launchFeedback");
const TARGET_BY_MODE = {
  step: "dashboard.html",
  live: "interactive.html"
};

// Error helpers keep the launch flow readable.
async function parseApiError(response) {
  const text = await response.text();
  if (!text) return `HTTP ${response.status}`;
  try {
    const data = JSON.parse(text);
    // FastAPI validation errors arrive as { detail: [...] }
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => d.msg || String(d)).join("; ");
    }
    return data.detail || data.message || `HTTP ${response.status}`;
  } catch {
    return text.slice(0, 200);
  }
}

/**
 * Classify any thrown error into a human-readable card payload.
 * Covers: connection refused, timeout, HTTP 4xx/5xx, and unknown.
 */
function classifyError(err, response) {
  // Network/connection error – fetch itself threw (server not running, CORS, etc.)
  if (err instanceof TypeError) {
    return {
      icon: "⚡",
      iconKind: "warn",
      title: "Cannot reach the simulation server",
      detail: `No response from ${API_BASE}. The backend may not be running.`,
      hint: "Start it with: <code>uvicorn app.main:app --port 8007 --reload</code>"
    };
  }

  // AbortController timeout
  if (err.name === "AbortError") {
    return {
      icon: "◷",
      iconKind: "warn",
      title: "Request timed out",
      detail: "The server did not respond within 15 seconds.",
      hint: "The backend may be under load. Wait a moment and try again."
    };
  }

  // HTTP errors where we have the response object
  if (response) {
    const s = response.status;

    if (s === 404) return {
      icon: "✕",
      iconKind: "error",
      title: "API endpoint not found (404)",
      detail: `POST ${API_BASE}/runs returned 404. The server may be an older version.`,
      hint: "Check the backend is running the latest code and on the correct port."
    };

    if (s === 422) return {
      icon: "✕",
      iconKind: "error",
      title: "Invalid configuration",
      detail: err.message || "The server rejected this scenario or team combination.",
      hint: "Try a different scenario or team style. Check the backend logs if this repeats."
    };

    if (s === 429) return {
      icon: "◷",
      iconKind: "warn",
      title: "Too many requests",
      detail: "The server is rate-limiting new runs right now.",
      hint: "Wait a few seconds, then retry."
    };

    if (s === 500) return {
      icon: "✕",
      iconKind: "error",
      title: "Server error (500)",
      detail: err.message || "An unexpected error occurred inside the simulation engine.",
      hint: "Check the backend terminal for a Python traceback. Try a different team style."
    };

    if (s === 503) return {
      icon: "◷",
      iconKind: "warn",
      title: "Server unavailable (503)",
      detail: "The simulation server is temporarily unavailable.",
      hint: "Wait a moment and retry. Restart the backend if the problem persists."
    };

    return {
      icon: "✕",
      iconKind: "error",
      title: `Request failed (HTTP ${s})`,
      detail: err.message || `The server returned an unexpected ${s} status.`,
      hint: "Check the backend terminal for more detail."
    };
  }

  // Catch-all
  return {
    icon: "✕",
    iconKind: "error",
    title: "Unexpected error",
    detail: err.message || String(err),
    hint: "Refresh the page and try again, or check the browser console for detail."
  };
}

function showError({ icon, iconKind, title, detail, hint }) {
  launchFeedback.innerHTML = `
    <div class="err-card-top">
      <div class="err-card-icon ${iconKind === "warn" ? "warn" : ""}">${icon}</div>
      <div>
        <p class="err-card-title">${title}</p>
        <p class="err-card-detail">${detail}</p>
      </div>
    </div>
    <p class="err-card-hint">${hint}</p>
    <div class="err-card-actions">
      <button class="btn-retry" type="button" id="btnErrRetry">↺ Try again</button>
      <button class="btn-err-dismiss" type="button" id="btnErrDismiss">Dismiss</button>
    </div>
  `;
  launchFeedback.classList.add("is-visible");
  document.getElementById("btnErrRetry").addEventListener("click", launchSimulation);
  document.getElementById("btnErrDismiss").addEventListener("click", clearError);
}

function clearError() {
  launchFeedback.classList.remove("is-visible");
  launchFeedback.innerHTML = "";
}

// Render the three-step wizard and the live summary card.
function renderStepper() {
  stepperEl.innerHTML = STEPS.map((step, index) => {
    const done = state.currentStep > step.n && isStepComplete(step.n);
    const current = state.currentStep === step.n;
    const cls = ["stepper-item"];
    if (done) cls.push("is-done");
    if (current) cls.push("is-current");
    const separator = index < STEPS.length - 1 ? '<span class="stepper-sep" aria-hidden="true"></span>' : "";
    return `
      <div class="${cls.join(" ")}">
        <span class="stepper-dot">${done ? "✓" : step.n}</span>
        <span>${step.label}</span>
      </div>
      ${separator}
    `;
  }).join("");
}

function renderOptionGrid(container, options, group, selectedValue) {
  container.innerHTML = Object.entries(options).map(([key, option]) => `
    <button type="button" class="option-card ${selectedValue === key ? "is-selected" : ""}" data-group="${group}" data-value="${key}">
      <div class="option-icon-row">
        <span class="option-icon">${option.icon || ""}</span>
        <span class="option-tag">${option.tag}</span>
      </div>
      <div class="option-name">${option.label}</div>
      <p class="option-desc">${option.description}</p>
      <div class="option-check" aria-hidden="true">
        <svg viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7.5" fill="currentColor" opacity="0.12"/><path d="M5 8l2.5 2.5L11 5.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </div>
    </button>
  `).join("");
}

function isStepComplete(step) {
  if (step === 1) return !!state.scenario;
  if (step === 2) return !!state.team;
  if (step === 3) return !!state.mode;
  return false;
}

function allStepsComplete() {
  return STEPS.every((step) => isStepComplete(step.n));
}

function renderSteps() {
  document.querySelectorAll(".step-card").forEach((element) => {
    const stepNumber = Number(element.dataset.step);
    element.classList.toggle("is-active", stepNumber === state.currentStep);
  });

  document.querySelectorAll(".step-continue[data-next]").forEach((button) => {
    const fromStep = Number(button.closest(".step-card").dataset.step);
    button.disabled = !isStepComplete(fromStep) || state.launching;
  });

  launchFromStep.disabled = !allStepsComplete() || state.launching;
}

function renderSummary() {
  if (state.scenario) {
    summaryScenario.textContent = SCENARIOS[state.scenario].label;
    sumScenarioItem.classList.remove("is-pending");
  } else {
    summaryScenario.textContent = "Not selected yet";
    sumScenarioItem.classList.add("is-pending");
  }

  if (state.team) {
    summaryTeam.textContent = TEAMS[state.team].label;
    sumTeamItem.classList.remove("is-pending");
  } else {
    summaryTeam.textContent = state.currentStep >= 2 ? "Choose next" : "Not selected yet";
    sumTeamItem.classList.add("is-pending");
  }

  if (state.mode) {
    summaryMode.textContent = MODES[state.mode].label;
    sumModeItem.classList.remove("is-pending");
  } else {
    summaryMode.textContent = state.currentStep >= 3 ? "Choose next" : "Not selected yet";
    sumModeItem.classList.add("is-pending");
  }

  const launchLabel = state.mode === "live" ? "Launch live interactive" : "Launch simulation";
  launchBtn.textContent = launchLabel;
  launchFromStep.textContent = state.launching ? "Creating run…" : launchLabel;
  launchBtn.disabled = !allStepsComplete() || state.launching;
  launchBtn.classList.toggle("is-loading", state.launching && allStepsComplete());
}

function renderAll() {
  renderStepper();
  renderOptionGrid(scenarioGrid, SCENARIOS, "scenario", state.scenario);
  renderOptionGrid(teamGrid, TEAMS, "team", state.team);
  renderOptionGrid(modeGrid, MODES, "mode", state.mode);
  renderSteps();
  renderSummary();
}

// Create the run on the backend, then send the user to the right page.
async function launchSimulation() {
  if (!allStepsComplete() || state.launching) return;

  state.launching = true;
  clearError();
  renderSteps();
  renderSummary();

  const scenario = SCENARIOS[state.scenario];

  // 15-second timeout — shows a typed timeout error instead of hanging forever
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15_000);

  let response;
  try {
    response = await fetch(`${API_BASE}/runs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        environment: scenario.request.environment,
        goal: scenario.request.goal,
        team_type: state.team,
        // Tell the backend which mode launched this run so History can label it correctly.
        // "step" = Watch Mode (dashboard); "live" = Live Interactive (interaction page).
        run_mode: state.mode
      }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      // Attach the response so classifyError can read the status code
      const err = new Error(await parseApiError(response));
      err._response = response;
      throw err;
    }

    const data = await response.json();
    // Pass the scenario + team identity in the URL so the dashboard uses the
    // correct SCENARIOS template from the very first render. Without this, the
    // dashboard defaulted to "office" until the first status fetch landed,
    // which caused e.g. cafe runs to briefly render with office agent roles,
    // office task rows, and office blocker copy. Prefer the backend's own
    // initialised values from the POST /runs response over the user selection.
    const params = new URLSearchParams({
      run_id: data.run_id,
      mode: state.mode,
      scenario: data.requested_environment || scenario.request.environment,
      team: data.resolved_team_type || state.team
    });
    const target = TARGET_BY_MODE[state.mode] || "dashboard.html";
    window.location.href = `${target}?${params.toString()}`;

  } catch (err) {
    clearTimeout(timeoutId);
    // Use the response we captured above (if any) so classifyError sees the status
    const resp = err._response || (response && !response.ok ? response : null);
    showError(classifyError(err, resp));
  } finally {
    state.launching = false;
    renderSteps();
    renderSummary();
  }
}

document.addEventListener("click", (event) => {
  const option = event.target.closest(".option-card[data-group]");
  if (option) {
    const group = option.dataset.group;
    const value = option.dataset.value;
    state[group] = value;
    renderAll();
    return;
  }

  const nextButton = event.target.closest(".step-continue[data-next]");
  if (nextButton && !nextButton.disabled) {
    state.currentStep = Number(nextButton.dataset.next);
    renderAll();
    return;
  }

  const backButton = event.target.closest(".secondary-btn[data-back]");
  if (backButton) {
    state.currentStep = Number(backButton.dataset.back);
    renderAll();
  }
});

launchFromStep.addEventListener("click", launchSimulation);
launchBtn.addEventListener("click", launchSimulation);

renderAll();
