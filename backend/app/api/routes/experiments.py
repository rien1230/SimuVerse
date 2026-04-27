"""API routes for creating and inspecting experiment runs."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from app.services.experiment_service import (
    run_experiment, compare_experiments,
    run_multi_scenario_experiment, compare_intervention_experiment,
    compare_team_styles, compare_scenarios, robustness_experiment,
)
from app.sim.scenario_data import SCENARIOS, resolve_scenario_id

router = APIRouter(prefix="/experiments", tags=["experiments"])


def _normalize_scenario_ids(scenario_ids: List[str]) -> List[str]:
    initialised: List[str] = []
    seen = set()
    for scenario_id in scenario_ids:
        resolved = resolve_scenario_id(scenario_id)
        if resolved not in seen:
            initialised.append(resolved)
            seen.add(resolved)
    return initialised


class ExperimentRequest(BaseModel):
    scenario_id: str = Field(..., description="Scenario to run")
    n_runs: int = Field(default=20, ge=1, le=100)
    episode_max_ticks: int = Field(default=120, ge=10, le=500)
    skip_emotions: bool = Field(default=False, description="Disable NLP for baseline comparison")
    team_type: Optional[str] = Field(default=None, description="Optional team style")
    persist_runs: bool = Field(default=False, description="Save generated runs for replay")


class NLPCompareRequest(BaseModel):
    scenario_id: str
    n_runs: int = Field(default=20, ge=1, le=100)
    episode_max_ticks: int = Field(default=120, ge=10, le=500)


class MultiScenarioRequest(BaseModel):
    scenario_ids: List[str] = Field(..., description="List of scenario IDs to run")
    n_runs: int = Field(default=20, ge=1, le=100)
    episode_max_ticks: int = Field(default=120, ge=10, le=500)
    team_type: Optional[str] = Field(default=None)
    persist_runs: bool = Field(default=False)


class TeamStyleCompareRequest(BaseModel):
    scenario_id: str
    seed: int = Field(default=5902, ge=0)
    episode_max_ticks: int = Field(default=120, ge=10, le=500)
    team_types: List[str] = Field(default_factory=lambda: ["smooth", "tension", "creative"])
    persist_runs: bool = Field(default=True)


class ScenarioCompareRequest(BaseModel):
    team_type: str = Field(default="smooth")
    seed: int = Field(default=5902, ge=0)
    episode_max_ticks: int = Field(default=120, ge=10, le=500)
    scenario_ids: List[str] = Field(
        default_factory=lambda: ["office_proposal", "cafe_restaurant", "escape_puzzle"]
    )
    persist_runs: bool = Field(default=True)


class RobustnessRequest(BaseModel):
    scenario_id: str
    team_type: str = Field(default="smooth")
    seed_start: int = Field(default=5902, ge=0)
    n_runs: int = Field(default=5, ge=2, le=20)
    episode_max_ticks: int = Field(default=120, ge=10, le=500)
    persist_runs: bool = Field(default=True)


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
    scenario_id = resolve_scenario_id(request.scenario_id)
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{request.scenario_id}'")
    result = run_experiment(
        scenario_id=scenario_id,
        n_runs=request.n_runs,
        episode_max_ticks=request.episode_max_ticks,
        skip_emotions=request.skip_emotions,
        team_type=request.team_type,
        persist_runs=request.persist_runs,
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
    scenario_id = resolve_scenario_id(request.scenario_id)
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{request.scenario_id}'")
    return compare_experiments(
        scenario_id=scenario_id,
        n_runs=request.n_runs,
        episode_max_ticks=request.episode_max_ticks,
    )


@router.post("/multi-scenario")
async def multi_scenario_endpoint(request: MultiScenarioRequest):
    """
    Run multiple scenarios and compare results across environments.
    Useful for cross-scenario analysis in the dissertation.
    """
    scenario_ids = _normalize_scenario_ids(request.scenario_ids)
    invalid = [sid for sid in scenario_ids if sid not in SCENARIOS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown scenarios: {invalid}")
    return run_multi_scenario_experiment(
        scenario_ids=scenario_ids,
        n_runs=request.n_runs,
        episode_max_ticks=request.episode_max_ticks,
        team_type=request.team_type,
        persist_runs=request.persist_runs,
    )


@router.post("/compare-team-styles")
async def compare_team_styles_endpoint(request: TeamStyleCompareRequest):
    """
    Controlled experiment: same scenario and seed, different team styles.
    This isolates personality/team behaviour from environment randomness.
    """
    scenario_id = resolve_scenario_id(request.scenario_id)
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{request.scenario_id}'")
    result = compare_team_styles(
        scenario_id=scenario_id,
        seed=request.seed,
        episode_max_ticks=request.episode_max_ticks,
        team_types=request.team_types,
        persist_runs=request.persist_runs,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/compare-scenarios")
async def compare_scenarios_endpoint(request: ScenarioCompareRequest):
    """
    Controlled experiment: same team style and seed, different scenarios.
    This isolates scenario pressure from team composition.
    """
    scenario_ids = _normalize_scenario_ids(request.scenario_ids)
    invalid = [sid for sid in scenario_ids if sid not in SCENARIOS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown scenarios: {invalid}")
    result = compare_scenarios(
        team_type=request.team_type,
        seed=request.seed,
        episode_max_ticks=request.episode_max_ticks,
        scenario_ids=scenario_ids,
        persist_runs=request.persist_runs,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/robustness")
async def robustness_endpoint(request: RobustnessRequest):
    """
    Controlled experiment: same scenario and team style, multiple seeds.
    This tests whether the behaviour is consistent across reruns.
    """
    scenario_id = resolve_scenario_id(request.scenario_id)
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{request.scenario_id}'")
    result = robustness_experiment(
        scenario_id=scenario_id,
        team_type=request.team_type,
        seed_start=request.seed_start,
        n_runs=request.n_runs,
        episode_max_ticks=request.episode_max_ticks,
        persist_runs=request.persist_runs,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


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
    scenario_id = resolve_scenario_id(request.scenario_id)
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{request.scenario_id}'")
    return compare_intervention_experiment(
        scenario_id=scenario_id,
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
