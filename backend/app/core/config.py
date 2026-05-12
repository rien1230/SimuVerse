"""
Central configuration for SimuVerse backend.
Import settings from here rather than scattering magic numbers across files.

Central home for backend defaults and shared limits.
"""

# ── Simulation defaults ───────────────────────────────────────────────────
DEFAULT_EPISODE_MAX_TICKS: int = 120        # how many ticks a single run can last before it's force-stopped
DEFAULT_MIN_EVENTS_PER_TICK: int = 0        # minimum interaction events generated per tick (0 = natural)
DEFAULT_SCENARIO_ID: str = "office_proposal"
DEFAULT_ENVIRONMENT: str = "office"

# ── Experiment defaults ───────────────────────────────────────────────────
# Used by batch experiment helpers when a route does not supply an override.
DEFAULT_N_RUNS: int = 20                    # how many runs per experiment by default
DEFAULT_EXPERIMENT_MAX_TICKS: int = 120
DEFAULT_INTERVENTION_TICK: int = 5          # which tick to fire an intervention in comparison experiments

# ── Run history storage ───────────────────────────────────────────────────
RUNS_DIR_NAME: str = "data/runs"

# ── Emotion model config ──────────────────────────────────────────────────
EMOTION_MODEL_ID: str = "tuhanasinan/go-emotions-distilbert-pytorch"
EMOTION_USE_GPU: bool = False               # keeping this False so it runs on CPU without a GPU setup
EMOTION_USE_RELIABLE_ONLY: bool = False     # if True, only high-confidence emotion labels are kept

# ── Logging ───────────────────────────────────────────────────────────────
LOG_LEVEL: str = "INFO"

# ── API metadata ──────────────────────────────────────────────────────────
API_TITLE: str = "SimuVerse API"
API_VERSION: str = "1.0.0"
MAX_EXPERIMENT_RUNS: int = 100              # hard cap so a single request can't kick off hundreds of runs