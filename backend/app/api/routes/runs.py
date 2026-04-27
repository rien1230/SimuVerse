"""API routes for creating, controlling, and streaming live runs."""

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
registry = RunRegistry()
logger = logging.getLogger(__name__)


class CreateRunBody(BaseModel):
    """For validating create run requests."""
    seed: Optional[int] = None
    environment: Optional[str] = None
    scenario: Optional[str] = None
    goal: Optional[str] = None
    team_type: Optional[str] = None
    save_history: bool = True


def _locked_call(entry, fn, *args, **kwargs):
    """Run a method under a run's lock for thread safety."""
    with entry.lock:
        return fn(*args, **kwargs)


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


@router.post("/runs")
async def create_run(body: CreateRunBody) -> Dict[str, Any]:
    """Create a new simulation run."""
    try:
        requested_environment = body.environment or body.scenario
        if not requested_environment:
            raise ValueError("environment is required")

        config = build_simulation_config(
            requested_environment,
            body.goal,
            body.team_type or "balanced",
        )
        config["save_history"] = bool(body.save_history)
        config["source"] = "interactive"
        seed = body.seed if body.seed is not None else random.SystemRandom().randint(1, 2_147_483_647)
        run_id = await anyio.to_thread.run_sync(registry.create_run, seed, config)
        entry = registry.get_run(run_id)

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
        agents = [
            agent.to_state()
            for agent in sorted(list(model.agents), key=lambda a: a.public_id)
        ]

    if not scenario and hasattr(model, "scenario"):
        scenario = {
            "id": model.scenario.id,
            "name": getattr(model.scenario, "name", model.scenario.id),
            "description": getattr(model.scenario, "description", ""),
            "environment": getattr(model.scenario, "environment", ""),
            "tasks": getattr(model.scenario, "tasks", {}),
            "knowledge_map": getattr(model.scenario, "knowledge_map", {}),
            "progress": round(model.scenario.progress_ratio(), 3),
            "outcome": model.scenario.outcome(model_tick),
            "final_decision": getattr(model, "_final_decision", None),
        }

    if not group_state:
        group_state = {
            "tension": getattr(model, "group_tension", 0.0),
            "cohesion": getattr(model, "group_cohesion", 0.0),
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


@router.websocket("/runs/{run_id}/ws")
async def run_ws(websocket: WebSocket, run_id: str) -> None:
    """
    WebSocket endpoint for real-time simulation updates.
    """
    entry = registry.get_run(run_id)
    if not entry:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    await anyio.to_thread.run_sync(_inc_clients, run_id, +1)

    stop_event = asyncio.Event()
    auto_task: Optional[asyncio.Task] = None

    async def auto_loop(tick_hz: float) -> None:
        """Continuously step the simulation at a fixed rate."""
        sleep_s = 1.0 / max(0.1, tick_hz)

        while not stop_event.is_set():
            diff = await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.step)
            await websocket.send_json({"type": "tick", "data": diff})

            if diff.get("ended") is True:
                stop_event.set()
                return

            await asyncio.sleep(sleep_s)

    try:
        while True:
            msg = await websocket.receive_json()
            cmd = msg.get("cmd")

            if cmd == "step":
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
        pass
    finally:
        stop_event.set()
        if auto_task and not auto_task.done():
            auto_task.cancel()
        await anyio.to_thread.run_sync(_inc_clients, run_id, -1)
        await anyio.to_thread.run_sync(_save_run_on_disconnect, run_id)


def _save_run_on_disconnect(run_id: str) -> None:
    """Persist the run to history when the last WebSocket client disconnects."""
    entry = registry.get_run(run_id)
    if entry and entry.client_count == 0 and entry.manager.model.tick > 0:
        entry.manager._persist_history_once()


def _inc_clients(run_id: str, delta: int) -> None:
    """Safely change client_count for a run."""
    entry = registry.get_run(run_id)
    if not entry:
        return

    entry.client_count = max(0, entry.client_count + delta)
