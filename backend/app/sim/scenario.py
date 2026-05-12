"""Scenario state container for one run.

This file is the lightweight data object for scenario tasks and progress.
It does not decide behaviour — it just stores the scenario state.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Scenario:


    environment: str                       # which environment type this is (e.g. "office", "escape")
    id: str
    name: str
    description: str
    tasks: Dict[str, bool]                 # e.g. {"budget": False, "requirements": False}
    knowledge_map: Dict[str, List[str]]    # agent_id -> list of tasks they know about
    max_ticks: int = 20                    # how many simulation steps before the run is forced to end

    def complete_task(self, task: str) -> None:
        """Mark a task as done. Silently ignores unknown task names."""
        if task in self.tasks:
            self.tasks[task] = True

    def progress_ratio(self) -> float:
        """Returns what fraction of tasks are done, from 0.0 to 1.0."""
        done = sum(1 for v in self.tasks.values() if v)
        total = len(self.tasks)
        # Guard against dividing by zero if somehow there are no tasks
        return done / total if total else 0.0

    def is_success(self) -> bool:
        """Returns True only if every single task has been completed."""
        return all(self.tasks.values())

    def outcome(self, tick: int) -> str:

        if self.is_success():
            return "success"
        if tick >= self.max_ticks:
            # At least half done counts as partial rather than a full failure
            return "partial" if self.progress_ratio() >= 0.5 else "failure"
        return "running"
