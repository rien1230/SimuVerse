#Writes a summary of what happens in each tick/Run
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json


def _find_repo_root(start_file: Path) -> Path:
    """
    This function is to locate the repository root.
    """
    for parent in start_file.resolve().parents:
        if parent.name == "backend":
            return parent.parent

    #Goes up 3 levels if "backend" folder directory is  not found
    return start_file.resolve().parents[3]


@dataclass
class EventLogger:
    """
    Each run creates its own .jsonl file.
    Used JSON format because:
    - Each line is valid JSON
    - Easy to append new events
    - Human-readable and machine-parsable
    - Supports streaming/partial reading
    """

    run_id: str  # each simulation run has their own unique id in case of replays.
    base_dir: Optional[Path] = None

    def __post_init__(self) -> None:
        """
        Initialize the logger after the dataclass fields are set.

        Sets up the file path for this run's replay file.
        Creates the directory if it doesn't exist.
        """
        repo_root = _find_repo_root(Path(__file__))
        replays_dir = self.base_dir or (repo_root / "data" / "replays")
        # Create the directory if it doesn't exist and ensures it won't cause an error if it does.
        replays_dir.mkdir(parents=True, exist_ok=True)
        # Set the file path: data/replays/{run_id}.jsonl and using run_id in filename makes it easy to find specific replays.
        self.path: Path = replays_dir / f"{self.run_id}.jsonl"

    def start_new_replay(self, meta: Dict[str, Any]) -> None:
        """
        Writes the metadata header to start a new replay file.
        This overwrites any existing file with the same run_id, ensuring
        we start fresh for each run. The header contains important information
        needed for deterministic replay (seed, config, versions).
      """
        line = json.dumps(meta, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

        # Write the header line (mode "w" creates/overwrites the file)
        with self.path.open("w", encoding="utf-8") as f:
            f.write(line + "\n")

    def log(self, diff: Dict[str, Any]) -> None:
        """
        Appends one simulation tick's state diff to the replay file.

        Each call adds one line to the JSONL file. The diff contains:
        - Current tick number
        - Agent states
        - Relationship updates
        - Events that occurred

        """
        # Serialise the diff dictionary to JSON with same formatting as header.
        line = json.dumps(diff, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

        # Append the line to the replay file.
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")