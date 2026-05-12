
# This service is a focused evaluation helper.
# It is separate from the live run routes because it runs full simulations to
# compare team-style outcomes rather than driving one interactive session.
from __future__ import annotations

import io
import random
from contextlib import redirect_stdout
from typing import Any, Dict, List, Optional

from app.sim.agent_builder import apply_personality_to_agent, build_agent_traits
from app.sim.model import SimModel
from app.sim.scenario_data import SCENARIOS

_ESCAPE_IDS: List[str] = ["escape_room", "escape_proposal", "escape", "escape_puzzle"]

_SCENARIO_CONFIGS: Dict[str, Dict[str, Any]] = {
    "office": {"id": "office_proposal", "ticks": 25},
    "cafe":   {"id": "cafe_restaurant",  "ticks": 20},
    "escape": {"id": None,               "ticks": 20},
}

_TEAM_PRESETS: Dict[str, List[str]] = {
    "smooth_team":   ["Leader", "Easygoing", "Decisive", "Creative"],
    "tension_team":  ["Skeptical", "Overthinker", "Skeptical", "Decisive"],
    "creative_team": ["Creative", "Overthinker", "Creative", "Easygoing"],
    "pressure_team": ["Leader", "Decisive", "Skeptical", "Overthinker"],
}

_TEAM_STYLE_ALIASES: Dict[str, str] = {
    "smooth":        "smooth_team",
    "smooth_team":   "smooth_team",
    "tension":       "tension_team",
    "tension_team":  "tension_team",
    "creative":      "creative_team",
    "creative_team": "creative_team",
    "pressure":      "pressure_team",
    "pressure_team": "pressure_team",
}


# ──────────────────────────────────────────────────────────────────────────
# Normalisation helpers
# These keep the route layer simple by resolving scenario/team aliases here.
# ──────────────────────────────────────────────────────────────────────────

def _resolve_scenario(candidates: List[str]) -> Optional[str]:
    return next((s for s in candidates if s in SCENARIOS), None)


def _normalize_team_style(team_style: str) -> str:
    key = str(team_style or "").strip().lower().replace("-", "_")
    return _TEAM_STYLE_ALIASES.get(key, key)


def _get_scenario_id(scenario_type: str) -> Optional[str]:
    if scenario_type != "escape":
        return _SCENARIO_CONFIGS[scenario_type]["id"]
    return _resolve_scenario(_ESCAPE_IDS)


def compute_test_metrics(model: SimModel, scenario_type: str) -> Dict[str, Any]:
    """Compute personality test metrics from a completed simulation run."""
    all_events = [e for diff in model.history for e in diff.get("events", [])]

    coordination_reasons = {
        "escape_coordination", "escape_rush", "escape_unlock_attempt",
        "escape_door_open", "escape_forced_release", "escape_confirm_fallback",
        "escape_confirm", "office_confirm", "cafe_summary", "pull_quiet_member_in",
        "cafe_finalise", "leader_coord_opening", "leader_coordination",
        "leader_deadline", "pressure_escalation", "decisive_ultimatum",
    }
    coordination_phrases = (
        "keep moving", "keep the pace", "move on", "next piece", "next step",
        "stand by", "push on", "what's your status", "can you confirm",
        "straight answer", "less thinking", "we need", "let's keep",
        "time is tight", "running out", "no time",
    )
    emotional_markers = (
        "not ready", "still thinking", "not sure", "double-check",
        "wait", "what if", "spinning my wheels", "unsettled", "stalled",
    )

    coord_events = [
        e for e in all_events
        if e.get("reason") in coordination_reasons
        or (isinstance(e.get("text"), str) and any(p in e["text"].lower() for p in coordination_phrases))
        or e.get("type") == "ask_info"
    ]
    challenge_events = [e for e in all_events if e.get("type") in ("challenge", "refuse")]
    hesitation_events = [
        e for e in all_events
        if e.get("reason") in ("micro_drama_response", "overthinker_hesitate", "loop_break")
        or (e.get("type") == "say" and any(p in e.get("text", "").lower() for p in emotional_markers))
    ]

    total_events = max(1, len(all_events))
    peak_stress = max((a.stress for a in model.agents), default=0.0)
    avg_current_stress = sum(getattr(a, "stress", 0.0) for a in model.agents) / max(1, len(model.agents))
    avg_current_trust = sum(
        (sum((getattr(a, "trust", {}) or {}).values()) / len((getattr(a, "trust", {}) or {})))
        if (getattr(a, "trust", {}) or {}) else 0.5
        for a in model.agents
    ) / max(1, len(model.agents))

    conflict_score = getattr(model, "conflict_score", 0.0)
    coord_score = getattr(model, "coord_pressure_score", 0.0)

    emotional_score = min(
        1.0,
        (len(hesitation_events) / total_events) * 0.35
        + peak_stress * 0.25
        + avg_current_stress * 0.15
        + conflict_score * 0.25,
    )

    return {
        "ticks":          model.tick,
        "avg_trust":      round(avg_current_trust, 3),
        "peak_stress":    round(peak_stress, 3),
        "emotional":      round(emotional_score, 3),
        "coord_pressure": round(max(coord_score, len(coord_events) / total_events), 3),
        "conflict":       round(max(conflict_score, len(challenge_events) / total_events), 3),
    }


def run_personality_test(
    scenario: str,
    team_style: str,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Run a single personality test simulation and return metrics."""
    scenario_lower = scenario.lower()
    team_style_lower = _normalize_team_style(team_style)

    if scenario_lower not in _SCENARIO_CONFIGS or team_style_lower not in _TEAM_PRESETS:
        raise ValueError(f"Invalid scenario '{scenario}' or team style '{team_style}'")

    cfg = _SCENARIO_CONFIGS[scenario_lower]
    scenario_id = _get_scenario_id(scenario_lower)
    if not scenario_id:
        raise ValueError(f"No scenario found for '{scenario}'")

    seed = seed if seed is not None else random.SystemRandom().randint(1, 2_147_483_647)
    max_ticks = cfg["ticks"]

    model = SimModel(
        seed=seed,
        environment=SCENARIOS[scenario_id]["environment"],
        scenario_id=scenario_id,
        min_events_per_tick=0,
        episode_max_ticks=max_ticks,
    )
    model.skip_emotions = False
    model.conflict_score = 0.0
    model.coord_pressure_score = 0.0
    model.scenario_type = scenario_lower

    personalities = _TEAM_PRESETS[team_style_lower]
    for i, agent in enumerate(sorted(model.agents, key=lambda a: a.public_id)):
        ptype = personalities[i] if i < len(personalities) else "Easygoing"
        apply_personality_to_agent(agent, ptype)
        traits, _ = build_agent_traits(
            scenario_id,
            agent_id=agent.public_id,
            personality=ptype,
            add_noise=False,
        )
        for k, v in traits.items():
            setattr(agent, k, v)
            agent.traits[k] = v

    with redirect_stdout(io.StringIO()):
        while not model.ended and model.tick < max_ticks:
            model.step()
            if not model.last_diff:
                break
            if scenario_lower == "office":
                for e in model.last_diff.get("events", []):
                    etype = e.get("type")
                    reason = e.get("reason", "")
                    if etype in ("challenge", "refuse"):
                        model.conflict_score += 0.02
                    if reason in ("stress_driven_pressure", "frustrated_blocked_progress", "leader_deadline"):
                        model.conflict_score += 0.01
                    model.conflict_score = min(1.0, model.conflict_score)

    metrics = compute_test_metrics(model, scenario_lower)
    return {
        "seed":          seed,
        "scenario":      scenario_lower,
        "team_style":    team_style_lower,
        "personalities": {f"A{i+1}": p for i, p in enumerate(personalities)},
        "ticks":         metrics["ticks"],
        "success":       "3/3",
        "avg_trust":     metrics["avg_trust"],
        "emotional":     metrics["emotional"],
        "coord_pressure": metrics["coord_pressure"],
        "conflict":      metrics["conflict"],
        "peak_stress":   metrics["peak_stress"],
        "summary":       f"Test run for {scenario} with {team_style.replace('_', ' ')}.",
        "key_insight":   f"Peak stress: {metrics['peak_stress']}. Completed in {metrics['ticks']} ticks.",
    }
