from __future__ import annotations
from typing import Any, Dict, Optional


def reveal_info(model, agent_id: str, item: str, complete_task: bool = False) -> Dict[str, Any]:
    """
    Give an agent immediate knowledge of an item.
    Optionally also marks the task as complete (by default only the agent learns).
    """
    agent = _find_agent(model, agent_id)
    if not agent:
        return {"success": False, "reason": f"Agent {agent_id} not found"}
    if item not in model.scenario.tasks:
        return {"success": False, "reason": f"Item '{item}' not in scenario tasks"}

    agent.known_items.add(item)

    if complete_task:
        model.scenario.complete_task(item)
        message = f"{agent_id} now knows '{item}' — task marked complete."
    else:
        message = f"{agent_id} now knows '{item}'."

    # Small positive emotional nudge
    agent.valence = min(1.0, agent.valence + 0.10)
    agent.stress = max(0.0, agent.stress - 0.05)

    return {"success": True, "message": message}


def nudge_strategy(model, agent_id: str, strategy: str) -> Dict[str, Any]:
    """Push an agent toward a behavioural strategy."""
    valid = {"cooperative", "defensive", "confrontational", "avoidant", "neutral", "assertive"}
    if strategy not in valid:
        return {"success": False, "reason": f"Invalid strategy. Choose from: {valid}"}

    agent = _find_agent(model, agent_id)
    if not agent:
        return {"success": False, "reason": f"Agent {agent_id} not found"}

    old = agent.strategy
    agent.strategy = strategy

    # Adjust internal state to be consistent with the nudged strategy
    if strategy == "cooperative":
        agent.stress = max(0.0, agent.stress - 0.10)
        agent.valence = min(1.0, agent.valence + 0.08)
    elif strategy in ("defensive", "avoidant"):
        agent.stress = min(1.0, agent.stress + 0.05)
    elif strategy == "confrontational":
        agent.arousal = min(1.0, agent.arousal + 0.10)

    agent.last_thought = f"[Intervention] Strategy shifted from {old} to {strategy}."

    return {"success": True, "message": f"{agent_id} strategy changed: {old} → {strategy}."}


def boost_urgency(model, amount: float) -> Dict[str, Any]:
    """Raise group-level urgency."""
    amount = max(0.0, min(1.0, amount))

    env = model.environment
    current = getattr(env, "urgency_modifier", 1.0)
    env.urgency_modifier = min(3.0, current + amount)

    # Reset stall counter to make urgency effective immediately
    model.progress_stall_ticks = max(0, model.progress_stall_ticks - 5)

    return {
        "success": True,
        "message": f"Urgency boosted by {amount:.2f}. Environment urgency now {env.urgency_modifier:.2f}.",
    }


def inject_tension(model, amount: float) -> Dict[str, Any]:
    """Raise group tension."""
    amount = max(0.0, min(1.0, amount))
    model.group_tension = min(1.0, model.group_tension + amount)

    for agent in model.agents:
        agent.env_tension_modifier = model.group_tension
        agent.stress = min(1.0, agent.stress + amount * 0.3)

    return {
        "success": True,
        "message": f"Group tension raised by {amount:.2f}. Now at {model.group_tension:.2f}.",
    }


def force_meeting(model, agent_a_id: str, agent_b_id: str) -> Dict[str, Any]:
    """Force two agents into a conversation next tick."""
    agent_a = _find_agent(model, agent_a_id)
    agent_b = _find_agent(model, agent_b_id)

    if not agent_a or not agent_b:
        return {"success": False, "reason": "One or both agents not found"}
    if agent_a_id == agent_b_id:
        return {"success": False, "reason": "Cannot force a meeting between the same agent"}

    # Clear existing conversations
    for a in [agent_a, agent_b]:
        a.current_conversation_with = None
        a.conversation_turn = 0
        a.awaiting_reply_from = None

    # Pair them
    agent_a.current_conversation_with = agent_b_id
    agent_b.current_conversation_with = agent_a_id
    agent_a.conversation_turn = 1
    agent_b.conversation_turn = 1
    agent_a.last_reply_tick = model.tick
    agent_b.last_reply_tick = model.tick

    # Signal to the model that a conversation is ongoing (so other agents don't interrupt)
    model.conversation_ongoing = True

    # Small trust nudge
    agent_a.trust[agent_b_id] = min(1.0, agent_a.trust.get(agent_b_id, 0.5) + 0.05)
    agent_b.trust[agent_a_id] = min(1.0, agent_b.trust.get(agent_a_id, 0.5) + 0.05)

    return {
        "success": True,
        "message": f"Meeting forced between {agent_a_id} and {agent_b_id}. They will interact next tick.",
    }


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------
def _find_agent(model, agent_id: str):
    return next((a for a in model.agents if a.public_id == agent_id), None)