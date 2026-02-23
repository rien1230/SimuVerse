const API = "http://127.0.0.1:8000/api";

// Main app state
const state = {
  run_id: null,
  status: "idle",
  seed: null,
  config: null,
  view: "dual",
  ws: null,
  lastDiff: null,
  agentColor: new Map(),
  mode: "quick",
  scenario: "classroom",
  runCode: "SV-4F82X",
  hasActiveRun: false
};

// Helper functions
function $(id) { return document.getElementById(id); }

// Generate random run code (for display only)
function generateRunCode() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789";
  let code = "SV-";
  for (let i = 0; i < 5; i++) {
    code += chars[Math.floor(Math.random() * chars.length)];
  }
  return code;
}

// Switch between screens
function setScreen(name) {
  if (name === 'home' && state.run_id && state.status === 'running') {
    showExitModal(name);
    return;
  }

  for (const el of document.querySelectorAll(".screen")) {
    el.classList.remove("active");
  }
  $(`screen-${name}`).classList.add("active");

  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.remove('active');
    if (link.textContent.toLowerCase() === name) {
      link.classList.add('active');
    }
  });

  if (name === 'setup') {
    state.runCode = generateRunCode();
    if ($("runIdDisplay")) {
      $("runIdDisplay").textContent = state.runCode;
    }
  }
}

// Navigate to simulation run page
function goToSimulationRun(runId, scenario, mode) {
  window.location.href = `simulation-run.html?id=${runId}&scenario=${scenario}&mode=${mode}`;
}

// Show exit warning modal
function showExitModal(targetScreen) {
  const modal = $('exitWarning');
  modal.style.display = 'flex';

  $('exitCancel').onclick = () => {
    modal.style.display = 'none';
  };

  $('exitConfirm').onclick = () => {
    modal.style.display = 'none';
    state.run_id = null;
    state.status = 'idle';
    state.hasActiveRun = false;
    runPill();
    setScreen(targetScreen);
  };
}

// Switch view mode (for workspace - for backward compatibility)
function setView(name) {
  state.view = name;
  for (const el of document.querySelectorAll(".view")) {
    el.classList.remove("active");
  }
  $(`view-${name}`).classList.add("active");
}

function pillStatus(text) {
  state.status = text;
  if ($("statusPill")) $("statusPill").textContent = text;
}

function runPill() {
  if ($("runPill")) {
    $("runPill").textContent = state.run_id ? `run: ${state.run_id.slice(0,6)}` : "run: —";
  }
}

// API helpers
async function apiPost(path, body = null) {
  const url = `${API}${path}`;
  console.log(`POST ${url}`, body);

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: body ? JSON.stringify(body) : null,
    });

    console.log("Response status:", res.status);

    if (!res.ok) {
      const errorText = await res.text();
      console.error("Error response:", errorText);
      throw new Error(`${res.status}: ${errorText}`);
    }

    const data = await res.json();
    console.log("Response data:", data);
    return data;

  } catch (err) {
    console.error("Fetch error:", err);
    throw err;
  }
}

async function apiGet(path) {
  const url = `${API}${path}`;
  console.log(`GET ${url}`);

  try {
    const res = await fetch(url);
    console.log("Response status:", res.status);

    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`${res.status}: ${errorText}`);
    }

    const data = await res.json();
    return data;

  } catch (err) {
    console.error("Fetch error:", err);
    throw err;
  }
}

// Create quick simulation with defaults
async function createQuickSimulation() {
  try {
    // Show loading state
    if ($("quickStartBtn")) {
      $("quickStartBtn").textContent = "Creating...";
      $("quickStartBtn").disabled = true;
    }

    console.log("Creating quick simulation via backend");

    // Get scenario from dropdown
    const scenario = $("scenarioSelect")?.value || "classroom";

    // Generate a random seed
    const seed = Math.floor(Math.random() * 10000);

    // Configuration that matches what RunManager expects
    const config = {
      min_events_per_tick: 2,
      episode_max_ticks: 120
    };

    console.log("Sending to backend - seed:", seed, "config:", config);

    // Make API call to create a real run
    const out = await apiPost("/runs", {
      seed: seed,
      config: config
    });

    console.log("Backend response:", out);

    // Get the real run ID from backend
    const realRunId = out.run_id;

    if (!realRunId) {
      throw new Error("Backend didn't return a run_id");
    }

    // Update state
    state.run_id = realRunId;
    state.seed = seed;
    state.config = config;
    state.mode = "quick";
    state.hasActiveRun = true;

    // Navigate to simulation run page with REAL run ID
    goToSimulationRun(realRunId, scenario, "Quick");

  } catch(err) {
    console.error("Error creating simulation:", err);
    alert("Error creating simulation: " + err.message);
    if ($("quickStartBtn")) {
      $("quickStartBtn").textContent = "Start Simulation";
      $("quickStartBtn").disabled = false;
    }
  }
}

// Create advanced simulation (now just creates a run with same config)
async function createAdvancedSimulation() {
  try {
    // Show loading state
    if ($("advancedSetupBtn")) {
      $("advancedSetupBtn").textContent = "Creating...";
      $("advancedSetupBtn").disabled = true;
    }

    console.log("Creating advanced simulation via backend");

    const seed = Math.floor(Math.random() * 10000);
    const scenario = $("scenarioSelect")?.value || "classroom";

    // Configuration that matches what RunManager expects
    const config = {
      min_events_per_tick: 2,
      episode_max_ticks: 120
    };

    console.log("Sending to backend - seed:", seed, "config:", config);

    // Make API call to create a real run
    const out = await apiPost("/runs", {
      seed: seed,
      config: config
    });

    console.log("Backend response:", out);

    const realRunId = out.run_id;

    if (!realRunId) {
      throw new Error("Backend didn't return a run_id");
    }

    // Update state
    state.run_id = realRunId;
    state.seed = seed;
    state.config = config;
    state.mode = "advanced";
    state.hasActiveRun = true;

    // Navigate to simulation run page with REAL run ID
    goToSimulationRun(realRunId, scenario, "Advanced");

  } catch(err) {
    console.error("Error creating simulation:", err);
    alert("Error creating simulation: " + err.message);
    if ($("advancedSetupBtn")) {
      $("advancedSetupBtn").textContent = "Configure Settings";
      $("advancedSetupBtn").disabled = false;
    }
  }
}

// Initialise when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
  console.log('DOM loaded - initializing app');

  // === HOME SCREEN BUTTONS ===
  if ($("heroGetStarted")) {
    $("heroGetStarted").onclick = () => setScreen("consent");
  }

  if ($("navGetStarted")) {
    $("navGetStarted").onclick = () => setScreen("consent");
  }

  // Card CTA buttons
  document.querySelectorAll('.card-cta').forEach(btn => {
    btn.onclick = () => setScreen('consent');
  });

  // === CONSENT SCREEN LOGIC ===
  const checkboxes = [
    $("check1"), $("check2"), $("check3"), $("check4"), $("check5")
  ];

  function updateConsentButton() {
    const allChecked = checkboxes.every(cb => cb && cb.checked);
    if ($("consentContinue")) {
      $("consentContinue").disabled = !allChecked;
    }
  }

  checkboxes.forEach(cb => {
    if (cb) cb.onchange = updateConsentButton;
  });

  // Consent Continue button
  if ($("consentContinue")) {
    $("consentContinue").onclick = () => setScreen("setup");
  }

  // Consent Exit button
  if ($("consentExit")) {
    $("consentExit").onclick = () => setScreen("home");
  }

  // === SETUP SCREEN BUTTONS ===

  // Quick Mode button
  if ($("quickStartBtn")) {
    $("quickStartBtn").onclick = async () => {
      state.scenario = $("scenarioSelect")?.value || "classroom";
      state.runCode = $("runIdDisplay")?.textContent || generateRunCode();
      await createQuickSimulation();
    };
  }

  // Advanced Mode button - NOW CREATES SIMULATION DIRECTLY
  if ($("advancedSetupBtn")) {
    $("advancedSetupBtn").onclick = async () => {
      state.scenario = $("scenarioSelect")?.value || "classroom";
      state.runCode = $("runIdDisplay")?.textContent || generateRunCode();
      await createAdvancedSimulation();
    };
  }

  // Regenerate Run ID
  if ($("regenerateRunId")) {
    $("regenerateRunId").onclick = () => {
      state.runCode = generateRunCode();
      if ($("runIdDisplay")) {
        $("runIdDisplay").textContent = state.runCode;
      }
    };
  }

  // Back to Consent
  if ($("backToConsent")) {
    $("backToConsent").onclick = () => setScreen("consent");
  }

  // === NAVIGATION LINKS ===
  if ($("navHome")) {
    $("navHome").onclick = () => {
      if (state.hasActiveRun && state.status === "running") {
        showExitModal('home');
      } else {
        setScreen('home');
      }
    };
  }

  if ($("navAbout")) {
    $("navAbout").onclick = () => setScreen('about');
  }

  if ($("navContact")) {
    $("navContact").onclick = () => setScreen('contact');
  }

  // About and Contact back buttons
  if ($("backHomeFromAbout")) {
    $("backHomeFromAbout").onclick = () => setScreen('home');
  }

  if ($("backHomeFromContact")) {
    $("backHomeFromContact").onclick = () => setScreen('home');
  }

  // Initialise
  setScreen("home");
  if ($("statusPill")) pillStatus("idle");
  runPill();
});