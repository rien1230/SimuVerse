from __future__ import annotations
from typing import Dict, Any, Optional
import asyncio
import anyio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from app.services.run_registry import RunRegistry
from app.services.simulation_config import build_simulation_config, get_configuration_options  # NEW IMPORT

router = APIRouter()
registry = RunRegistry()

class CreateRunBody(BaseModel):
    """ for validating create run requests. Ensuring the incoming JSON has the right structure and types. """
    seed: int
    environment: str  # NEW: from frontend Page 1
    goal: str         # NEW: from frontend Page 1
    team_type: str    # NEW: from frontend Page 2

def _locked_call(entry, fn, *args, **kwargs):
    """ Helper function to run a method under a run's lock. Ensuring thread safety when multiple clients try to interact with the same simulation run at the same time. """
    with entry.lock:
        return fn(*args, **kwargs)

# NEW ROUTE: Get available configuration options for frontend
@router.get("/runs/options")
async def get_run_options() -> Dict[str, Any]:
    """ Get available environments, goals, and team presets for configuration. """
    return get_configuration_options()

@router.post("/runs")
async def create_run(body: CreateRunBody) -> Dict[str, Any]:
    """ Create a new simulation run. It creates the run, adds it to the registry, and returns the run_id. """
    try:
        # NEW: Build config from user choices (environment, goal, team_type)
        config = build_simulation_config(body.environment, body.goal, body.team_type)
        # synchronous function, so we run it in a thread pool. Preventing blocking the async event loop
        run_id = await anyio.to_thread.run_sync(registry.create_run, body.seed, config)
        entry = registry.get_run(run_id)
        # NEW: Return selected config for frontend confirmation
        return {
            "run_id": run_id,
            "status": entry.manager.status if entry else "created",
            "environment": config["environment"],
            "goal": config["goal"],
            "team_type": config["team_type"],
            "scenario_id": config["scenario_id"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/runs")
async def list_runs() -> Dict[str, Any]:
    """ Get a list of all active simulation runs. """
    runs = await anyio.to_thread.run_sync(registry.list_runs)
    return {"runs": runs}

@router.get("/runs/{run_id}")
async def get_run_status(run_id: str) -> Dict[str, Any]:
    """ Get detailed status of a specific run. """
    entry = registry.get_run(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Run not found")
    # Get current tick from the model (different models might store it differently)
    model_tick = getattr(entry.manager.model, "tick", 0)
    return {
        "run_id": run_id,
        "status": entry.manager.status,
        "seed": entry.manager.seed,
        "tick": model_tick,
        "config": entry.manager.config,
        "clients": entry.client_count,
    }

@router.post("/runs/{run_id}/start")
async def start_run(run_id: str) -> Dict[str, Any]:
    """ Start or resume a simulation run. Changes run status from 'idle' or 'paused' to 'running'. """
    entry = registry.get_run(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Run not found")
    # Run start() under the run's lock (thread-safe)
    await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.start)
    return {"run_id": run_id, "status": entry.manager.status}

@router.post("/runs/{run_id}/pause")
async def pause_run(run_id: str) -> Dict[str, Any]:
    """ Pause a running simulation. Changes run status from 'running' to 'paused'. """
    entry = registry.get_run(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Run not found")
    await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.pause)
    # Dict with updated status
    return {"run_id": run_id, "status": entry.manager.status}

@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str) -> Dict[str, Any]:
    """ Stop a simulation (terminal state). Changes run status to 'stopped'. Once stopped, a run cannot be resumed. """
    entry = registry.get_run(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Run not found")
    await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.stop)
    return {"run_id": run_id, "status": entry.manager.status}

@router.post("/runs/{run_id}/step")
async def step_run(run_id: str) -> Dict[str, Any]:
    """ Execute one simulation tick (advance time by one step). This is the core simulation operation. It: 1. Advances the simulation by one tick 2. Returns the state changes (diff) that happened 3. Updates the run status if the episode ended """
    entry = registry.get_run(run_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        # Execute one simulation tick (thread-safe with lock)
        diff = await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.step)
    except Exception as e:
        # If simulation encounters an error during step
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "run_id": run_id,
        "status": entry.manager.status,
        "tick": diff.get("tick", 0),
        "diff": diff, # The state changes that happened this tick
    }

@router.delete("/runs/{run_id}")
async def delete_run(run_id: str) -> Dict[str, Any]:
    """ Remove a run from the registry. doesn't delete the replay file from disk, just removes the run from the active registry. The replay file remains for analysis. """
    ok = await anyio.to_thread.run_sync(registry.delete_run, run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "deleted": True}

@router.websocket("/runs/{run_id}/ws")
async def run_ws(websocket: WebSocket, run_id: str) -> None:
    """ WebSocket endpoint for real-time simulation updates. This allows the frontend to: - Get live updates as the simulation runs - Control the simulation (start, pause, step, auto-run) - See state changes immediately without polling """
    # Check if the run exists
    entry = registry.get_run(run_id)
    if not entry:
        await websocket.close(code=1008) # Policy violation - run doesn't exist
        return
    # Accept the WebSocket connection
    await websocket.accept()
    await anyio.to_thread.run_sync(_inc_clients, run_id, +1)

    # Setup for auto-run (continuous stepping at a certain speed)
    stop_event = asyncio.Event()
    auto_task: Optional[asyncio.Task] = None

    async def auto_loop(tick_hz: float) -> None:
        """ Continuously step the simulation at a fixed rate. Used for the "auto" mode where the simulation runs by itself. """
        sleep_s = 1.0 / max(0.1, tick_hz) # Calculate sleep time between ticks
        while not stop_event.is_set():
            diff = await anyio.to_thread.run_sync(_locked_call, entry, entry.manager.step)
            # Send the tick diff to the client
            await websocket.send_json({"type": "tick", "data": diff})
            # Stop if the simulation ended
            if diff.get("ended") is True:
                stop_event.set()
                return
            # Wait before next tick (controls simulation speed)
            await asyncio.sleep(sleep_s)

    try:
        # Main WebSocket message loop
        while True:
            # Wait for a command from the client
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
                tick_hz = float(msg.get("tick_hz", 2)) # Default 2 ticks/sec
                stop_event.clear() # Reset stop flag
                # Cancel existing auto task if running
                if auto_task and not auto_task.done():
                    auto_task.cancel()
                # Start new auto task
                auto_task = asyncio.create_task(auto_loop(tick_hz=tick_hz))
                await websocket.send_json({
                    "type": "status",
                    "status": "auto_running",
                    "tick_hz": tick_hz
                })
            elif cmd == "auto_stop":
                # Stop auto-run
                stop_event.set() # Signal auto loop to stop
                if auto_task and not auto_task.done():
                    auto_task.cancel() # Cancel the task
                await websocket.send_json({"type": "status", "status": "auto_stopped"})
            else:
                # Unknown command
                await websocket.send_json({"type": "error", "message": f"Unknown cmd: {cmd}"})
    except WebSocketDisconnect:
        # Client disconnected normally
        pass
    finally:
        stop_event.set() # Stop any auto-run
        if auto_task and not auto_task.done():
            auto_task.cancel()
        # Decrement client count (one less viewer)
        await anyio.to_thread.run_sync(_inc_clients, run_id, -1)

def _inc_clients(run_id: str, delta: int) -> None:
    """ Safely change client_count for a run. This tracks how many WebSocket connections are watching a run. Used for monitoring and potentially for cleanup decisions. """
    entry = registry.get_run(run_id)
    if not entry:
        return # Run doesn't exist (was deleted while clients were connected)
    # Update client count, ensuring it doesn't go below 0
    entry.client_count = max(0, entry.client_count + delta)