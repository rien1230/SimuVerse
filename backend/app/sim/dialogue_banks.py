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
    if stress < 0.30:
        return "calm"
    if stress < 0.55:
        return "mild"
    return "tense"


# ── Lookup helper ─────────────────────────────────────────────────────────────

def _scenario_type(agent: "SimAgent") -> str:
    behaviour = getattr(agent.model, "behaviour", None)
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

    Falls back through: exact match → any-personality pool → None.
    Substitutes {item}, {info}, {role} placeholders.
    """
    env = _scenario_type(agent)
    personality = getattr(agent, "personality_type", "Easygoing")
    tone = get_tone(agent.stress)

    env_pools = BANKS.get(env, BANKS.get("office", {}))

    # Try exact personality match first, then fall back to Easygoing as default
    for ptype in (personality, "Easygoing"):
        tone_map = env_pools.get(ptype, {})
        action_pool = tone_map.get(tone, {}).get(action)
        if action_pool:
            phrase = random.choice(action_pool)
            if item:
                phrase = phrase.replace("{item}", item)
            if info:
                phrase = phrase.replace("{info}", info)
            if role:
                phrase = phrase.replace("{role}", role)
            # Strip stray unfilled placeholders
            for placeholder in ("{item}", "{info}", "{role}"):
                phrase = phrase.replace(placeholder, "")
            return phrase.strip()

    return None
