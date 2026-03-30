from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, Literal


class InterventionRequest(BaseModel):
    run_id: str = Field(..., description="Active simulation run ID")
    type: Literal[
        "reveal_info",
        "nudge_strategy",
        "boost_urgency",
        "inject_tension",
        "force_meeting",
    ] = Field(..., description="Intervention type")
    params: Dict[str, Any] = Field(default_factory=dict)


class InterventionResponse(BaseModel):
    success: bool
    message: str
    intervention_type: str
    tick_applied: int


# Optional param models (for documentation)
class RevealInfoParams(BaseModel):
    agent_id: str
    item: str
    complete_task: bool = False


class NudgeStrategyParams(BaseModel):
    agent_id: str
    strategy: str


class BoostUrgencyParams(BaseModel):
    amount: float = Field(ge=0.0, le=1.0)


class InjectTensionParams(BaseModel):
    amount: float = Field(ge=0.0, le=1.0)


class ForceMeetingParams(BaseModel):
    agent_a_id: str
    agent_b_id: str