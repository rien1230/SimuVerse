"""
app/sim/agent_builder.py

Builds agent trait dicts and assigns personality_type.

Roles (office), preferences (cafe), and archetypes (escape) are fixed by the system.

Usage:
    from app.sim.agent_builder import build_agent_traits, build_all_agents, get_personality_phrase

    # Single agent
    traits, ptype = build_agent_traits("office_proposal", agent_id="A1", personality="Skeptical")

    # All four agents
    all_traits = build_all_agents("office_proposal", personalities=["Leader","Skeptical","Overthinker","Creative"])

    # Get a personality phrase for dialogue
    phrase = get_personality_phrase(agent, action_type="challenge")

This file is the construction layer for agent personalities.
This module turns team presets into concrete trait values and labels.
"""
from __future__ import annotations

import random
from typing import Optional, Tuple, Dict

from app.sim.personality_maps import (
    PERSONALITIES,
    PERSONALITY_ACTION_BIAS,
    PERSONALITY_PHRASES,
    OFFICE_ROLE_MAP,
    CAFE_PREF_MAP,
    ESCAPE_ARCHETYPE_MAP,
    OFFICE_DEFAULT_ROLES,
    CAFE_DEFAULT_PREFS,
    ESCAPE_DEFAULT_ARCHETYPES,
)

# ── Validation / shared constants ─────────────────────────────────────────
# All personality types recognised by the simulation. Checked at agent-creation
# time so bad config fails early and clearly.
VALID_PERSONALITY_TYPES: frozenset = frozenset({
    "Leader",
    "Decisive",
    "Easygoing",
    "Skeptical",
    "Overthinker",
    "Creative",
})


# ── Trait shaping helpers ────────────────────────────────────────────────

def _clamp(x: float) -> float:
    """Clamp a float to [0, 1] so trait values never go out of range."""
    return max(0.0, min(1.0, x))


def _add_variation(traits: dict, scale: float = 0.04) -> dict:
    """Add small random noise to each trait so agents aren't perfectly identical.
    The default scale of 0.04 gives noticeable but not dramatic variation.
    """
    return {k: _clamp(v + random.uniform(-scale, scale)) for k, v in traits.items()}


def _resolve_escape_archetype(agent_id: Optional[str], personality: str) -> str:
    """Map a user-facing personality label to a valid escape-room archetype name.

    The escape scenario uses a different vocabulary ("Takes Charge", "Doubter",
    etc.) rather than the standard personality labels, so we need this translation
    layer. We try candidates in priority order and return the first one that
    actually exists in ESCAPE_ARCHETYPE_MAP, which keeps us safe if the map
    ever changes.
    """
    # Translate personality labels to the closest escape archetype equivalent.
    # Leader and Decisive both map to "Takes Charge" because that archetype
    # captures the high-agency, directive behaviour they both share.
    escape_personality_map = {
        "Leader": "Takes Charge",
        "Decisive": "Takes Charge",
        "Easygoing": "Calm One",
        "Skeptical": "Doubter",
        "Overthinker": "Overthinker",
        "Creative": "Overthinker",  # Creative is closest to Overthinker in escape context
    }

    candidates = []

    # First priority: personality-derived archetype
    mapped = escape_personality_map.get(personality)
    if mapped:
        candidates.append(mapped)

    # Second priority: the agent's default escape archetype (if agent_id is known)
    if agent_id:
        default_arch = ESCAPE_DEFAULT_ARCHETYPES.get(agent_id)
        if default_arch:
            candidates.append(default_arch)

    # Final safety net — guaranteed archetypes to try if everything else misses
    candidates.extend(
        [
            "Calm One",
            "Takes Charge",
            "Doubter",
            "Overthinker",
        ]
    )

    # Return the first candidate that actually exists in the archetype map
    for candidate in candidates:
        if candidate in ESCAPE_ARCHETYPE_MAP:
            return candidate

    # Ultimate fallback: first available archetype in the imported map
    if ESCAPE_ARCHETYPE_MAP:
        return next(iter(ESCAPE_ARCHETYPE_MAP))

    raise ValueError("ESCAPE_ARCHETYPE_MAP is empty; cannot resolve escape archetype.")


def build_agent_traits(
    scenario_id: str,
    agent_id: Optional[str] = None,
    personality: Optional[str] = None,
    add_noise: bool = True,
) -> Tuple[dict, str]:
    """Build the OCEAN trait dict for one agent in a given scenario.

    The approach differs per scenario type because each has its own
    base-trait vocabulary:
      - Office: base traits come from the agent's role (e.g. PM, Developer)
      - Cafe:   base traits come from the agent's social preference style
      - Escape: base traits come from a thematic archetype (e.g. "Doubter")

    In all cases we then add the personality delta on top so the final
    traits reflect both the situational starting point and the personality.

    Parameters
    ----------
    scenario_id : str
        Used to detect scenario type (looks for "escape" / "cafe" in the id).
    agent_id : str, optional
        Which agent slot (A1–A4). Used to look up role/preference defaults.
    personality : str, optional
        Personality label from VALID_PERSONALITY_TYPES. Defaults to "Easygoing".
    add_noise : bool
        If True, small random variation is added so two agents with the same
        personality aren't completely identical.

    Returns
    -------
    (traits_dict, personality_type_str)
    """
    sid = scenario_id.lower()
    personality = personality or "Easygoing"

    # ── Escape: personality label maps to an escape archetype ─────────────────
    if "escape" in sid:
        archetype = _resolve_escape_archetype(agent_id, personality)
        traits = dict(ESCAPE_ARCHETYPE_MAP[archetype])

        # Still apply personality delta so traits vary within the same archetype.
        # Without this, all "Takes Charge" agents would have identical OCEAN scores.
        p_delta = PERSONALITIES.get(personality, {})
        for k in ("E", "A", "N", "C", "O"):
            traits[k] = _clamp(traits.get(k, 0.5) + p_delta.get(k, 0.0))

        return (_add_variation(traits) if add_noise else traits), personality

    # ── Cafe: preference base + personality delta ─────────────────────────────
    if "cafe" in sid:
        # Each agent slot has a default "preference style" that sets their
        # baseline social orientation before personality is layered on top.
        pref = CAFE_DEFAULT_PREFS.get(agent_id, "Easygoing") if agent_id else "Easygoing"
        base = dict(CAFE_PREF_MAP[pref])
        p_delta = PERSONALITIES.get(personality, {})
        traits = {k: _clamp(base[k] + p_delta.get(k, 0.0)) for k in base}
        return (_add_variation(traits) if add_noise else traits), personality

    # ── Office (default): role base + personality delta ──────────────────────
    # Each slot has a professional role (PM, Developer, etc.) that shapes the
    # starting OCEAN profile, then personality shifts it further.
    role = OFFICE_DEFAULT_ROLES.get(agent_id, "Developer") if agent_id else "Developer"
    base = dict(OFFICE_ROLE_MAP[role])
    p_delta = PERSONALITIES.get(personality, {})
    traits = {k: _clamp(base[k] + p_delta.get(k, 0.0)) for k in base}
    return (_add_variation(traits) if add_noise else traits), personality


def build_all_agents(
    scenario_id: str,
    personalities: Optional[list] = None,
) -> Dict[str, Tuple[dict, str]]:
    """Build trait dicts for all four agent slots at once.

    Convenience wrapper around build_agent_traits for when we want to
    configure an entire team in one call.

    Parameters
    ----------
    scenario_id : str
        Passed through to build_agent_traits for scenario-type detection.
    personalities : list of str, optional
        Personality labels for A1, A2, A3, A4 in that order.
        Defaults to a spread of archetypes if not provided.

    Returns
    -------
    dict mapping agent_id → (traits_dict, personality_type_str)
    """
    agent_ids = ["A1", "A2", "A3", "A4"]
    if not personalities:
        personalities = ["Leader", "Skeptical", "Overthinker", "Creative"]
    # Multiply and slice to always produce exactly 4 entries,
    # even if the caller passes fewer than 4 personalities.
    personalities = (personalities * 4)[:4]

    return {
        aid: build_agent_traits(
            scenario_id,
            agent_id=aid,
            personality=personalities[i],
        )
        for i, aid in enumerate(agent_ids)
    }


def apply_personality_to_agent(agent, personality_type: str) -> None:
    """
    Attach personality_type to a SimAgent instance.
    Call this after agent creation in model.py.

    Raises ValueError for unrecognised personality types so misconfigured
    callers get an immediate, descriptive error rather than silent wrong
    behaviour.
    """
    if personality_type not in VALID_PERSONALITY_TYPES:
        raise ValueError(
            f"Unknown personality type: {personality_type!r}. "
            f"Valid: {sorted(VALID_PERSONALITY_TYPES)}"
        )
    agent.personality_type = personality_type
    agent.personality_bias = PERSONALITY_ACTION_BIAS.get(personality_type, {})


def get_personality_phrase(agent, action_type: str) -> Optional[str]:
    """
    Returns a personality-specific phrase for the given action type,
    or None if no pool exists for this combination.
    """
    ptype = getattr(agent, "personality_type", None)
    if not ptype:
        return None

    pool = PERSONALITY_PHRASES.get(ptype, {}).get(action_type)
    return random.choice(pool) if pool else None


def personality_action_modifier(agent, base_prob: float, action_type: str) -> float:
    """Adjust a base action probability up or down based on personality bias.

    For example, a "Decisive" agent might have a higher challenge bias,
    making them more likely to push back. We clamp to [0.05, 0.95] to
    avoid fully blocking or guaranteeing any action.

    Usage in choose_action:
        prob = personality_action_modifier(agent, 0.40, "challenge")
    """
    bias = getattr(agent, "personality_bias", {})
    return max(0.05, min(0.95, base_prob + bias.get(action_type, 0.0)))
# ── Public builder functions ─────────────────────────────────────────────
# These are the entry points used by RunManager / SimModel when building agents.
