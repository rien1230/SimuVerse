"""
Domain-specific exceptions

Raise these instead of bare ValueError / RuntimeError so callers
can catch specific failure modes rather than catching everything.

"""
from __future__ import annotations


class SimuVerseError(Exception):
    """Base class for all application errors."""


# ── Configuration errors ───────────────────────────────────────────────────

class ConfigurationError(SimuVerseError):
    """A simulation configuration value is invalid."""


class InvalidEnvironmentError(ConfigurationError):
    """Raised when the user requests an environment name that doesn't exist (e.g. typo)."""
    def __init__(self, environment: str) -> None:
        super().__init__(f"Unknown environment: '{environment}'")
        # Store the bad value so callers can include it in error responses
        self.environment = environment


class InvalidGoalError(ConfigurationError):
    """Raised when a goal doesn't belong to the chosen environment."""
    def __init__(self, goal: str, environment: str) -> None:
        super().__init__(f"Unknown goal '{goal}' for environment '{environment}'")
        self.goal = goal
        self.environment = environment


class InvalidTeamTypeError(ConfigurationError):
    """Raised when a team_type string doesn't match any known preset."""
    def __init__(self, team_type: str) -> None:
        super().__init__(f"Unknown team type: '{team_type}'")
        self.team_type = team_type


# ── Run lifecycle errors ───────────────────────────────────────────────────

class RunError(SimuVerseError):
    """A problem with a simulation run's lifecycle."""


class RunAlreadyStoppedError(RunError):
    """Raised when a caller tries to step or restart a run that has already stopped."""
    def __init__(self, run_id: str = "") -> None:
        # Include the run_id in the message if we have one, otherwise keep it generic
        msg = f"Run '{run_id}' is already stopped." if run_id else "Run is already stopped."
        super().__init__(msg)
        self.run_id = run_id


class RunNotFoundError(RunError):
    """Raised when a run_id is not present in the registry (was never created, or was cleaned up)."""
    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run '{run_id}' not found.")
        self.run_id = run_id
