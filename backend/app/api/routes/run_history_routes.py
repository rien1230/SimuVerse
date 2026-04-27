"""API routes for browsing saved run history and replay details."""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from app.services.run_history_service import (
    list_runs,
    load_run,
    compare_runs,
    delete_run,
    clear_runs,
    replay_run,
)

router = APIRouter(prefix="/runs", tags=["run history"])
history_router = APIRouter(prefix="/history", tags=["run history"])


@router.get("/")
async def get_all_runs(scenario_id: Optional[str] = Query(None, description="Filter by scenario")):
    """
    List all saved simulation runs.
    Optionally filter by scenario_id (e.g. 'office_proposal').
    """
    runs = list_runs(scenario_id=scenario_id)
    return {"runs": runs, "count": len(runs)}


@history_router.get("/runs")
async def get_all_saved_runs(scenario_id: Optional[str] = Query(None, description="Filter by scenario")):
    """Alias endpoint for saved run history to avoid clashing with live run registry routes."""
    runs = list_runs(scenario_id=scenario_id)
    return {"runs": runs, "count": len(runs)}


@router.get("/{run_id}")
async def get_run(run_id: str):
    """Get the full summary of a single saved run including per-agent state."""
    run = load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run


@history_router.get("/runs/{run_id}")
async def get_saved_run(run_id: str):
    """Alias endpoint for a single saved run summary."""
    run = load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run


@router.delete("/{run_id}")
async def delete_run_endpoint(run_id: str):
    """Delete a saved run from history."""
    deleted = delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {"success": True, "message": f"Run '{run_id}' deleted"}


@history_router.delete("/runs/{run_id}")
async def delete_saved_run(run_id: str):
    """Alias endpoint for deleting a saved run from history."""
    deleted = delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {"success": True, "message": f"Run '{run_id}' deleted"}


@history_router.delete("/runs")
async def clear_saved_runs():
    """Delete all saved runs from history."""
    deleted_count = clear_runs()
    return {
        "success": True,
        "deleted_count": deleted_count,
        "message": f"Cleared {deleted_count} saved run{'s' if deleted_count != 1 else ''}",
    }


@router.get("/compare/{run_id_a}/{run_id_b}")
async def compare_two_runs(run_id_a: str, run_id_b: str):
    """
    Compare two saved runs side by side.
    Returns metrics, outcomes, task completion and intervention counts
    for both runs, plus a delta showing the difference.
    """
    result = compare_runs(run_id_a, run_id_b)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"One or both runs not found: '{run_id_a}', '{run_id_b}'"
        )
    return result


@router.get("/{run_id}/replay")
async def get_replay(run_id: str):
    """
    Return the full tick-by-tick history for a saved run.

    Each tick entry contains agent states, events, metrics, and group state.
    Enables post-hoc analysis and frontend replay without re-running the simulation.
    The system supports deterministic replay of simulations by storing per-tick
    state transitions, enabling reproducibility and auditability.
    """
    history = replay_run(run_id)
    if history is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {
        "run_id":      run_id,
        "tick_count":  len(history),
        "history":     history,
    }


@history_router.get("/runs/{run_id}/replay")
async def get_saved_replay(run_id: str):
    """Alias endpoint for replaying a saved run."""
    history = replay_run(run_id)
    if history is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {
        "run_id":     run_id,
        "tick_count": len(history),
        "history":    history,
    }


@router.get("/{run_id}/replay/{tick}")
async def get_replay_tick(run_id: str, tick: int):
    """
    Return the state at a specific tick for a saved run.

    Useful for stepping through a simulation tick by tick from the frontend,
    or for inspecting a specific moment (e.g. when a deadlock occurred).
    Tick numbers start at 1.
    """
    history = replay_run(run_id)
    if history is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    if tick < 1 or tick > len(history):
        raise HTTPException(
            status_code=400,
            detail=f"Tick {tick} out of range. Run '{run_id}' has {len(history)} ticks (1–{len(history)})."
        )
    # History is 0-indexed, ticks are 1-indexed
    return history[tick - 1]
