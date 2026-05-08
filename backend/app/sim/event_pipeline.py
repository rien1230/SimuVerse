"""Final event cleanup before a tick is shown in the UI or saved to replay."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.sim.model import SimModel

_LOWERCASE_I_PATTERN = re.compile(r"(?<![A-Za-z'])i(?![A-Za-z'])")
# Do NOT capitalise after an ellipsis (e.g. "Umm... okay" must stay lowercase)
_AFTER_PUNCT_LOWER = re.compile(r"(?<!\.)([.!?]\s+)([a-z])")
_SENTENCE_START_LOWER = re.compile(r"^\s*([a-z])")
_AFTER_COLON_DASH_LOWER = re.compile(r"([:—]\s+)([a-z])")
_COLLAPSE_SPACES = re.compile(r"\s{2,}")


def _polish_dialogue(text: str) -> str:
    """Final cleanup pass for any rendered dialogue text."""
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
    for ev in normalized:
        raw = ev.get("text")
        if isinstance(raw, str) and raw:
            ev["text"] = _polish_dialogue(raw)
    return normalized


def filter_events(
    model: "SimModel",
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    share_actors = {
        event["actor"] for event in events if event.get("type") == "share_info"
    }
    focus_item = getattr(model, "_intervention_focus_item", None)
    focus_until = getattr(model, "_intervention_focus_until", -1)
    quiet_until = getattr(model, "_intervention_quiet_until", -1)
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
            # If a user-triggered share/agree is already queued for this pair,
            # skip the stale ask so the next tick doesn't argue with itself.
            continue

        if (
            forced_pair_active
            and actor in (forced_agents or set())
            and (
                reason in {"escape_owner_guard", "ownership_guard"}
                or (target and target not in (forced_agents or set()) and not reason.startswith("user_"))
            )
        ):
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

        if actor in share_actors and event_type == "say":
            if any(phrase in text for phrase in hesitation):
                continue

        filtered.append(event)

    return filtered
