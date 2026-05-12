"""
app/sim/dialogue_banks.py

Structured dialogue system: environment → personality → tone → action → phrases

Tone bands (based on agent stress):
    calm  : 0.00 – 0.29
    mild  : 0.30 – 0.54
    tense : 0.55+

Usage:
    from app.sim.dialogue_banks import pick_line, get_tone

    text = pick_line(agent, "agree")
    text = pick_line(agent, "share", info="the budget is £15 per head")
    text = pick_line(agent, "ask",   item="lock")

Data now lives in data/dialogue/*.json, loaded by dialogue_loader.py.

This file is the access layer for the structured dialogue bank.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.sim.agent import SimAgent

# Re-export data from loader for backward compatibility
from app.sim.dialogue_loader import BANKS  # noqa: F401

__all__ = ["BANKS", "get_tone", "pick_line"]


# ── Tone mapping ─────────────────────────────────────────────────────────────

def get_tone(stress: float) -> str:
    """
    Convert a numeric stress value into one of three tone labels.

    The tone is used to select which set of phrases an agent uses —
    stressed agents sound more clipped and urgent, calm agents are warmer.
    """
    if stress < 0.30:
        return "calm"
    if stress < 0.55:
        return "mild"
    return "tense"


# ── Lookup helper ─────────────────────────────────────────────────────────────

def _scenario_type(agent: "SimAgent") -> str:
    """Get the scenario environment type from the agent's model behaviour object."""
    behaviour = getattr(agent.model, "behaviour", None)
    # Default to "office" if behaviour isn't set yet (e.g. during early init)
    return getattr(behaviour, "scenario_type", "office")


def pick_line(
    agent: "SimAgent",
    action: str,
    item: str = "",
    info: str = "",
    role: str = "",
) -> Optional[str]:
    """
    Return a phrase from the structured dialogue bank for the given agent and action.

    Looks up phrases by environment, personality, tone, and action type.
    Falls back through: exact personality match → Easygoing default → None.
    Substitutes {item}, {info}, {role} placeholders before returning.

    Returns None if no matching phrase exists (caller decides what to do then).
    """
    env = _scenario_type(agent)
    personality = getattr(agent, "personality_type", "Easygoing")
    tone = get_tone(agent.stress)

    # If the environment isn't in the banks at all, fall back to office phrases
    env_pools = BANKS.get(env, BANKS.get("office", {}))

    # Try exact personality match first, then fall back to Easygoing as default
    for ptype in (personality, "Easygoing"):
        tone_map = env_pools.get(ptype, {})
        action_pool = tone_map.get(tone, {}).get(action)
        if action_pool:
            phrase = random.choice(action_pool)
            # Substitute any placeholders that were passed in
            if item:
                phrase = phrase.replace("{item}", item)
            if info:
                phrase = phrase.replace("{info}", info)
            if role:
                phrase = phrase.replace("{role}", role)
            # Clean up any placeholders that weren't filled (e.g. {item} with no item arg)
            for placeholder in ("{item}", "{info}", "{role}"):
                phrase = phrase.replace(placeholder, "")
            return phrase.strip()

    return None
