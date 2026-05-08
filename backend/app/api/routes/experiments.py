"""API routes for creating and inspecting experiment runs."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from app.services.experiment_service import (
    run_experiment, compare_experiments,
    run_multi_scenario_experiment, compare_intervention_experiment,
    compare_team_styles, compare_scenarios, robustness_experiment,
)
from app.services.experiment_runner import run_experiment_batch, VALID_TEAM_STYLES
from app.sim.scenario_data import SCENARIOS, resolve_scenario_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/experiments", tags=["experiments"])


def _normalize_scenario_ids(scenario_ids: List[str]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for scenario_id in scenario_ids:
        resolved = resolve_scenario_id(scenario_id)
        if resolved not in seen:
            normalized.append(resolved)
            seen.add(resolved)
    return normalized


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


# ── Batch experiment runner ────────────────────────────────────────────────────

class ExperimentBatchRequest(BaseModel):
    # Which experiment to run
    experiment_type: str = Field(
        default="team_comparison",
        description="team_comparison | scenario_comparison | seed_reproducibility",
    )
    # ── Team comparison ──────────────────────────────────────────────────────
    scenario: str = Field(
        default="escape",
        description="Single scenario (team_comparison / seed_reproducibility).",
    )
    team_styles: List[str] = Field(
        default=["smooth", "tension", "creative", "pressure"],
        description="Team styles to compare (team_comparison only).",
    )
    # ── Scenario comparison ──────────────────────────────────────────────────
    scenarios: List[str] = Field(
        default=[],
        description="Multiple scenario short names (scenario_comparison only).",
    )
    team_style: Optional[str] = Field(
        default=None,
        description="Single team style (scenario_comparison / seed_reproducibility).",
    )
    # ── Shared ───────────────────────────────────────────────────────────────
    seeds: List[int] = Field(
        default=[101, 102, 103, 104, 105],
        description="RNG seeds — each seed runs once per style or scenario.",
    )
    max_steps: int = Field(default=30, ge=5, le=120, description="Step cap per run.")
    group_by: str = Field(default="team_style")


_VALID_EXP_TYPES = {"team_comparison", "scenario_comparison", "seed_reproducibility"}


@router.post("/batch")
async def run_batch_experiment(body: ExperimentBatchRequest) -> Dict[str, Any]:
    """
    Run a controlled batch experiment using the real simulation engine.

    Supports three experiment types:
      • team_comparison      — fixed scenario, compare multiple team styles across seeds
      • scenario_comparison  — fixed team style, compare multiple scenarios across seeds
      • seed_reproducibility — fixed team + scenario, verify consistency across seeds
    """
    if body.experiment_type not in _VALID_EXP_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown experiment_type '{body.experiment_type}'. "
                   f"Valid: {sorted(_VALID_EXP_TYPES)}",
        )
    if not body.seeds:
        raise HTTPException(422, "At least one seed is required.")
    if len(body.seeds) > 20:
        raise HTTPException(422, "Maximum 20 seeds per batch request.")

    if body.experiment_type == "team_comparison":
        invalid = [s for s in body.team_styles if s not in VALID_TEAM_STYLES]
        if invalid:
            raise HTTPException(422, f"Unknown team style(s): {invalid}.")
        if not body.team_styles:
            raise HTTPException(422, "At least one team style is required.")

    elif body.experiment_type == "scenario_comparison":
        if not body.scenarios:
            raise HTTPException(422, "Provide at least one scenario for scenario_comparison.")
        if not body.team_style:
            raise HTTPException(422, "team_style is required for scenario_comparison.")

    elif body.experiment_type == "seed_reproducibility":
        if not body.team_style:
            raise HTTPException(422, "team_style is required for seed_reproducibility.")

    try:
        return run_experiment_batch(body.model_dump())
    except Exception as exc:
        logger.exception("Experiment batch failed")
        raise HTTPException(status_code=500, detail=str(exc))
