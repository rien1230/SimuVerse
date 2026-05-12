
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
