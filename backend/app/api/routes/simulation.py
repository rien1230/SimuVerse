from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.sim.model import SimModel
from app.sim.scenario_data import SCENARIOS
from app.services.run_history_service import save_run

router = APIRouter(prefix="/simulation", tags=["simulation"])

class SimStartRequest(BaseModel):
    scenario_id: str = "office_proposal"
    seed: int = 42
    episode_max_ticks: int = 30
    skip_emotions: bool = False

@router.post("/start")
def start_simulation(req: SimStartRequest):
    if req.scenario_id not in SCENARIOS:
        return {"error": f"Unknown scenario: {req.scenario_id}"}

    model = SimModel(
        seed=req.seed,
        scenario_id=req.scenario_id,
        environment=SCENARIOS[req.scenario_id]["environment"],
        episode_max_ticks=req.episode_max_ticks,
    )
    model.skip_emotions = req.skip_emotions

    while not model.ended and model.tick < req.episode_max_ticks:
        model.step()

    run_id = save_run(model)
    return {
        "run_id":     run_id,
        "outcome":    model.end_reason,
        "ticks":      model.tick,
    }