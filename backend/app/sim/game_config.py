"""
Game balance constants — all tuning values live here so they're easy to find and adjust.

Rather than scattering magic numbers across model.py and behaviour files, everything
that controls how the simulation feels (stress, trust, tension, challenge rates, etc.)
is centralised here. If the simulation feels off, this is the first place to look.

This is the main balancing file for the simulation.
"""
from typing import Dict, List, Tuple

# ── Stress caps per (scenario_type, team_preset) ─────────────────────────────
# Hard ceiling on how stressed any agent can get in a given scenario + team combo.
# Escape room scenarios allow much higher stress because urgency is part of the theme.
STRESS_CAPS: Dict[Tuple[str, str], float] = {
    ("office", "smooth_team"):   0.24,
    ("office", "balanced_team"): 0.35,
    ("office", "tension_team"):  0.42,
    ("office", "creative_team"): 0.36,
    ("office", "pressure_team"): 0.36,

    ("cafe", "smooth_team"):   0.23,
    ("cafe", "balanced_team"): 0.20,
    ("cafe", "tension_team"):  0.33,
    ("cafe", "creative_team"): 0.32,
    ("cafe", "pressure_team"): 0.42,

    ("escape", "smooth_team"):   0.46,
    ("escape", "balanced_team"): 0.56,
    ("escape", "tension_team"):  0.65,
    ("escape", "creative_team"): 0.52,
    ("escape", "pressure_team"): 0.58,
}

# ── Initial group state (tension, cohesion) per team preset ───────────────────
# Seeds group_tension and group_cohesion before scenario offsets are applied.
# Values are derived from the balanced_team baseline (0.20, 0.55) plus small
# per-preset deltas applied once at model initialisation:
#   smooth_team:   −0.05 tension, +0.08 cohesion
#   balanced_team:  0.00 tension,  0.00 cohesion  (reference)
#   creative_team: +0.02 tension, +0.04 cohesion
#   pressure_team: +0.06 tension, −0.04 cohesion
#   tension_team:  +0.10 tension, −0.08 cohesion
# Scenario env_mod offsets (initial_tension_delta / initial_cohesion_delta) are
# applied on top of these values in model.py.  Pressure is unaffected here.
PRESET_INITIAL_STATE: Dict[str, Tuple[float, float]] = {
    "smooth_team":   (0.15, 0.63),   # baseline −0.05 tension, +0.08 cohesion
    "balanced_team": (0.20, 0.55),   # reference — no change
    "creative_team": (0.22, 0.59),   # baseline +0.02 tension, +0.04 cohesion
    "pressure_team": (0.26, 0.51),   # baseline +0.06 tension, −0.04 cohesion
    "tension_team":  (0.30, 0.47),   # baseline +0.10 tension, −0.08 cohesion
}

# ── Residual tension floors ───────────────────────────────────────────────────
# Prevent perfect 0.00 tension even after successful, calm runs.
# Applied every tick in _update_group_state as max(team_floor, scenario_floor).
# Tension Team / Pressure Team have elevated floors because their starting
# character means some ambient friction always remains.
# final floor = max(PRESET_TENSION_FLOOR[team], SCENARIO_TENSION_FLOOR[scenario])
PRESET_TENSION_FLOOR: Dict[str, float] = {
    "smooth_team":   0.00,   # scenario floor dominates
    "balanced_team": 0.00,
    "creative_team": 0.00,
    "pressure_team": 0.10,
    "tension_team":  0.12,
}

SCENARIO_TENSION_FLOOR: Dict[str, float] = {
    "cafe":   0.02,
    "office": 0.03,
    "escape": 0.08,
}

# ── Trust deltas per team preset ─────────────────────────────────────────────
# Added on top of trait-derived initial trust for each agent pair.
# How much to bump (or drop) initial trust between agents based on their team preset.
# These deltas are added on top of each agent pair's trait-derived starting trust.
# Negative values mean the team starts out more suspicious of each other.
PRESET_TRUST_DELTA: Dict[str, float] = {
    "smooth_team":   0.12,
    "balanced_team": 0.00,
    "creative_team": 0.06,
    "pressure_team": -0.08,
    "tension_team":  -0.15,
}

# ── Initial stress seeds per team preset ─────────────────────────────────────
# Base stress value before scenario delta and per-agent noise are applied.
# Starting stress value before the scenario offset and per-agent noise are applied.
# Pressure and tension teams begin noticeably more stressed, which affects their
# early dialogue choices and how quickly conflicts escalate.
PRESET_STRESS_SEED: Dict[str, float] = {
    "smooth_team":   0.06,
    "balanced_team": 0.11,
    "creative_team": 0.09,
    "pressure_team": 0.22,
    "tension_team":  0.26,
}

# ── Trust caps per scenario environment ──────────────────────────────────────
# Prevents trust from rising unrealistically high in low-stakes scenarios.
# Maximum trust any agent pair can reach, capped per environment.
# Escape room has the highest cap because shared urgency bonds teams quickly.
TRUST_CAPS: Dict[str, float] = {
    "office": 0.82,
    "cafe":   0.78,   # warm cooperation encouraged — let trust build naturally
    "escape": 0.85,
}

# ── Challenge probability bias per team preset ───────────────────────────────
# Direct multiplier on the base challenge-event probability in each scenario.
# Tension/pressure teams escalate faster; smooth teams de-escalate naturally.
# Multiplier on the base probability of a challenge event firing each tick.
# 1.0 = balanced_team baseline. Values above 1 mean more frequent challenges.
PRESET_CHALLENGE_BIAS: Dict[str, float] = {
    "smooth_team":   0.55,
    "balanced_team": 1.00,
    "creative_team": 0.80,
    "pressure_team": 1.30,
    "tension_team":  1.60,
}

# ── Agree/compromise probability bias per team preset ────────────────────────
# Direct multiplier on the base agree/compromise probability in each scenario.
# Smooth teams converge easily; tension teams resist agreement longer.
# Multiplier on the base probability of agree/compromise events.
# Pairs nicely with PRESET_CHALLENGE_BIAS — tension teams both challenge more AND agree less.
PRESET_AGREE_BIAS: Dict[str, float] = {
    "smooth_team":   1.50,
    "balanced_team": 1.00,
    "creative_team": 1.20,
    "pressure_team": 0.80,
    "tension_team":  0.60,
}

# ── Outcome label taxonomy ────────────────────────────────────────────────────
# Human-readable run outcome strings produced by classify_run_outcome().
# Listed here so the frontend and exports can reference canonical values.
# All possible outcome strings that classify_run_outcome() can produce.
# Listed here as a reference so the frontend knows what values to expect,
# and so we don't accidentally produce an unlisted label by typo.
OUTCOME_LABELS: List[str] = [
    "In progress",
    "Completed smoothly — high-trust cooperative run",
    "Completed smoothly — low-stress cooperative run",
    "Completed cooperatively",
    "Completed after intervention",
    "Completed with moderate friction",
    "Completed under moderate pressure",
    "Completed under pressure — intervention helped",
    "Completed with tension — high conflict run",
    "Completed with tension — intervention helped",
    "Partial completion",
    "Partial completion — high friction",
    "Partial completion after intervention",
    "Incomplete — unresolved blocker",
    "Incomplete — high conflict",
]
