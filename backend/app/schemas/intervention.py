"""Schema definitions for intervention requests and responses.

These models are the API contract for live interventions.
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, Literal, Optional


class InterventionRequest(BaseModel):
    """Incoming intervention payload from the frontend."""
    run_id: str = Field(..., description="Active simulation run ID")
    type: Literal[
        "reveal_info",
        "nudge_strategy",
        "boost_urgency",
        "ease_pressure",
        "inject_tension",
        "force_meeting",
        "inject_emotion",
    ] = Field(..., description="Intervention type")
    params: Dict[str, Any] = Field(default_factory=dict)


class InterventionResponse(BaseModel):
    """Structured intervention result returned back to the frontend."""
    success: bool
    message: str
    intervention_type: str
    tick_applied: int
    # Pressure interventions (boost_urgency / ease_pressure)
    pressure_before: Optional[float] = None
    pressure_after: Optional[float] = None
    # Share-boost window duration (boost_urgency) — persists for N ticks only
    share_boost_ticks: Optional[int] = None
    # Agent stress side-effect (reveal_info, nudge_strategy)
    stress_before: Optional[float] = None
    stress_after: Optional[float] = None
    stress_delta: Optional[float] = None
    # Strategy nudge (nudge_strategy)
    strategy_before: Optional[str] = None
    strategy_after: Optional[str] = None
    lock_duration: Optional[int] = None
    # Group tension (inject_tension)
    tension_before: Optional[float] = None
    tension_after: Optional[float] = None
    # Pairwise trust (force_meeting)
    trust_before: Optional[float] = None
    trust_after: Optional[float] = None
    trust_delta: Optional[float] = None
    # Emotion injection (inject_emotion)
    detected_emotion: Optional[str] = None
    decay_ticks: Optional[int] = None


class RevealInfoParams(BaseModel):
    """Typed params for reveal_info."""
    agent_id: str
    item: str
    complete_task: bool = False


class NudgeStrategyParams(BaseModel):
    """Typed params for nudge_strategy."""
    agent_id: str
    strategy: str


class BoostUrgencyParams(BaseModel):
    """Typed params for boost_urgency."""
    amount: float = Field(ge=0.0, le=1.0)


class EasePressureParams(BaseModel):
    """Typed params for ease_pressure."""
    amount: float = Field(ge=0.0, le=1.0)


class InjectTensionParams(BaseModel):
    """Typed params for inject_tension."""
    amount: float = Field(ge=0.0, le=1.0)


class ForceMeetingParams(BaseModel):
    """Typed params for force_meeting."""
    agent_a_id: str
    agent_b_id: str
