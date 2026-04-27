"""API routes for one-off simulation helpers used by the frontend."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import anyio
from app.sim.model import SimModel
from app.sim.scenario_data import SCENARIOS, resolve_scenario_id
from app.services.run_history_service import save_run

router = APIRouter(prefix="/simulation", tags=["simulation"])
logger = logging.getLogger(__name__)

class SimStartRequest(BaseModel):
    scenario_id: str = "office_proposal"
    seed: int = 42
    episode_max_ticks: int = 30
    skip_emotions: bool = False
    team_type: Optional[str] = None
    save_history: bool = True


def _generate_interpretation(model: SimModel) -> Dict[str, Any]:
    """Generate experiment-framed interpretation of a completed simulation run."""
    agents = list(model.agents)
    history = model.history

    # ── Aggregate metrics across the run ──────────────────────────────────────
    all_stress = [tick["metrics"]["avg_stress"] for tick in history if "metrics" in tick]
    peak_stress = max(all_stress) if all_stress else 0.0
    final_stress = all_stress[-1] if all_stress else 0.0

    all_trust = [tick["metrics"]["avg_trust"] for tick in history if "metrics" in tick]
    final_trust = all_trust[-1] if all_trust else 0.5

    refusal_total = sum(
        tick["metrics"].get("refusal_count", 0)
        for tick in history if "metrics" in tick
    )
    share_total = sum(
        tick["metrics"].get("share_count", 0)
        for tick in history if "metrics" in tick
    )

    # ── Per-agent stats ────────────────────────────────────────────────────────
    per_agent_refusals: Dict[str, int] = {}
    per_agent_shares: Dict[str, int] = {}
    for tick in history:
        for ev in tick.get("events", []):
            actor = ev.get("actor", "")
            if ev.get("type") == "refuse":
                per_agent_refusals[actor] = per_agent_refusals.get(actor, 0) + 1
            elif ev.get("type") == "share_info":
                per_agent_shares[actor] = per_agent_shares.get(actor, 0) + 1

    # Agent personalities
    personalities = {a.public_id: getattr(a, "personality_type", "Easygoing") for a in agents}

    # Most reluctant agent (most refusals)
    reluctant_id = max(per_agent_refusals, key=per_agent_refusals.get) if per_agent_refusals else None
    reluctant_personality = personalities.get(reluctant_id, "") if reluctant_id else ""
    reluctant_refusals = per_agent_refusals.get(reluctant_id, 0) if reluctant_id else 0

    # Most cooperative agent (most shares)
    cooperative_id = max(per_agent_shares, key=per_agent_shares.get) if per_agent_shares else None
    cooperative_personality = personalities.get(cooperative_id, "") if cooperative_id else ""

    # ── Scenario-level framing ─────────────────────────────────────────────────
    scenario_id = model.scenario.id
    env_type = "office" if "office" in scenario_id else "cafe" if "cafe" in scenario_id else "escape"

    env_labels = {
        "office": "professional task-coordination",
        "cafe":   "low-stakes social decision-making",
        "escape": "high-pressure collaborative problem-solving",
    }
    env_label = env_labels.get(env_type, env_type)

    completion_ticks = model.tick
    outcome = model.end_reason or "unknown"
    progress = model.scenario.progress_ratio()

    # ── Experiment 1: Personality effect ─────────────────────────────────────
    personality_counts: Dict[str, int] = {}
    for p in personalities.values():
        personality_counts[p] = personality_counts.get(p, 0) + 1
    dominant_p = max(personality_counts, key=personality_counts.get) if personality_counts else "mixed"

    p1_lines = []
    if reluctant_id and reluctant_refusals > 0:
        p1_lines.append(
            f"{reluctant_personality} agents delayed sharing "
            f"({reluctant_refusals} refusal{'s' if reluctant_refusals > 1 else ''} recorded)."
        )
    if cooperative_id and per_agent_shares.get(cooperative_id, 0) > 1:
        coop_shares = per_agent_shares[cooperative_id]
        p1_lines.append(
            f"{cooperative_personality} agents drove information flow "
            f"({coop_shares} shares)."
        )
    if peak_stress > 0.35:
        p1_lines.append(
            f"Peak group stress reached {peak_stress:.2f} — "
            f"high-N personality traits amplified tension under pressure."
        )
    elif peak_stress < 0.15:
        p1_lines.append(
            f"Peak stress stayed low at {peak_stress:.2f} — "
            f"agreeable personality mix kept dynamics stable."
        )

    experiment_1 = {
        "label": "Experiment 1 — Personality Effect",
        "finding": " ".join(p1_lines) if p1_lines else
                   f"Personality mix ({dominant_p}-dominant) produced {outcome} in {completion_ticks} ticks.",
        "metrics": {
            "peak_stress":      round(peak_stress, 3),
            "final_trust":      round(final_trust, 3),
            "total_refusals":   refusal_total,
            "total_shares":     share_total,
        },
    }

    # ── Experiment 2: Environment effect ─────────────────────────────────────
    stress_trajectory = "rising" if len(all_stress) >= 4 and all_stress[-1] > all_stress[0] else "stable"
    coord_label = {
        "office": "structured and sequential — agents queued information by role.",
        "cafe":   "negotiation-driven — preferences expressed before constraints resolved.",
        "escape": "pressure-sequential — clues unlocked in strict dependency order.",
    }.get(env_type, "unstructured.")

    e2_lines = [
        f"Environment: {env_label}.",
        f"Coordination pattern: {coord_label}",
        f"Stress trajectory was {stress_trajectory} "
        f"(start {all_stress[0]:.2f} → end {final_stress:.2f})." if all_stress else "",
    ]
    if outcome == "success":
        e2_lines.append(
            f"Task completed in {completion_ticks} ticks "
            f"({round(progress * 100)}% of tasks resolved)."
        )
    else:
        e2_lines.append(
            f"Run ended as {outcome} at tick {completion_ticks} "
            f"with {round(progress * 100)}% task completion."
        )

    experiment_2 = {
        "label": "Experiment 2 — Environment Effect",
        "finding": " ".join(l for l in e2_lines if l),
        "metrics": {
            "completion_ticks":   completion_ticks,
            "progress_pct":       round(progress * 100, 1),
            "stress_start":       round(all_stress[0], 3) if all_stress else 0,
            "stress_end":         round(final_stress, 3),
            "stress_trajectory":  stress_trajectory,
        },
    }

    # ── Overall summary — scenario-aware thresholds ───────────────────────────
    # Escape is inherently high-pressure; adjust what counts as "smooth"
    stress_hi = 0.30 if env_type == "escape" else 0.35
    stress_lo = 0.12 if env_type == "escape" else 0.20

    if outcome == "success" and peak_stress <= stress_lo:
        if env_type == "escape":
            summary = (
                f"Clean escape — group solved all clues in {completion_ticks} ticks "
                f"with peak stress at {peak_stress:.2f}. Strong coordination under time pressure."
            )
        else:
            summary = (
                f"Smooth run — high cooperation, low conflict. "
                f"{env_label.capitalize()} scenario completed in {completion_ticks} ticks."
            )
    elif outcome == "success" and peak_stress >= stress_hi:
        summary = (
            f"Successful but tense — stress peaked at {peak_stress:.2f}. "
            f"Agents pushed through pressure to complete the {env_type} scenario in {completion_ticks} ticks."
        )
    elif outcome == "success":
        summary = (
            f"{env_label.capitalize()} scenario completed in {completion_ticks} ticks. "
            f"Stress peaked at {peak_stress:.2f} — moderate tension, resolved through trust ({final_trust:.2f})."
        )
    elif outcome in ("partial", "failure"):
        summary = (
            f"Incomplete run ({round(progress * 100)}% done). "
            f"Group dynamics broke down under {env_type} conditions — refusals blocked progress."
        )
    else:
        summary = f"Outcome: {outcome}. {env_label.capitalize()} scenario, {completion_ticks} ticks."

    return {
        "summary":      summary,
        "experiment_1": experiment_1,
        "experiment_2": experiment_2,
    }


def _run_simulation_sync(req: SimStartRequest) -> Dict[str, Any]:
    """Run a full simulation synchronously — called off the event loop via anyio."""
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

    while not model.ended and model.tick < req.episode_max_ticks:
        model.step()

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
    interpretation = _generate_interpretation(model)
    return {
        "run_id":          run_id,
        "outcome":         model.end_reason,
        "ticks":           model.tick,
        "interpretation":  interpretation,
    }


@router.post("/start")
async def start_simulation(req: SimStartRequest):
    try:
        return await anyio.to_thread.run_sync(_run_simulation_sync, req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Unexpected error running simulation scenario=%s seed=%s", req.scenario_id, req.seed)
        raise HTTPException(status_code=500, detail="Could not run the simulation right now. Please try again.")
