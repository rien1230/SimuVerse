from fastapi import APIRouter, HTTPException
from app.schemas.intervention import InterventionRequest, InterventionResponse
from app.services.intervention_service import apply_intervention
from app.api.routes.runs import registry   # reuse the same active run registry

router = APIRouter(prefix="/interventions", tags=["interventions"])


@router.post("/apply", response_model=InterventionResponse)
async def apply_intervention_endpoint(request: InterventionRequest):
    """
    Apply a user intervention to a running simulation.
    """
    entry = registry.get_run(request.run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Run '{request.run_id}' not found")

    model = entry.manager.model
    if model is None:
        raise HTTPException(status_code=404, detail=f"Run '{request.run_id}' has no active model")

    if model.ended:
        raise HTTPException(status_code=400, detail="Simulation has already ended")

    result = apply_intervention(model, request.type, request.params)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("reason", "Intervention failed"))

    return InterventionResponse(
        success=True,
        message=result["message"],
        intervention_type=request.type,
        tick_applied=model.tick,
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