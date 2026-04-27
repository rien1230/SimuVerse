"""Intervention helpers that push a run toward movement, clarity, or tension."""

from __future__ import annotations
from typing import Any, Dict, Optional
import random


def reveal_info(model, agent_id: str, item: str, complete_task: bool = False) -> Dict[str, Any]:
    """
    Give an agent immediate knowledge of an item.
    Optionally also marks the task as complete.
    Also queues a visible conversation event so it appears in the log.
    """
    agent = _find_agent(model, agent_id)
    if not agent:
        return {"success": False, "reason": f"Agent {agent_id} not found"}
    if item not in model.scenario.tasks:
        return {"success": False, "reason": f"Item '{item}' not in scenario tasks"}

    # Already-known case: nothing to reveal. Still return success so the UI
    # banner is informative, but don't queue any dialogue — emitting a share
    # line when the agent already had the info reads as an info-dump.
    already_known = item in agent.known_items
    task_already_complete = bool(model.scenario.tasks.get(item, False))

    agent.known_items.add(item)
    if not already_known:
        agent.intervention_reveal_ticks[item] = getattr(model, "tick", 0)

    if complete_task:
        model.scenario.complete_task(item)
        message = f"{agent_id} now knows '{item}' — task marked complete."
    else:
        message = f"{agent_id} now knows '{item}'."

    agent.valence = min(1.0, agent.valence + 0.10)
    agent.stress = max(0.0, agent.stress - 0.05)

    target = None
    if not task_already_complete and not already_known:
        target = _pick_focus_partner(model, agent, item)

    if not task_already_complete and not already_known:
        focus_until = getattr(model, "tick", 0) + 2
        current_blocker = _current_blocker_item(model)
        if target is not None:
            if _should_surface_reveal_now(model, item):
                _set_intervention_focus(model, item, focus_until, quiet_ticks=2)
                _prime_focus_pair(model, agent, target, item, focus_until)
                if item not in getattr(target, "known_items", set()):
                    _queue_event(
                        model,
                        {
                            "type": "share_info",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": _direct_intervention_share_text(agent, item, target.public_id),
                            "item": item,
                            "reason": "user_reveal_info",
                        },
                    )
                    spoken = _spoken_item(item)
                    _queue_event(
                        model,
                        {
                            "type": "agree",
                            "actor": target.public_id,
                            "target": agent.public_id,
                            "text": _scenario_reveal_ack_text(model, item),
                            "preference": item,
                            "reason": "user_reveal_info",
                        },
                    )
                else:
                    spoken = _spoken_item(item)
                    _queue_event(
                        model,
                        {
                            "type": "suggest",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": _scenario_reveal_close_text(model, item),
                            "preference": item,
                            "reason": "user_reveal_info",
                        },
                    )
                    _queue_event(
                        model,
                        {
                            "type": "agree",
                            "actor": target.public_id,
                            "target": agent.public_id,
                            "text": _scenario_reveal_followup_text(model, item),
                            "preference": item,
                            "reason": "user_reveal_info",
                        },
                    )
            else:
                if item == current_blocker:
                    _set_intervention_focus(model, item, focus_until, quiet_ticks=2)
                    _prime_focus_agents([agent], item, focus_until)
                if target is not None:
                    _queue_event(
                        model,
                        {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": _delayed_reveal_coordination_text(agent, item),
                            "item": item,
                            "reason": "user_reveal_info",
                        },
                    )

    if complete_task and target is not None:
        _queue_event(
            model,
            {
                "type": "say",
                "actor": target.public_id,
                "target": agent.public_id,
                "text": "Good — that gives us what we need.",
                "reason": "task acknowledged",
            },
        )

    return {"success": True, "message": message}


def nudge_strategy(model, agent_id: str, strategy: str) -> Dict[str, Any]:
    """
    Push an agent toward a behavioural strategy.
    Also queues a visible line so the change is reflected in conversation.
    """
    valid = {"cooperative", "defensive", "confrontational", "avoidant", "neutral", "assertive"}
    if strategy not in valid:
        return {"success": False, "reason": f"Invalid strategy. Choose from: {valid}"}

    agent = _find_agent(model, agent_id)
    if not agent:
        return {"success": False, "reason": f"Agent {agent_id} not found"}

    old = agent.strategy
    agent.strategy = strategy

    current_tick = getattr(model, "tick", 0)
    # When the nudge would otherwise be a no-op (already this strategy), we
    # reinforce: extend the lock further and apply the strategy's valence /
    # stress effect anyway so the next tick still shows a visible behavioural
    # shift instead of silently succeeding.
    is_noop = (old == strategy)
    lock_ticks = 6 if is_noop else 4
    agent.strategy_locked_until = current_tick + lock_ticks
    agent.strategy_lock_source = "intervention"

    queued_event = None

    if strategy == "cooperative":
        agent.stress = max(0.0, agent.stress - 0.10)
        agent.valence = min(1.0, agent.valence + 0.08)
        focus_item = _current_blocker_item(model)
        action_item = _actionable_intervention_item(model, focus_item)
        target = _pick_focus_partner(model, agent, action_item or focus_item) if focus_item else None
        if focus_item:
            _set_intervention_focus(model, focus_item, current_tick + 2, quiet_ticks=2)
            _prime_focus_agents(
                [a for a in (agent, target) if a is not None],
                focus_item,
                current_tick + 2,
            )
            spoken = _spoken_item(action_item or focus_item)
            agent_knows = (action_item or focus_item) in getattr(agent, "known_items", set())
            target_knows = target is not None and (action_item or focus_item) in getattr(target, "known_items", set())

            # Cooperative nudge must look like *help*, not a question. If the
            # nudged agent knows the blocker, they share — even if the partner
            # also knows (acts as a confirm/lock-in). Only fall back to asking
            # when the nudged agent has no information at all.
            if agent_knows and target is not None:
                queued_event = {
                    "type": "share_info",
                    "actor": agent.public_id,
                    "target": target.public_id,
                    "text": _direct_intervention_share_text(agent, action_item or focus_item, target.public_id),
                    "item": action_item or focus_item,
                    "reason": "user_nudge_strategy",
                }
                line = queued_event["text"]
                _queue_event(
                    model,
                    {
                        "type": "agree",
                        "actor": target.public_id,
                        "target": agent.public_id,
                        "text": random.choice(
                            [
                                f"Good. {spoken.title()} is clear enough to use.",
                                f"Right. That's the piece we needed on {spoken}.",
                                f"Perfect. We can move with {spoken} now.",
                            ]
                        ),
                        "preference": action_item or focus_item,
                        "reason": "user_nudge_strategy",
                    },
                )
            elif target_knows:
                # Nudged agent has nothing on this item, but the partner does.
                # Frame it as a commitment to apply, then pull the real answer
                # straight through so the nudge feels immediately useful.
                queued_event = {
                    "type": "ask_info",
                    "actor": agent.public_id,
                    "target": target.public_id,
                    "text": random.choice(
                        [
                            f"Talk me through {spoken} — let's close it now.",
                            f"Walk me through {spoken} and we'll lock it in.",
                            f"Give me your read on {spoken} — let's finish it together.",
                        ]
                    ),
                    "item": action_item or focus_item,
                    "reason": "user_nudge_strategy",
                }
                line = queued_event["text"]
                _queue_event(
                    model,
                    {
                        "type": "share_info",
                        "actor": target.public_id,
                        "target": agent.public_id,
                        "text": _direct_intervention_share_text(target, action_item or focus_item, agent.public_id),
                        "item": action_item or focus_item,
                        "reason": "user_nudge_strategy",
                    },
                )
            else:
                # Neither side has it yet — commit to a concrete joint next
                # move instead of sounding politely passive.
                queued_event = {
                    "type": "suggest",
                    "actor": agent.public_id,
                    "target": target.public_id if target is not None else _pick_other_agent(model, agent_id).public_id,
                    "text": _scenario_cooperative_commitment(model, action_item or focus_item),
                    "preference": action_item or focus_item,
                    "reason": "user_nudge_strategy",
                }
                line = queued_event["text"]
                if target is not None:
                    _queue_event(
                        model,
                        {
                            "type": "agree",
                            "actor": target.public_id,
                            "target": agent.public_id,
                            "text": _scenario_supportive_reply(model, action_item or focus_item),
                            "preference": action_item or focus_item,
                            "reason": "user_nudge_strategy",
                        },
                    )
        else:
            target = _pick_other_agent(model, agent_id)
            line = "Okay — let's keep this constructive and get the blocker clear."
    elif strategy in ("defensive", "avoidant"):
        agent.stress = min(1.0, agent.stress + 0.05)
        if strategy == "defensive":
            line = "I want to be careful here before I commit to anything."
        else:
            line = "I'd rather slow this down a bit before we push ahead."
    elif strategy == "confrontational":
        agent.arousal = min(1.0, agent.arousal + 0.10)
        line = "We're wasting time — someone needs to make a call."
    elif strategy == "assertive":
        line = "Let's be direct and resolve the blocker now."
    else:
        line = "Okay — let's reset and take this one step at a time."

    if is_noop:
        agent.last_thought = f"[Intervention] {strategy.title()} approach reinforced."
    else:
        agent.last_thought = f"[Intervention] Strategy shifted from {old} to {strategy}."

    if strategy != "cooperative":
        target = _pick_other_agent(model, agent_id)
    if target:
        _queue_event(
            model,
            queued_event
            or {
                "type": "say",
                "actor": agent.public_id,
                "target": target.public_id,
                "text": line,
                "reason": "user_nudge_strategy",
            },
        )

    if is_noop:
        message = f"{agent_id} reinforced as {strategy}."
    else:
        message = f"{agent_id} strategy changed: {old} → {strategy}."
    return {"success": True, "message": message}

def boost_urgency(model, amount: float) -> Dict[str, Any]:
    """
    Raise group-level urgency.
    Also queues visible pressure dialogue.
    """
    amount = max(0.0, min(1.0, amount))

    env = model.environment
    current = getattr(env, "urgency_modifier", 1.0)
    env.urgency_modifier = min(3.0, current + amount)

    model.progress_stall_ticks = max(0, model.progress_stall_ticks - 5)

    speaker = _pick_leaderish_agent(model)
    focus_item = _current_blocker_item(model)
    target = _pick_focus_partner(model, speaker, focus_item) if speaker and focus_item else (
        _pick_other_agent(model, speaker.public_id) if speaker else None
    )

    if speaker and target:
        if focus_item:
            _set_intervention_focus(model, focus_item, getattr(model, "tick", 0) + 2, quiet_ticks=2)
            _prime_focus_agents([speaker, target], focus_item, getattr(model, "tick", 0) + 2)
            spoken = _spoken_item(focus_item)
            if focus_item in getattr(target, "known_items", set()) and focus_item not in getattr(speaker, "known_items", set()):
                text = (
                    f"{target.public_id}, {spoken} is the hold-up now. What do you have?"
                    if amount >= 0.5
                    else f"{target.public_id}, we need {spoken} now. Talk me through it."
                )
                event_type = "ask_info"
            elif focus_item in getattr(speaker, "known_items", set()) and focus_item not in getattr(target, "known_items", set()) and _item_ready_for_immediate_surface(model, focus_item):
                text = speaker._generate_share_text(focus_item, target.public_id)
                text = _direct_intervention_share_text(speaker, focus_item, target.public_id)
                event_type = "share_info"
            else:
                text = _scenario_urgent_prompt(model, focus_item, amount)
                event_type = "say"
        elif amount >= 0.5:
            text = "We are running out of time now — no more waiting."
            event_type = "say"
        elif amount >= 0.25:
            text = "Let's move faster — we need progress this tick."
            event_type = "say"
        else:
            text = "Quick pace now — let's keep momentum up."
            event_type = "say"

        _queue_event(
            model,
            {
                "type": event_type,
                "actor": speaker.public_id,
                "target": target.public_id,
                "text": text,
                "item": focus_item,
                "reason": "user_boost_urgency",
            },
        )

    return {
        "success": True,
        "message": f"Urgency boosted by {amount:.2f}. Environment urgency now {env.urgency_modifier:.2f}.",
    }


def inject_tension(model, amount: float) -> Dict[str, Any]:
    """
    Raise group tension.
    Also queues a visible tense interaction.
    """
    amount = max(0.0, min(1.0, amount))
    model.group_tension = min(1.0, model.group_tension + amount)

    for agent in model.agents:
        agent.env_tension_modifier = model.group_tension
        agent.stress = min(1.0, agent.stress + amount * 0.3)

    actor = _pick_high_stress_agent(model)
    focus_item = _current_blocker_item(model)
    target = _pick_focus_partner(model, actor, focus_item) if actor and focus_item else (
        _pick_other_agent(model, actor.public_id) if actor else None
    )

    if actor and target:
        if focus_item:
            _set_intervention_focus(model, focus_item, getattr(model, "tick", 0) + 2, quiet_ticks=2)
            _prime_focus_agents([actor, target], focus_item, getattr(model, "tick", 0) + 2)
            event_type, text = _scenario_tension_line(model, focus_item, amount)
            event = {
                "type": event_type,
                "actor": actor.public_id,
                "target": target.public_id,
                "text": text,
                "item": focus_item,
                "reason": "user_inject_tension",
            }
        elif amount >= 0.5:
            event = {
                "type": "challenge",
                "actor": actor.public_id,
                "target": target.public_id,
                "text": f"{target.public_id}, this is dragging — something needs to change now.",
                "reason": "user_inject_tension",
            }
        else:
            event = {
                "type": "say",
                "actor": actor.public_id,
                "target": target.public_id,
                "text": "Something about this is starting to feel tense.",
                "reason": "user_inject_tension",
            }
        _queue_event(model, event)

    return {
        "success": True,
        "message": f"Group tension raised by {amount:.2f}. Now at {model.group_tension:.2f}.",
    }


def force_meeting(model, agent_a_id: str, agent_b_id: str) -> Dict[str, Any]:
    """
    Force two agents into a conversation next tick.
    Also queues visible opening lines so the meeting shows in the log.
    """
    agent_a = _find_agent(model, agent_a_id)
    agent_b = _find_agent(model, agent_b_id)

    if not agent_a or not agent_b:
        return {"success": False, "reason": "One or both agents not found"}
    if agent_a_id == agent_b_id:
        return {"success": False, "reason": "Cannot force a meeting between the same agent"}

    for agent in getattr(model, "agents", []):
        agent.current_conversation_with = None
        agent.conversation_turn = 0
        agent.awaiting_reply_from = None

    agent_a.current_conversation_with = agent_b_id
    agent_b.current_conversation_with = agent_a_id
    agent_a.conversation_turn = 1
    agent_b.conversation_turn = 1
    agent_a.last_reply_tick = model.tick
    agent_b.last_reply_tick = model.tick

    model.conversation_ongoing = True
    model._forced_meeting_agents = {agent_a_id, agent_b_id}
    # Hold the meeting closed for 3 ticks: opener tick + 2 follow-up ticks.
    # During this window, agent.decide_event() returns None for any agent not
    # in the pair (see agent.py:283), so the forced pair owns the airspace and
    # cannot be interrupted by a third agent jumping topics.
    model._forced_meeting_until = getattr(model, "tick", 0) + 3
    model._forced_meeting_started_tick = getattr(model, "tick", 0)
    # Pin the meeting's anchor item so we can detect drift and re-prime the
    # forced topic across the whole window (set below once we know the item).
    model._forced_meeting_item = None

    agent_a.trust[agent_b_id] = min(1.0, agent_a.trust.get(agent_b_id, 0.5) + 0.05)
    agent_b.trust[agent_a_id] = min(1.0, agent_b.trust.get(agent_a_id, 0.5) + 0.05)

    # Anchor the opener to the most relevant unresolved task. Prefer the
    # current bottleneck and knowledge asymmetry between the chosen agents so
    # the forced exchange lands on something they can actually move.
    blocked_item = _current_blocker_item(model, prefer_agents=[agent_a, agent_b])
    if blocked_item:
        # Lock topic across the full meeting window so the pair stays on the
        # one unresolved item rather than drifting onto map/pattern/door.
        focus_until = getattr(model, "tick", 0) + 4
        model._forced_meeting_item = blocked_item
        _set_intervention_focus(model, blocked_item, focus_until, quiet_ticks=2)
        _prime_focus_pair(model, agent_a, agent_b, blocked_item, focus_until)

        a_knows = blocked_item in getattr(agent_a, "known_items", set())
        b_knows = blocked_item in getattr(agent_b, "known_items", set())

        if a_knows ^ b_knows:
            asker, knower = (agent_b, agent_a) if a_knows else (agent_a, agent_b)
            _queue_event(
                model,
                {
                    "type": "ask_info",
                    "actor": asker.public_id,
                    "target": knower.public_id,
                    "text": asker._generate_ask_text(blocked_item, knower.public_id),
                    "item": blocked_item,
                    "reason": "user_force_meeting",
                },
            )
            _queue_event(
                model,
                {
                    "type": "share_info",
                    "actor": knower.public_id,
                    "target": asker.public_id,
                    "text": knower._generate_share_text(blocked_item, asker.public_id),
                    "item": blocked_item,
                    "reason": "user_force_meeting",
                },
            )
            # Mark item as revealed in the escape-logic tracker so the ask-guard
            # (which checks _escape_revealed) prevents the asker from re-asking
            # after the share arrives next tick.
            if not hasattr(model, "_escape_revealed"):
                model._escape_revealed = {}
            model._escape_revealed[blocked_item] = True
        elif a_knows and b_knows:
            spoken = _spoken_item(blocked_item)
            info = agent_a._generate_info_text(blocked_item) or agent_b._generate_info_text(blocked_item) or spoken
            _queue_event(
                model,
                {
                    "type": "suggest",
                    "actor": agent_a.public_id,
                    "target": agent_b.public_id,
                    "text": _scenario_meeting_use_text(model, blocked_item, info),
                    "preference": blocked_item,
                    "reason": "user_force_meeting",
                },
            )
            _queue_event(
                model,
                {
                    "type": "agree",
                    "actor": agent_b.public_id,
                    "target": agent_a.public_id,
                    "text": _scenario_meeting_confirm_text(model, blocked_item),
                    "preference": blocked_item,
                    "reason": "user_force_meeting",
                },
            )
        else:
            _queue_event(
                model,
                {
                    "type": "suggest",
                    "actor": agent_a.public_id,
                    "target": agent_b.public_id,
                    "text": _scenario_meeting_open_text(model, blocked_item),
                    "preference": blocked_item,
                    "reason": "user_force_meeting",
                },
            )
            _queue_event(
                model,
                {
                    "type": "agree",
                    "actor": agent_b.public_id,
                    "target": agent_a.public_id,
                    "text": _scenario_meeting_anchor_text(model, blocked_item),
                    "preference": blocked_item,
                    "reason": "user_force_meeting",
                },
            )
    else:
        _queue_event(
            model,
            {
                "type": "say",
                "actor": agent_a.public_id,
                "target": agent_b.public_id,
                "text": f"{agent_b.public_id}, quick sync — anything still open on your side?",
                "reason": "user_force_meeting",
            },
        )
        _queue_event(
            model,
            {
                "type": "say",
                "actor": agent_b.public_id,
                "target": agent_a.public_id,
                "text": "Nothing pressing from me right now.",
                "reason": "user_force_meeting",
            },
        )

    return {
        "success": True,
        "message": f"Meeting forced between {agent_a_id} and {agent_b_id}. They will interact next tick.",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_agent(model, agent_id: str):
    return next((a for a in model.agents if a.public_id == agent_id), None)


def _queue_event(model, event: Dict[str, Any]) -> None:
    if not hasattr(model, "_pending_events"):
        model._pending_events = []
    model._pending_events.append(event)


def _pick_other_agent(model, agent_id: str):
    others = [a for a in model.agents if a.public_id != agent_id]
    return random.choice(others) if others else None


def _pick_leaderish_agent(model):
    preferred = None

    for agent in model.agents:
        roleish = getattr(agent, "personality_type", "")
        if roleish in {"Leader", "Decisive", "Assertive"}:
            preferred = agent
            break

    if preferred:
        return preferred

    return random.choice(list(model.agents)) if list(model.agents) else None


def _pick_high_stress_agent(model):
    agents = list(model.agents)
    if not agents:
        return None
    return max(agents, key=lambda a: getattr(a, "stress", 0.0))


def _spoken_item(item: str) -> str:
    spoken_map = {
        "lock": "pattern",
        "door": "door code",
        "unlock": "exit lock",
        "tech_specs": "spec doc",
        "dietary_constraint": "dietary constraint",
        "budget_constraint": "budget",
        "location_constraint": "location",
    }
    return spoken_map.get(str(item), str(item).replace("_", " "))


def _direct_intervention_share_text(agent, item: str, target_id: str) -> str:
    info = agent._generate_info_text(item) or _spoken_item(item)
    spoken = _spoken_item(item)
    scenario_type = getattr(getattr(agent.model, "behaviour", None), "scenario_type", "office")

    if scenario_type == "escape":
        options = [
            f"Here's the {spoken}: {info}",
            f"I've got the {spoken} clue: {info}",
            f"Right — {spoken}: {info}",
        ]
    elif scenario_type == "cafe":
        options = [
            f"Here's what I've got on {spoken}: {info}",
            f"Right, on {spoken}: {info}",
            f"I've got the {spoken} bit: {info}",
        ]
    else:
        options = [
            f"Here's the {spoken}: {info}",
            f"I've got the {spoken} detail: {info}",
            f"Right — {spoken}: {info}",
        ]

    return random.choice(options)


def _scenario_kind(model) -> str:
    return getattr(getattr(model, "behaviour", None), "scenario_type", "office")


def _current_blocker_item(model, prefer_agents=None) -> Optional[str]:
    scenario = getattr(model, "scenario", None)
    tasks = getattr(scenario, "tasks", {}) or {}
    bottleneck = getattr(model, "bottleneck_item", None)
    if bottleneck and bottleneck in tasks and not tasks.get(bottleneck, False) and bottleneck != "unlock":
        return bottleneck
    return _pick_blocked_item(model, prefer_agents=prefer_agents)


def _should_surface_reveal_now(model, item: str) -> bool:
    current = _current_blocker_item(model)
    if current and item != current:
        if _recent_requester_for_item(model, item) is None and getattr(model, "progress_stall_ticks", 0) < 4:
            return False
    return _item_ready_for_immediate_surface(model, item)


def _scenario_reveal_ack_text(model, item: str) -> str:
    spoken = _spoken_item(item)
    scenario_type = _scenario_kind(model)
    if scenario_type == "escape":
        return random.choice(
            [
                f"Good. That gives us {spoken}.",
                f"Right. {spoken.title()} is usable now.",
                f"Okay. That's enough on {spoken} to move.",
            ]
        )
    if scenario_type == "cafe":
        return random.choice(
            [
                f"Good. That helps with {spoken}.",
                f"Right. {spoken.title()} is clearer now.",
                f"Okay. That gives us something solid on {spoken}.",
            ]
        )
    return random.choice(
        [
            f"Good. That gives us {spoken}.",
            f"Right. {spoken.title()} is usable now.",
            f"Okay. That's enough on {spoken} to move.",
        ]
    )


def _scenario_reveal_close_text(model, item: str) -> str:
    spoken = _spoken_item(item)
    scenario_type = _scenario_kind(model)
    if scenario_type == "escape":
        return random.choice(
            [
                f"I've got {spoken} as well. Let's close it now.",
                f"{spoken.title()} is clear on my side too. Bring it in.",
                f"Okay, I've got {spoken}. Let's use it.",
            ]
        )
    if scenario_type == "cafe":
        return random.choice(
            [
                f"I've got the {spoken} side too. Let's settle it properly.",
                f"{spoken.title()} is clearer on my side as well. Let's close it.",
                f"Okay, I've got {spoken} too. Let's bring that into the choice.",
            ]
        )
    return random.choice(
        [
            f"I've got {spoken} as well now. Let's lock it in.",
            f"{spoken.title()} is clear on my side too. Let's close it.",
            f"Okay, I've got {spoken}. Let's close it.",
        ]
    )


def _scenario_reveal_followup_text(model, item: str) -> str:
    spoken = _spoken_item(item)
    scenario_type = _scenario_kind(model)
    if scenario_type == "escape":
        return random.choice(
            [
                f"Good. That's enough on {spoken} to use.",
                f"Right. {spoken.title()} is solid. Move.",
                f"Okay. We can use {spoken} now.",
            ]
        )
    if scenario_type == "cafe":
        return random.choice(
            [
                f"Good. That's enough on {spoken} to decide with.",
                f"Right. {spoken.title()} is one less thing to argue over.",
                f"Okay. We can work with {spoken} now.",
            ]
        )
    return random.choice(
        [
            f"Good. That's enough on {spoken} to move.",
            f"Right. {spoken.title()} is solid enough to use.",
            f"Okay. We can move with {spoken} now.",
        ]
    )


def _scenario_cooperative_commitment(model, item: str) -> str:
    spoken = _spoken_item(item)
    scenario_type = _scenario_kind(model)
    if scenario_type == "escape":
        return random.choice(
            [
                f"Stay with me on {spoken} — I'll close the gap and come straight back.",
                f"I'll take point on {spoken} and bring back the answer this tick.",
                f"Let's pin down {spoken} now and bring back something we can use.",
            ]
        )
    if scenario_type == "cafe":
        return random.choice(
            [
                f"I'll take point on {spoken} and bring back a clear answer this tick.",
                f"Stay with me on {spoken} — I'll tighten it up so we can decide.",
                f"Let's close {spoken} now and come back with something we can choose from.",
            ]
        )
    return random.choice(
        [
            f"I'll take point on {spoken} and bring back the detail this tick.",
            f"Stay with me on {spoken} — I'll close the gap and come straight back.",
            f"Let's pin down {spoken} now and bring back something we can use.",
        ]
    )


def _scenario_supportive_reply(model, item: str) -> str:
    spoken = _spoken_item(item)
    scenario_type = _scenario_kind(model)
    if scenario_type == "escape":
        return random.choice(
            [
                f"Right. Stay on {spoken}.",
                f"Okay. Bring back something solid on {spoken}.",
                f"Good. Close {spoken} and come straight back.",
            ]
        )
    if scenario_type == "cafe":
        return random.choice(
            [
                f"Right. Stay on {spoken}.",
                f"Okay. Bring back something solid on {spoken}.",
                f"Good. Close {spoken} so we can choose.",
            ]
        )
    return random.choice(
        [
            f"Right. Stay on {spoken}.",
            f"Okay. {spoken.title()} first, then we move.",
            f"Good. Bring back something we can use on {spoken}.",
        ]
    )


def _scenario_meeting_use_text(model, item: str, info: str) -> str:
    spoken = _spoken_item(item)
    clean_info = str(info or "").rstrip(".!?")
    scenario_type = _scenario_kind(model)
    if scenario_type == "escape":
        return random.choice(
            [
                f"We've got {spoken}: {clean_info}. Use it now.",
                f"That's {spoken}: {clean_info}. Move with it.",
                f"{spoken.title()} is clear: {clean_info}. Bring it in now.",
            ]
        )
    if scenario_type == "cafe":
        return random.choice(
            [
                f"We've got the {spoken} piece: {clean_info}. Use it to make the call.",
                f"That gives us {spoken}: {clean_info}. Let's decide from it.",
                f"{spoken.title()} is clear: {clean_info}. Use that to land the choice.",
            ]
        )
    return random.choice(
        [
            f"We've got {spoken}: {clean_info}. Use it now.",
            f"That's {spoken}: {clean_info}. Move with it.",
            f"{spoken.title()} is clear: {clean_info}. Bring it in now.",
        ]
    )


def _scenario_meeting_confirm_text(model, item: str) -> str:
    spoken = _spoken_item(item)
    scenario_type = _scenario_kind(model)
    if scenario_type == "escape":
        return random.choice(
            [
                f"Good. {spoken.title()} now.",
                f"Right. That's enough on {spoken}. Use it.",
                f"Okay. {spoken.title()} is ready. Move.",
            ]
        )
    if scenario_type == "cafe":
        return random.choice(
            [
                f"Good. That's enough on {spoken}. Decide from it.",
                f"Right. {spoken.title()} is clear enough. Let's choose.",
                f"Okay. Use that {spoken} call and land it.",
            ]
        )
    return random.choice(
        [
            f"Good. {spoken.title()} now.",
            f"Right. That's enough on {spoken}. Use it.",
            f"Okay. {spoken.title()} is ready. Move.",
        ]
    )


def _scenario_meeting_open_text(model, item: str) -> str:
    spoken = _spoken_item(item)
    scenario_type = _scenario_kind(model)
    if scenario_type == "escape":
        return random.choice(
            [
                f"We still need {spoken}. Which one of us can close it fastest?",
                f"{spoken.title()} is still the hold-up. Let's pin down who has it.",
                f"We're stuck on {spoken}. Let's sort it between us now.",
            ]
        )
    if scenario_type == "cafe":
        return random.choice(
            [
                f"We still need the {spoken} part. Which one of us can settle it quickest?",
                f"{spoken.title()} is still the sticking point. Let's close it between us.",
                f"We haven't landed {spoken} yet. Let's sort it now.",
            ]
        )
    return random.choice(
        [
            f"We still need {spoken}. Which one of us can close it quickest?",
            f"{spoken.title()} is still the hold-up. Let's pin down who has it.",
            f"We haven't landed {spoken} yet. Let's sort it between us now.",
        ]
    )


def _scenario_meeting_anchor_text(model, item: str) -> str:
    spoken = _spoken_item(item)
    scenario_type = _scenario_kind(model)
    if scenario_type == "escape":
        return random.choice(
            [
                f"Right. {spoken.title()} first.",
                f"Okay. {spoken.title()} is the blocker.",
                f"Fine. {spoken.title()} before anything else.",
            ]
        )
    if scenario_type == "cafe":
        return random.choice(
            [
                f"Right. {spoken.title()} first.",
                f"Okay. {spoken.title()} is the sticking point.",
                f"Fine. We sort {spoken} before we choose.",
            ]
        )
    return random.choice(
        [
            f"Right. {spoken.title()} first.",
            f"Okay. {spoken.title()} is the blocker.",
            f"Fine. {spoken.title()} before anything else.",
        ]
    )


def _scenario_urgent_prompt(model, item: Optional[str], amount: float) -> str:
    spoken = _spoken_item(item or "the blocker")
    scenario_type = getattr(getattr(model, "behaviour", None), "scenario_type", "office")

    if scenario_type == "escape":
        if amount >= 0.5:
            return f"{spoken.title()} is the blocker now. Close it this tick."
        return f"Let's settle {spoken} now and keep moving."

    if scenario_type == "cafe":
        if amount >= 0.5:
            return f"Let's stop circling {spoken} and make the call now."
        return f"Let's settle {spoken} so we can actually choose."

    if amount >= 0.5:
        return f"{spoken.title()} is holding the work up. Close it now."
    return f"Let's lock {spoken} so the rest can move."


def _scenario_tension_line(model, item: Optional[str], amount: float) -> tuple[str, str]:
    spoken = _spoken_item(item or "the blocker")
    scenario_type = getattr(getattr(model, "behaviour", None), "scenario_type", "office")

    if scenario_type == "escape":
        if amount >= 0.25:
            return (
                "challenge",
                random.choice(
                    [
                        f"We keep circling {spoken}. Is it right or not?",
                        f"{spoken.title()} is still shaky. Check it now.",
                        f"We're still stuck on {spoken}. I need a straight answer.",
                    ]
                ),
            )
        return (
            "say",
            random.choice(
                [
                    f"{spoken.title()} is starting to feel shaky.",
                    f"I don't like how loose {spoken} still feels.",
                    f"{spoken.title()} still doesn't feel settled enough.",
                ]
            ),
        )

    if scenario_type == "cafe":
        if amount >= 0.25:
            return (
                "challenge",
                random.choice(
                    [
                        f"We're still not aligned on {spoken}. Is this actually workable?",
                        f"{spoken.title()} still feels shaky to me.",
                        f"We keep bouncing on {spoken}. Can someone lock it down?",
                    ]
                ),
            )
        return (
            "say",
            random.choice(
                [
                    f"{spoken.title()} still feels a bit unresolved.",
                    f"I'm not convinced we've really settled {spoken}.",
                    f"{spoken.title()} still feels wobbly.",
                ]
            ),
        )

    if amount >= 0.25:
        return (
            "challenge",
            random.choice(
                [
                    f"{spoken.title()} still feels shaky. I need a straight answer.",
                    f"We're not solid on {spoken} yet.",
                    f"{spoken.title()} is still loose. Can we lock it down?",
                ]
            ),
        )
    return (
        "say",
        random.choice(
            [
                f"{spoken.title()} still doesn't feel fully settled.",
                f"I'm not convinced {spoken} is clear enough yet.",
                f"{spoken.title()} still feels loose.",
            ]
        ),
    )


def _delayed_reveal_coordination_text(agent, item: str) -> str:
    model = agent.model
    spoken = _spoken_item(item)
    blocker = getattr(model, "bottleneck_item", None)
    blocker_spoken = _spoken_item(blocker) if blocker and blocker != item else None
    scenario_type = getattr(getattr(model, "behaviour", None), "scenario_type", "office")

    if scenario_type == "escape":
        if blocker_spoken:
            options = [
                f"I've got {spoken} ready. Close {blocker_spoken} and I'll call it immediately.",
                f"{spoken.title()} is ready on my side. Once {blocker_spoken} lands, I'll bring it straight in.",
                f"I've got the {spoken} piece lined up. Finish {blocker_spoken} and I'll use it.",
            ]
        else:
            options = [
                f"I've got {spoken} ready to use as soon as we need it.",
                f"{spoken.title()} is ready on my side. Pull me in when it opens up.",
                f"I've got the {spoken} piece ready. I'll use it the moment it matters.",
            ]
    elif scenario_type == "cafe":
        if blocker_spoken:
            options = [
                f"I've got the {spoken} side. Once {blocker_spoken} is clear, I can narrow this down fast.",
                f"The {spoken} piece is ready with me. Let me bring it in once {blocker_spoken} is settled.",
                f"I've got {spoken} covered. As soon as {blocker_spoken} is clear, I'll use it to tighten the choice.",
            ]
        else:
            options = [
                f"I've got the {spoken} side ready to bring in.",
                f"The {spoken} piece is with me. I'll use it when the choice tightens up.",
                f"I've got {spoken} covered and ready to use.",
            ]
    else:
        if blocker_spoken:
            options = [
                f"I've got the {spoken} piece ready. Once {blocker_spoken} lands, I'll slot it straight in.",
                f"{spoken.title()} is ready on my side. Finish {blocker_spoken} and I'll bring it through.",
                f"I've got {spoken} lined up. As soon as {blocker_spoken} is closed, I'll use it.",
            ]
        else:
            options = [
                f"I've got the {spoken} piece ready to bring in.",
                f"{spoken.title()} is ready on my side. Pull me in when we need it.",
                f"I've got {spoken} lined up and ready to use.",
            ]

    return random.choice(options)


def _prime_focus_agents(agents, item: str, until_tick: int) -> None:
    for agent in agents:
        if agent is None:
            continue
        agent.forced_topic_item = item
        agent.forced_topic_until = until_tick


def _prime_focus_pair(model, agent_a, agent_b, item: str, until_tick: int) -> None:
    _prime_focus_agents([agent_a, agent_b], item, until_tick)
    for agent, other in ((agent_a, agent_b), (agent_b, agent_a)):
        agent.current_conversation_with = other.public_id
        agent.awaiting_reply_from = None
        agent.conversation_turn = 1
        agent.last_reply_tick = getattr(model, "tick", 0)
    model.conversation_ongoing = True


def _set_intervention_focus(model, item: Optional[str], until_tick: int, quiet_ticks: int = 2) -> None:
    if not item:
        return
    model._intervention_focus_item = item
    model._intervention_focus_until = max(
        getattr(model, "_intervention_focus_until", -1),
        until_tick,
    )
    current_tick = getattr(model, "tick", 0)
    model._intervention_quiet_item = item
    model._intervention_quiet_until = max(
        getattr(model, "_intervention_quiet_until", -1),
        current_tick + quiet_ticks,
    )


def _recent_requester_for_item(model, item: str, exclude: Optional[str] = None):
    current_tick = getattr(model, "tick", 0)
    for event in reversed(getattr(model, "prev_events", [])[-10:]):
        if event.get("type") != "ask_info" or event.get("item") != item:
            continue
        actor = event.get("actor")
        if actor and actor != exclude:
            return _find_agent(model, actor)

    for snap in reversed(getattr(model, "history", [])[-4:]):
        snap_tick = snap.get("tick", current_tick)
        if current_tick - snap_tick > 3:
            continue
        for event in reversed(snap.get("events", []) or []):
            if event.get("type") != "ask_info" or event.get("item") != item:
                continue
            actor = event.get("actor")
            if actor and actor != exclude:
                return _find_agent(model, actor)

    return None


def _pick_focus_partner(model, source_agent, item: Optional[str]):
    if source_agent is None:
        return None

    others = [a for a in getattr(model, "agents", []) if a.public_id != source_agent.public_id]
    if not others:
        return None

    if item:
        recent_requester = _recent_requester_for_item(model, item, exclude=source_agent.public_id)
        if recent_requester is not None:
            return recent_requester

        knowledge_map = getattr(getattr(model, "scenario", None), "knowledge_map", {}) or {}
        for other in others:
            if item in (knowledge_map.get(other.public_id, []) or []):
                return other

        bottleneck_holder = getattr(model, "bottleneck_holder", None)
        if bottleneck_holder and bottleneck_holder != source_agent.public_id:
            holder = _find_agent(model, bottleneck_holder)
            if holder is not None:
                return holder

        lacking = [a for a in others if item not in getattr(a, "known_items", set())]
        if lacking:
            lacking.sort(key=lambda ag: (ag.public_id != "A1", ag.public_id))
            return lacking[0]

    leaderish = [a for a in others if getattr(a, "personality_type", "") in {"Leader", "Decisive"} or a.public_id == "A1"]
    if leaderish:
        leaderish.sort(key=lambda ag: (ag.public_id != "A1", ag.public_id))
        return leaderish[0]

    return others[0]


def _actionable_intervention_item(model, item: Optional[str]) -> Optional[str]:
    if not item:
        return item

    scenario_type = getattr(getattr(model, "behaviour", None), "scenario_type", "office")
    if scenario_type == "escape" and item == "unlock":
        tasks = getattr(getattr(model, "scenario", None), "tasks", {}) or {}
        if not tasks.get("door", False):
            return "door"
        if not tasks.get("key", False):
            return "key"
        if not tasks.get("lock", False):
            return "lock"
        if not tasks.get("map", False):
            return "map"
        return "door"

    return item


def _item_ready_for_immediate_surface(model, item: str) -> bool:
    tasks = list((getattr(getattr(model, "scenario", None), "tasks", {}) or {}).keys())
    if not tasks or item not in tasks:
        return True

    if item == getattr(model, "bottleneck_item", None):
        return True

    if _recent_requester_for_item(model, item) is not None:
        return True

    completed = sum(1 for done in getattr(model.scenario, "tasks", {}).values() if done)
    idx = tasks.index(item)
    if idx <= completed + 1:
        return True

    if getattr(model, "progress_stall_ticks", 0) >= 4:
        return True

    return False


def _pick_blocked_item(model, prefer_agents=None):
    """Return the identifier of the most salient incomplete task, or None.

    Used to anchor intervention dialogue to the group's actual current
    blocker. Reads `scenario.tasks: Dict[str, bool]` where True means the
    task is already completed — those are skipped so we never anchor a
    forced meeting or opener on a topic that has already been resolved.

    If `prefer_agents` is a list of agent objects, items they own (via
    `scenario.knowledge_map`) are preferred so the forced exchange lands
    on something at least one of the participants is actually positioned
    to move forward.
    """
    scenario = getattr(model, "scenario", None)
    if scenario is None:
        return None

    tasks = getattr(scenario, "tasks", None) or {}
    if not tasks:
        return None

    unresolved = [item for item, done in tasks.items() if not done and item != "unlock"]
    if not unresolved:
        return None

    knowledge_map = getattr(scenario, "knowledge_map", {}) or {}
    bottleneck_item = getattr(model, "bottleneck_item", None)
    focus_item = getattr(model, "_intervention_focus_item", None)
    focus_until = getattr(model, "_intervention_focus_until", -1)

    if (
        focus_item
        and focus_item in unresolved
        and getattr(model, "tick", 0) <= focus_until
    ):
        return focus_item

    def _knowledge_count(item: str) -> int:
        return sum(
            1
            for ag in getattr(model, "agents", [])
            if item in getattr(ag, "known_items", set())
        )

    def _recent_share_count(item: str, within: int = 2) -> int:
        current_tick = getattr(model, "tick", 0)
        count = 0
        for snap in reversed(getattr(model, "history", [])[-(within + 2):]):
            snap_tick = snap.get("tick", current_tick)
            if current_tick - snap_tick > within:
                continue
            for event in snap.get("events", []) or []:
                if event.get("type") == "share_info" and event.get("item") == item:
                    count += 1
        return count

    scored = []
    for idx, item in enumerate(unresolved):
        pending_confirm = (
            item in getattr(model, "_escape_pending_confirm", {})
            or item in getattr(model, "_office_pending_confirm", {})
        )
        recent_share_count = _recent_share_count(item, within=2)
        if (
            pending_confirm
            and recent_share_count > 0
            and item != bottleneck_item
            and item != focus_item
        ):
            continue
        if (
            recent_share_count >= 2
            and _knowledge_count(item) >= 3
            and getattr(model, "progress_stall_ticks", 0) < 4
            and item != bottleneck_item
            and item != focus_item
            and not pending_confirm
        ):
            continue
        # Tighter dedup: a non-bottleneck item that has already been shared at
        # least once and is now known by two or more agents is "done circling".
        # Prevents the redundant map/key re-share the user flagged.
        if (
            item != bottleneck_item
            and item != focus_item
            and recent_share_count >= 1
            and _knowledge_count(item) >= 2
            and getattr(model, "progress_stall_ticks", 0) < 4
        ):
            continue

        score = 0.0
        if item == bottleneck_item:
            score += 7.0
        if prefer_agents:
            prefer_knowers = [
                ag for ag in prefer_agents
                if item in getattr(ag, "known_items", set())
            ]
            if 0 < len(prefer_knowers) < len(prefer_agents):
                score += 6.0

            if any(
                item in (knowledge_map.get(getattr(ag, "public_id", None), []) or [])
                for ag in prefer_agents
            ):
                score += 4.0

        if recent_share_count > 0 and item != bottleneck_item:
            score -= 3.0

        if _knowledge_count(item) >= 3 and item != bottleneck_item:
            score -= 2.0

        score -= idx * 0.05
        scored.append((score, item))

    if not scored:
        return None

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored[0][1]
