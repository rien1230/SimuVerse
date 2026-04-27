"""
app/sim/agent_builder.py

Builds agent trait dicts and assigns personality_type.

User picks personality only.
Roles (office), preferences (cafe), archetypes (escape) are fixed by the system.

Usage:
    from app.sim.agent_builder import build_agent_traits, build_all_agents, get_personality_phrase

    # Single agent
    traits, ptype = build_agent_traits("office_proposal", agent_id="A1", personality="Skeptical")

    # All four agents
    all_traits = build_all_agents("office_proposal", personalities=["Leader","Skeptical","Overthinker","Creative"])

    # Get a personality phrase for dialogue
    phrase = get_personality_phrase(agent, action_type="challenge")
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

# All personality types recognised by the simulation.  Checked at agent-creation
# time so misconfigured callers get an immediate, descriptive error rather than
# silent wrong behaviour.
VALID_PERSONALITY_TYPES: frozenset = frozenset({
    "Leader",
    "Decisive",
    "Easygoing",
    "Skeptical",
    "Overthinker",
    "Creative",
})


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _add_variation(traits: dict, scale: float = 0.04) -> dict:
    return {k: _clamp(v + random.uniform(-scale, scale)) for k, v in traits.items()}


def _resolve_escape_archetype(agent_id: Optional[str], personality: str) -> str:
    """
    Map user-facing personality labels to valid escape archetype names.
    Falls back safely if a key is missing from ESCAPE_ARCHETYPE_MAP.
    """
    escape_personality_map = {
        "Leader": "Takes Charge",
        "Decisive": "Takes Charge",
        "Easygoing": "Calm One",
        "Skeptical": "Doubter",
        "Overthinker": "Overthinker",
        "Creative": "Overthinker",
    }

    candidates = []

    mapped = escape_personality_map.get(personality)
    if mapped:
        candidates.append(mapped)

    if agent_id:
        default_arch = ESCAPE_DEFAULT_ARCHETYPES.get(agent_id)
        if default_arch:
            candidates.append(default_arch)

    candidates.extend(
        [
            "Calm One",
            "Takes Charge",
            "Doubter",
            "Overthinker",
        ]
    )

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
    """
    Returns (traits_dict, personality_type_str).

    Office:  role base + personality delta
    Cafe:    preference base + personality delta
    Escape:  archetype directly (personality label maps to archetype)
    """
    sid = scenario_id.lower()
    personality = personality or "Easygoing"

    # ── Escape: personality label maps to an escape archetype ─────────────────
    if "escape" in sid:
        archetype = _resolve_escape_archetype(agent_id, personality)
        traits = dict(ESCAPE_ARCHETYPE_MAP[archetype])

        # Still apply personality delta so traits vary within the same archetype
        p_delta = PERSONALITIES.get(personality, {})
        for k in ("E", "A", "N", "C", "O"):
            traits[k] = _clamp(traits.get(k, 0.5) + p_delta.get(k, 0.0))

        return (_add_variation(traits) if add_noise else traits), personality

    # ── Cafe: preference base + personality delta ─────────────────────────────
    if "cafe" in sid:
        pref = CAFE_DEFAULT_PREFS.get(agent_id, "Easygoing") if agent_id else "Easygoing"
        base = dict(CAFE_PREF_MAP[pref])
        p_delta = PERSONALITIES.get(personality, {})
        traits = {k: _clamp(base[k] + p_delta.get(k, 0.0)) for k in base}
        return (_add_variation(traits) if add_noise else traits), personality

    # ── Office (default): role base + personality delta ──────────────────────
    role = OFFICE_DEFAULT_ROLES.get(agent_id, "Developer") if agent_id else "Developer"
    base = dict(OFFICE_ROLE_MAP[role])
    p_delta = PERSONALITIES.get(personality, {})
    traits = {k: _clamp(base[k] + p_delta.get(k, 0.0)) for k in base}
    return (_add_variation(traits) if add_noise else traits), personality


def build_all_agents(
    scenario_id: str,
    personalities: Optional[list] = None,
) -> Dict[str, Tuple[dict, str]]:
    """
    Returns {agent_id: (traits, personality_type)} for all 4 agents.

    personalities = ["Leader", "Skeptical", "Overthinker", "Creative"]
    (order maps to A1, A2, A3, A4)
    """
    agent_ids = ["A1", "A2", "A3", "A4"]
    if not personalities:
        personalities = ["Leader", "Skeptical", "Overthinker", "Creative"]
    personalities = (personalities * 4)[:4]  # pad/trim to exactly 4

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
    """
    Adjusts base probability by personality bias.
    Use in choose_action: prob = personality_action_modifier(agent, 0.40, "challenge")
    """
    bias = getattr(agent, "personality_bias", {})
    return max(0.05, min(0.95, base_prob + bias.get(action_type, 0.0)))