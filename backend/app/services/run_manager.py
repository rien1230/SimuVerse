# Manages one simulation run: starting, pausing, stepping, and logging everything for replay.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Literal
import logging
import time
import uuid
import sys

logger = logging.getLogger(__name__)

import mesa

from app.sim.model import SimModel
from app.sim.agent_builder import apply_personality_to_agent, build_agent_traits
from app.services.event_logger import EventLogger
from app.services.run_history_service import save_run

# Define possible states for the simulation run.
RunStatus = Literal["idle", "running", "paused", "stopped"]

SIMUVERSION = "0.3.0"
SCHEMA_VERSION = 1


@dataclass
class RunManager:
    """
    One RunManager per simulation run — holds the model, status, config,
    and event logger. Controls start/pause/step/stop and writes to history
    when the run finishes.
    """

    seed: int  # Random seed for deterministic simulation

    # Config captured for replay determinism
    config: Dict[str, Any] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: RunStatus = "idle"  # Current state of the run
    model: SimModel = field(init=False)
    logger: EventLogger = field(init=False)  # Handles logging for replay
    history_saved: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        """
        Called automatically after __init__ by the dataclass machinery.
        Sets defaults, builds SimModel, applies personality/team settings,
        starts the event logger, and writes the replay metadata header.
        """
        logger.debug("RunManager init — seed=%s config=%s", self.seed, self.config)

        # Default configuration values
        defaults = {
            "min_events_per_tick": 0,
            "episode_max_ticks": 120,
            "environment": "office",
            "scenario_id": "office_proposal",
            "use_nlp": False,
            "team_type": None,
            "team_preset": None,
        }

        # Merge configurations: user-provided values override defaults
        merged = {**defaults, **(self.config or {})}
        self.config = merged

        logger.debug(
            "RunManager merged config — env=%s scenario=%s",
            self.config.get("environment"),
            self.config.get("scenario_id"),
        )

        # Only pass arguments that SimModel actually accepts.
        # Keep the full config for replay metadata, but filter what goes into the model.
        sim_config = {
            "min_events_per_tick": self.config.get("min_events_per_tick", 2),
            "episode_max_ticks": self.config.get("episode_max_ticks", 120),
            "environment": self.config.get("environment", "office"),
            "scenario_id": self.config.get("scenario_id", "office_proposal"),
            "use_nlp": self.config.get("use_nlp", False),
            "team_type": None,
            "team_preset": None,
        }

        # Create the simulation model with the filtered config
        try:
            self.model = SimModel(seed=self.seed, **sim_config)
            logger.debug("SimModel created — run_id=%s", self.run_id)
        except Exception as e:
            logger.exception("Failed to create SimModel: %s", e)
            raise

        # Align frontend-created runs with the same deterministic personality
        # application path used by test_personalities.py.
        scenario_type = self.config.get("environment", "office")
        if scenario_type == "escape_room":
            scenario_type = "escape"
        self.model.scenario_type = scenario_type
        self.model.team_type = self.config.get("resolved_team_type") or self.config.get("team_type")
        self.model.team_preset = self.config.get("team_preset") or self.model.team_preset
        self.model.conflict_score = 0.0
        self.model.coord_pressure_score = 0.0

        personalities = list(self.config.get("agent_personalities") or [])
        if personalities:
            for index, agent in enumerate(sorted(self.model.agents, key=lambda a: a.public_id)):
                personality = personalities[index] if index < len(personalities) else "Easygoing"
                apply_personality_to_agent(agent, personality)
                traits, _ = build_agent_traits(
                    self.config.get("scenario_id", "office_proposal"),
                    agent_id=agent.public_id,
                    personality=personality,
                    add_noise=False,
                )
                for key, value in traits.items():
                    setattr(agent, key, value)
                    agent.traits[key] = value

        # Initialise the event logger for this specific run
        self.logger = EventLogger(run_id=self.run_id)

        # Write metadata header to the replay file first
        self.logger.start_new_replay(
            meta={
                "type": "run_meta",
                "schema_version": SCHEMA_VERSION,
                "sim_version": SIMUVERSION,
                "run_id": self.run_id,
                "seed": self.seed,
                "config": self.config,          # full config from route/services
                "sim_config": sim_config,       # actual config passed to SimModel
                "python": sys.version.split()[0],
                "mesa": getattr(mesa, "__version__", "unknown"),
            }
        )
        logger.debug("RunManager ready — run_id=%s", self.run_id)

    def start(self) -> None:
        """Move status to running. Raises if the run is already stopped."""
        if self.status == "stopped":
            raise RuntimeError("Run is stopped. Create a new RunManager for a new run.")
        self.status = "running"

    def pause(self) -> None:
        """Switch from running to paused. Ignored if already paused or stopped."""
        if self.status == "running":
            self.status = "paused"

    def stop(self) -> None:
        """Force status to stopped and save to history if any ticks ran."""
        self.status = "stopped"
        if self.model.tick > 0:
            self._persist_history_once()

    def _persist_history_once(self) -> None:
        """Write the final run snapshot to disk exactly once.

        Sets history_saved = True so repeated calls do nothing. This is the
        final save — called when the run ends naturally or is force-stopped.
        """
        if self.history_saved:
            return
        if not bool(self.config.get("save_history", True)):
            return

        save_run(
            self.model,
            run_id=self.run_id,
            config=self.config,
        )
        self.history_saved = True

    def _checkpoint_history(self) -> None:
        """Write an intermediate snapshot without marking the run as finally saved.

        Called on WebSocket disconnect so there's something in history even if
        the user never came back. Because history_saved stays False, a reconnect
        that runs to completion will overwrite this with the real final result.
        Skipped if the final save already happened.
        """
        if self.history_saved:
            return  # Final state already written; checkpoint would only downgrade it
        if not bool(self.config.get("save_history", True)):
            return
        try:
            save_run(
                self.model,
                run_id=self.run_id,
                config=self.config,
            )
        except Exception:
            logger.exception(
                "Failed to write disconnect checkpoint for run %s", self.run_id
            )

    def step(self) -> Dict[str, Any]:
        """Advance the simulation by one tick and return the state diff.

        Calls model.step(), logs the diff, and stops the run automatically
        if the scenario ended. Raises if the run is already stopped.
        """
        if self.status == "stopped":
            raise RuntimeError("Run is stopped. Create a new RunManager for a new run.")

        # Allow manual stepping from idle/paused too
        if self.status == "idle":
            self.status = "paused"

        # Advance the simulation model by one tick
        ret = self.model.step()

        # Extract the state diff from the model
        if isinstance(ret, dict):
            diff = ret
        else:
            diff = getattr(self.model, "last_diff", None)

        if diff is None:
            raise RuntimeError("Model produced no diff. Check SimModel.step sets self.last_diff.")

        # Log one JSONL line for replay capability
        self.logger.log(diff)

        # Auto-stop if the simulation ended
        if diff.get("ended") is True:
            self.status = "stopped"
            self._persist_history_once()

        return diff

    def run_loop(self, max_steps: Optional[int] = None, tick_hz: Optional[float] = None) -> None:
        """Step repeatedly until the run ends, max_steps is hit, or status changes.

        tick_hz controls how many ticks per second (None = as fast as possible).
        Used for batch experiments and automated testing.
        """
        if self.status != "running":
            raise RuntimeError("Call start() before run_loop().")

        steps_done = 0
        sleep_s = (1.0 / tick_hz) if (tick_hz and tick_hz > 0) else 0.0

        while self.status == "running":
            diff = self.step()
            steps_done += 1

            if diff.get("ended") is True:
                self.status = "stopped"
                break

            if max_steps is not None and steps_done >= max_steps:
                self.pause()
                break

            if sleep_s > 0:
                time.sleep(sleep_s)
