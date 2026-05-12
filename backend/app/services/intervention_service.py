"""Service layer that validates and dispatches intervention actions.

Interventions are live actions the user can apply to a running simulation
to change what happens. Each type is handled by a dedicated private function
which validates the params before calling the low-level sim function.

The public entry point is apply_intervention() — it routes the request to
the right handler using a dispatch table (_HANDLERS) and always returns a
dict with "success" and "message" so the API layer never has to deal with
inconsistent return shapes.

Main service entry point for live interventions before they reach sim/interventions.py.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from app.sim import interventions as iv

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _failure(message: str) -> Dict[str, Any]:
    return {
        "success": False,
        "message": message,
    }


def _normalise_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure every handler result always contains:
      - success: bool
      - message: str
    """
    if not isinstance(result, dict):
        return _failure("Intervention handler returned an invalid result")

    success = bool(result.get("success", False))
    message = result.get("message") or result.get("reason")

    if not message:
        message = "Intervention applied successfully" if success else "Intervention failed"

    normalised = dict(result)
    normalised["success"] = success
    normalised["message"] = message
    return normalised


# ---------------------------------------------------------------------------
# Private handlers — defined first so the dispatch table can reference them
# ---------------------------------------------------------------------------

def _handle_reveal_info(model, params: Dict[str, Any]) -> Dict[str, Any]:
    # Reveal-target restrictions live here because they are API/service rules,
    # not core simulation rules. The sim layer still keeps the real task chain.
    agent_id = params.get("agent_id")
    item = params.get("item")

    if not agent_id or not item:
        return _failure("reveal_info requires 'agent_id' and 'item'")

    scenario_type = getattr(getattr(model, "behaviour", None), "scenario_type", "")
    current_blocker = iv._current_blocker_item(model)
    if scenario_type == "cafe" and item == "decision":
        tasks = getattr(getattr(model, "scenario", None), "tasks", {}) or {}
        # block premature shortcuts — the final decision needs the three prerequisites first
        prerequisites_done = all(
            bool(tasks.get(key, False))
            for key in ("dietary_constraint", "budget_constraint", "location_constraint")
        )
        if current_blocker != "decision" or not prerequisites_done:
            return _failure(
                "Decision cannot be targeted directly in Cafe before the final decision phase. "
                "Resolve Dietary Constraint, Budget, and Location first."
            )
    if scenario_type == "escape" and item == "unlock":
        tasks = getattr(getattr(model, "scenario", None), "tasks", {}) or {}
        prerequisites_done = all(
            bool(tasks.get(key, False))
            for key in ("map", "lock", "key", "door")
        )
        if current_blocker != "unlock" or not prerequisites_done:
            return _failure(
                "Final Unlock cannot be targeted directly in Escape before the final unlock phase. "
                "Resolve Room Map, Lock Pattern, Key Location, and Door Code first."
            )

    return _normalise_result(iv.reveal_info(model, agent_id, item))


def _handle_nudge_strategy(model, params: Dict[str, Any]) -> Dict[str, Any]:
    agent_id = params.get("agent_id")
    strategy = params.get("strategy")

    if not agent_id or not strategy:
        return _failure("nudge_strategy requires 'agent_id' and 'strategy'")

    return _normalise_result(iv.nudge_strategy(model, agent_id, strategy))


def _handle_boost_urgency(model, params: Dict[str, Any]) -> Dict[str, Any]:
    amount = params.get("amount", 0.2)

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return _failure("'amount' must be a float between 0.0 and 1.0")

    if not 0.0 <= amount <= 1.0:
        return _failure("'amount' must be between 0.0 and 1.0")

    return _normalise_result(iv.boost_urgency(model, amount))


def _handle_ease_pressure(model, params: Dict[str, Any]) -> Dict[str, Any]:
    amount = params.get("amount", 0.2)

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return _failure("'amount' must be a float between 0.0 and 1.0")

    if not 0.0 <= amount <= 1.0:
        return _failure("'amount' must be between 0.0 and 1.0")

    return _normalise_result(iv.ease_pressure(model, amount))


def _handle_inject_tension(model, params: Dict[str, Any]) -> Dict[str, Any]:
    amount = params.get("amount", 0.2)

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return _failure("'amount' must be a float between 0.0 and 1.0")

    if not 0.0 <= amount <= 1.0:
        return _failure("'amount' must be between 0.0 and 1.0")

    return _normalise_result(iv.inject_tension(model, amount))


def _handle_force_meeting(model, params: Dict[str, Any]) -> Dict[str, Any]:
    agent_a = params.get("agent_a_id")
    agent_b = params.get("agent_b_id")

    if not agent_a or not agent_b:
        return _failure("force_meeting requires 'agent_a_id' and 'agent_b_id'")

    return _normalise_result(iv.force_meeting(model, agent_a, agent_b))


def _handle_inject_emotion(model, params: Dict[str, Any]) -> Dict[str, Any]:
    """Classify free-text emotion and apply the effect to all agents immediately.

    Uses the same classify_user_emotion + inject_user_emotion pipeline as the
    /simulation/start endpoint, so the effect (stress/trust/valence delta) and
    its decay are identical to what the setup-form emotion injection produces.
    """
    text = str(params.get("text", "")).strip()
    if not text:
        return _failure("inject_emotion requires a 'text' field in params")
    try:
        log_entry = model.inject_user_emotion(text, tick=getattr(model, "tick", 0))
        emotion = log_entry.get("detected_emotion", "neutral")
        short = text if len(text) <= 45 else text[:42] + "\u2026"
        return {
            "success": True,
            "message": (
                f"Emotion '{emotion}' detected and applied to all agents "
                f"(\"{short}\")."
            ),
        }
    except Exception as exc:
        return _failure(f"Emotion injection failed: {exc}")


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

# dispatch table — add new intervention types here, not in apply_intervention
_HANDLERS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "reveal_info": _handle_reveal_info,
    "nudge_strategy": _handle_nudge_strategy,
    "boost_urgency": _handle_boost_urgency,
    "ease_pressure": _handle_ease_pressure,
    "inject_tension": _handle_inject_tension,
    "force_meeting": _handle_force_meeting,
    "inject_emotion": _handle_inject_emotion,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def apply_intervention(
    model,
    intervention_type: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Route an intervention request to the correct handler.

    Always returns a dict containing:
      - success: bool
      - message: str
    """
    # single entry point — every intervention type routes through here
    handler = _HANDLERS.get(intervention_type)

    if not handler:
        logger.warning("Unknown intervention type requested: '%s'", intervention_type)
        return _failure(
            f"Unknown intervention type '{intervention_type}'. "
            f"Valid types: {list(_HANDLERS.keys())}"
        )

    result = _normalise_result(handler(model, params))

    if result["success"]:
        logger.info(
            "Intervention applied: type=%s, params=%s, tick=%s",
            intervention_type,
            params,
            getattr(model, "tick", "?"),
        )
    else:
        logger.warning(
            "Intervention failed: type=%s, message=%s",
            intervention_type,
            result["message"],
        )

    return result
