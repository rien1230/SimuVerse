"""API routes for applying live interventions to an active run.

This route file is the API-facing entry point for intervention buttons in the
Live Interaction page. The actual behaviour lives deeper in:
- services/intervention_service.py -> validation + dispatch
- sim/interventions.py             -> low-level simulation mutations
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.intervention import InterventionRequest, InterventionResponse
from app.services.run_registry import RunRegistry


class _InterventionRequestBase(BaseModel):
    """Minimal validated shape for intervention payloads — used for inline docs only.
    The real validation happens in InterventionRequest from app.schemas.intervention.
    """
    run_id: str
    type: str
    params: Dict[str, Any] = {}


# Reuse the singleton registry so we can look up the active run by ID
registry = RunRegistry()

router = APIRouter(prefix="/interventions", tags=["interventions"])
logger = logging.getLogger(__name__)


@router.post("/apply", response_model=InterventionResponse)
async def apply_intervention_endpoint(request: InterventionRequest) -> InterventionResponse:
    """Apply a user-triggered intervention to a live simulation run.

    Interventions let the user nudge agent behaviour mid-run — e.g. boosting urgency,
    injecting an emotion, or forcing a meeting between two agents.

    The result contains before/after values for whatever metric the intervention touched,
    so the frontend can show the user what changed.
    """
    # This endpoint stays intentionally thin:
    # 1. find the active run
    # 2. call model.apply_intervention(...)
    # 3. reshape the result into the API response model
    try:
        entry = registry.get_run(request.run_id)
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"Run '{request.run_id}' not found",
            )

        model = getattr(entry.manager, "model", None)
        if model is None:
            raise HTTPException(
                status_code=404,
                detail=f"Run '{request.run_id}' has no active model",
            )

        if getattr(model, "ended", False):
            raise HTTPException(
                status_code=400,
                detail="Simulation has already ended",
            )

        # Call model.apply_intervention() — not the service directly — so the
        # intervention is logged to _tick_interventions / _applied_interventions_log
        # and therefore appears in the saved history and run summary.
        result = model.apply_intervention(request.type, request.params)

        if not result.get("success", False):
            # Prefer 'reason' over 'message' for failure details
            reason = result.get("reason") or result.get("message") or "Intervention failed"
            raise HTTPException(status_code=400, detail=reason)

        # emotion_effect can be a nested dict, so unpack it carefully
        _emotion_effect = result.get("emotion_effect") or {}
        return InterventionResponse(
            success=result["success"],
            message=result.get("message", ""),
            intervention_type=request.type,
            tick_applied=result.get("tick_applied", getattr(model, "tick", 0)),
            # Pressure changes from boost_urgency / ease_pressure
            pressure_before=result.get("pressure_before"),
            pressure_after=result.get("pressure_after"),
            share_boost_ticks=result.get("share_boost_ticks"),
            # Stress side-effects that come along with some interventions
            stress_before=result.get("stress_before"),
            stress_after=result.get("stress_after"),
            stress_delta=result.get("stress_delta"),
            # Strategy change from nudge_strategy
            strategy_before=result.get("strategy_before"),
            strategy_after=result.get("strategy_after"),
            lock_duration=result.get("lock_duration"),
            # Group tension from inject_tension
            tension_before=result.get("tension_before"),
            tension_after=result.get("tension_after"),
            # Trust changes between agents
            trust_before=result.get("trust_before"),
            trust_after=result.get("trust_after"),
            trust_delta=result.get("trust_delta"),
            # Emotion injection result
            detected_emotion=result.get("detected_emotion"),
            # Fall back to the nested emotion_effect duration if top-level decay_ticks is missing
            decay_ticks=(
                result.get("decay_ticks")
                or (_emotion_effect.get("duration_ticks") if isinstance(_emotion_effect, dict) else None)
            ),
        )
    except HTTPException:
        raise  # re-raise our own HTTP errors without wrapping them
    except Exception:
        logger.exception(
            "Unexpected intervention failure for run_id=%s type=%s params=%s",
            request.run_id,
            request.type,
            request.params,
        )
        raise HTTPException(
            status_code=500,
            detail="Could not apply the intervention right now. Please try again.",
        )


@router.get("/types")
async def list_intervention_types():
    """List the intervention catalogue so the frontend knows what controls exist."""
    return {
        "interventions": [
            {
                "type": "reveal_info",
                "description": "Give an agent knowledge of an item",
                "params": {
                    "agent_id": "string (A1-A4)",
                    "item": "string (task name)"
                },
            },
            {
                "type": "nudge_strategy",
                "description": "Push an agent toward a behavioural strategy",
                "params": {
                    "agent_id": "string (A1-A4)",
                    "strategy": "cooperative | defensive | confrontational | avoidant | neutral | assertive"
                },
            },
            {
                "type": "boost_urgency",
                "description": "Raise urgency — agents become more willing to share",
                "params": {"amount": "float 0.0–1.0"},
            },
            {
                "type": "ease_pressure",
                "description": "Lower urgency — agents get more breathing room",
                "params": {"amount": "float 0.0–1.0"},
            },
            {
                "type": "inject_tension",
                "description": "Raise group tension — agents become more guarded",
                "params": {"amount": "float 0.0–1.0"},
            },
            {
                "type": "force_meeting",
                "description": "Force two agents into a conversation next tick",
                "params": {
                    "agent_a_id": "string (A1-A4)",
                    "agent_b_id": "string (A1-A4)"
                },
            },
            {
                "type": "inject_emotion",
                "description": "Inject an emotional message that all agents perceive",
                "params": {"text": "string"},
            },
        ]
    }
