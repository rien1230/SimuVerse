"""API routes for applying live interventions to an active run."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.intervention import InterventionRequest, InterventionResponse
from app.services.intervention_service import apply_intervention
from app.services.run_registry import RunRegistry


class _InterventionRequestBase(BaseModel):
    """Minimal validated shape for intervention payloads (used for documentation)."""
    run_id: str
    type: str
    params: Dict[str, Any] = {}

registry = RunRegistry()

router = APIRouter(prefix="/interventions", tags=["interventions"])
logger = logging.getLogger(__name__)


@router.post("/apply", response_model=InterventionResponse)
async def apply_intervention_endpoint(request: InterventionRequest) -> InterventionResponse:
    """
    Apply a user intervention to a running simulation.
    """
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

        result = apply_intervention(model, request.type, request.params)

        if not result.get("success", False):
            reason = result.get("reason") or result.get("message") or "Intervention failed"
            raise HTTPException(status_code=400, detail=reason)

        return InterventionResponse(
            success=result["success"],
            message=result["message"],
            intervention_type=request.type,
            tick_applied=getattr(model, "tick", 0),
        )
    except HTTPException:
        raise
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
        ]
    }
