"""API routes for creating, controlling, and streaming live runs.

Main route file for the interactive simulation flow.

Route layout in here:
- POST   /runs              -> create a new run
- GET    /runs/{run_id}     -> read current state for one run
- POST   /runs/{run_id}/step -> advance one tick
- POST   /runs/{run_id}/start/pause/stop -> lifecycle controls
- WS     /runs/{run_id}/ws  -> live streaming channel for the interaction page
"""

from __future__ import annotations

from typing import Dict, Any, Optional, List
import asyncio
import json
import os
import random
import logging

import anyio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.exceptions import SimuVerseError
from app.services.run_registry import RunRegistry
from app.services.simulation_config import (
    build_simulation_config,
    get_configuration_options,
    normalize_environment,
)
from app.services.personality_test_service import run_personality_test

router = APIRouter()
# Singleton registry shared across all requests in this process
registry = RunRegistry()
logger = logging.getLogger(__name__)


class CreateRunBody(BaseModel):
    """Validated request body for POST /runs.

    'environment' and 'scenario' are both accepted so the frontend can use either field name.
    """
    seed: Optional[int] = None          # if not provided, a cryptographically random seed is used
    environment: Optional[str] = None
    scenario: Optional[str] = None      # alias for environment (checked as fallback)
    goal: Optional[str] = None
    team_type: Optional[str] = None
    save_history: bool = True
    # Optional free-text emotion that gets classified and injected at tick 0,
    # shifting all agents' stress/trust/valence before the first step runs.
    emotion_text: Optional[str] = None
    # Frontend mode that launched this run: "step" = Watch Mode, "live" = Live Interactive.
    # Stored in config so History can label and route the run correctly.
    run_mode: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────
# Shared route helper
# Small wrapper so any action on a run happens under that run's own lock.
# ──────────────────────────────────────────────────────────────────────────

def _locked_call(entry, fn, *args, **kwargs):
    """Acquire a run's per-run lock and then call fn — keeps concurrent step calls safe."""
    with entry.lock:
        return fn(*args, **kwargs)


# ──────────────────────────────────────────────────────────────────────────
# Read-only helper routes
# Small endpoints the frontend uses to populate dropdowns or preview data.
# ──────────────────────────────────────────────────────────────────────────

@router.get("/runs/options")
async def get_run_options() -> Dict[str, Any]:
    """Get available environments, goals, and team presets for configuration."""
    return get_configuration_options()




@router.get("/runs/personality-results/{scenario}/{team_style}")
async def get_personality_results(scenario: str, team_style: str, seed: Optional[int] = None) -> Dict[str, Any]:
    """Run a live personality test simulation and return metrics."""
    try:
        results = await anyio.to_thread.run_sync(run_personality_test, scenario, team_style, seed)
        return results
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception(
            "Failed to compute personality results for scenario=%s team_style=%s seed=%s",
            scenario,
            team_style,
            seed,
        )
        raise HTTPException(
            status_code=500,
            detail="Could not compute personality test results right now. Please try again.",
        )


# ──────────────────────────────────────────────────────────────────────────
# Run creation
# This is where setup-page selections become a real RunManager in memory.
# ──────────────────────────────────────────────────────────────────────────

@router.post("/runs")
async def create_run(body: CreateRunBody) -> Dict[str, Any]:
    """Create a new simulation run and register it for WebSocket streaming.

    Returns the run_id the client uses for all subsequent step/start/stop calls.
    """
    try:
        # Accept either 'environment' or 'scenario' as the environment name
        requested_environment = body.environment or body.scenario
        if not requested_environment:
            raise ValueError("environment is required")

        config = build_simulation_config(
            requested_environment,
            body.goal,
            body.team_type or "balanced",
        )
        config["save_history"] = bool(body.save_history)

        # Map frontend mode to a canonical source value saved in the run config.
        # "step" (Watch Mode) → "watch"; "live" (Live Interactive) → "live_interactive".
        # Runs created without run_mode (legacy / API calls) keep "interactive".
        _run_mode = str(body.run_mode or "").strip().lower()
        if _run_mode == "step":
            config["source"] = "watch"
        elif _run_mode == "live":
            config["source"] = "live_interactive"
        else:
            config["source"] = "interactive"

        # Use a crypto-random seed if none was supplied so runs are non-deterministic by default
        seed = body.seed if body.seed is not None else random.SystemRandom().randint(1, 2_147_483_647)

        # RunManager creation is CPU-bound (builds the SimModel), so run it in a thread
        run_id = await anyio.to_thread.run_sync(registry.create_run, seed, config, None)
        entry = registry.get_run(run_id)

        # Apply initial group mood if provided — classifies the text and injects
        # the emotion effect at tick 0 before any steps run.
        if body.emotion_text and entry:
            _model = getattr(entry.manager, "model", None)
            if _model is not None:
                _text = body.emotion_text.strip()
                try:
                    # NLP is blocking, so keep it off the event loop
                    await anyio.to_thread.run_sync(
                        lambda: _model.inject_user_emotion(_text, tick=0)
                    )
                except Exception:
                    # Emotion injection is best-effort — don't fail the whole run creation
                    logger.warning(
                        "Could not apply initial emotion for run %s: text=%r",
                        run_id, _text[:60],
                    )

        return {
            "run_id": run_id,
            "seed": seed,
            "status": entry.manager.status if entry else "created",
            "environment": config["environment"],
            "requested_environment": normalize_environment(requested_environment),
            "goal": config["goal"],
            "team_type": config["team_type"],
            "resolved_team_type": config["resolved_team_type"],
            "scenario_id": config["scenario_id"],
            "save_history": config["save_history"],
        }
    except (ValueError, SimuVerseError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception(
            "Failed to create run for environment=%s scenario=%s goal=%s team_type=%s",
            body.environment,
            body.scenario,
            body.goal,
            body.team_type,
        )
        raise HTTPException(
            status_code=500,
            detail="Could not create the simulation run right now. Please check the backend and try again.",
        )


# ──────────────────────────────────────────────────────────────────────────
# Run status / CRUD
# These routes read or remove runs that already exist in the registry.
# ──────────────────────────────────────────────────────────────────────────

@router.get("/runs")
async def list_runs() -> Dict[str, Any]:
    """Get a list of all active simulation runs."""
    runs = await anyio.to_thread.run_sync(registry.list_runs)
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def get_run_status(run_id: str) -> Dict[str, Any]:
    """Get detailed status of a specific run, including current live simulation state."""
    entry = registry.get_run(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Run not found")

    model = entry.manager.model
    model_tick = getattr(model, "tick", 0)

    last_diff = getattr(model, "last_diff", None) or {}

    agents = last_diff.get("agents", [])
    ties = last_diff.get("ties", [])
    events = last_diff.get("events", [])
    metrics = last_diff.get("metrics", {})
    group_state = last_diff.get("group_state", {})
    scenario = last_diff.get("scenario", {})

    # The UI can ask for status before the first streamed diff lands, so keep
    # these fallbacks around and build a readable snapshot straight from model state.
    if not agents and hasattr(model, "agents"):
        # Build a state snapshot directly from agent objects when no diff is available yet
        agents = [
            agent.to_state()
            for agent in sorted(list(model.agents), key=lambda a: a.public_id)
        ]

    if not scenario and hasattr(model, "scenario"):
        # Same idea — build a scenario snapshot so the UI has something to display on first load
        scenario = {
            "id": model.scenario.id,
            "name": getattr(model.scenario, "name", model.scenario.id),
            "description": getattr(model.scenario, "description", ""),
            "environment": getattr(model.scenario, "environment", ""),
            "tasks": getattr(model.scenario, "tasks", {}),
            "knowledge_map": getattr(model.scenario, "knowledge_map", {}),
            "progress": round(model.scenario.progress_ratio(), 3),
            "urgency_modifier": round(getattr(model.environment, "urgency_modifier", 0.0), 3),
            "outcome": model.scenario.outcome(model_tick),
            "final_decision": getattr(model, "_final_decision", None),
        }

    if not group_state:
        group_state = {
            "tension": getattr(model, "group_tension", 0.0),
            "cohesion": getattr(model, "group_cohesion", 0.0),
            "pressure": round(getattr(model.environment, "urgency_modifier", 0.0), 3),
            "stall_ticks": getattr(model, "progress_stall_ticks", 0),
            "success_streak": getattr(model, "recent_success_ticks", 0),
            "bottleneck_item": getattr(model, "bottleneck_item", None),
            "bottleneck_holder": getattr(model, "bottleneck_holder", None),
            "bottleneck_age": getattr(model, "bottleneck_age", 0),
        }

    return {
        "run_id": run_id,
        "status": entry.manager.status,
        "seed": entry.manager.seed,
        "tick": model_tick,
        "config": entry.manager.config,
        "clients": entry.client_count,
        "agents": agents,
        "ties": ties,
        "events": events,
        "metrics": metrics,
        "group_state": group_state,
        "scenario": scenario,
        "history": getattr(model, "history", []),
        "ended": getattr(model, "ended", False),
        "end_reason": getattr(model, "end_reason", ""),
        "saved_to_history": getattr(entry.manager, "history_saved", False),
    }


# ──────────────────────────────────────────────────────────────────────────
# Run control routes
# These are the core POST actions used once a live run already exists.
# ──────────────────────────────────────────────────────────────────────────

@router.post("/runs/{run_id}/start")
async def start_run(run_id: str) -> Dict[str, Any]:
    """Start or resume a simulation run. Changes run status from idle or paused to running."""
    entry = registry.get_run(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Run not found")

    await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.start)
    return {"run_id": run_id, "status": entry.manager.status}


@router.post("/runs/{run_id}/pause")
async def pause_run(run_id: str) -> Dict[str, Any]:
    """Pause a running simulation. Changes run status from running to paused."""
    entry = registry.get_run(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Run not found")

    await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.pause)
    return {"run_id": run_id, "status": entry.manager.status}


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str) -> Dict[str, Any]:
    """Stop a simulation. Changes run status to stopped."""
    entry = registry.get_run(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Run not found")

    await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.stop)
    return {"run_id": run_id, "status": entry.manager.status}


@router.post("/runs/{run_id}/step")
async def step_run(run_id: str) -> Dict[str, Any]:
    """
    Execute one simulation tick.
    Advances the simulation by one tick and returns the state diff.
    """
    entry = registry.get_run(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Run not found")

    try:
        diff = await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.step)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "run_id": run_id,
        "status": entry.manager.status,
        "tick": diff.get("tick", 0),
        "diff": diff,
    }


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str) -> Dict[str, Any]:
    """Remove a run from the registry."""
    ok = await anyio.to_thread.run_sync(registry.delete_run, run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found")

    return {"run_id": run_id, "deleted": True}


# ──────────────────────────────────────────────────────────────────────────
# Live WebSocket flow
# The interaction page uses this channel for real-time step-by-step updates.
# ──────────────────────────────────────────────────────────────────────────

@router.websocket("/runs/{run_id}/ws")
async def run_ws(websocket: WebSocket, run_id: str) -> None:
    """WebSocket endpoint for real-time simulation updates.

    Accepts JSON messages with a 'cmd' field. Supported commands:
      step       — advance one tick and send the diff back
      start      — mark the run as running
      pause      — pause the run
      stop       — stop the run
      auto       — start a background loop stepping at tick_hz per second
      auto_stop  — cancel the auto loop

    Each tick diff is sent as {"type": "tick", "data": <diff>}.
    Status changes are sent as {"type": "status", "status": <new_status>}.
    """
    entry = registry.get_run(run_id)
    if not entry:
        # Close with policy violation code if the run doesn't exist
        await websocket.close(code=1008)
        return

    await websocket.accept()
    # Track how many clients are watching this run (used for checkpoint-on-disconnect logic)
    await anyio.to_thread.run_sync(_inc_clients, run_id, +1)

    stop_event = asyncio.Event()
    auto_task: Optional[asyncio.Task] = None

    async def auto_loop(tick_hz: float) -> None:
        """Background task that steps the sim repeatedly at a fixed rate.

        Stops itself when the scenario ends, or when stop_event is set externally.
        """
        sleep_s = 1.0 / max(0.1, tick_hz)  # clamp to avoid infinite speed

        while not stop_event.is_set():
            diff = await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.step)
            await websocket.send_json({"type": "tick", "data": diff})

            # Stop looping if the scenario ended naturally
            if diff.get("ended") is True:
                stop_event.set()
                return

            await asyncio.sleep(sleep_s)

    try:
        while True:
            msg = await websocket.receive_json()
            cmd = msg.get("cmd")

            if cmd == "step":
                # Single manual tick — runs in a thread so the event loop stays responsive
                diff = await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.step)
                await websocket.send_json({"type": "tick", "data": diff})

            elif cmd == "start":
                await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.start)
                await websocket.send_json({"type": "status", "status": entry.manager.status})

            elif cmd == "pause":
                await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.pause)
                await websocket.send_json({"type": "status", "status": entry.manager.status})

            elif cmd == "stop":
                await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.stop)
                await websocket.send_json({"type": "status", "status": entry.manager.status})

            elif cmd == "auto":
                tick_hz = float(msg.get("tick_hz", 2))
                stop_event.clear()

                # Cancel any existing auto loop before starting a new one
                if auto_task and not auto_task.done():
                    auto_task.cancel()

                auto_task = asyncio.create_task(auto_loop(tick_hz=tick_hz))
                await websocket.send_json(
                    {
                        "type": "status",
                        "status": "auto_running",
                        "tick_hz": tick_hz,
                    }
                )

            elif cmd == "auto_stop":
                stop_event.set()
                if auto_task and not auto_task.done():
                    auto_task.cancel()
                await websocket.send_json({"type": "status", "status": "auto_stopped"})

            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown cmd: {cmd}"}
                )

    except WebSocketDisconnect:
        # Normal disconnection — handled in finally block
        pass
    finally:
        # Always clean up: stop the auto loop, decrement clients, checkpoint if needed
        stop_event.set()
        if auto_task and not auto_task.done():
            auto_task.cancel()
        await anyio.to_thread.run_sync(_inc_clients, run_id, -1)
        await anyio.to_thread.run_sync(_save_run_on_disconnect, run_id)


# ──────────────────────────────────────────────────────────────────────────
# Disconnect support helpers
# These make sure a live run is checkpointed if the last client disappears.
# ──────────────────────────────────────────────────────────────────────────

def _save_run_on_disconnect(run_id: str) -> None:
    """Checkpoint the run to history when the last WebSocket client disconnects.

    Uses _checkpoint_history() rather than _persist_history_once() so the
    history_saved flag is NOT set.  This means that if the client reconnects
    and the run completes, _persist_history_once() can still overwrite the
    checkpoint with the correct final result.

    If the run has already been marked as final (history_saved = True) —
    e.g. it completed naturally before the last client dropped — the checkpoint
    is skipped entirely (handled inside _checkpoint_history).
    """
    entry = registry.get_run(run_id)
    if entry and entry.client_count == 0 and entry.manager.model.tick > 0:
        entry.manager._checkpoint_history()


def _inc_clients(run_id: str, delta: int) -> None:
    """Increment or decrement the WebSocket client count for a run.

    Clamped to 0 so it can never go negative even if disconnect fires twice.
    """
    entry = registry.get_run(run_id)
    if not entry:
        return

    entry.client_count = max(0, entry.client_count + delta)

