from __future__ import annotations
import logging
from typing import Any, Dict

from app.sim import interventions as iv

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Private handlers — defined first so the dispatch table can reference them
# ---------------------------------------------------------------------------

def _handle_reveal_info(model, params: Dict[str, Any]) -> Dict[str, Any]:
    agent_id = params.get("agent_id")
    item     = params.get("item")
    if not agent_id or not item:
        return {"success": False, "reason": "reveal_info requires 'agent_id' and 'item'"}
    return iv.reveal_info(model, agent_id, item)


def _handle_nudge_strategy(model, params: Dict[str, Any]) -> Dict[str, Any]:
    agent_id = params.get("agent_id")
    strategy = params.get("strategy")
    if not agent_id or not strategy:
        return {"success": False, "reason": "nudge_strategy requires 'agent_id' and 'strategy'"}
    return iv.nudge_strategy(model, agent_id, strategy)


def _handle_boost_urgency(model, params: Dict[str, Any]) -> Dict[str, Any]:
    amount = params.get("amount", 0.2)
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"success": False, "reason": "'amount' must be a float between 0.0 and 1.0"}
    return iv.boost_urgency(model, amount)


def _handle_inject_tension(model, params: Dict[str, Any]) -> Dict[str, Any]:
    amount = params.get("amount", 0.2)
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"success": False, "reason": "'amount' must be a float between 0.0 and 1.0"}
    return iv.inject_tension(model, amount)


def _handle_force_meeting(model, params: Dict[str, Any]) -> Dict[str, Any]:
    agent_a = params.get("agent_a_id")
    agent_b = params.get("agent_b_id")
    if not agent_a or not agent_b:
        return {"success": False, "reason": "force_meeting requires 'agent_a_id' and 'agent_b_id'"}
    return iv.force_meeting(model, agent_a, agent_b)


# ---------------------------------------------------------------------------
# Dispatch table — defined after handlers so references are valid
# ---------------------------------------------------------------------------

_HANDLERS: Dict[str, Any] = {
    "reveal_info":    _handle_reveal_info,
    "nudge_strategy": _handle_nudge_strategy,
    "boost_urgency":  _handle_boost_urgency,
    "inject_tension": _handle_inject_tension,
    "force_meeting":  _handle_force_meeting,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def apply_intervention(model, intervention_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route an intervention request to the correct handler.
    Returns a result dict with 'success' and 'message' or 'reason'.
    """
    handler = _HANDLERS.get(intervention_type)
    if not handler:
        logger.warning(f"Unknown intervention type requested: '{intervention_type}'")
        return {
            "success": False,
            "reason": (
                f"Unknown intervention type '{intervention_type}'. "
                f"Valid types: {list(_HANDLERS.keys())}"
            ),
        }
    result = handler(model, params)
    if result.get("success"):
        logger.info(f"Intervention applied: type={intervention_type}, params={params}, tick={getattr(model, 'tick', '?')}")
    else:
        logger.warning(f"Intervention failed: type={intervention_type}, reason={result.get('reason')}")
    return result