from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List
from app.services.experiment_service import (
    run_experiment, compare_experiments,
    run_multi_scenario_experiment, compare_intervention_experiment,
)
from app.sim.scenario_data import SCENARIOS

router = APIRouter(prefix="/experiments", tags=["experiments"])


class ExperimentRequest(BaseModel):
    scenario_id: str = Field(..., description="Scenario to run")
    n_runs: int = Field(default=20, ge=1, le=100)
    episode_max_ticks: int = Field(default=120, ge=10, le=500)
    skip_emotions: bool = Field(default=False, description="Disable NLP for baseline comparison")


class NLPCompareRequest(BaseModel):
    scenario_id: str
    n_runs: int = Field(default=20, ge=1, le=100)
    episode_max_ticks: int = Field(default=120, ge=10, le=500)


class MultiScenarioRequest(BaseModel):
    scenario_ids: List[str] = Field(..., description="List of scenario IDs to run")
    n_runs: int = Field(default=20, ge=1, le=100)
    episode_max_ticks: int = Field(default=120, ge=10, le=500)


class InterventionExperimentRequest(BaseModel):
    scenario_id: str
    intervention_type: str = Field(..., description="e.g. nudge_strategy, boost_urgency")
    intervention_params: Dict[str, Any] = Field(default_factory=dict)
    intervention_tick: int = Field(default=5, ge=1, description="Which tick to apply intervention")
    n_runs: int = Field(default=20, ge=1, le=100)
    episode_max_ticks: int = Field(default=120, ge=10, le=500)


@router.post("/run")
async def run_experiment_endpoint(request: ExperimentRequest):
    """
    Run a scenario n_runs times and return aggregate statistics.
    Uses whole-run metric averages, not just final tick.
    Set skip_emotions=true for a baseline run without NLP.
    """
    if request.scenario_id not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{request.scenario_id}'")
    result = run_experiment(
        scenario_id=request.scenario_id,
        n_runs=request.n_runs,
        episode_max_ticks=request.episode_max_ticks,
        skip_emotions=request.skip_emotions,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/compare-nlp")
async def compare_nlp_endpoint(request: NLPCompareRequest):
    """
    Key academic experiment: same scenario, NLP on vs NLP off.
    Returns side-by-side metrics, deltas, nlp_better flags, and a plain-English summary.
    Directly answers: does the NLP pipeline affect agent behaviour?
    """
    if request.scenario_id not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{request.scenario_id}'")
    return compare_experiments(
        scenario_id=request.scenario_id,
        n_runs=request.n_runs,
        episode_max_ticks=request.episode_max_ticks,
    )


@router.post("/multi-scenario")
async def multi_scenario_endpoint(request: MultiScenarioRequest):
    """
    Run multiple scenarios and compare results across environments.
    Useful for cross-scenario analysis in the dissertation.
    """
    invalid = [sid for sid in request.scenario_ids if sid not in SCENARIOS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown scenarios: {invalid}")
    return run_multi_scenario_experiment(
        scenario_ids=request.scenario_ids,
        n_runs=request.n_runs,
        episode_max_ticks=request.episode_max_ticks,
    )


@router.post("/compare-intervention")
async def compare_intervention_endpoint(request: InterventionExperimentRequest):
    """
    Compare baseline runs against runs with a specific intervention applied.
    Directly answers: does this intervention improve coordination?

    Example body:
    {
        "scenario_id": "office_proposal",
        "intervention_type": "nudge_strategy",
        "intervention_params": {"agent_id": "A3", "strategy": "cooperative"},
        "intervention_tick": 5,
        "n_runs": 20
    }
    """
    if request.scenario_id not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{request.scenario_id}'")
    return compare_intervention_experiment(
        scenario_id=request.scenario_id,
        intervention_type=request.intervention_type,
        intervention_params=request.intervention_params,
        intervention_tick=request.intervention_tick,
        n_runs=request.n_runs,
        episode_max_ticks=request.episode_max_ticks,
    )


@router.get("/scenarios")
async def list_scenarios():
    """List all scenarios available for experiments."""
    return {
        "scenarios": [
            {
                "id":          sid,
                "name":        data["name"],
                "environment": data["environment"],
                "tasks":       list(data.get("tasks", {}).keys()),
                "max_ticks":   data.get("max_ticks", 30),
            }
            for sid, data in SCENARIOS.items()
        ]
    }