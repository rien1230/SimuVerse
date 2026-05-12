"""
Final event cleanup before a tick is shown in the UI or saved to replay.

The pipeline runs in this order every tick:
    1. dedupe_same_actor_events  — remove duplicate events from the same agent
    2. filter_events             — drop stale/conflicting events based on active interventions
    3. dedupe_by_phrase_and_text — remove near-duplicate phrasing across the whole event list
    4. polish_dialogue           — fix capitalisation, spacing, and pronoun casing

This file exists so the final event list is cleaned up in one predictable place
before history, replay, and the frontend all consume it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.sim.model import SimModel

# These regex patterns are used by _polish_dialogue (defined in model.py).
# They're kept here so the module is self-documenting about what text fixes get applied.
_LOWERCASE_I_PATTERN = re.compile(r"(?<![A-Za-z'])i(?![A-Za-z'])")
# Do NOT capitalise after an ellipsis (e.g. "Umm... okay" must stay lowercase)
_AFTER_PUNCT_LOWER = re.compile(r"(?<!\.)([.!?]\s+)([a-z])")
_SENTENCE_START_LOWER = re.compile(r"^\s*([a-z])")
_AFTER_COLON_DASH_LOWER = re.compile(r"([:—]\s+)([a-z])")
_COLLAPSE_SPACES = re.compile(r"\s{2,}")


def _polish_dialogue(text: str) -> str:

    from app.sim.model import _polish_dialogue as _model_polish
    return _model_polish(text)


def normalize_events(
    model: "SimModel",
    collected_events: List[Dict[str, Any]],
    existing_events: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:

    from app.sim.model import _polish_dialogue

    # Keep this order stable: trim duplicates first, then remove contradictions,
    # then polish the final text that actually reaches the UI/replay log.
    normalized = model._dedupe_same_actor_events(collected_events)
    normalized = filter_events(model, normalized)
    normalized = model._dedupe_by_phrase_and_text(
        normalized,
        existing_events=existing_events,
    )
    # polish runs last — only applied to events that survived all filters
    for ev in normalized:
        raw = ev.get("text")
        if isinstance(raw, str) and raw:
            ev["text"] = _polish_dialogue(raw)
    return normalized


def filter_events(
    model: "SimModel",
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:

    # Track which agents are sharing info this tick — used later to suppress hesitation lines
    share_actors = {
        event["actor"] for event in events if event.get("type") == "share_info"
    }

    # Pull intervention state off the model (defaulting safely if not set)
    focus_item = getattr(model, "_intervention_focus_item", None)
    focus_until = getattr(model, "_intervention_focus_until", -1)
    quiet_until = getattr(model, "_intervention_quiet_until", -1)
    # True only if we're still inside the focus + quiet window for this intervention
    focus_quiet_active = bool(
        focus_item
        and getattr(model, "tick", 0) <= focus_until
        and getattr(model, "tick", 0) <= quiet_until
    )
    forced_agents = getattr(model, "_forced_meeting_agents", None)
    forced_until = getattr(model, "_forced_meeting_until", -1)
    forced_pair_active = bool(
        forced_agents and getattr(model, "tick", 0) <= forced_until
    )

    # Build a set of (actor, target, item) tuples for any user-triggered shares/agrees
    # so we can detect when an old ask_info is now redundant
    intervention_surfaces = {
        (
            str(event.get("actor", "")),
            str(event.get("target", "")),
            str(event.get("item") or event.get("preference") or ""),
        )
        for event in events
        if str(event.get("reason", "")).startswith("user_")
        and event.get("type") in {"share_info", "agree", "suggest"}
    }

    # Phrases that indicate an agent is stalling rather than actually sharing info.
    # We filter these out when the agent ends up sharing anyway in the same tick.
    hesitation = {
        "not ready",
        "still thinking",
        "not ignoring",
        "i'm just not ready",
        "give me a second",
        "i do have",
        "not sure i should",
        "i wasn't ready",
        "this can't wait much longer",
    }

    filtered: List[Dict[str, Any]] = []
    for event in events:
        text = str(event.get("text", "")).lower()
        event_type = str(event.get("type", ""))
        actor = str(event.get("actor", ""))
        target = str(event.get("target", ""))
        item = str(event.get("item") or event.get("preference") or "")
        reason = str(event.get("reason", ""))

        if (
            event_type == "ask_info"
            and (target, actor, item) in intervention_surfaces
            and not reason.startswith("user_")
        ):
            # intervention already handled this pair — the ask is now redundant
            continue

        if (
            forced_pair_active
            and actor in (forced_agents or set())
            and (
                reason in {"escape_owner_guard", "ownership_guard"}
                or (target and target not in (forced_agents or set()) and not reason.startswith("user_"))
            )
        ):
            # Don't let ownership guards or redirects to third parties break up a forced meeting
            continue

        if (
            focus_quiet_active
            and not reason.startswith("user_")
        ):
            # During a short intervention focus window, keep side chatter out so
            # the forced topic actually gets a clean beat on screen.
            if item and item != str(focus_item):
                continue
            if not item and event_type in {"say", "agree", "challenge", "suggest", "compliment"}:
                continue

        # If an agent is actively sharing info this tick, drop their hesitation lines —
        # they've already decided to share, so the reluctance reads as contradictory
        if actor in share_actors and event_type == "say":
            if any(phrase in text for phrase in hesitation):
                continue

        filtered.append(event)

    return filtered
