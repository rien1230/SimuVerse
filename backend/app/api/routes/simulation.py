"""API routes for one-off simulation helpers used by the frontend.

This file is for helper endpoints that do not need a long-lived live run.
So if I need:
- full one-shot simulation execution
- emotion classification preview
Use this route file instead of runs.py for one-shot simulation results.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import anyio
from app.sim.model import SimModel
from app.sim.scenario_data import SCENARIOS, resolve_scenario_id
from app.services.run_history_service import save_run
from app.sim.metrics import generate_run_interpretation

router = APIRouter(prefix="/simulation", tags=["simulation"])
logger = logging.getLogger(__name__)


class ClassifyEmotionRequest(BaseModel):
    """Request body for the emotion classifier — just the raw text to analyse."""
    text: str


@router.post("/classify-emotion")
async def classify_emotion(req: ClassifyEmotionRequest) -> Dict[str, Any]:
    """Classify free text into an emotion without running a simulation.

    Used by the frontend emotion-preview feature so users can see what emotion
    will be detected before launching or applying a mood injection.
    """
    # Return a neutral fallback immediately rather than hitting the NLP model with empty input
    if not req.text or not req.text.strip():
        return {
            "top_emotion": "neutral",
            "confidence": 0.0,
            "valence": 0.0,
            "arousal": 0.0,
            "intensity": 0.0,
            "fallback_used": True,
            "interpretation": "No text provided.",
            "top_labels": [],
        }
    try:
        # Import here to avoid loading the NLP model at startup — it's heavy
        from app.sim.emotions_analyser import classify_user_emotion
        # The NLP model is CPU-bound, so run it in a thread to avoid blocking the event loop
        result = await anyio.to_thread.run_sync(
            lambda: classify_user_emotion(req.text.strip(), tick=0)
        )
        return result
    except Exception:
        logger.exception("classify_emotion failed for text=%r", req.text[:80])
        raise HTTPException(status_code=500, detail="Could not classify the emotion.")

class SimStartRequest(BaseModel):
    """Request body for the /simulation/start endpoint — runs a full scenario in one shot."""
    scenario_id: str = "office_proposal"
    seed: int = 42
    episode_max_ticks: int = 30
    skip_emotions: bool = False   # set True to run without NLP for faster baseline comparisons
    team_type: Optional[str] = None
    save_history: bool = True
    # Optional user emotion input — classified and injected at emotion_tick
    emotion_text: Optional[str] = None
    emotion_tick: int = 0   # 0 = inject before the loop starts


def _run_simulation_sync(req: SimStartRequest) -> Dict[str, Any]:
    """Run a full simulation synchronously — called off the event loop via anyio.

    This is the 'fire and forget' path: it loops until the scenario ends or hits
    the tick limit, then returns a summary. The WebSocket path in runs.py handles
    interactive step-by-step control instead.
    """
    # This path is deliberately separate from the live RunManager path.
    # It is useful for quick one-shot runs, exports, and helper tooling.
    # Resolve aliases like "escape" → "escape_puzzle" before validating
    scenario_id = resolve_scenario_id(req.scenario_id)
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {req.scenario_id}")

    model = SimModel(
        seed=req.seed,
        scenario_id=scenario_id,
        environment=SCENARIOS[scenario_id]["environment"],
        episode_max_ticks=req.episode_max_ticks,
        team_type=req.team_type,
    )
    model.skip_emotions = req.skip_emotions

    # ── User emotion injection ─────────────────────────────────────────────
    # Inject before the loop when emotion_tick == 0, otherwise inject mid-run.
    emotion_log_entry = None
    if req.emotion_text:
        if req.emotion_tick == 0:
            emotion_log_entry = model.inject_user_emotion(req.emotion_text, tick=0)

    while not model.ended and model.tick < req.episode_max_ticks:
        model.step()
        # Mid-run injection: fire exactly once when the model reaches the target tick
        if (
            req.emotion_text
            and req.emotion_tick > 0
            and model.tick == req.emotion_tick
            and emotion_log_entry is None  # ensure we only inject once
        ):
            emotion_log_entry = model.inject_user_emotion(req.emotion_text, tick=model.tick)

    run_id = None
    if req.save_history:
        run_id = save_run(
            model,
            config={
                "scenario_id": scenario_id,
                "environment": SCENARIOS[scenario_id]["environment"],
                "episode_max_ticks": req.episode_max_ticks,
                "team_type": req.team_type,
                "use_nlp": not req.skip_emotions,
                "save_history": True,
            },
        )
    # Generate a plain-English summary of what happened during the run
    interpretation = generate_run_interpretation(model)
    return {
        "run_id":          run_id,
        "outcome":         model.end_reason,
        "ticks":           model.tick,
        "interpretation":  interpretation,
        "emotion_summary": model.emotion_summary(),
    }


@router.post("/start")
async def start_simulation(req: SimStartRequest):
    """Run a complete simulation and return the outcome summary.

    The heavy simulation loop runs in a thread so it doesn't block FastAPI's async event loop.
    """
    try:
        return await anyio.to_thread.run_sync(_run_simulation_sync, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Unexpected error running simulation scenario=%s seed=%s", req.scenario_id, req.seed)
        raise HTTPException(status_code=500, detail="Could not run the simulation right now. Please try again.")
