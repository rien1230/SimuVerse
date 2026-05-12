"""
agent_text.py — dialogue text generation extracted from SimAgent.

All _generate_* methods plus their phrase-cooldown helpers are moved here as
module-level functions that accept `agent` as their first argument.  This
mirrors the pattern established by agent_stress.py and keeps agent.py focused
on state management, decision logic, and event handling.

The agent.py methods that previously implemented these are now thin one-liner
wrappers that delegate here, so call-sites inside agent.py are unchanged.

This file keeps the phrasing / wording layer separate from the decision logic.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.sim.agent import SimAgent

from app.sim.scenario_data import ITEM_LABELS, ITEM_INFO_TEMPLATES
from app.sim.scenario_logic.base_logic import get_env_dialogue
from app.sim.dialogue_banks import pick_line


def _lbl(item: str) -> str:
    """Get a readable display label for an item key (e.g. 'tech_specs' → 'Tech Specs')."""
    return ITEM_LABELS.get(item, item.replace("_", " ").title())


# ── Phrase-cooldown helpers ──────────────────────────────────────────────────
# These reduce repetition so agents do not keep reusing the same line.

def recently_said(agent: "SimAgent", text: str) -> bool:
    """Check if this exact text is still in the agent's short-term utterance memory."""
    return text in agent.recent_utterances


def phrase_on_cooldown(agent: "SimAgent", phrase_key: str) -> bool:
    """Check whether a phrase key is still within its cooldown window (model-level tracking)."""
    cooldowns = getattr(agent.model, "phrase_cooldowns", {})
    tick_now = getattr(agent.model, "tick", 0)
    return cooldowns.get(phrase_key, 0) > tick_now


def register_phrase(agent: "SimAgent", phrase_key: str, cooldown_ticks: int = 4) -> None:
    """Mark a phrase key as used so it won't be picked again for cooldown_ticks ticks."""
    if not hasattr(agent.model, "phrase_cooldowns"):
        agent.model.phrase_cooldowns = {}
    tick_now = getattr(agent.model, "tick", 0)
    agent.model.phrase_cooldowns[phrase_key] = tick_now + cooldown_ticks


def unique_say(agent: "SimAgent", pool: list, phrase_key: str, cooldown: int = 4) -> str:
    """
    Pick a phrase from the pool that hasn't been said recently (model-wide).
    Registers it so the same phrase won't come up again for a while.
    Falls back to any phrase in the pool if all have been used recently.
    """
    if not hasattr(agent.model, "phrase_cooldowns"):
        agent.model.phrase_cooldowns = {}
    recent = list(getattr(agent.model, "_recent_phrases", []))
    fresh = [p for p in pool if p not in recent]
    chosen = random.choice(fresh) if fresh else random.choice(pool)  # fall back when all used
    recent.append(chosen)
    recent = recent[-8:]  # keep only the last 8 phrases in the rolling window
    agent.model._recent_phrases = recent
    register_phrase(agent, phrase_key, cooldown)
    return chosen


def phrase_used_recently(agent: "SimAgent", phrase_key: str, lookback: int = 3) -> bool:
    """Alias for phrase_on_cooldown — kept for call-site compatibility."""
    return phrase_on_cooldown(agent, phrase_key)


def pick_fresh(agent: "SimAgent", options: list) -> str:
    """
    Pick an option the agent hasn't said recently, then add it to their utterance memory.
    Prevents the same line from repeating back-to-back in conversation.
    """
    fresh = [o for o in options if o not in agent.recent_utterances]
    chosen = random.choice(fresh) if fresh else random.choice(options)
    agent.recent_utterances.append(chosen)
    return chosen


# ── Text generators ──────────────────────────────────────────────────────────
# Each generate_* function first tries to delegate to the scenario logic class
# (which has scenario-specific phrasing), then falls back to env-aware generic pools.
# All text passes through _polish_dialogue() in model.py before reaching the UI.

def generate_help_text(agent: "SimAgent", target_id: str, item: str) -> str:
    """Generate a line where the agent offers to help with a specific item."""
    logic = getattr(agent.model, "behaviour", None)
    if logic and hasattr(logic, "generate_help_text"):
        return logic.generate_help_text(agent, target_id, item)
    return f"I'll help with {_lbl(item)}."


def generate_compliment_text(agent: "SimAgent", target_id: str) -> str:
    """
    Generate a positive acknowledgement directed at another agent.
    Used after they've shared useful information or made progress.
    Rotates through phrases so the same compliment doesn't repeat immediately.
    """
    options = [
        f"That helped a lot, {agent._r(target_id)}.",
        f"Good — that makes things a lot clearer, {agent._r(target_id)}.",
        f"Nice one, {agent._r(target_id)}, that moves us forward.",
        f"{agent._r(target_id)}, that was exactly what we needed.",
        f"Well done, {agent._r(target_id)} — that unblocked us.",
        f"Appreciated, {agent._r(target_id)} — that's the piece we needed.",
        f"Good contribution, {agent._r(target_id)}.",
    ]
    return unique_say(agent, options, "compliment", cooldown=3)


def generate_ignore_text(agent: "SimAgent", target_id: str) -> str:
    """Generate a dismissive non-response — agent is busy or uninterested."""
    logic = getattr(agent.model, "behaviour", None)
    if logic and hasattr(logic, "generate_ignore_text"):
        return logic.generate_ignore_text(agent, target_id)
    return "..."


def generate_insult_text(agent: "SimAgent", target_id: str) -> str:
    """Generate a hostile or dismissive line — only used when tension is high."""
    logic = getattr(agent.model, "behaviour", None)
    if logic and hasattr(logic, "generate_insult_text"):
        return logic.generate_insult_text(agent, target_id)
    return f"{agent._r(target_id)}, that's not helping."


def generate_say_text(agent: "SimAgent", target_id: str) -> str:
    """
    Generate a generic 'say' line — used for coordination or filler when there's
    nothing specific to share. Tries the scenario logic first, then the structured
    dialogue bank, then the env-appropriate pool.
    """
    logic = getattr(agent.model, "behaviour", None)
    if logic and hasattr(logic, "generate_say_text"):
        return logic.generate_say_text(agent, target_id)
    # Structured bank (env + personality + tone)
    banked = pick_line(agent, "say", role=agent._r(target_id))
    if banked:
        return banked
    pool = get_env_dialogue(agent.model, "say")
    if pool:
        return random.choice(pool)
    return f"{agent._r(target_id)}, we need to keep moving."


def generate_ask_text(agent: "SimAgent", item: str, target_id: str) -> str:
    """
    Generate a question asking for a specific item from another agent.
    Uses the scenario logic if available, otherwise falls back to env-appropriate templates.
    """
    logic = getattr(agent.model, "behaviour", None)
    if logic and hasattr(logic, "generate_ask_text"):
        return logic.generate_ask_text(agent, item, target_id)

    # Env-aware fallback using {item} placeholder substitution
    pool = get_env_dialogue(agent.model, "ask")
    if pool:
        template = random.choice(pool)
        chosen = template.replace("{item}", _lbl(item))
    else:
        chosen = random.choice([
            f"{agent._r(target_id)}, do you have anything on {_lbl(item)}?",
            f"I need {_lbl(item)} — can you help, {agent._r(target_id)}?",
            f"Do you have {_lbl(item)}, {agent._r(target_id)}?",
        ])
    agent.recent_utterances.append(chosen)
    return chosen


def generate_info_text(agent: "SimAgent", item: str) -> str:
    """
    Get the actual factual content for an item the agent knows.
    First checks scenario-specific templates (e.g. specific clue text),
    then falls back to the behaviour logic, then a generic placeholder.
    """
    templates = ITEM_INFO_TEMPLATES.get(getattr(agent.model.scenario, "id", ""), {})
    options = templates.get(item)
    if options:
        return random.choice(options)

    behaviour = getattr(agent.model, "behaviour", None)
    if behaviour and hasattr(behaviour, "info_text"):
        btext = behaviour.info_text(item)
        if btext:
            return btext

    # Last resort — vague but better than nothing
    return "it's important context for the next step — worth knowing."


def generate_share_text(agent: "SimAgent", item: str, target_id: str) -> str:
    """
    Generate the full text for sharing an item's information with another agent.
    Combines the factual info text with scenario-appropriate phrasing.
    """
    logic = getattr(agent.model, "behaviour", None)
    if logic and hasattr(logic, "generate_share_text"):
        return logic.generate_share_text(agent, item, target_id)

    info = generate_info_text(agent, item)
    # Env-aware fallback — uses {info} placeholder substitution
    pool = get_env_dialogue(agent.model, "share")
    if pool and info:
        template = random.choice(pool)
        return template.replace("{info}", info)
    return random.choice([
        f"Here's what I know, {agent._r(target_id)}: {info}",
        f"Okay — {info}",
        f"I'll share this: {info}",
    ])


def generate_refuse_text(agent: "SimAgent", item: str, target_id: str) -> str:
    """
    Generate a refusal — the agent has the info but won't share it right now.
    Tone varies heavily by scenario: escape refusals are terse, cafe ones are gentle,
    office ones are professional. Personality also affects the wording.
    """
    # Try structured bank first (env + personality + tone aware)
    banked = pick_line(agent, "refuse", item=_lbl(item))
    if banked:
        return banked
    behaviour = getattr(agent.model, "behaviour", None)
    scenario_type = getattr(behaviour, "scenario_type", "office")

    if scenario_type == "escape":
        # Short, urgent — even refusals are terse in an escape room
        if agent.strategy == "confrontational":
            options = [
                "No. Not yet.",
                "I'm not sharing that.",
                "Not enough time to explain — trust me.",
                "Hold it.",
            ]
        else:
            options = [
                "Not yet — I'm still working it.",
                "Give me a second.",
                "I need to verify it first.",
                "Hold on.",
            ]
    elif scenario_type == "cafe":
        # Soft, light — refusals barely register
        if agent.strategy == "confrontational":
            options = [
                f"I'd rather not yet.",
                f"Not sure I want to go there yet.",
                "I'm going to hold off on that.",
            ]
        else:
            options = [
                f"I'd rather wait a bit on that, {agent._r(target_id)}.",
                "Not sure yet — give me a sec.",
                "I'm still figuring that out.",
                f"Maybe later — I'm just not ready on {_lbl(item)}.",
            ]
    else:
        # Office — professional and controlled
        if agent.strategy == "defensive":
            options = [
                f"I don't think it's the right time to share {_lbl(item)}, {agent._r(target_id)}.",
                f"I'd rather hold off on {_lbl(item)} a bit longer.",
                "I'm not comfortable sharing that yet.",
                f"Not right now — I need a bit more time before I share {_lbl(item)}.",
                f"{agent._r(target_id)}, I'd prefer to keep {_lbl(item)} to myself for the moment.",
            ]
        elif agent.strategy == "confrontational":
            options = [
                "No.",
                f"I'm not sharing {_lbl(item)}, {agent._r(target_id)}.",
                "Why should I hand that over right now?",
                "Not happening.",
                f"{agent._r(target_id)}, I'll keep {_lbl(item)} to myself.",
            ]
        elif agent.strategy == "avoidant":
            options = [
                f"Sorry, {agent._r(target_id)} — I'd rather not share {_lbl(item)} right now.",
                "I'm not quite ready to share that.",
                f"Maybe later — I just need more time with {_lbl(item)}.",
                "I'd prefer to hold off, if that's okay.",
            ]
        else:
            options = [
                f"I don't think I can share {_lbl(item)} right now, {agent._r(target_id)}.",
                f"Not yet — I want to wait a bit longer on {_lbl(item)}.",
                "I'd rather hold off on that a bit longer.",
                f"I'm going to keep {_lbl(item)} to myself for the moment.",
                "Not right now.",
            ]
    return random.choice(options)


def generate_agree_text(agent: "SimAgent", target_id: str, pref: str) -> str:
    """
    Generate an agreement line — agent is signing off on a preference or decision.
    Phrasing depends heavily on scenario and strategy: escape is short and decisive,
    cafe is casual, office is professional.
    """
    # Try structured bank first (env + personality + tone aware)
    banked = pick_line(agent, "agree", item=pref or "")
    if banked:
        return banked
    behaviour = getattr(agent.model, "behaviour", None)
    scenario_type = getattr(behaviour, "scenario_type", "office")
    p = pref or "it"

    if scenario_type == "escape":
        # Short, decisive, no fluff
        if agent.strategy == "confrontational":
            options = [f"Fine. {p}. Move.", f"Alright — {p}. Go."]
        else:
            options = [
                f"Yes. {p}. Let's go.",
                "Confirmed. Go.",
                f"Good. {p}. Do it.",
                "That's it. Move.",
            ]
    elif scenario_type == "cafe":
        # Casual, preference-based, warm
        if agent.strategy == "confrontational":
            options = [
                f"Alright, {p} — I can live with that.",
                f"Fine, {p}. I suppose.",
                f"Okay. {p}. If that's what we're going with.",
            ]
        elif agent.strategy == "cooperative":
            options = [
                f"Yeah, {p} sounds really good.",
                f"I'm happy with {p}.",
                f"{p} is a good call.",
                f"{p.capitalize()} sounds good to me. Let's do that.",
            ]
        else:
            options = [
                f"Yeah, {p} works for me.",
                f"I'm good with {p}.",
                f"Sounds fair enough — {p}.",
                f"Okay, {p} — I'm in.",
            ]
    else:
        # Office — professional, closing-oriented
        if agent.strategy == "cooperative":
            options = [
                f"Yes. Let's go with {p}.",
                f"I'm on board with {p}. That's settled.",
                f"Good call. Let's go with {p}.",
                f"Agreed. {p} is the right move.",
                "Alright, that is the call. Let's move forward.",
            ]
        elif agent.strategy == "confrontational":
            options = [
                f"Fine. {p} works.",
                f"Alright — {p} it is.",
                f"I'll go with {p} this time.",
                f"Okay, {p}. But I'm watching how this plays out.",
            ]
        else:
            if not pref or pref == "unknown":
                options = [
                    "Agreed — let's go with that.",
                    "I'm fine with that. Let's go.",
                    "I'm on board with that.",
                ]
            else:
                options = [
                    f"{p} makes sense to me. Let's go with that.",
                    f"Yeah, {p} is the way to go — that's decided.",
                    f"I'm with you on {p}, {agent._r(target_id)}. Let's move forward.",
                    f"Okay — {p}. We can close that out.",
                    f"I agree — {p}. That's settled.",
                ]
    return random.choice(options)


def generate_challenge_text(agent: "SimAgent", target_id: str, pref: str) -> str:
    """
    Generate a pushback or challenge — agent disagrees with someone's preference or claim.
    Confrontational agents are blunter; defensive agents are more cautious.
    Escape challenges are direct and urgent; cafe challenges are light; office is controlled.
    """
    # Try structured bank first (env + personality + tone aware)
    banked = pick_line(agent, "challenge", item=pref or "")
    if banked:
        return banked
    behaviour = getattr(agent.model, "behaviour", None)
    scenario_type = getattr(behaviour, "scenario_type", "office")
    p = pref or "that"

    if scenario_type == "escape":
        # Direct, urgent — challenges are sharp and fast
        if agent.strategy == "confrontational":
            options = [
                f"No. {p} is wrong.",
                f"That doesn't add up — check again.",
                f"{p}? No. We're wasting time.",
                "Are you sure? That could cost us.",
            ]
        else:
            options = [
                f"I don't think {p} is right.",
                f"That doesn't add up — I'd double-check.",
                f"Are you sure about {p}? We need to be certain.",
                "That could cost us time if it's wrong.",
            ]
    elif scenario_type == "cafe":
        # Light, preference-based — challenges are gentle opinions
        if agent.strategy == "confrontational":
            options = [
                f"I'm not convinced {p} is the right call.",
                f"Hmm, {p} doesn't feel right to me.",
                f"I'd push back on {p}.",
            ]
        else:
            options = [
                f"I'm not fully sold on {p}.",
                f"Hmm, not sure {p} quite works for me.",
                f"That doesn't quite work for me, {agent._r(target_id)}.",
                f"I'd push back on {p}.",
            ]
    else:
        # Office — controlled, professional pushback
        if agent.strategy == "confrontational":
            options = [
                f"{p}? No. We need something better.",
                f"I strongly disagree with {p}, {agent._r(target_id)}.",
                f"That's the wrong move. {p} won't work here.",
                f"{agent._r(target_id)}, {p} creates more problems than it solves.",
                f"No — {p} is not the answer.",
            ]
        elif agent.strategy == "defensive":
            options = [
                f"I have concerns about {p}, {agent._r(target_id)}.",
                f"I'm not sure {p} is safe here.",
                f"Something about {p} doesn't sit right with me.",
                f"I'd want to think more carefully before committing to {p}.",
            ]
        else:
            options = [
                f"I'm not convinced {p} is the right choice.",
                f"{p} feels risky to me, {agent._r(target_id)}.",
                f"I'd push back on {p} — there might be a better option.",
                f"I don't think {p} solves the real problem here.",
                f"I'm not sure about {p}.",
            ]
    return random.choice(options)
