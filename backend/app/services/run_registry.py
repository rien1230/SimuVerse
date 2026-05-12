# backend/app/services/run_registry.py
# In-memory registry of live runs.
# RunManager handles one run; RunRegistry keeps track of all active runs.
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, List, Any
from threading import Lock
import time

from app.services.run_manager import RunManager


@dataclass
class RunEntry:
    """
    Container holding all information for a single simulation run ensuring everything needed to manage one run is in one place.
    """
    manager: RunManager  # The actual simulation controller
    lock: Lock  # Ensures only one thread steps this run at a time
    created_at: float  # When this run was created (timestamp)
    last_accessed: float  # When this run was last used (for cleanup)
    client_count: int = 0  # Number of active WebSocket connections


class RunRegistry:
    """
    Thread-safe registry for multiple concurrent runs.
    One instance per process (simple singleton).

    Purpose: Manages multiple simulation runs happening at the same time.
    This allows the web interface to have multiple simulations active, each with their own state, and prevents them from interfering with each other.
    """
    _instance: Optional["RunRegistry"] = None
    _instance_lock: Lock = Lock()

    def __new__(cls):
        """
        Singleton pattern implementation.
        Ensures only one RunRegistry exists in the entire application.
        Preventing having multiple registries that don't know about each other's runs.
        """
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False  # Mark as not initialized yet
            return cls._instance

    def __init__(self):
        """
        Initialize the registry (only called once due to singleton pattern).
        Sets up the internal data structures and configuration limits.
        """
        if self._initialized:
            return  # Already initialized (singleton pattern)

        self._runs: Dict[str, RunEntry] = {}  # Dictionary mapping run_id -> RunEntry
        self._runs_lock = Lock()  # Lock to protect the _runs dictionary (thread safety)
        self.max_active_runs = 20  # Maximum number of runs allowed at once
        self.idle_timeout_sec = 3600  # 1 hour - runs idle longer than this get cleaned up
        self._initialized = True  # Mark as initialized

    def create_run(self, seed: int, config: Optional[Dict[str, Any]] = None, owner: Optional[str] = None) -> str:
        """
        Create a new simulation run and add it to the registry.

        Steps:
        1. Clean up old idle runs
        2. If at max capacity, remove the oldest (least recently used) run
        3. Create a new RunManager with the given seed and config
        4. Create a RunEntry to hold it
        5. Add to registry and return the run_id

        Args:
            seed: Random seed for deterministic simulation
            config: Optional configuration overrides for the simulation

        Returns:
            str: The unique run_id for the newly created run
        """
        # This is where a live run first appears in backend memory.
        with self._runs_lock:  # Lock the registry to prevent race conditions
            self._cleanup_idle_locked()  # Remove runs that have been idle too long

            # If we're at maximum capacity, remove the least recently used run
            if len(self._runs) >= self.max_active_runs:
                # Find the run that was accessed least recently
                oldest_id = min(self._runs.items(), key=lambda kv: kv[1].last_accessed)[0]
                del self._runs[oldest_id]  # Remove it to make space

            # Create the new simulation run
            rm = RunManager(seed=seed, config=(config or {}), owner=owner)

            # Create an entry to store the run and its metadata
            entry = RunEntry(
                manager=rm,
                lock=Lock(),  # Each run gets its own lock
                created_at=time.time(),
                last_accessed=time.time(),  # Mark as just accessed
            )

            # Store in registry and return the ID
            self._runs[rm.run_id] = entry
            return rm.run_id

    def get_run(self, run_id: str) -> Optional[RunEntry]:
        """
        Retrieve a run from the registry by its ID.

        Also updates the last_accessed timestamp to mark the run as "in use".
        This prevents it from being cleaned up as an idle run.

        Args:
            run_id: The unique identifier of the run to retrieve

        Returns:
            Optional[RunEntry]: The run entry if found, None otherwise
        """
        with self._runs_lock:
            entry = self._runs.get(run_id)
            if entry:
                entry.last_accessed = time.time()  # Update access time
            return entry

    def delete_run(self, run_id: str) -> bool:
        """
        Remove a run from the registry.

        Note: This only removes it from the registry, not from disk.
        The replay file on disk remains for later analysis.

        Args:
            run_id: The unique identifier of the run to remove

        """
        with self._runs_lock:
            # pop removes the key if it exists, returns None if not found
            return self._runs.pop(run_id, None) is not None

    def list_runs(self) -> List[Dict[str, Any]]:
        """Return a summary dict for every active run (id, status, tick, client count)."""
        with self._runs_lock:
            out: List[Dict[str, Any]] = []
            for run_id, entry in self._runs.items():
                # Gets the  current tick from the model (if it is available).
                tick = getattr(entry.manager.model, "tick", 0)
                out.append(
                    {
                        "run_id": run_id,
                        "status": entry.manager.status,
                        "seed": entry.manager.seed,
                        "tick": tick,
                        "created_at": entry.created_at,
                        "last_accessed": entry.last_accessed,
                        "clients": entry.client_count,
                        "config": entry.manager.config,
                    }
                )
            return out

    def _cleanup_idle_locked(self) -> None:
        """
        Internal method to remove runs that haven't been accessed in a while.
        This prevents memory leaks from runs that were started but never cleaned up.
        Called automatically when creating new runs or on a timer (if implemented).
        Note: Must be called with _runs_lock already held.
        """
        now = time.time()
        # Find runs that haven't been accessed for longer than idle_timeout_sec.
        dead = [
            run_id
            for run_id, entry in self._runs.items()
            if (now - entry.last_accessed) > self.idle_timeout_sec
        ]
        # Removes them from the registry.
        for run_id in dead:
            del self._runs[run_id]
