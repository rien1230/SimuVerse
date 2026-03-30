import random
from typing import Dict, Any

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
            "plan_vacation": "cafe_vacation",
            "choose_restaurant": "cafe_restaurant"
        }
    },
    "escape_room": {
        "description": "High pressure teamwork to solve puzzles",
        "goals": {
            "find_exit_code": "escape_code",
            "solve_puzzle": "escape_puzzle"
        }
    }
}

# Team presets
TEAM_PRESETS = {
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
        {"E": 0.6, "A": 0.2, "N": 0.8},
        {"E": 0.5, "A": 0.3, "N": 0.7},
        {"E": 0.4, "A": 0.25, "N": 0.8},
        {"E": 0.7, "A": 0.2, "N": 0.75}
    ],
    "random": None
}

def build_simulation_config(environment: str, goal: str, team_type: str) -> Dict[str, Any]:
    """Build the simulation configuration from user selections."""
    if environment not in ENVIRONMENTS:
        raise ValueError(f"Invalid environment: {environment}")
    if goal not in ENVIRONMENTS[environment]["goals"]:
        raise ValueError(f"Invalid goal for {environment}: {goal}")
    if team_type not in TEAM_PRESETS:
        raise ValueError(f"Invalid team type: {team_type}")

    scenario_id = ENVIRONMENTS[environment]["goals"][goal]

    if TEAM_PRESETS[team_type] is None:
        agents = [
            {
                "E": random.uniform(0.0, 1.0),
                "A": random.uniform(0.0, 1.0),
                "N": random.uniform(0.0, 1.0)
            }
            for _ in range(4)
        ]
    else:
        agents = [dict(agent) for agent in TEAM_PRESETS[team_type]]

    return {
        "environment": environment,
        "goal": goal,
        "team_type": team_type,
        "scenario_id": scenario_id,
        "agents": agents
    }

def get_configuration_options() -> Dict[str, Any]:
    """Expose valid configuration options for the frontend."""
    return {
        "environments": ENVIRONMENTS,
        "team_presets": list(TEAM_PRESETS.keys())
    }