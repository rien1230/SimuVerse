"""
agent_stress.py — passive (per-tick) stress update logic extracted from SimAgent.

The event-driven stress updates inside apply_events remain in agent.py because
they are tightly interleaved with trust, valence, memory, and knowledge updates
on the same conditional branches — splitting them would require duplicating or
reordering logic in ways that would change behaviour.

Only the *passive* tick block (environment decay + personality modifiers +
bottleneck pressure) is self-contained enough to extract cleanly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.sim.agent import SimAgent
    from app.sim.model import SimModel


def clamp(x: float, lo: float, hi: float) -> float:
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
    rm = env_rules.get("recovery_multiplier", 1.0)

    # Valence decays toward 0 — faster rm means faster decay
    valence_decay = 1.0 - (0.035 * rm)
    agent.valence *= clamp(valence_decay, 0.92, 0.99)
    agent.arousal = clamp(agent.arousal * 0.98 + 0.015, 0.0, 1.0)

    # Passive stress decay — scaled by recovery_multiplier
    stress_decay_rate = clamp(0.008 * rm, 0.004, 0.016)
    agent.stress = clamp(agent.stress * (1.0 - stress_decay_rate), 0.0, 1.0)

    # Personality-type modifiers (applied before scenario-logic hook, matching original order)
    ptype_stress = getattr(agent, "personality_type", "Easygoing")
    if ptype_stress == "Easygoing":
        agent.stress = clamp(agent.stress * 0.985, 0.0, 1.0)
    elif ptype_stress == "Overthinker":
        agent.stress = clamp(agent.stress + 0.008, 0.0, 1.0)
    elif ptype_stress == "Skeptical":
        agent.stress = clamp(agent.stress + 0.005, 0.0, 1.0)
    elif ptype_stress == "Creative":
        progress = model.scenario.progress_ratio()
        if progress < 0.6:
            agent.stress = clamp(agent.stress + 0.006, 0.0, 1.0)

    # Scenario-logic passive tick hook
    logic = getattr(model, "behaviour", None)
    tick = getattr(model, "tick", 0)
    if logic and hasattr(logic, "apply_passive_tick_effects"):
        logic.apply_passive_tick_effects(agent, tick)

    # Bottleneck pressure — scaled by environment stress multiplier so
    # escape-room runs feel urgently stuck while cafe runs stay relaxed.
    bottleneck_holder = getattr(model, "bottleneck_holder", None)
    bottleneck_age = getattr(model, "bottleneck_age", 0)
    sm = env_rules.get("stress_multiplier", 1.0)

    if model.scenario.progress_ratio() < 1.0 and bottleneck_age >= 2:
        agent.stress = clamp(agent.stress + 0.006 * sm, 0.0, 1.0)

    if (
        model.scenario.progress_ratio() < 1.0
        and agent.public_id == bottleneck_holder
        and bottleneck_age >= 2
    ):
        agent.stress = clamp(agent.stress + 0.015 * sm, 0.0, 1.0)

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

    if bottleneck_holder and bottleneck_holder != agent.public_id and bottleneck_age >= 3:
        current = agent.trust.get(bottleneck_holder, 0.5)
        agent.trust[bottleneck_holder] = clamp(current - 0.008, 0.0, 1.0)
