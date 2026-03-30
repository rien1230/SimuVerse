# app/sim/scenario.py
from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class Scenario:
    environment: str
    id: str
    name: str
    description: str
    tasks: Dict[str, bool]           # e.g. {"budget": False, "requirements": False}
    knowledge_map: Dict[str, List[str]]  # agent_id -> list of tasks they know
    max_ticks: int = 20

    def complete_task(self, task: str) -> None:
        if task in self.tasks:
            self.tasks[task] = True

    def progress_ratio(self) -> float:
        done = sum(1 for v in self.tasks.values() if v)
        total = len(self.tasks)
        return done / total if total else 0.0

    def is_success(self) -> bool:
        return all(self.tasks.values())

    def outcome(self, tick: int) -> str:
        """Return 'success', 'partial', or 'failure' if ended, else 'running'."""
        if self.is_success():
            return "success"
        if tick >= self.max_ticks:
            return "partial" if self.progress_ratio() >= 0.5 else "failure"
        return "running"