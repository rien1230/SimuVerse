"""Builds the normalized config that each simulation run starts from."""

import random
from typing import Dict, Any, List, Optional

from app.core.exceptions import InvalidEnvironmentError, InvalidGoalError, InvalidTeamTypeError

# Environment and goal mapping
ENVIRONMENTS = {
    "office": {
        "description": "Workplace collaboration and negotiation tasks",
        "goals": {
            "complete_proposal": "office_proposal",
            "assign_roles": "office_roles"
        }
    },
    "cafe": {
        "description": "Casual coffee planning and social coordination",
        "goals": {
            "choose_restaurant": "cafe_restaurant"
        }
    },
    "escape_room": {
        "description": "High pressure teamwork to solve puzzles",
        "goals": {
            "solve_puzzle": "escape_puzzle"
        }
    }
}

ENVIRONMENT_ALIASES = {
    "office": "office",
    "cafe": "cafe",
    "escape": "escape_room",
    "escape_room": "escape_room",
}

DEFAULT_GOALS = {
    "office": "complete_proposal",
    "cafe": "choose_restaurant",
    "escape_room": "solve_puzzle",
}

GOAL_ALIASES = {
    "cafe": {
        "plan_vacation": "choose_restaurant",
    },
    "escape_room": {
        "find_exit_code": "solve_puzzle",
    },
}

# Team presets
TEAM_PRESETS = {
    "smooth": [
        {"E": 0.58, "A": 0.82, "N": 0.18},
        {"E": 0.50, "A": 0.86, "N": 0.16},
        {"E": 0.42, "A": 0.80, "N": 0.22},
        {"E": 0.56, "A": 0.78, "N": 0.24}
    ],
    "tension": [
        {"E": 0.62, "A": 0.20, "N": 0.82},
        {"E": 0.46, "A": 0.25, "N": 0.78},
        {"E": 0.38, "A": 0.18, "N": 0.86},
        {"E": 0.66, "A": 0.22, "N": 0.74}
    ],
    "creative": [
        {"E": 0.70, "A": 0.58, "N": 0.30},
        {"E": 0.62, "A": 0.52, "N": 0.34},
        {"E": 0.54, "A": 0.48, "N": 0.36},
        {"E": 0.68, "A": 0.56, "N": 0.28}
    ],
    "pressure": [
        {"E": 0.78, "A": 0.34, "N": 0.58},
        {"E": 0.72, "A": 0.30, "N": 0.60},
        {"E": 0.60, "A": 0.28, "N": 0.64},
        {"E": 0.82, "A": 0.32, "N": 0.56}
    ],
    "balanced": [
        {"E": 0.5, "A": 0.5, "N": 0.5},
        {"E": 0.5, "A": 0.5, "N": 0.5},
        {"E": 0.5, "A": 0.5, "N": 0.5},
        {"E": 0.5, "A": 0.5, "N": 0.5}
    ],
    "cooperative": [
        {"E": 0.6, "A": 0.8, "N": 0.2},
        {"E": 0.5, "A": 0.85, "N": 0.2},
        {"E": 0.4, "A": 0.75, "N": 0.3},
        {"E": 0.6, "A": 0.8, "N": 0.25}
    ],
    "tense": [
        {"E": 0.65, "A": 0.15, "N": 0.82},
        {"E": 0.50, "A": 0.28, "N": 0.78},
        {"E": 0.35, "A": 0.20, "N": 0.85},
        {"E": 0.70, "A": 0.18, "N": 0.76}
    ],
    "random": None
}

TEAM_STYLE_PERSONALITIES = {
    "smooth": ["Leader", "Easygoing", "Decisive", "Creative"],
    "tension": ["Skeptical", "Overthinker", "Skeptical", "Decisive"],
    "creative": ["Creative", "Overthinker", "Creative", "Easygoing"],
    "pressure": ["Leader", "Decisive", "Skeptical", "Overthinker"],
    "balanced": ["Leader", "Easygoing", "Skeptical", "Creative"],
    "cooperative": ["Leader", "Easygoing", "Easygoing", "Creative"],
    "tense": ["Leader", "Skeptical", "Overthinker", "Skeptical"],
}

EPISODE_MAX_TICKS = {
    "office": 25,
    "cafe": 20,
    "escape_room": 20,
}

TEAM_PRESET_LABELS = {
    "smooth": "smooth_team",
    "tension": "tension_team",
    "creative": "creative_team",
    "pressure": "pressure_team",
    "balanced": "balanced_team",
}


def canonical_team_preset(team_type: str) -> str:
    normalized = normalize_team_type(team_type)
    return TEAM_PRESET_LABELS.get(normalized, normalized)

TEAM_TYPE_ALIASES = {
    "smooth": "smooth",
    "cooperative": "smooth",
    "balanced": "balanced",
    "tension": "tension",
    "tense": "tension",
    "creative": "creative",
    "pressure": "pressure",
    "random": "random",
}

AVAILABLE_PERSONALITIES = [
    "Leader",
    "Decisive",
    "Easygoing",
    "Skeptical",
    "Overthinker",
    "Creative",
]


def normalize_team_type(team_type: str) -> str:
    key = str(team_type or "balanced").strip().lower()
    return TEAM_TYPE_ALIASES.get(key, key)


def normalize_environment(environment: str) -> str:
    key = str(environment or "").strip().lower()
    return ENVIRONMENT_ALIASES.get(key, key)


def default_goal_for_environment(environment: str) -> str:
    normalized_environment = normalize_environment(environment)
    if normalized_environment not in DEFAULT_GOALS:
        raise InvalidEnvironmentError(environment)
    return DEFAULT_GOALS[normalized_environment]


def normalize_goal(environment: str, goal: Optional[str]) -> Optional[str]:
    if goal is None:
        return None
    normalized_environment = normalize_environment(environment)
    goal_key = str(goal).strip().lower()
    return GOAL_ALIASES.get(normalized_environment, {}).get(goal_key, goal_key)


def resolve_team_personalities(team_type: str) -> List[str]:
    normalized = normalize_team_type(team_type)
    if normalized == "random":
        return [random.choice(AVAILABLE_PERSONALITIES) for _ in range(4)]
    return list(TEAM_STYLE_PERSONALITIES.get(normalized, TEAM_STYLE_PERSONALITIES["balanced"]))


def build_simulation_config(
    environment: str,
    goal: Optional[str] = None,
    team_type: str = "balanced",
) -> Dict[str, Any]:
    """Build the simulation configuration from user selections."""
    normalized_environment = normalize_environment(environment)
    if normalized_environment not in ENVIRONMENTS:
        raise InvalidEnvironmentError(environment)

    resolved_goal = normalize_goal(
        normalized_environment,
        goal or default_goal_for_environment(normalized_environment),
    )
    if resolved_goal not in ENVIRONMENTS[normalized_environment]["goals"]:
        raise InvalidGoalError(resolved_goal, normalized_environment)

    normalized_team_type = normalize_team_type(team_type)
    if normalized_team_type not in TEAM_PRESETS:
        raise InvalidTeamTypeError(team_type)

    scenario_id = ENVIRONMENTS[normalized_environment]["goals"][resolved_goal]

    if TEAM_PRESETS[normalized_team_type] is None:
        agents = [
            {
                "E": random.uniform(0.0, 1.0),
                "A": random.uniform(0.0, 1.0),
                "N": random.uniform(0.0, 1.0)
            }
            for _ in range(4)
        ]
    else:
        agents = [dict(agent) for agent in TEAM_PRESETS[normalized_team_type]]

    return {
        "environment": normalized_environment,
        "goal": resolved_goal,
        "team_type": team_type,
        "resolved_team_type": normalized_team_type,
        "team_preset": canonical_team_preset(normalized_team_type),
        "scenario_id": scenario_id,
        "agents": agents,
        "agent_personalities": resolve_team_personalities(normalized_team_type),
        "episode_max_ticks": EPISODE_MAX_TICKS.get(normalized_environment, 20),
        "min_events_per_tick": 0,
    }

def get_configuration_options() -> Dict[str, Any]:
    """Expose valid configuration options for the frontend."""
    return {
        "environments": ENVIRONMENTS,
        "team_presets": list(TEAM_PRESETS.keys())
    }
