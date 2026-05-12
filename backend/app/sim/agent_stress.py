"""
agent_stress.py — passive (per-tick) stress update logic extracted from SimAgent.

The event-driven stress updates inside apply_events remain in agent.py because
they are tightly interleaved with trust, valence, memory, and knowledge updates
on the same conditional branches — splitting them would require duplicating or
reordering logic in ways that would change behaviour.

Only the *passive* tick block (environment decay + personality modifiers +
bottleneck pressure) is self-contained enough to extract cleanly.

So this file exists to keep agent.py from becoming even larger while still
keeping the passive stress rules in one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.sim.agent import SimAgent
    from app.sim.model import SimModel


def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp x between lo and hi. Used everywhere stress/trust values are updated."""
    return max(lo, min(hi, x))


def apply_tick_stress(agent: "SimAgent", env_rules: dict, model: "SimModel") -> None:
    """Apply per-tick passive stress changes to agent.

    This covers:
    - Environment-modulated valence decay and arousal nudge
    - Passive stress decay scaled by recovery_multiplier
    - Personality-type stress modifiers
    - Bottleneck-pressure stress additions
    - Bottleneck trust erosion toward the holder (non-self)

    The scenario-logic hook (apply_passive_tick_effects) is also called here so
    that all passive tick effects stay co-located.
    """
    # recovery_multiplier comes from ENVIRONMENT_RULES in base_logic.py (café=1.2, escape=0.7)
    rm = env_rules.get("recovery_multiplier", 1.0)

    # Valence drifts back toward neutral (0.0) each tick.
    # A higher recovery_multiplier means the environment lets agents
    # recover faster — e.g. the casual café setting vs. the escape room.
    valence_decay = 1.0 - (0.035 * rm)
    agent.valence *= clamp(valence_decay, 0.92, 0.99)
    # Arousal slowly creeps up to a low baseline (0.015 per tick) unless
    # active events push it higher — keeps agents from being completely flat.
    agent.arousal = clamp(agent.arousal * 0.98 + 0.015, 0.0, 1.0)

    # Passive stress decay: stress reduces slightly every tick even with no events.
    # The rate is bounded so no environment setting can make stress decay trivially fast
    # or stick at full intensity permanently.
    stress_decay_rate = clamp(0.008 * rm, 0.004, 0.016)
    agent.stress = clamp(agent.stress * (1.0 - stress_decay_rate), 0.0, 1.0)

    # Personality-type modifiers applied on top of the base decay.
    # These are intentionally small — personality should bias stress accumulation,
    # not dominate it.
    ptype_stress = getattr(agent, "personality_type", "Easygoing")
    if ptype_stress == "Easygoing":
        # Extra passive relief — Easygoing types genuinely don't carry stress as long
        agent.stress = clamp(agent.stress * 0.985, 0.0, 1.0)
    elif ptype_stress == "Overthinker":
        # Always adding a small background anxiety even in calm ticks
        agent.stress = clamp(agent.stress + 0.008, 0.0, 1.0)
    elif ptype_stress == "Skeptical":
        # Mild background wariness — less than Overthinker but still present
        agent.stress = clamp(agent.stress + 0.005, 0.0, 1.0)
    elif ptype_stress == "Creative":
        # Creatives only accumulate extra stress when progress is low;
        # they're fine when things are moving forward
        progress = model.scenario.progress_ratio()
        if progress < 0.6:
            agent.stress = clamp(agent.stress + 0.006, 0.0, 1.0)

    # Let the scenario logic apply any additional passive effects specific
    # to that scenario (e.g. escape-room countdown pressure)
    logic = getattr(model, "behaviour", None)
    tick = getattr(model, "tick", 0)
    if logic and hasattr(logic, "apply_passive_tick_effects"):
        logic.apply_passive_tick_effects(agent, tick)

    # Bottleneck pressure: when a task has been stuck for 2+ ticks,
    # everyone gets a small stress bump. The holder gets a larger one
    # because they're on the critical path and feel the heat most.
    # Scaled by stress_multiplier so escape-room runs feel more urgent.
    bottleneck_holder = getattr(model, "bottleneck_holder", None)
    bottleneck_age = getattr(model, "bottleneck_age", 0)
    sm = env_rules.get("stress_multiplier", 1.0)

    # Group-wide pressure: everyone feels the stall
    if model.scenario.progress_ratio() < 1.0 and bottleneck_age >= 2:
        agent.stress = clamp(agent.stress + 0.006 * sm, 0.0, 1.0)

    # Extra pressure on the bottleneck holder specifically
    if (
        model.scenario.progress_ratio() < 1.0
        and agent.public_id == bottleneck_holder
        and bottleneck_age >= 2
    ):
        agent.stress = clamp(agent.stress + 0.015 * sm, 0.0, 1.0)

    # Personality-based emotional stress from prolonged bottleneck.
    # Overthinkers and Skeptics internalise stalls more than Easygoing types.
    if bottleneck_age >= 2 and model.scenario.progress_ratio() < 1.0:
        ptype_bn = getattr(agent, "personality_type", "Easygoing")
        bn_emotional = {
            "Overthinker": 0.015,
            "Skeptical": 0.010,
            "Decisive": 0.005,
            "Leader": 0.004,
            "Creative": 0.004,
            "Easygoing": 0.001,
        }.get(ptype_bn, 0.005)
        agent.emotional_stress = clamp(agent.emotional_stress + bn_emotional, 0.0, 1.0)

    # Trust erosion: if the bottleneck holder has been stuck for 3+ ticks,
    # other agents slowly lose faith in them — simulates rising frustration.
    # 0.008 per tick is small enough that a single stall doesn't destroy trust
    if bottleneck_holder and bottleneck_holder != agent.public_id and bottleneck_age >= 3:
        current = agent.trust.get(bottleneck_holder, 0.5)
        agent.trust[bottleneck_holder] = clamp(current - 0.008, 0.0, 1.0)
