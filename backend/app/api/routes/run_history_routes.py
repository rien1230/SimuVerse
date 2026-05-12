"""API routes for browsing saved run history and replay details.

This file is the backend entry point for:
- History page listing
- saved run details
- replay loading
- deleting/clearing saved runs
"""

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

# Two routers with different prefixes so the frontend can reach history either via
# /api/runs/... or /api/history/runs/... — both sets of routes do the same thing.
router = APIRouter(prefix="/runs", tags=["run history"])
history_router = APIRouter(prefix="/history", tags=["run history"])


# ──────────────────────────────────────────────────────────────────────────
# Saved run listing
# ──────────────────────────────────────────────────────────────────────────

@router.get("/")
async def get_all_runs(
    scenario_id: Optional[str] = Query(None, description="Filter by scenario"),
):
    """List all saved simulation runs, optionally filtered by scenario."""
    runs = list_runs(scenario_id=scenario_id)
    return {"runs": runs, "count": len(runs)}


@history_router.get("/runs")
async def get_all_saved_runs(
    scenario_id: Optional[str] = Query(None, description="Filter by scenario"),
):
    """Alias endpoint for saved run history (same as GET /runs/ but under /history prefix)."""
    runs = list_runs(scenario_id=scenario_id)
    return {"runs": runs, "count": len(runs)}


# ──────────────────────────────────────────────────────────────────────────
# Single saved run / deletion
# ──────────────────────────────────────────────────────────────────────────

@router.get("/{run_id}")
async def get_run(run_id: str):
    """Get the full summary of a single saved run by its ID."""
    run = load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run


@history_router.get("/runs/{run_id}")
async def get_saved_run(run_id: str):
    """Alias endpoint for a single saved run summary (under /history prefix)."""
    run = load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run


@router.delete("/{run_id}")
async def delete_run_endpoint(run_id: str):
    """Permanently delete a saved run from history."""
    deleted = delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {"success": True, "message": f"Run '{run_id}' deleted"}


@history_router.delete("/runs/{run_id}")
async def delete_saved_run(run_id: str):
    """Alias endpoint for deleting a saved run (under /history prefix)."""
    deleted = delete_run(run_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return {"success": True, "message": f"Run '{run_id}' deleted"}


@history_router.delete("/runs")
async def clear_saved_runs():
    """Delete all saved runs at once — useful for resetting between experiments."""
    deleted_count = clear_runs()
    return {
        "success": True,
        "deleted_count": deleted_count,
        # Grammar: "1 run" vs "2 runs"
        "message": f"Cleared {deleted_count} saved run{'s' if deleted_count != 1 else ''}",
    }


# ──────────────────────────────────────────────────────────────────────────
# Comparison + replay
# These are the routes the dashboard/history replay UI leans on.
# ──────────────────────────────────────────────────────────────────────────

@router.get("/compare/{run_id_a}/{run_id_b}")
async def compare_two_runs(run_id_a: str, run_id_b: str):
    """Compare two saved runs side by side, returning metrics for both and the deltas."""
    result = compare_runs(run_id_a, run_id_b)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"One or both runs not found: '{run_id_a}', '{run_id_b}'"
        )
    return result


@router.get("/{run_id}/replay")
async def get_replay(run_id: str):
    """Return the full tick-by-tick history for a saved run so the frontend can replay it."""
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
    """Alias endpoint for replaying a saved run (under /history prefix)."""
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
    """Return the simulation state at a single specific tick (1-indexed) for scrubbing."""
    history = replay_run(run_id)
    if history is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    # Ticks are 1-indexed in the API but 0-indexed in the history list
    if tick < 1 or tick > len(history):
        raise HTTPException(
            status_code=400,
            detail=f"Tick {tick} out of range. Run '{run_id}' has {len(history)} ticks (1–{len(history)})."
        )
    return history[tick - 1]
