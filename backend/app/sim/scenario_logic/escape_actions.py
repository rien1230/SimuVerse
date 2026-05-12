"""
escape_actions.py
=================
Per-tick action modifiers for the escape-room scenario:

  _pressure_personality_ids  — identifies agents whose personality creates
                               time-pressure (Decisive / Leader).
  _stress_profile            — classifies the team's current stress level as a
                               string ("smooth" | "creative" | "pressure" |
                               "tension"), respecting the team_preset floor.
  _apply_escape_tick_stress  — applies per-tick stress increments / reliefs to
                               a single agent based on profile, recent events,
                               and bottleneck age.

Imported by escape_logic.py.  All three functions reference agent/model
attributes at call time, so they carry no mutable state themselves.

This file is intentionally focused on Escape-specific per-tick stress/pressure
adjustments, rather than the full scenario flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Set

if TYPE_CHECKING:
    from app.sim.agent import SimAgent
    from app.sim.model import SimModel


# ──────────────────────────────────────────────────────────────────────────────
# Stress profile helpers
# These decide how much Escape pressure should build for the current team.
# ──────────────────────────────────────────────────────────────────────────────
def _pressure_personality_ids(model: "SimModel") -> Set[str]:
    ids: Set[str] = set()
    for agent in getattr(model, "agents", []):
        if getattr(agent, "personality_type", "") in {"Decisive", "Leader"}:
            ids.add(agent.public_id)
    return ids


def _stress_profile(model: "SimModel") -> str:
    """
    Derive an urgency profile from the team's personality mix, then apply the
    team_preset as a floor so a pressure_team / tension_team always generates
    at least that level of in-room urgency — even when the random personality
    draw doesn't naturally match.

    Smooth teams stay smooth regardless of preset (no cap upward imposed here).
    """
    personalities = [getattr(a, "personality_type", "") for a in getattr(model, "agents", [])]
    counts = {p: personalities.count(p) for p in set(personalities)}

    if counts.get("Skeptical", 0) >= 2 and counts.get("Overthinker", 0) >= 1:
        computed = "tension"
    elif (
        counts.get("Leader", 0) >= 1
        and counts.get("Decisive", 0) >= 1
        and (counts.get("Skeptical", 0) >= 1 or counts.get("Overthinker", 0) >= 1)
    ):
        computed = "pressure"
    elif counts.get("Creative", 0) >= 2 or (
        counts.get("Creative", 0) >= 1 and counts.get("Overthinker", 0) >= 1
    ):
        computed = "creative"
    else:
        computed = "smooth"

    # team_preset acts as a floor: a pressure_team should never be treated as
    # smooth just because the personality mix happened to draw without Skeptical.
    _profile_rank = {"smooth": 0, "creative": 1, "pressure": 2, "tension": 3}
    _preset_floor = {
        "pressure_team": "pressure",
        "tension_team":  "tension",
    }.get(getattr(model, "team_preset", "") or "")
    if _preset_floor and _profile_rank.get(computed, 0) < _profile_rank.get(_preset_floor, 0):
        return _preset_floor

    return computed


def _apply_escape_tick_stress(agent: "SimAgent") -> None:
    from app.sim.agent import clamp
    from app.sim.scenario_logic.base_logic import get_env_rules

    model = agent.model
    tick = getattr(model, "tick", 0)
    max_ticks = max(1, getattr(model, "episode_max_ticks", 20))
    tick_pct = tick / max_ticks

    logic = agent.traits.get("C", 0.5)
    neuroticism = agent.traits.get("N", 0.5)
    profile = _stress_profile(model)

    # stress grows linearly with time; high-C agents (logical) offset it
    base_tick_stress = (0.010 + 0.014 * tick_pct) * (0.65 + neuroticism) - (logic * 0.040)

    if profile == "pressure":
        base_tick_stress += 0.018
    elif profile == "tension":
        base_tick_stress += 0.010
    elif profile == "creative":
        base_tick_stress += 0.004
    elif profile == "smooth":
        # Smooth teams are calmer — but escape is still an escape room.
        # A small floor ensures some baseline urgency regardless of team fit.
        base_tick_stress -= 0.008  # was -0.048; reduced so smooth doesn't become a spa

    # Ensure escape always has at least a tiny positive tick stress floor
    # (the room's time pressure exists regardless of team personality)
    base_tick_stress = max(base_tick_stress, 0.004)

    # Scale by environment stress multiplier so physics are consistent with apply_events
    env_stress_mult = get_env_rules(model).get("stress_multiplier", 1.0)
    base_tick_stress *= env_stress_mult

    agent.stress = clamp(agent.stress + base_tick_stress, 0.0, 1.0)

    blocker_age = getattr(model, "_escape_bottleneck_age", 0)
    # pressure teams feel stalls hardest; smooth teams absorb them better
    bottleneck_mult = {
        "smooth": 0.30,
        "creative": 0.70,
        "tension": 0.65,
        "pressure": 1.25,
    }[profile]

    # cumulative hits — tiers stack, so a 6-tick stall adds all three
    if blocker_age >= 2:
        agent.stress = clamp(agent.stress + 0.012 * bottleneck_mult * (0.7 + neuroticism), 0.0, 1.0)
    if blocker_age >= 4:
        agent.stress = clamp(agent.stress + 0.020 * bottleneck_mult * (0.7 + neuroticism), 0.0, 1.0)
    if blocker_age >= 6:
        agent.stress = clamp(agent.stress + 0.028 * bottleneck_mult * (0.7 + neuroticism), 0.0, 1.0)

    # ── No-progress stall penalty ────────────────────────────────────────────
    # If no task has been completed in a while, every agent feels the freeze.
    items_done = sum(1 for v in model.scenario.tasks.values() if v)
    last_done = getattr(model, "_escape_last_items_done", 0)
    if items_done > last_done:
        model._escape_last_items_done = items_done
        model._escape_last_progress_tick = tick
    stall_ticks = tick - getattr(model, "_escape_last_progress_tick", 0)
    if stall_ticks >= 4:
        stall_mult = {"smooth": 0.30, "creative": 0.60, "tension": 0.70, "pressure": 1.40}[profile]
        stall_penalty = 0.022 * stall_mult * (0.6 + neuroticism)
        agent.stress = clamp(agent.stress + stall_penalty, 0.0, 1.0)

    prev = getattr(model, "prev_events", [])
    pressure_ids = _pressure_personality_ids(model)

    recent_share = any(
        e.get("type") == "share_info" and e.get("target") == agent.public_id
        for e in prev[-8:]
    )
    if recent_share:
        relief = {
            "smooth": 0.055,
            "creative": 0.028,
            "tension": 0.018,
            "pressure": 0.010,
        }[profile]
        agent.stress = clamp(agent.stress - relief, 0.0, 1.0)

    for e in prev[-6:]:
        if e.get("target") != agent.public_id:
            continue

        etype = e.get("type", "")
        reason = e.get("reason", "")
        actor_id = e.get("actor", "")

        if etype == "refuse":
            hit = {"smooth": 0.020, "creative": 0.035, "tension": 0.050, "pressure": 0.060}[profile]
            agent.stress = clamp(agent.stress + hit, 0.0, 1.0)

        elif reason == "escape_rush":
            hit = 0.050 if actor_id in pressure_ids else 0.038
            if profile == "pressure":
                hit *= 1.25
            elif profile == "tension":
                hit *= 1.05
            elif profile == "smooth":
                hit *= 0.45
            agent.stress = clamp(agent.stress + hit, 0.0, 1.0)

        elif etype == "challenge" and reason == "escape_doubt":
            hit = 0.020
            if profile == "pressure":
                hit *= 1.20
            elif profile == "tension":
                hit *= 1.05
            elif profile == "creative":
                hit *= 0.85
            elif profile == "smooth":
                hit *= 0.30
            agent.stress = clamp(agent.stress + hit, 0.0, 1.0)

        elif etype == "ask_info" and reason == "escape_ask_owner":
            hit = 0.010
            if actor_id in pressure_ids:
                hit += 0.012
            if profile == "pressure":
                hit *= 1.15
            elif profile == "tension":
                hit *= 1.05
            elif profile == "creative":
                hit *= 0.85
            elif profile == "smooth":
                hit *= 0.30
            agent.stress = clamp(agent.stress + hit, 0.0, 1.0)

    rush_count = sum(
        1
        for e in prev[-10:]
        if e.get("target") == agent.public_id and e.get("reason") == "escape_rush"
    )
    if rush_count >= 2:
        stack = {
            "smooth": 0.012,
            "creative": 0.026,
            "tension": 0.032,
            "pressure": 0.075,
        }[profile]
        agent.stress = clamp(agent.stress + stack, 0.0, 1.0)

    ask_count = sum(
        1
        for e in prev[-8:]
        if e.get("target") == agent.public_id
        and e.get("type") == "ask_info"
        and e.get("reason") == "escape_ask_owner"
    )
    if ask_count >= 2:
        extra = {
            "smooth": 0.001,
            "creative": 0.006,
            "tension": 0.012,
            "pressure": 0.026,
        }[profile] * (ask_count - 1)
        agent.stress = clamp(agent.stress + extra, 0.0, 1.0)

    # Slow trust decay — relationships drift without positive interaction
    if hasattr(agent, "trust") and agent.trust:
        for other_id in agent.trust:
            agent.trust[other_id] = clamp(agent.trust[other_id] * 0.995, 0.0, 1.0)
