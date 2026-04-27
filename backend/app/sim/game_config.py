"""Game balance constants — single source of truth for all tuning values."""
from typing import Dict, Tuple

# ── Stress caps per (scenario_type, team_preset) ─────────────────────────────
# Prevents agent stress from exceeding scenario-appropriate ceilings.
STRESS_CAPS: Dict[Tuple[str, str], float] = {
    ("office", "smooth_team"):   0.24,
    ("office", "tension_team"):  0.42,
    ("office", "creative_team"): 0.36,
    ("office", "pressure_team"): 0.36,

    ("cafe", "smooth_team"):   0.15,
    ("cafe", "tension_team"):  0.30,
    ("cafe", "creative_team"): 0.24,
    ("cafe", "pressure_team"): 0.34,

    ("escape", "smooth_team"):   0.38,
    ("escape", "tension_team"):  0.65,
    ("escape", "creative_team"): 0.52,
    ("escape", "pressure_team"): 0.58,
}

# ── Initial group state (tension, cohesion) per team preset ───────────────────
# Seeds group_tension and group_cohesion before scenario offsets are applied.
PRESET_INITIAL_STATE: Dict[str, Tuple[float, float]] = {
    "smooth_team":   (0.08, 0.75),
    "balanced_team": (0.20, 0.55),
    "creative_team": (0.15, 0.62),
    "pressure_team": (0.38, 0.35),
    "tension_team":  (0.50, 0.28),
}

# ── Trust deltas per team preset ─────────────────────────────────────────────
# Added on top of trait-derived initial trust for each agent pair.
PRESET_TRUST_DELTA: Dict[str, float] = {
    "smooth_team":   0.12,
    "balanced_team": 0.00,
    "creative_team": 0.06,
    "pressure_team": -0.08,
    "tension_team":  -0.15,
}

# ── Initial stress seeds per team preset ─────────────────────────────────────
# Base stress value before scenario delta and per-agent noise are applied.
PRESET_STRESS_SEED: Dict[str, float] = {
    "smooth_team":   0.06,
    "balanced_team": 0.11,
    "creative_team": 0.09,
    "pressure_team": 0.22,
    "tension_team":  0.26,
}

# ── Trust caps per scenario environment ──────────────────────────────────────
# Prevents trust from rising unrealistically high in low-stakes scenarios.
TRUST_CAPS: Dict[str, float] = {
    "office": 0.82,
    "cafe":   0.60,   # low-stakes social scene — keep trust in a steady band
    "escape": 0.85,
}
