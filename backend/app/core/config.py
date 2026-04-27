"""
Central configuration for SimuVerse backend.
Import settings from here rather than scattering numbers across files.
"""

# Simulation defaults
DEFAULT_EPISODE_MAX_TICKS: int = 120
DEFAULT_MIN_EVENTS_PER_TICK: int = 0
DEFAULT_SCENARIO_ID: str = "office_proposal"
DEFAULT_ENVIRONMENT: str = "office"

# Experiment defaults
DEFAULT_N_RUNS: int = 20
DEFAULT_EXPERIMENT_MAX_TICKS: int = 120
DEFAULT_INTERVENTION_TICK: int = 5

# Run history
RUNS_DIR_NAME: str = "data/runs"

# Emotion model
EMOTION_MODEL_ID: str = "tuhanasinan/go-emotions-distilbert-pytorch"
EMOTION_USE_GPU: bool = False
EMOTION_USE_RELIABLE_ONLY: bool = False

# Logging
LOG_LEVEL: str = "INFO"

# API
API_TITLE: str = "SimuVerse API"
API_VERSION: str = "1.0.0"
MAX_EXPERIMENT_RUNS: int = 100