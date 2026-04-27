"""
Domain-specific exceptions for

"""
from __future__ import annotations


class SimuVerseError(Exception):
    """Base class for all SimuVerse application errors."""


# ── Configuration errors ───────────────────────────────────────────────────

class ConfigurationError(SimuVerseError):
    """A simulation configuration value is invalid."""


class InvalidEnvironmentError(ConfigurationError):
    def __init__(self, environment: str) -> None:
        super().__init__(f"Unknown environment: '{environment}'")
        self.environment = environment


class InvalidGoalError(ConfigurationError):
    def __init__(self, goal: str, environment: str) -> None:
        super().__init__(f"Unknown goal '{goal}' for environment '{environment}'")
        self.goal = goal
        self.environment = environment


class InvalidTeamTypeError(ConfigurationError):
    def __init__(self, team_type: str) -> None:
        super().__init__(f"Unknown team type: '{team_type}'")
        self.team_type = team_type


# ── Run lifecycle errors ───────────────────────────────────────────────────

class RunError(SimuVerseError):
    """A problem with a simulation run's lifecycle."""


class RunAlreadyStoppedError(RunError):
    def __init__(self, run_id: str = "") -> None:
        msg = f"Run '{run_id}' is already stopped." if run_id else "Run is already stopped."
        super().__init__(msg)
        self.run_id = run_id


class RunNotFoundError(RunError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run '{run_id}' not found.")
        self.run_id = run_id
