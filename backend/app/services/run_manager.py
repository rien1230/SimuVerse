# Manages one simulation run. starting + pausing + stepping + logging everything for replay.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Literal
import time
import uuid
import sys
import mesa
from app.sim.model import SimModel
from app.services.event_logger import EventLogger

# Define possible states for the simulation run.
RunStatus = Literal["idle", "running", "paused", "stopped"]

SIMUVERSION = "0.3.0"
SCHEMA_VERSION = 1


@dataclass
class RunManager:
    """
    Manages the lifecycle of a single simulation run.

    Responsibilities:
    - Creates and configures the simulation model
    - Manages run states: idle + running + paused + stopped
    - Executes simulation ticks deterministically
    - Logs all events for replay capability
    - Handles automatic stopping conditions

    """

    seed: int  # Random seed for deterministic simulation

    # Config captured for replay determinism
    config: Dict[str, Any] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: RunStatus = "idle"  # Current state of the run
    model: SimModel = field(init=False)
    logger: EventLogger = field(init=False)  # Handles logging for replay

    def __post_init__(self) -> None:
        """
        Initialises the RunManager after dataclass fields are set.

        This is where I:
        1. Set up default configuration
        2. Create the simulation model
        3. Initialise the event logger
        4. Write metadata header for replay file
        """
        # DEBUG: Print what's received
        print(f"\n=== RunManager __post_init__ ===")
        print(f"Seed: {self.seed}")
        print(f"Original config: {self.config}")

        # Default configuration values (Milestone 2/3)
        defaults = {
            "min_events_per_tick": 2,  # Minimum events to generate per tick
            "episode_max_ticks": 120,  # Maximum ticks before auto-stop
        }

        # Merge configurations: user-provided values override defaults
        merged = {**defaults, **(self.config or {})}
        self.config = merged

        # DEBUG: Print merged config
        print(f"Merged config: {self.config}")
        print(f"Config keys: {list(self.config.keys())}")
        print(f"Environment value: {self.config.get('environment', 'NOT FOUND')}")

        # Create the simulation model with the seed and merged config
        # This is where the actual agent-based simulation is instantiated
        print(f"Creating SimModel with seed={self.seed} and config={self.config}")
        try:
            self.model = SimModel(seed=self.seed, **self.config)
            print(f" SimModel created successfully")
        except Exception as e:
            print(f" Failed to create SimModel: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise

        # Initialise the event logger for this specific run
        self.logger = EventLogger(run_id=self.run_id)

        # Write metadata header to the replay file FIRST and including all information needed for deterministic replay.
        self.logger.start_new_replay(
            meta={
                "type": "run_meta",  # Identifies this as metadata line
                "schema_version": SCHEMA_VERSION,  # For compatibility checks
                "sim_version": SIMUVERSION,  # SimuVerse version
                "run_id": self.run_id,  # Unique identifier for this run
                "seed": self.seed,  # Random seed used
                "config": self.config,  # Complete configuration
                "python": sys.version.split()[0],  # Python version (major.minor)
                "mesa": getattr(mesa, "__version__", "unknown"),  # Mesa framework version
            }
        )
        print(f" RunManager initialization complete for run_id: {self.run_id}\n")

    # The different type of simulation run state:

    def start(self) -> None:
        """
        Start or resume the simulation run.

        Raises:
            RuntimeError: If trying to start a stopped run
        """
        if self.status == "stopped":
            raise RuntimeError("Run is stopped. Create a new RunManager for a new run.")
        # idle -> running, paused -> running (resume)
        self.status = "running"

    def pause(self) -> None:
        """
        Pause the simulation run.

        Only transitions from 'running' to 'paused' and other states would remain unchanged.
        """
        # running -> paused
        if self.status == "running":
            self.status = "paused"

    def stop(self) -> None:
        """
        Stop the simulation run.
        Can be called from any state to force stop (So,run can't be restarted at all).
        """
        # any -> stopped
        self.status = "stopped"

    # One deterministic tick:

    def step(self) -> Dict[str, Any]:
        """
        Execute one simulation tick (time step).

        This is the core method that advances the simulation.
        It:
        1. Advances the model by one tick
        2. Captures the state changes (diff)
        3. Logs the diff for replay
        4. Updates run status if episode ended

        Returns:
            Dictionary containing the state diff for this tick

        Raises:
            RuntimeError: If run is stopped or model produces no diff
        """
        if self.status == "stopped":
            raise RuntimeError("Run is stopped. Create a new RunManager for a new run.")
        # Allow manual stepping from idle/paused too. Allowing users step through paused simulations
        if self.status == "idle":
            self.status = "paused"

        # Advances the simulation model by one tick
        ret = self.model.step()

        # Extract the state diff from the model
        if isinstance(ret, dict):
            diff = ret
        else:
            diff = getattr(self.model, "last_diff", None)

        # Ensures that there is a diff
        if diff is None:
            raise RuntimeError("Model produced no diff. Check SimModel.step sets self.last_diff.")

        # Log one JSONL line for determinism + replay capability (enables exact replay of simulations)
        self.logger.log(diff)

        # Auto-stop: this happens when episode_max_ticks is reached or other end conditions
        if diff.get("ended") is True:
            self.status = "stopped"

        return diff

    # Optional: run continuously (useful later for websocket "play")
    def run_loop(self, max_steps: Optional[int] = None, tick_hz: Optional[float] = None) -> None:
        """
        Run the simulation continuously (not single-step).

        This method is useful for:
        - Automated testing
        - WebSocket streaming with auto-play
        - Batch processing

        Args:
            max_steps: Maximum number of ticks to run (None = unlimited)
            tick_hz: Simulation speed in ticks per second (None = as fast as possible)

        Raises:
            RuntimeError: If run is not in 'running' state
        """
        if self.status != "running":
            raise RuntimeError("Call start() before run_loop().")

        steps_done = 0
        # Calculate sleep time between ticks if tick_hz is specified
        sleep_s = (1.0 / tick_hz) if (tick_hz and tick_hz > 0) else 0.0

        # Main simulation loop
        while self.status == "running":
            d = self.step()  # Execute one tick
            steps_done += 1

            # Check if episode ended
            if d.get("ended") is True:
                self.status = "stopped"
                break

            # Check if we've reached max steps
            if max_steps is not None and steps_done >= max_steps:
                self.pause()
                break

            # Control simulation speed if tick_hz is specified
            if sleep_s > 0:
                time.sleep(sleep_s)