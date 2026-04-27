"""Escape-room-specific task flow and guard rails for clue sharing."""

from __future__ import annotations

import random
from collections import deque
from typing import TYPE_CHECKING, Optional, List, Dict, Any, Set, Tuple

from app.sim.scenario_logic.base_logic import BaseLogic, get_env_modifiers

if TYPE_CHECKING:
    from app.sim.agent import SimAgent
    from app.sim.model import SimModel


# ──────────────────────────────────────────────────────────────────────────────
# labels
# ──────────────────────────────────────────────────────────────────────────────

def _lbl(item: str) -> str:
    """Formal display label — use for logging/UI only."""
    label_map = {
        "map": "Room Map",
        "lock": "Lock Pattern",
        "key": "Key Location",
        "door": "Door Code",
        "unlock": "Final Unlock",
        "digit_1": "Door Digit 1",
        "digit_2": "Door Digit 2",
        "digit_3": "Door Digit 3",
        "order": "Digit Order",
    }
    return label_map.get(item, item.replace("_", " ").title())


def _spoken(item: str) -> str:
    """Natural spoken alias — use in all dialogue generation."""
    spoken_map = {
        "map": "the map",
        "lock": "the pattern",
        "key": "the key",
        "door": "the code",
        "unlock": "the door",
        "digit_1": "the first digit",
        "digit_2": "the second digit",
        "digit_3": "the third digit",
        "order": "the order",
    }
    return spoken_map.get(item, item.replace("_", " "))


# ──────────────────────────────────────────────────────────────────────────────
# ownership + progress model
# ──────────────────────────────────────────────────────────────────────────────

ESCAPE_CLUE_OWNER = {
    "map": "A1",   # Team Leader
    "lock": "A3",  # Puzzle Solver
    "key": "A2",   # Code Breaker
    "door": "A4",  # Scout
}

ROLE_NAMES = {
    "A1": "Team Leader",
    "A2": "Code Breaker",
    "A3": "Puzzle Solver",
    "A4": "Scout",
}

ESCAPE_PROGRESS_TASKS = {
    "map": False,
    "lock": False,
    "key": False,
    "door": False,
    "unlock": False,  # final two-tick door-open sequence
}

ESCAPE_PRIORITY = ["map", "lock", "key", "door"]


# ──────────────────────────────────────────────────────────────────────────────
# traits
# ──────────────────────────────────────────────────────────────────────────────

def _logic(agent) -> float:
    return agent.traits.get("C", 0.5)


def _creativity(agent) -> float:
    return agent.traits.get("O", 0.5)


def _patience(agent) -> float:
    return 1.0 - agent.traits.get("N", 0.5)


def _confidence(agent) -> float:
    return agent.traits.get("E", 0.5)


def _trust_trait(agent) -> float:
    return agent.traits.get("A", 0.5)


# ──────────────────────────────────────────────────────────────────────────────
# dialogue pools
# ──────────────────────────────────────────────────────────────────────────────

SHARE_TEXTS = {
    "Leader": [
        "Here: {info}",
        "Going with this: {info}",
        "Call it: {info}",
        "This is what we have: {info}",
    ],
    "Skeptical": [
        "I'll say it, but I'm not fully sold: {info}",
        "Here's my read — check it: {info}",
        "Tentative, but: {info}",
        "This is what I've got. Check it: {info}",
    ],
    "Overthinker": [
        "Could be wrong, but {info}",
        "It keeps fitting when I check: {info}",
        "Saying it before I lose my nerve: {info}",
        "Okay, {info}",
    ],
    "Creative": [
        "Try this angle: {info}",
        "This might be it: {info}",
        "What if it's this: {info}",
        "I'm seeing this: {info}",
    ],
    "Decisive": [
        "Got it. {info}",
        "That's it. {info}",
        "Here: {info}",
        "Done. {info}",
    ],
    "Easygoing": [
        "Okay, {info}",
        "Right, got one: {info}",
        "Here's mine: {info}",
        "Think I've got it — {info}",
    ],
}

CONFIRM_TEXTS = {
    "Leader": [
        "That lines up. Keep going.",
        "Good. Move on it.",
        "That checks out. Keep the chain moving.",
        "Alright, we've got that. What are we missing?",
        "Good. Push the next clue.",
        "That's solid. Keep going.",
        "Locked in. Go.",
        "Good. Don't slow down.",
    ],
    "Skeptical": [
        "Alright. I can buy that.",
        "I'll take it. That holds up.",
        "Fine. Use it.",
        "Okay. Bring it in.",
    ],
    "Overthinker": [
        "Okay... I think that's right.",
        "Alright... I think we're okay.",
        "That looks right. Go with it.",
        "Yeah... okay. Hold onto that.",
    ],
    "Creative": [
        "Yeah, there it is.",
        "Nice, that's the missing piece.",
        "There — that's what was missing.",
        "Oh, that fits better than I expected.",
    ],
    "Decisive": [
        "Good. Move to the next one.",
        "Confirmed. Move.",
        "Confirmed. Go.",
        "That's it — don't stall here.",
    ],
    "Easygoing": [
        "Yeah, that actually makes sense now.",
        "Nice one — that helps a lot.",
        "Cool, that slots in.",
        "Alright, good — I can work with that.",
    ],
}

DOUBT_TEXTS = {
    "Leader": [
        "{role}, lock {item} down — no ambiguity.",
        "{item} is the blocker. Clean answer.",
        "{role}, confirm {item} before we move.",
        "No drift on {item}, {role}.",
    ],
    "Skeptical": [
        "{role}, run {item} past me one more time.",
        "Are we actually sure on {item}, or guessing?",
        "I don't trust {item} yet.",
        "Convince me on {item}, {role}.",
    ],
    "Overthinker": [
        "What if {item} is a red herring?",
        "It fits, but — one more pass on {item}?",
        "I'm not fully settled on {item}.",
        "Could we be misreading {item}?",
    ],
    "Creative": [
        "What if we've been reading {item} backwards?",
        "What if we're reading {item} wrong?",
        "{item} might mean something else entirely.",
        "I think {item} might mean something else.",
    ],
    "Decisive": [
        "{role}, {item}. Now.",
        "Stop stalling — give me {item}.",
        "{item} — direct answer.",
        "We're blocked on {item}, {role}. Move.",
    ],
    "Easygoing": [
        "Hmm — you sure on {item}?",
        "Quick sanity check on {item}?",
        "{item} — right, yeah?",
        "One more look at {item}?",
    ],
}

RUSH_TEXTS = {
    "Leader": [
        "We do not have time to stall here.",
        "Enough delay — move.",
        "{role}, whatever you've got, use it now.",
        "We need action, not more waiting.",
    ],
    "Skeptical": [
        "At this point, we need action.",
        "Enough thinking. Act.",
        "{role}, stop holding back and move.",
        "We're losing time here.",
    ],
    "Overthinker": [
        "I know we need to be careful, but we have to move.",
        "We're running out of time — we need something now.",
        "I hate rushing this, but we need action.",
        "At this point, movement is better than silence.",
    ],
    "Creative": [
        "Stop circling it. Pick a direction.",
        "We need movement more than theories right now.",
        "Enough circling. Try something.",
        "We can't keep talking about it. Try something.",
    ],
    "Decisive": [
        "We're overthinking this. Just move.",
        "Do it now.",
        "Enough thinking. Act.",
        "{role}, move.",
    ],
    "Easygoing": [
        "Come on, let's move this forward.",
        "We need to keep going now.",
        "Alright, no more waiting — try it.",
        "Let's not stall here.",
    ],
}

REFUSAL_TEXTS = {
    "Easygoing": [
        "Hang on — I want to verify {item} one more time before I say it.",
        "Give me a second. I don't want to share {item} until I'm sure.",
        "Not quite yet — I want to be certain about {item} first.",
    ],
    "Decisive": [
        "Not yet — I want {item} locked in properly.",
        "Give me one second. I need to be certain on {item}.",
        "I'll share it, but I want to check {item} once more first.",
    ],
    "Leader": [
        "Hold on. I want to verify {item} before we commit to it.",
        "Not yet — I need confidence on {item} before I put it out there.",
        "I'm nearly there on {item}. Give me a moment.",
    ],
    "Creative": [
        "Wait — I think there's one more angle on {item} I want to check.",
        "Give me a moment. {item} doesn't feel complete to me yet.",
        "I want to look at {item} from another direction before I commit.",
    ],
    "Skeptical": [
        "Not yet — I still have doubts about {item}.",
        "I want {item} properly verified before I put it forward.",
        "I'm not satisfied with {item} yet. Give me a tick.",
    ],
    "Overthinker": [
        "Wait — I'm not ready to call {item} yet.",
        "I need one more pass on {item} before I share it.",
        "Something about {item} still doesn't sit right. Just a moment.",
    ],
}

REFUSAL_REASONS = {
    "map": [
        ("I want to verify the route first", 1),
        ("I need to check the room layout one more time", 1),
    ],
    "lock": [
        ("I want to verify the lock pattern first", 1),
        ("I need to confirm the symbol order", 1),
    ],
    "key": [
        ("I want to be sure on the key clue first", 1),
        ("I need to verify where the key actually points", 1),
    ],
    "door": [
        ("I want to verify the door code first", 1),
        ("I need to confirm the door digits properly", 1),
    ],
}

PROGRESS_TEXTS = [
    "Nice — that clears one blocker.",
    "Good. One piece down.",
    "Alright, that gives us momentum.",
    "Good — we're getting somewhere now.",
    "Nice. That narrows the room down.",
]

URGENCY_PULSES = {
    "Leader": [
        "Clock's against us — we need to keep the pressure on.",
        "Time's bleeding — if we stall here we're stuck.",
        "We've burned through too much time already — focus.",
        "This room isn't going to give us a second chance. Move.",
    ],
    "Decisive": [
        "Enough. Clock's running — every second matters now.",
        "We're losing time. Decide and go.",
        "Less thinking, more doing — now.",
        "We don't have time to hesitate.",
    ],
    "Skeptical": [
        "We're dragging — I don't love it, but we have to push.",
        "Time's not on our side. I'm uneasy but we can't wait.",
        "Every minute we hesitate we're worse off.",
    ],
    "Overthinker": [
        "I know I'm slowing us down, but... we really have to move.",
        "I keep second-guessing — we don't have time for that.",
        "Okay, okay — I know. We need to act. The clock.",
    ],
    "Creative": [
        "Feels like the walls are closing in. Pick a direction.",
        "We can't keep guessing. The room's counting us out.",
        "Let's stop spiralling — we're on the clock.",
    ],
    "Easygoing": [
        "Right, okay — this is actually getting tight. Let's push.",
        "We're running thin on time now, genuinely.",
        "Alright, no more stalling — time's actually against us.",
    ],
}

RECHECK_TEXTS = {
    "Skeptical": [
        "Wait — {item}. Did we actually read that right?",
        "Back to {item} for a second. Something's off.",
        "Not convinced on {item}. Sanity-check?",
        "Before we push on — {item}, anyone else want to look again?",
    ],
    "Overthinker": [
        "I keep snagging on {item} — did we confirm it properly?",
        "Something about {item} is off. Moved on too fast?",
        "{item} — I think we jumped on that one.",
    ],
    "Creative": [
        "What if {item} isn't what we thought? Worth a second look.",
        "Reading {item} again — there might be more to it.",
    ],
}

INTERRUPT_TEXTS = {
    "Leader": [
        "— just get to the answer. We don't have time.",
        "— skip the caveats. What's the read?",
        "— shorter. What do you have?",
    ],
    "Decisive": [
        "— cut to it.",
        "— the answer. Now.",
        "— skip the preamble.",
    ],
}

WRONG_ASSUMPTION_TEXTS = [
    "Wait — that doesn't actually fit. We need to look at {item} again.",
    "Hold on, that doesn't add up. Back to {item}.",
    "No, that's off — the {item} read has to be wrong.",
    "That can't be right — we're misreading {item}.",
]

WRAPUP_FAST = [
    "Door's open. Clean run — nobody panicked, nobody froze. Textbook.",
    "That was sharp. Out before the clock even threatened us.",
    "Beautiful. Straight through, no wasted moves. Let's go.",
]

WRAPUP_MESSY = [
    "Door's open. That took longer than it should have — but we're out.",
    "We got there. Messy, loud, and I don't want to talk about the middle ten minutes.",
    "Out. Barely held it together, but out.",
]

WRAPUP_INTENSE = [
    "Door's open. That was the wire — any longer and we were cooked.",
    "We got out. I could feel the seconds burning. Don't want to do that again.",
    "Out — breathe. That one nearly had us.",
]

WRAPUP_NEUTRAL = [
    "That's the last piece. Door's open — we're out.",
    "Got there. Not pretty, not slow — just done.",
    "Right — we cracked it. Let's move.",
    "Door's open. Good work, everyone.",
    "That's it. We're clear.",
]

# Two-tick final unlock sequence
UNLOCK_ATTEMPT_TEXTS = {
    "Leader": [
        "Entering {code}. Hold.",
        "Code's {code} — I'm putting it in. Stand by.",
        "Alright — {code}. Everyone hold.",
        "{code}. Entering now. Don't move.",
    ],
    "Decisive": [
        "{code}. Going in now.",
        "Entering {code}. Stand clear.",
        "{code} — doing it.",
    ],
    "Easygoing": [
        "Right, trying {code}. Everyone hold tight.",
        "Okay — entering {code} now. Fingers crossed.",
        "{code}. Here goes.",
    ],
    "Skeptical": [
        "Entering {code}. If this is wrong, we're back to square one.",
        "Trying {code}. I hope we read it right.",
        "{code} — going in. We'd better have this right.",
    ],
    "Overthinker": [
        "Okay, {code} — I think that's it. Entering now. Everyone just… hold.",
        "It's {code}. I keep second-guessing it, but — entering.",
        "Right. {code}. Here goes. Please be right.",
    ],
    "Creative": [
        "Alright, {code}. Let's try it.",
        "{code}. Moment of truth.",
        "Entering {code}. This should be the last piece.",
    ],
}

DOOR_OPEN_TEXTS = {
    "Leader": [
        "Door's open. Out.",
        "We're through. Good work.",
        "That's it — door's open. Let's go.",
    ],
    "Decisive": [
        "Door's open. Go.",
        "Through. Move now.",
        "That's it. Out.",
    ],
    "Easygoing": [
        "It worked — door's open! Let's go!",
        "We're out! Nice one.",
        "Door clicked — we're through!",
    ],
    "Skeptical": [
        "It worked. Door's open.",
        "Right, we're out. Door's open.",
        "Okay, we did it. Door's open.",
    ],
    "Overthinker": [
        "Oh — it worked! Door's open! I can't believe it.",
        "Door's open — we actually did it!",
        "We got it — door clicked! Out, everyone, out!",
    ],
    "Creative": [
        "Door's open — brilliant. Let's move.",
        "It clicked! Door's open — we did it.",
        "Yes — door's open. That was the last piece.",
    ],
}


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────

def _pick(pool_map: Dict[str, List[str]], personality: str, fallback: List[str], **fmt) -> str:
    pool = pool_map.get(personality) or fallback
    text = random.choice(pool)
    return text.format(**fmt)


_ESCAPE_CLUE_ORDER = ["map", "lock", "key", "door"]

_CONTEXT_BRIDGES: dict = {
    ("map",  "lock"): [
        "Map's cleared. Pattern's what we need now — {info}",
        "East wall's done. Lock pattern next: {info}",
        "Map's sorted. Here's what I have on the pattern: {info}",
        "Room map done. Pattern: {info}",
    ],
    ("lock", "key"):  [
        "Pattern's confirmed. Key location: {info}",
        "Lock's down. Key clue: {info}",
        "Pattern cleared. Key location: {info}",
        "Lock done. Here's the key clue: {info}",
    ],
    ("key",  "door"): [
        "Key's in. Code should be {info}",
        "Got the key. Door code: {info}",
        "Key confirmed. Code is {info}",
        "Last bit — the code is {info}",
    ],
}


def _context_bridge_prefix(agent: "SimAgent", item: str, info: str) -> str:
    """Return a contextual share line that references the prior solved clue, or empty string."""
    model = agent.model
    idx = _ESCAPE_CLUE_ORDER.index(item) if item in _ESCAPE_CLUE_ORDER else -1
    if idx <= 0:
        return ""
    prev_item = _ESCAPE_CLUE_ORDER[idx - 1]
    if not model.scenario.tasks.get(prev_item, False):
        return ""
    import random as _r
    if _r.random() > 0.45:
        return ""
    options = _CONTEXT_BRIDGES.get((prev_item, item), [])
    if not options:
        return ""
    template = _r.choice(options)
    return template.format(info=info)


def _voice(text: str, personality: str) -> str:
    """Light personality tone filter — makes each personality sound distinct."""
    if not text:
        return text
    if personality == "Decisive":
        # Short, sharp — strip trailing softeners
        text = text.replace(", if that makes sense", "").replace(", I think", "").strip()
    elif personality == "Overthinker":
        # Add hedging prefix occasionally
        hedges = ["I think ", "Maybe — ", "I could be wrong, but "]
        # Skip hedging if text starts with a direct address (role name, comma) — lowercasing breaks it
        _is_direct_address = len(text) > 2 and text[0].isupper() and ", " in text[:25]
        if random.random() < 0.28 and not text.startswith(("I think", "Maybe", "I could", "Back", "That seems", "Okay", "Could be")) and not _is_direct_address:
            text = random.choice(hedges) + text[0].lower() + text[1:]
    elif personality == "Easygoing":
        # Slightly warmer — soften imperatives
        text = text.replace("We need ", "We probably need ").replace("Give me ", "Just give me ")
    elif personality == "Skeptical":
        # Add verification tag only to neutral statements — never to acceptances or confirmations
        _is_acceptance = any(w in text for w in ("I'll take", "I'll go", "I'll accept", "that holds", "Moving on", "enough.", "keep going"))
        if random.random() < 0.14 and not _is_acceptance and not text.endswith(("?", "yet.", "now.")) and len(text) < 40:
            suffix = random.choice(["Check it once.", "I want to confirm that.", "Let's be sure."])
            text = text.rstrip(".") + ". " + suffix
    elif personality == "Creative":
        # Creative should stay natural, not sound like a narrator.
        _is_direct_address = len(text) > 2 and text[0].isupper() and ", " in text[:25]
        if random.random() < 0.08 and not text.startswith(("What if", "Maybe", "Try this", "Or maybe")) and not _is_direct_address:
            creative_preamble = random.choice([
                "Try this: ",
                "What if ",
                "Or maybe ",
            ])
            if creative_preamble.endswith(" "):
                text = creative_preamble + text[0].lower() + text[1:]
            else:
                text = creative_preamble + text[0].lower() + text[1:]
    return text


def _pressure_personality_ids(model) -> Set[str]:
    ids: Set[str] = set()
    for agent in getattr(model, "agents", []):
        if getattr(agent, "personality_type", "") in {"Decisive", "Leader"}:
            ids.add(agent.public_id)
    return ids


def _stress_profile(model) -> str:
    """
    Leader + Decisive alone should not auto-create a pressure team.
    Pressure needs at least one tense ingredient too.
    """
    personalities = [getattr(a, "personality_type", "") for a in getattr(model, "agents", [])]
    counts = {p: personalities.count(p) for p in set(personalities)}

    if counts.get("Skeptical", 0) >= 2 and counts.get("Overthinker", 0) >= 1:
        return "tension"

    if (
        counts.get("Leader", 0) >= 1
        and counts.get("Decisive", 0) >= 1
        and (counts.get("Skeptical", 0) >= 1 or counts.get("Overthinker", 0) >= 1)
    ):
        return "pressure"

    if counts.get("Creative", 0) >= 2 or (
        counts.get("Creative", 0) >= 1 and counts.get("Overthinker", 0) >= 1
    ):
        return "creative"

    return "smooth"


def _apply_escape_tick_stress(agent: "SimAgent") -> None:
    from app.sim.agent import clamp
    from app.sim.scenario_logic.base_logic import get_env_rules

    model = agent.model
    tick = getattr(model, "tick", 0)
    max_ticks = max(1, getattr(model, "episode_max_ticks", 20))
    tick_pct = tick / max_ticks

    logic = agent.traits.get("C", 0.5)
    neuroticism = agent.traits.get("N", 0.5)
    profile = _stress_profile(model)

    # Base tick stress: time pressure escalates as tick_pct rises
    base_tick_stress = (0.010 + 0.014 * tick_pct) * (0.65 + neuroticism) - (logic * 0.040)

    if profile == "pressure":
        base_tick_stress += 0.018
    elif profile == "tension":
        base_tick_stress += 0.010
    elif profile == "creative":
        base_tick_stress += 0.004
    elif profile == "smooth":
        # Smooth teams are calmer — but escape is still an escape room.
        # A small floor ensures some baseline urgency regardless of team fit.
        base_tick_stress -= 0.008  # was -0.048; reduced so smooth doesn't become a spa

    # Ensure escape always has at least a tiny positive tick stress floor
    # (the room's time pressure exists regardless of team personality)
    base_tick_stress = max(base_tick_stress, 0.004)

    # Scale by environment stress multiplier so physics are consistent with apply_events
    env_stress_mult = get_env_rules(model).get("stress_multiplier", 1.0)
    base_tick_stress *= env_stress_mult

    agent.stress = clamp(agent.stress + base_tick_stress, 0.0, 1.0)

    blocker_age = getattr(model, "_escape_bottleneck_age", 0)
    bottleneck_mult = {
        "smooth": 0.30,
        "creative": 0.70,
        "tension": 0.65,
        "pressure": 1.25,
    }[profile]

    if blocker_age >= 2:
        agent.stress = clamp(agent.stress + 0.012 * bottleneck_mult * (0.7 + neuroticism), 0.0, 1.0)
    if blocker_age >= 4:
        agent.stress = clamp(agent.stress + 0.020 * bottleneck_mult * (0.7 + neuroticism), 0.0, 1.0)
    if blocker_age >= 6:
        agent.stress = clamp(agent.stress + 0.028 * bottleneck_mult * (0.7 + neuroticism), 0.0, 1.0)

    # ── No-progress stall penalty ────────────────────────────────────────────
    # If no task has been completed in a while, every agent feels the freeze.
    items_done = sum(1 for v in model.scenario.tasks.values() if v)
    last_done = getattr(model, "_escape_last_items_done", 0)
    if items_done > last_done:
        model._escape_last_items_done = items_done
        model._escape_last_progress_tick = tick
    stall_ticks = tick - getattr(model, "_escape_last_progress_tick", 0)
    if stall_ticks >= 4:
        stall_mult = {"smooth": 0.30, "creative": 0.60, "tension": 0.70, "pressure": 1.40}[profile]
        stall_penalty = 0.022 * stall_mult * (0.6 + neuroticism)
        agent.stress = clamp(agent.stress + stall_penalty, 0.0, 1.0)

    prev = getattr(model, "prev_events", [])
    pressure_ids = _pressure_personality_ids(model)

    recent_share = any(
        e.get("type") == "share_info" and e.get("target") == agent.public_id
        for e in prev[-8:]
    )
    if recent_share:
        relief = {
            "smooth": 0.055,
            "creative": 0.028,
            "tension": 0.018,
            "pressure": 0.010,
        }[profile]
        agent.stress = clamp(agent.stress - relief, 0.0, 1.0)

    for e in prev[-6:]:
        if e.get("target") != agent.public_id:
            continue

        etype = e.get("type", "")
        reason = e.get("reason", "")
        actor_id = e.get("actor", "")

        if etype == "refuse":
            hit = {"smooth": 0.020, "creative": 0.035, "tension": 0.050, "pressure": 0.060}[profile]
            agent.stress = clamp(agent.stress + hit, 0.0, 1.0)

        elif reason == "escape_rush":
            hit = 0.050 if actor_id in pressure_ids else 0.038
            if profile == "pressure":
                hit *= 1.25
            elif profile == "tension":
                hit *= 1.05
            elif profile == "smooth":
                hit *= 0.45
            agent.stress = clamp(agent.stress + hit, 0.0, 1.0)

        elif etype == "challenge" and reason == "escape_doubt":
            hit = 0.020
            if profile == "pressure":
                hit *= 1.20
            elif profile == "tension":
                hit *= 1.05
            elif profile == "creative":
                hit *= 0.85
            elif profile == "smooth":
                hit *= 0.30
            agent.stress = clamp(agent.stress + hit, 0.0, 1.0)

        elif etype == "ask_info" and reason == "escape_ask_owner":
            hit = 0.010
            if actor_id in pressure_ids:
                hit += 0.012
            if profile == "pressure":
                hit *= 1.15
            elif profile == "tension":
                hit *= 1.05
            elif profile == "creative":
                hit *= 0.85
            elif profile == "smooth":
                hit *= 0.30
            agent.stress = clamp(agent.stress + hit, 0.0, 1.0)

    rush_count = sum(
        1
        for e in prev[-10:]
        if e.get("target") == agent.public_id and e.get("reason") == "escape_rush"
    )
    if rush_count >= 2:
        stack = {
            "smooth": 0.012,
            "creative": 0.026,
            "tension": 0.032,
            "pressure": 0.075,
        }[profile]
        agent.stress = clamp(agent.stress + stack, 0.0, 1.0)

    ask_count = sum(
        1
        for e in prev[-8:]
        if e.get("target") == agent.public_id
        and e.get("type") == "ask_info"
        and e.get("reason") == "escape_ask_owner"
    )
    if ask_count >= 2:
        extra = {
            "smooth": 0.001,
            "creative": 0.006,
            "tension": 0.012,
            "pressure": 0.026,
        }[profile] * (ask_count - 1)
        agent.stress = clamp(agent.stress + extra, 0.0, 1.0)

    # Slow trust decay — relationships drift without positive interaction
    if hasattr(agent, "trust") and agent.trust:
        for other_id in agent.trust:
            agent.trust[other_id] = clamp(agent.trust[other_id] * 0.995, 0.0, 1.0)


# ──────────────────────────────────────────────────────────────────────────────
# logic
# ──────────────────────────────────────────────────────────────────────────────

class EscapeLogic(BaseLogic):
    scenario_type = "escape"
    ROLES = ROLE_NAMES

    # Phrases/reasons that indicate active coordination under pressure.
    # The base metric counts only the explicit [COORD] tag, which was
    # under-reporting how much directing/chivvying happens in Escape runs.
    _COORD_REASONS = (
        "escape_coordination",
        "escape_rush",
        "escape_unlock_attempt",
        "escape_door_open",
        "escape_forced_release",
        "escape_confirm_fallback",
    )
    _COORD_PHRASES = (
        "keep moving",
        "keep the pace",
        "keep the pressure",
        "move on",
        "move now",
        "next piece",
        "next step",
        "next clue",
        "on it",
        "hold ",
        "hold on",
        "stand by",
        "on my go",
        "stay with me",
        "stay with it",
        "push on",
        "push onto",
        "focus",
        "everyone ",
        "let's go",
        "lets go",
        "watch the clock",
        "running out",
        "we're out of",
        "we are out of",
        "no time",
        "give me a ",
        "don't move",
        "what are we missing",
        "what's missing",
        "can you confirm",
        "please confirm",
        "we still need",
        "we need the",
        "share what you know",
        "what do you have",
        "what have you got",
        "what's your status",
        "status?",
        "direct answer",
        "straight answer",
        "less thinking",
        "don't stall",
        "clock's running",
        "clock is running",
        "every second",
        "time's tight",
        "no more delays",
    )

    def role(self, agent_id: str) -> str:
        return self.ROLES.get(agent_id, agent_id)

    def scenario_modifiers(self, model: "SimModel") -> Dict[str, float]:
        # Escape: high-pressure, time-limited — stressed agents distrust fast
        return {
            "base_trust_delta": -0.08,
            "arousal_rate": 1.3,
            "refusal_weight": 1.1,
            "cooperation_weight": 1.1,
            "initial_tension_delta": 0.12,
            "initial_cohesion_delta": -0.10,
            "initial_stress_delta": 0.14,
        }

    def accumulate_run_metrics(
        self,
        model: "SimModel",
        events: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        """Escape-specific metric accumulation.

        Counts coordination *phrases* as well as the explicit [COORD] tag so
        that CoordPres reflects the actual directing-under-pressure feel of
        the scene, not just one narrow event reason.
        """
        emotional = 0.0
        coord_pressure = 0.0
        conflict = 0.0

        for event in events:
            etype = event.get("type", "")
            reason = event.get("reason", "")
            text = str(event.get("text", "")).lower()

            if reason in self._COORD_REASONS:
                coord_pressure += 0.035

            # Check coordination phrases across all event types with text
            if text and any(p in text for p in self._COORD_PHRASES):
                coord_pressure += 0.025

            if etype == "ask_info":
                # Asking at all under time pressure is coordination pressure
                coord_pressure += 0.020

            if etype == "agree" and reason in ("escape_confirm", "escape_confirm_fallback"):
                # Confirms under time pressure count as coordination
                coord_pressure += 0.015

            if etype == "challenge":
                conflict += 0.05
                emotional += 0.03

            if etype == "refuse":
                conflict += 0.04
                emotional += 0.04

            if reason == "escape_recheck":
                emotional += 0.03

        # Roll in any coord_pressure_bonus that escape collected directly
        bonus = getattr(model, "coord_pressure_bonus", 0.0)
        if bonus:
            coord_pressure += bonus
            model.coord_pressure_bonus = 0.0

        return {
            "emotional": emotional,
            "coord_pressure": coord_pressure,
            "conflict": conflict,
        }

    # ──────────────────────────────────────────────────────────────────
    # state init
    # ──────────────────────────────────────────────────────────────────

    def _init_state(self, model: "SimModel") -> None:
        if set(getattr(model.scenario, "tasks", {}).keys()) != set(ESCAPE_PROGRESS_TASKS.keys()):
            model.scenario.tasks = ESCAPE_PROGRESS_TASKS.copy()
        else:
            for key in ESCAPE_PROGRESS_TASKS:
                model.scenario.tasks.setdefault(key, False)

        if not hasattr(model, "_escape_revealed"):
            model._escape_revealed = {key: False for key in ESCAPE_PROGRESS_TASKS}

        if not hasattr(model, "_escape_confirmed"):
            model._escape_confirmed = {key: False for key in ESCAPE_PROGRESS_TASKS}

        if not hasattr(model, "_escape_last_share_tick"):
            model._escape_last_share_tick = {}

        if not hasattr(model, "_escape_last_ask_tick"):
            model._escape_last_ask_tick = {}

        if not hasattr(model, "_escape_ask_count"):
            model._escape_ask_count = {}

        if not hasattr(model, "_escape_refusal_until"):
            model._escape_refusal_until = {}

        if not hasattr(model, "_escape_metrics"):
            model._escape_metrics = {}

        for key in ("conflicts", "agreements", "compromises", "probes", "pressure", "refusals"):
            model._escape_metrics.setdefault(key, 0)

        if not hasattr(model, "_escape_progress_text_last_tick"):
            model._escape_progress_text_last_tick = -99

        if not hasattr(model, "_escape_bottleneck_age"):
            model._escape_bottleneck_age = 0

        if not hasattr(model, "_escape_bottleneck_item"):
            model._escape_bottleneck_item = None

        if not hasattr(model, "_escape_phrase_history"):
            model._escape_phrase_history = {}

        if not hasattr(model, "_escape_last_rush_tick"):
            model._escape_last_rush_tick = {}

        if not hasattr(model, "_escape_last_doubt_tick"):
            model._escape_last_doubt_tick = {}

        if not hasattr(model, "_escape_intent_history"):
            model._escape_intent_history = {}

        if not hasattr(model, "_escape_last_progress_item"):
            model._escape_last_progress_item = None

        if not hasattr(model, "_escape_impression_tick"):
            model._escape_impression_tick = -99

        if not hasattr(model, "_escape_pending_confirm"):
            model._escape_pending_confirm = {}

        if not hasattr(model, "_escape_last_urgency_tick"):
            model._escape_last_urgency_tick = -99

        if not hasattr(model, "_escape_recheck_count"):
            model._escape_recheck_count = 0

        if not hasattr(model, "_escape_last_recheck_tick"):
            model._escape_last_recheck_tick = -99

        # Fix facts once at model init so all presets share the same clue truths
        if not hasattr(model, "_escape_facts"):
            model._escape_facts = {
                "map":  random.choice([
                    "the panel's behind the bookshelf on the east wall.",
                    "the room splits into three sections, hidden panel east side.",
                    "east wall — there's a panel behind the bookshelf.",
                ]),
                "lock": random.choice([
                    "triangle, circle, square.",
                    "the ceiling symbols — triangle, then circle, then square.",
                    "it's triangle → circle → square, in that order.",
                ]),
                "key":  random.choice([
                    "magnetic, stuck to the metal panel.",
                    "under the loose tile by the door.",
                    "magnetic key, attached to the metal panel.",
                ]),
                "door": random.choice([
                    "4-2-7-1.",
                    "four, two, seven, one.",
                ]),
                # Short numeric form always used in the ENTER event text
                "_door_code_short": "4-2-7-1",
            }

    def _priority_missing(self, model: "SimModel") -> List[str]:
        self._init_state(model)
        missing = [key for key in ESCAPE_PRIORITY if not model.scenario.tasks.get(key, False)]
        focus_item = self._active_intervention_focus_item(model)
        if focus_item and focus_item in missing:
            return [focus_item] + [key for key in missing if key != focus_item]
        return missing

    def _active_intervention_focus_item(self, model: "SimModel") -> Optional[str]:
        item = getattr(model, "_intervention_focus_item", None)
        if not item:
            return None
        if getattr(model, "tick", 0) > getattr(model, "_intervention_focus_until", -1):
            model._intervention_focus_item = None
            model._intervention_focus_until = -1
            return None
        if model.scenario.tasks.get(item, False):
            return None
        return item

    def _intervention_quiet_active(self, model: "SimModel") -> bool:
        item = getattr(model, "_intervention_quiet_item", None)
        until = getattr(model, "_intervention_quiet_until", -1)
        if not item or getattr(model, "tick", 0) > until:
            return False
        tension = float(getattr(model, "group_tension", 0.0) or 0.0)
        stall = int(getattr(model, "progress_stall_ticks", 0) or 0)
        return tension < 0.85 and stall < 6

    def _update_bottleneck(self, model: "SimModel") -> None:
        missing = self._priority_missing(model)
        current = missing[0] if missing else None
        if current == getattr(model, "_escape_bottleneck_item", None):
            model._escape_bottleneck_age += 1
        else:
            model._escape_bottleneck_item = current
            model._escape_bottleneck_age = 0

    def _ask_key(self, asker: str, target: str, item: str) -> Tuple[str, str, str]:
        return (asker, target, item)

    def _note_ask(self, model: "SimModel", asker: str, target: str, item: str) -> None:
        key = self._ask_key(asker, target, item)
        model._escape_last_ask_tick[key] = getattr(model, "tick", 0)
        model._escape_ask_count[key] = model._escape_ask_count.get(key, 0) + 1

    def _ask_count(self, model: "SimModel", asker: str, target: str, item: str) -> int:
        return model._escape_ask_count.get(self._ask_key(asker, target, item), 0)

    def _all_asks_to_target(self, model: "SimModel", target: str, item: str) -> int:
        total = 0
        for (_, target_id, asked_item), count in model._escape_ask_count.items():
            if target_id == target and asked_item == item:
                total += count
        return total

    def _can_ask_again(self, model: "SimModel", asker: str, target: str, item: str) -> bool:
        last_tick = model._escape_last_ask_tick.get(self._ask_key(asker, target, item), -999)
        tick_now = getattr(model, "tick", 0)
        if tick_now - last_tick < 2:
            return False

        tension = float(getattr(model, "group_tension", 0.0) or 0.0)
        stall = int(getattr(model, "progress_stall_ticks", 0) or 0)

        quiet_item = getattr(model, "_intervention_quiet_item", None)
        if (
            quiet_item == item
            and self._intervention_quiet_active(model)
        ):
            return False

        pending_events = getattr(model, "_pending_events", []) or []
        recent_resolution = any(
            (e.get("type") in {"share_info", "agree"} and e.get("item") == item)
            for e in [*(pending_events[-6:]), *(getattr(model, "prev_events", [])[-6:])]
        )
        pending_confirm = (
            item in getattr(model, "_escape_pending_confirm", {})
            or item in getattr(model, "_office_pending_confirm", {})
        )
        if (
            (recent_resolution or pending_confirm)
            and tension < 0.80
            and stall < 4
        ):
            return False

        return True

    def _owner_for(self, item: str) -> str:
        return ESCAPE_CLUE_OWNER[item]

    def _owner_agent(self, model: "SimModel", item: str):
        owner_id = self._owner_for(item)
        return next((a for a in getattr(model, "agents", []) if a.public_id == owner_id), None)

    def _is_smooth_personality(self, personality: str) -> bool:
        return personality in {"Leader", "Easygoing", "Decisive"}

    def _get_urgency_level(self, agent: "SimAgent", item: str) -> str:
        stress = getattr(agent, "stress", 0.3)
        blocker_age = getattr(agent.model, "_escape_bottleneck_age", 0)
        if stress > 0.55 or blocker_age > 4:
            return "high"
        if stress > 0.28 or blocker_age > 2:
            return "medium"
        return "low"

    def _recent_same_ask_count(self, model, actor: str, target: str, item: str, within: int = 5) -> int:
        tick_now = getattr(model, "tick", 0)
        key = self._ask_key(actor, target, item)
        last_tick = model._escape_last_ask_tick.get(key, -999)
        count = model._escape_ask_count.get(key, 0)
        if tick_now - last_tick <= within:
            return count
        return 0

    def _recent_blocker_events(self, model: "SimModel", item: str, event_types: Set[str], window: int = 6) -> int:
        """Count recent events of given types for a specific blocker item."""
        return sum(
            1 for e in getattr(model, "prev_events", [])[-window:]
            if e.get("item") == item and e.get("type") in event_types
        )

    def _can_rush_again(self, model, actor: str, target: str, item: str) -> bool:
        last = model._escape_last_rush_tick.get((actor, target, item), -99)
        return getattr(model, "tick", 0) - last >= 3

    def _can_doubt_again(self, model, actor: str, target: str, item: str) -> bool:
        last = model._escape_last_doubt_tick.get((actor, target, item), -99)
        return getattr(model, "tick", 0) - last >= 3

    def _note_rush(self, model, actor: str, target: str, item: str) -> None:
        model._escape_last_rush_tick[(actor, target, item)] = getattr(model, "tick", 0)

    def _note_doubt(self, model, actor: str, target: str, item: str) -> None:
        model._escape_last_doubt_tick[(actor, target, item)] = getattr(model, "tick", 0)

    def _note_intent(self, model, agent_id: str, reason: str) -> None:
        history = model._escape_intent_history.setdefault(agent_id, deque(maxlen=6))
        history.append((getattr(model, "tick", 0), reason))

    def _recent_intent_count(self, model, agent_id: str, reason: str, within: int = 4) -> int:
        tick_now = getattr(model, "tick", 0)
        history = model._escape_intent_history.get(agent_id, [])
        return sum(1 for t, r in history if r == reason and tick_now - t <= within)

    def _pick_fresh_phrase(self, agent: "SimAgent", options: List[str]) -> str:
        recent = agent.model._escape_phrase_history.get(agent.public_id, [])
        filtered = [o for o in options if o not in recent[-4:]]
        chosen = random.choice(filtered if filtered else options)
        agent.model._escape_phrase_history.setdefault(agent.public_id, []).append(chosen)
        return chosen

    def _callback_prefix(self, agent: "SimAgent", item: str) -> str:
        prev = getattr(agent.model, "prev_events", [])[-5:]
        related = [e for e in prev if e.get("item") == item]
        if not related:
            return ""

        if random.random() < 0.72:
            return ""

        options = [
            f"Back to {_spoken(item)} — ",
        ]
        return self._pick_fresh_phrase(agent, options)

    def _merge_prefix(self, prefix: str, text: str) -> str:
        if not prefix:
            return text
        if not text:
            return prefix.strip()

        # After an em-dash continuation prefix, the following word should be
        # lowercase — unless it's "I"/"I'm"/"I'll" or a proper noun we can't
        # detect cheaply. Keep capitals only for the standalone pronoun "I".
        first = text[:1]
        if first == "I" and (len(text) == 1 or text[1:2] in (" ", "'")):
            return prefix + text
        return prefix + first.lower() + text[1:]

    def _build_flow_text(self, agent: "SimAgent", text: str, item: Optional[str] = None) -> str:
        if not item:
            return text
        prefix = self._callback_prefix(agent, item)
        return self._merge_prefix(prefix, text)

    def _best_share_target(self, agent: "SimAgent", item: str, others: List["SimAgent"]) -> str:
        primary = self._primary_asker_for_item(agent, others, item)
        if primary is not None:
            return primary.public_id

        prev = getattr(agent.model, "prev_events", [])[-8:]

        for event in reversed(prev):
            if event.get("item") == item and event.get("target") == agent.public_id:
                asker = event.get("actor")
                if asker and asker != agent.public_id:
                    return asker

        leader = next((a for a in others if a.public_id == "A1" and a.public_id != agent.public_id), None)
        if leader:
            return leader.public_id

        candidates = [a for a in others if a.public_id != agent.public_id]
        if not candidates:
            return others[0].public_id if others else agent.public_id
        return random.choice(candidates).public_id

    def _primary_asker_for_item(
        self,
        owner: "SimAgent",
        others: List["SimAgent"],
        item: str,
    ) -> Optional["SimAgent"]:
        model = owner.model
        ranked: List[Tuple[int, int, float, "SimAgent"]] = []

        for other in others:
            if other.public_id == owner.public_id:
                continue
            ask_count = self._ask_count(model, other.public_id, owner.public_id, item)
            if ask_count <= 0:
                continue

            last_tick = model._escape_last_ask_tick.get(
                self._ask_key(other.public_id, owner.public_id, item),
                -999,
            )
            trust = owner.trust.get(other.public_id, 0.5)
            leader_bonus = 1 if other.public_id == "A1" else 0
            ranked.append((ask_count + leader_bonus, last_tick, trust, other))

        if ranked:
            return max(ranked, key=lambda row: (row[0], row[1], row[2]))[3]

        return next(
            (
                a for a in others
                if a.public_id == "A1" and a.public_id != owner.public_id
            ),
            None,
        )

    def _active_requester_for_item(
        self,
        model: "SimModel",
        item: str,
        within: int = 2,
    ) -> Optional[str]:
        owner = self._owner_agent(model, item)
        if owner is None:
            return None

        others = [a for a in getattr(model, "agents", []) if a.public_id != owner.public_id]
        primary = self._primary_asker_for_item(owner, others, item)
        if primary is None:
            return None

        last_tick = model._escape_last_ask_tick.get(
            self._ask_key(primary.public_id, owner.public_id, item),
            -999,
        )
        if getattr(model, "tick", 0) - last_tick <= within:
            return primary.public_id
        return None

    def _pending_confirm_for_item(self, model: "SimModel", item: str) -> Optional[Dict[str, Any]]:
        self._init_state(model)
        rec = model._escape_pending_confirm.get(item)
        if not rec:
            return None

        tick_now = getattr(model, "tick", 0)
        if (tick_now - rec.get("share_tick", -999)) > 4:
            model._escape_pending_confirm.pop(item, None)
            if not model._escape_confirmed.get(item, False):
                model._escape_revealed[item] = False
            return None
        return rec

    def _should_force_owner_release(self, agent: "SimAgent", item: str) -> bool:
        if self._owner_for(item) != agent.public_id:
            return False
        if item not in getattr(agent, "known_items", set()):
            return False
        if agent.model._escape_revealed.get(item, False):
            return False

        model = agent.model
        profile = _stress_profile(model)
        ask_volume = self._all_asks_to_target(model, agent.public_id, item)
        blocker_age = getattr(model, "_escape_bottleneck_age", 0)
        others = [a for a in getattr(model, "agents", []) if a.public_id != agent.public_id]
        primary = self._primary_asker_for_item(agent, others, item)
        trust_to_primary = agent.trust.get(getattr(primary, "public_id", None), 0.5)
        personality = getattr(agent, "personality_type", "Easygoing")

        if personality == "Decisive" and ask_volume >= 1:
            return True
        if personality == "Leader" and ask_volume >= 1 and blocker_age >= 1:
            return True
        if personality == "Easygoing" and (ask_volume >= 2 or blocker_age >= 3):
            return True
        if personality == "Creative" and ask_volume >= 2 and blocker_age >= 2:
            return True
        if personality == "Overthinker" and ask_volume >= 2 and blocker_age >= 3:
            return True
        if personality == "Skeptical" and ask_volume >= 2 and blocker_age >= 3:
            return True

        if profile == "pressure" and (ask_volume >= 1 or blocker_age >= 2):
            return True
        if profile == "smooth" and (ask_volume >= 2 or blocker_age >= 3):
            return True
        if profile == "creative" and (ask_volume >= 2 or blocker_age >= 4):
            return True
        if profile == "tension" and (ask_volume >= 3 or blocker_age >= 4):
            return True

        if trust_to_primary >= 0.60 and ask_volume >= 1 and blocker_age >= 1:
            return True
        if ask_volume >= 3:
            return True
        if blocker_age >= 5:
            return True
        if getattr(agent, "stress", 0.0) >= 0.78 and ask_volume >= 1:
            return True
        return False

    def _maybe_wrong_target(self, agent: "SimAgent", correct_target, others: List["SimAgent"]):
        personality = getattr(agent, "personality_type", "Easygoing")
        if personality in {"Leader", "Easygoing", "Decisive"}:
            miscoord_prob = 0.0
        elif personality == "Creative":
            miscoord_prob = 0.01
        else:
            miscoord_prob = 0.015

        if random.random() < miscoord_prob:
            alternatives = [a for a in others if a.public_id != correct_target.public_id and a != agent]
            if alternatives:
                return random.choice(alternatives)
        return correct_target

    def _progress_followup_text(self, agent: "SimAgent", item: str) -> str:
        personality = getattr(agent, "personality_type", "Easygoing")
        label = _spoken(item)

        options_map = {
            "Leader": [
                f"Good. {label} is settled.",
                f"Alright, {label} is clear now.",
                f"That clears {label}. Move on.",
            ],
            "Skeptical": [
                f"Okay — {label} seems solid enough now.",
                f"Fine. I can live with that on {label}.",
                f"Right, {label} looks clearer now.",
            ],
            "Overthinker": [
                f"Okay, that helps settle {label}.",
                f"That makes {label} feel a lot stronger.",
                f"Alright, I can stop worrying about {label}.",
            ],
            "Creative": [
                f"Nice, {label} fits now.",
                f"That makes {label} feel much clearer.",
                f"Okay, {label} finally makes sense.",
            ],
            "Decisive": [
                f"Good. {label} is done. Next.",
                f"Fine. {label} is sorted.",
                f"That handles {label}. Move.",
            ],
            "Easygoing": [
                f"Nice — that clears {label}.",
                f"Good, {label} makes sense now.",
                f"Alright, that's sorted.",
            ],
        }

        return self._pick_fresh_phrase(agent, options_map.get(personality, options_map["Easygoing"]))

    def _owner_ready_to_share(self, agent: "SimAgent", item: str) -> bool:
        model = agent.model
        tick_now = getattr(model, "tick", 0)
        profile = _stress_profile(model)

        if self._owner_for(item) != agent.public_id:
            return False

        # Hard trust block: if average trust is very low, owner withholds
        if hasattr(agent, "trust") and agent.trust:
            avg_trust = sum(agent.trust.values()) / max(1, len(agent.trust))
            if avg_trust < 0.25 and self._all_asks_to_target(model, agent.public_id, item) == 0:
                return False  # distrust overrides willingness to share

        if model._escape_revealed.get(item, False):
            return False

        # SINGLE-BLOCKER DISCIPLINE: only share if this item is the current priority blocker
        # This prevents multi-clue solving bursts (e.g. lock + key in same tick cluster)
        priority_missing = [k for k in ESCAPE_PRIORITY if not model.scenario.tasks.get(k, False)]
        if priority_missing and item != priority_missing[0]:
            # Allow with 10% chance to simulate minor out-of-order info sharing
            if random.random() < 0.90:
                return False

        refusal_until = model._escape_refusal_until.get((agent.public_id, item), -1)
        if tick_now < refusal_until:
            return False

        personality = getattr(agent, "personality_type", "Easygoing")
        ask_volume = self._all_asks_to_target(model, agent.public_id, item)
        blocker_age = getattr(model, "_escape_bottleneck_age", 0)

        base = {
            "Easygoing": 0.88,
            "Decisive": 0.84,
            "Leader": 0.80,
            "Creative": 0.68,
            "Skeptical": 0.38,
            "Overthinker": 0.28,
        }.get(personality, 0.65)

        if ask_volume >= 1:
            base += 0.14
        if ask_volume >= 2:
            base += 0.12
        if blocker_age >= 2:
            base += 0.08
        if agent._intervention_strategy_active("cooperative") and ask_volume >= 1:
            base += 0.24
        if tick_now >= 8:
            base += 0.10
        if tick_now >= 12:
            base += 0.14

        # ── Memory influence ──────────────────────────────────────────
        if hasattr(agent, "memory"):
            # If askers have a conflict-prone impression, owner is more resistant
            for other in getattr(agent.model, "agents", []):
                if other.public_id == agent.public_id:
                    continue
                imp = agent.memory.get_impression(other.public_id)
                if imp and "conflict_prone" in imp.get("patterns", {}):
                    base -= 0.12  # distrust reduces willingness to share
                elif imp and "positive" in imp.get("patterns", {}):
                    base += 0.06  # positive impression increases willingness
            # Recent similar positive recall boosts confidence to share
            try:
                similar = agent.memory.recall_similar(_lbl(item), "approval")
                if similar:
                    base += min(0.08, len(similar) * 0.02)
            except Exception:
                pass
        # ── Profile adjustments ───────────────────────────────────────
        # Memory-influenced sharing: if the agent has a negative impression of the
        # primary asker (conflict-prone), they hold back slightly
        if hasattr(agent, "memory") and agent.memory:
            stm = list(agent.stm)
            recent_asker = next(
                (m.get("from") for m in reversed(stm[-6:])
                 if m.get("item") == item and m.get("kind") in {"ask_info", "challenge"}),
                None,
            )
            if recent_asker:
                impression = agent.memory.get_impression(recent_asker)
                if impression and "conflict_prone" in impression.get("patterns", {}):
                    base -= 0.12   # conflict-prone asker = owner more reluctant
                elif impression and "positive" in impression.get("patterns", {}):
                    base += 0.08   # positive relationship = more willing to share

        if profile == "smooth":
            base += 0.22   # smooth teams share readily — lowest friction
            if ask_volume >= 1:
                base += 0.10
        elif profile == "pressure":
            if ask_volume >= 1:
                return True
            base += 0.16
            if blocker_age >= 1:
                base += 0.10
            if blocker_age >= 3:
                base += 0.14
        elif profile == "tension":
            if ask_volume >= 2:
                base += 0.16
            if tick_now >= 10:
                base += 0.08
        elif profile == "creative":
            base -= 0.03

        # If owner just refused this item, resist sharing for a beat
        recent_refusal = any(
            e.get("type") == "refuse"
            and e.get("actor") == agent.public_id
            and e.get("item") == item
            for e in getattr(model, "prev_events", [])[-3:]
        )
        if recent_refusal and ask_volume < 3 and blocker_age < 3 and random.random() < 0.60:
            return False

        if self._should_force_owner_release(agent, item):
            return True

        return random.random() < min(base, 0.98)

    def _maybe_refuse(self, agent: "SimAgent", asker_id: str, item: str) -> Optional[Dict[str, Any]]:
        model = agent.model
        tick_now = getattr(model, "tick", 0)
        profile = _stress_profile(model)

        if self._owner_for(item) != agent.public_id:
            return None
        if model._escape_revealed.get(item, False):
            return None

        if profile == "smooth":
            return None

        refusal_until = model._escape_refusal_until.get((agent.public_id, item), -1)
        if tick_now < refusal_until:
            return None

        personality = getattr(agent, "personality_type", "Easygoing")
        ask_volume = self._all_asks_to_target(model, agent.public_id, item)
        blocker_age = getattr(model, "_escape_bottleneck_age", 0)

        refuse_prob = {
            "Easygoing": 0.00,
            "Decisive": 0.01,
            "Leader": 0.02,
            "Creative": 0.08,
            "Skeptical": 0.18,
            "Overthinker": 0.28,
        }.get(personality, 0.10)

        if agent._intervention_strategy_active("cooperative"):
            refuse_prob *= 0.10

        if ask_volume >= 2:
            refuse_prob -= 0.08
        if blocker_age >= 2:
            refuse_prob -= 0.08
        if ask_volume >= 3 or blocker_age >= 4:
            refuse_prob = 0.0
        if tick_now >= 10:
            refuse_prob -= 0.10
        if tick_now >= 14:
            refuse_prob = 0.0

        if profile == "pressure":
            refuse_prob *= 0.25
        elif profile == "creative":
            refuse_prob *= 0.95
        elif profile == "tension":
            refuse_prob *= 0.85

        # Memory: impression of the asker modulates refusal
        if hasattr(agent, "memory"):
            try:
                imp = agent.memory.get_impression(asker_id)
                if imp:
                    if "positive" in imp.get("patterns", {}):
                        refuse_prob *= 0.70   # trust reduces refusal
                    if "conflict_prone" in imp.get("patterns", {}):
                        refuse_prob *= 1.25   # distrust increases refusal
            except Exception:
                pass

        if random.random() < max(0.0, refuse_prob):
            _, base_eta = random.choice(REFUSAL_REASONS[item])
            # Personality-scaled delay: hesitant types hold out longer
            if personality in {"Skeptical", "Overthinker"}:
                eta = base_eta + 2
            elif personality == "Creative":
                eta = base_eta + 1
            else:
                eta = base_eta
            model._escape_refusal_until[(agent.public_id, item)] = tick_now + eta
            model._escape_metrics["refusals"] += 1
            model._escape_metrics["conflicts"] += 1

            refusal_pool = REFUSAL_TEXTS.get(personality, REFUSAL_TEXTS["Easygoing"])
            text = self._pick_fresh_phrase(
                agent,
                [t.format(item=_spoken(item)) for t in refusal_pool],
            )

            return {
                "type": "refuse",
                "actor": agent.public_id,
                "target": asker_id,
                "text": text,
                "item": item,
                "reason": "escape_structured_refusal",
            }

        return None

    def _share_event(self, agent: "SimAgent", target_id: str, item: str) -> Dict[str, Any]:
        model = agent.model

        # HARD sequencing guard: only share current priority blocker
        priority_missing = [k for k in ESCAPE_PRIORITY if not model.scenario.tasks.get(k, False)]
        if priority_missing and item != priority_missing[0]:
            if random.random() < 0.97:
                return None

        # Wrong clue: under high pressure/tension, agents sometimes share uncertain info
        profile = _stress_profile(model)
        _wrong_clue_prob = 0.05 if profile == "tension" else 0.02 if profile == "pressure" else 0.0
        if _wrong_clue_prob > 0 and random.random() < _wrong_clue_prob:
            personality = getattr(agent, "personality_type", "Easygoing")
            if personality in {"Skeptical", "Overthinker", "Creative"}:
                wrong_texts = [
                    f"Wait — I'm not fully sure on {_spoken(item)}. Check it once before we go with it.",
                    f"This could be wrong, but here's my best read on {_spoken(item)} — verify it.",
                    f"This looks right for {_spoken(item)}, but I want it double-checked.",
                ]
                model._escape_metrics["conflicts"] += 1
                return {
                    "type": "share_info",
                    "actor": agent.public_id,
                    "target": target_id,
                    "text": random.choice(wrong_texts),
                    "item": item,
                    "reason": "escape_uncertain_clue",
                    "partial": True,
                    "can_complete": False,  # requires follow-up confirmation
                }

        # Dedup guard: if already revealed this tick, suppress
        current_tick = getattr(model, "tick", 0)
        if model._escape_last_share_tick.get(item, -99) == current_tick:
            return None  # already shared this item this tick

        model._escape_revealed[item] = True
        model._escape_last_share_tick[item] = current_tick
        model._escape_pending_confirm[item] = {
            "owner": agent.public_id,
            "confirmer": target_id,
            "share_tick": current_tick,
        }
        model._intervention_quiet_item = item
        model._intervention_quiet_until = max(
            getattr(model, "_intervention_quiet_until", -1),
            current_tick + 1,
        )

        info = self.info_text(item, model=agent.model) or f"I found something on {_spoken(item)}."
        personality = getattr(agent, "personality_type", "Easygoing")

        # Context bridge: reference prior solved clue if available (creates memory-like continuity)
        bridge = _context_bridge_prefix(agent, item, info)
        if bridge:
            raw_text = bridge
        else:
            raw_text = _pick(SHARE_TEXTS, personality, SHARE_TEXTS["Easygoing"], info=info)

        tick = getattr(model, "tick", 0)
        max_t = getattr(model, "episode_max_ticks", 120)
        time_pressure = tick / max(1, max_t)
        if time_pressure > 0.75 and personality in {"Easygoing", "Decisive", "Overthinker"} and not bridge:
            raw_text = f"We're running out of time. {raw_text}"

        text = _voice(self._build_flow_text(agent, raw_text, item=item), personality)

        return {
            "type": "share_info",
            "actor": agent.public_id,
            "target": target_id,
            "text": text,
            "item": item,
            "reason": "escape_owner_share",
            "partial": False,
            "can_complete": True,
        }

    def _confirm_event(self, agent: "SimAgent", target_id: str, item: str) -> Optional[Dict[str, Any]]:
        model = agent.model
        # Guard: suppress duplicate confirms — only one agent should confirm per item
        if model._escape_confirmed.get(item, False):
            return None
        recent_confirms = [e for e in getattr(model, "prev_events", [])[-8:]
                           if e.get("reason") == "escape_confirm" and e.get("preference") == item]
        if recent_confirms:
            return None
        model._escape_confirmed[item] = True
        model._escape_pending_confirm.pop(item, None)
        if not model.scenario.tasks.get(item, False):
            model.scenario.complete_task(item)
        model._escape_metrics["agreements"] += 1
        model._escape_last_progress_item = item
        model._intervention_quiet_item = item
        model._intervention_quiet_until = max(
            getattr(model, "_intervention_quiet_until", -1),
            getattr(model, "tick", 0) + 2,
        )

        personality = getattr(agent, "personality_type", "Easygoing")
        text = _voice(_pick(CONFIRM_TEXTS, personality, CONFIRM_TEXTS["Easygoing"]), personality)

        # Update emotional impressions periodically
        tasks_done = sum(1 for v in model.scenario.tasks.values() if v)
        if tasks_done % 2 == 0:
            self._update_memory_impressions(agent)

        return {
            "type": "agree",
            "actor": agent.public_id,
            "target": target_id,
            "text": text,
            "preference": item,
            "reason": "escape_confirm",
        }

    def _can_doubt(self, agent: "SimAgent", item: str) -> bool:
        model = agent.model
        tick_now = getattr(model, "tick", 0)
        blocker_age = getattr(model, "_escape_bottleneck_age", 0)
        personality = getattr(agent, "personality_type", "Easygoing")
        owner_id = self._owner_for(item)
        ask_volume = self._all_asks_to_target(model, owner_id, item)
        profile = _stress_profile(model)

        # After a blocker has just been shared/confirmed, or freshly revealed
        # by intervention, don't immediately bounce back into doubt unless the
        # run is genuinely tense or stalled.
        recent_stabilised = (
            hasattr(agent, "_item_recently_stabilized")
            and agent._item_recently_stabilized(item, within=3)
        )
        recent_reveal = (
            hasattr(agent, "_item_recently_revealed")
            and agent._item_recently_revealed(item, within=1)
        )
        focus_item = self._active_intervention_focus_item(model)
        quiet_item = getattr(model, "_intervention_quiet_item", None)
        quiet_active = self._intervention_quiet_active(model)
        if quiet_active and quiet_item and item != quiet_item:
            return False
        if (
            focus_item
            and item != focus_item
            and getattr(model, "group_tension", 0.0) < 0.85
            and getattr(model, "progress_stall_ticks", 0) < 6
        ):
            return False
        if (recent_stabilised or recent_reveal) and getattr(model, "group_tension", 0.0) < 0.65 and getattr(model, "progress_stall_ticks", 0) < 4:
            return False

        if profile == "smooth":
            return tick_now >= 14 and (ask_volume >= 5 or blocker_age >= 7)

        if profile == "creative":
            return tick_now >= 7 and (ask_volume >= 3 or blocker_age >= 4)

        if self._is_smooth_personality(personality):
            return tick_now >= 8 and (ask_volume >= 3 or blocker_age >= 4)

        if personality in {"Skeptical", "Overthinker"}:
            # Memory: if owner has a positive impression, Skeptical trusts them more → doubt threshold rises
            if hasattr(agent, "memory") and agent.memory:
                owner_id = self._owner_for(item)
                impression = agent.memory.get_impression(owner_id)
                if impression and "positive" in impression.get("patterns", {}):
                    return tick_now >= 5 or ask_volume >= 2 or blocker_age >= 2
            return tick_now >= 3 or ask_volume >= 1 or blocker_age >= 1

        return tick_now >= 4 or ask_volume >= 2 or blocker_age >= 2

    def _can_rush(self, agent: "SimAgent") -> bool:
        model = agent.model
        tick_now = getattr(model, "tick", 0)
        max_t = getattr(model, "episode_max_ticks", 120)
        tick_pct = tick_now / max(1, max_t)
        blocker_age = getattr(model, "_escape_bottleneck_age", 0)
        personality = getattr(agent, "personality_type", "Easygoing")
        profile = _stress_profile(model)

        if profile == "smooth":
            return blocker_age >= 18 or tick_pct >= 0.98 or agent.stress > 0.95
        if profile == "creative":
            return blocker_age >= 7 or tick_pct >= 0.78 or agent.stress > 0.80
        if profile == "pressure":
            return blocker_age >= 2 or tick_pct >= 0.38 or agent.stress > 0.30
        if self._is_smooth_personality(personality):
            return blocker_age >= 6 or tick_pct >= 0.70 or agent.stress > 0.55
        return blocker_age >= 3 or tick_pct >= 0.55 or agent.stress > 0.50

    def _update_memory_impressions(self, agent: "SimAgent") -> None:
        """Update emotional impressions at end of run."""
        try:
            if hasattr(agent, "memory") and agent.memory:
                tick_now = getattr(agent.model, "tick", 0)
                agent.memory.update_impressions(tick_now)
        except Exception:
            pass

    def is_failed(self, model: "SimModel") -> bool:
        """True if the episode timed out with tasks still incomplete."""
        missing = [k for k, v in model.scenario.tasks.items() if not v]
        return len(missing) > 0 and getattr(model, "tick", 0) >= getattr(model, "episode_max_ticks", 120)

    def _wrapup_text(self, agent: "SimAgent") -> str:
        model = agent.model
        tick_now = getattr(model, "tick", 0)
        max_t = getattr(model, "episode_max_ticks", 120)
        tick_pct = tick_now / max(1, max_t)

        peak = 0.0
        if hasattr(model, "agents"):
            peak = max(getattr(a, "stress", 0.0) for a in model.agents)

        conflict = model._escape_metrics.get("conflicts", 0)

        if peak > 0.60:
            pool = WRAPUP_INTENSE
        elif conflict >= 4 or tick_pct > 0.70:
            pool = WRAPUP_MESSY
        elif tick_now < 8:
            pool = WRAPUP_FAST
        else:
            pool = WRAPUP_NEUTRAL

        return random.choice(pool)

    # ──────────────────────────────────────────────────────────────────
    # main action logic
    # ──────────────────────────────────────────────────────────────────

    def choose_action(self, agent: "SimAgent", others: List["SimAgent"]) -> Optional[Dict[str, Any]]:
        model = agent.model
        self._init_state(model)
        self._update_bottleneck(model)
        _apply_escape_tick_stress(agent)

        tick_now = getattr(model, "tick", 0)

        # Refresh memory impressions every 5 ticks
        if hasattr(agent, "memory") and tick_now - getattr(model, "_escape_impression_tick", -99) >= 5:
            try:
                agent.memory.update_impressions(tick_now)
                model._escape_impression_tick = tick_now
            except Exception:
                pass
        max_t = getattr(model, "episode_max_ticks", 120)
        tick_pct = tick_now / max(1, max_t)

        personality = getattr(agent, "personality_type", "Easygoing")
        logic = _logic(agent)
        creativity = _creativity(agent)
        blocker_age = getattr(model, "_escape_bottleneck_age", 0)
        profile = _stress_profile(model)

        missing = self._priority_missing(model)
        if not missing:
            return None

        blocker = missing[0]
        blocker_owner = self._owner_for(blocker)

        # keep sim mostly focused on current blocker
        force_blocker_focus = random.random() < 0.84

        # Memory-driven occasional recall line (rare, adds texture)
        if hasattr(agent, "memory") and random.random() < 0.04 and not force_blocker_focus:
            try:
                similar_mems = agent.memory.recall_similar(_lbl(blocker), "curiosity")
                if similar_mems:
                    available = [a for a in others if a != agent]
                    if available:
                        tgt = random.choice(available)
                        return {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": tgt.public_id,
                            "text": self._pick_fresh_phrase(agent, [
                                f"Wait — {_spoken(blocker)} ties back to an earlier clue. Give me a second.",
                                f"I've seen {_spoken(blocker)} before — let me place it.",
                                f"{_spoken(blocker)} rings a bell. Hold on.",
                            ]),
                            "item": blocker,
                            "reason": "escape_memory_recall",
                        }
            except Exception:
                pass

        # 1) owner responds to asks/challenges about current blocker
        if agent.public_id == blocker_owner and not model._escape_revealed.get(blocker, False):
            recent_targeted = next(
                (
                    m for m in reversed(list(agent.stm)[-8:])
                    if m.get("from")
                    and m.get("item") == blocker
                    and m.get("kind") in {"ask_info", "challenge"}
                ),
                None,
            )
            if recent_targeted:
                asker_id = recent_targeted.get("from")
                ask_volume = self._all_asks_to_target(model, agent.public_id, blocker)

                # Very stressed owners can hesitate briefly, but not once the blocker is clearly stalled.
                profile_check = _stress_profile(model)
                if (
                    profile_check == "pressure"
                    and agent.stress > 0.85
                    and ask_volume == 0
                    and blocker_age < 2
                    and random.random() < 0.10
                ):
                    return None  # overwhelmed — stops responding

                # Low trust can delay an early response, but should not block the room forever.
                if hasattr(agent, "trust"):
                    trust_to_asker = agent.trust.get(asker_id, 0.5)
                    if (
                        trust_to_asker < 0.20
                        and ask_volume < 2
                        and blocker_age < 3
                        and random.random() < 0.35
                    ):
                        return None  # ignored — coordination breaks down

                refusal = self._maybe_refuse(agent, asker_id, blocker)
                if refusal is not None:
                    return refusal
                if self._owner_ready_to_share(agent, blocker):
                    _share = self._share_event(agent, asker_id, blocker)
                    if _share is not None:
                        return _share

        # 2) confirm newly shared blocker clue using a strict pending confirmer.
        pending = self._pending_confirm_for_item(model, blocker)
        if (
            pending
            and model._escape_revealed.get(blocker, False)
            and not model._escape_confirmed.get(blocker, False)
            and pending.get("confirmer") == agent.public_id
            and pending.get("owner") != agent.public_id
        ):
            recent_share = next(
                (
                    m for m in reversed(list(agent.stm)[-6:])
                    if m.get("kind") == "share_info"
                    and m.get("item") == blocker
                    and m.get("from") == pending.get("owner")
                ),
                None,
            )
            if recent_share:
                reason = recent_share.get("reason", "")
                is_uncertain = reason == "escape_uncertain_clue"

                if is_uncertain:
                    model._escape_pending_confirm.pop(blocker, None)
                    model._escape_revealed[blocker] = False
                    model._escape_metrics["conflicts"] += 1
                    return {
                        "type": "challenge",
                        "actor": agent.public_id,
                        "target": recent_share["from"],
                        "text": self._pick_fresh_phrase(agent, [
                            f"That doesn't match what I have on {_spoken(blocker)}. Can you check again?",
                            f"I'm not sure that's right for {_spoken(blocker)} — something feels off.",
                            f"That might be wrong. We need to verify {_spoken(blocker)} properly.",
                        ]),
                        "item": blocker,
                        "reason": "escape_wrong_clue_reject",
                    }

            share_age = tick_now - pending.get("share_tick", tick_now)
            if personality in {"Skeptical", "Overthinker"} and share_age <= 0 and random.random() < 0.12:
                return None
            return self._confirm_event(agent, pending["owner"], blocker)

        # 2b) Memory recall — occasionally surface a relevant past experience
        if hasattr(agent, "memory") and agent.memory and random.random() < 0.04:
            try:
                memories = agent.memory.recall_similar(_lbl(blocker), "neutral", limit=3)
                if memories:
                    mem = memories[0]
                    mem_emotion = mem.get("primary_emotion", "neutral")
                    # Only surface if emotionally relevant
                    if mem_emotion not in {"neutral", "confusion"} and len(others) > 0:
                        tgt = random.choice([a for a in others if a != agent])
                        recall_texts = {
                            "fear":    f"This feels like last time with {_spoken(blocker)} — let's be careful.",
                            "anger":   f"Last time we stalled on something like this it cost us. Let's move.",
                            "joy":     f"We cracked something similar before — I think we can do this.",
                            "surprise":f"Wait — this reminds me of something. Let me think about {_spoken(blocker)}.",
                        }
                        recall_text = recall_texts.get(mem_emotion,
                            f"Something about {_spoken(blocker)} reminds me of an earlier clue.")
                        return {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": tgt.public_id,
                            "text": recall_text,
                            "item": blocker,
                            "reason": "escape_memory_recall",
                        }
            except Exception:
                pass  # memory recall is best-effort

        # 3) short progress follow-up only right after the progress happened
        last_progress_item = getattr(model, "_escape_last_progress_item", None)
        last_share_tick = model._escape_last_share_tick.get(last_progress_item, -999) if last_progress_item else -999

        if (
            last_progress_item
            and last_progress_item != blocker
            and tick_now - last_share_tick <= 1
            and random.random() < 0.035
        ):
            available = [a for a in others if a != agent]
            if available:
                target = random.choice(available)
                return {
                    "type": "say",
                    "actor": agent.public_id,
                    "target": target.public_id,
                    "text": self._progress_followup_text(agent, last_progress_item),
                    "item": last_progress_item,
                    "reason": "escape_progress_followup",
                }

        # 4) proactive owner share
        if agent.public_id == blocker_owner and not model._escape_revealed.get(blocker, False):
            incoming_asks = self._all_asks_to_target(model, agent.public_id, blocker)

            proactive_prob = {
                "Easygoing": 0.10,
                "Decisive": 0.10,
                "Leader": 0.08,
                "Creative": 0.08,
                "Skeptical": 0.03,
                "Overthinker": 0.02,
            }.get(personality, 0.06)

            if blocker_age >= 2:
                proactive_prob += 0.08
            if tick_pct >= 0.60:
                proactive_prob += 0.08

            if profile == "smooth":
                if tick_now <= 2:
                    proactive_prob *= 0.08
                elif tick_now <= 4 and incoming_asks == 0:
                    proactive_prob *= 0.20
            elif profile == "creative":
                proactive_prob *= 0.75
            elif profile == "pressure":
                proactive_prob *= 1.20

            # Smooth teams: force share if blocker stalling (age>=3 or 2+ asks)
            if profile == "smooth" and agent.public_id == blocker_owner:
                ask_vol_now = self._all_asks_to_target(model, agent.public_id, blocker)
                if ask_vol_now >= 2 or blocker_age >= 3:
                    _share = self._share_event(agent, self._best_share_target(agent, blocker, others), blocker)
                    if _share is not None:
                        return _share

            # Pressure teams can hesitate, but not after repeated requests have made the blocker obvious.
            if (
                profile == "pressure"
                and agent.stress > 0.85
                and incoming_asks == 0
                and blocker_age < 2
                and random.random() < 0.12
            ):
                return None  # too stressed to take initiative — waits for someone else

            # Scale proactive share by env modifier for this personality type
            env_mods = get_env_modifiers(agent.model, personality)
            proactive_prob *= env_mods.get("share_bias", 1.0)

            if random.random() < proactive_prob:
                if personality == "Creative" and blocker_age >= 2 and random.random() < 0.20:
                    target = random.choice([a for a in others if a != agent])
                    text = self._pick_fresh_phrase(
                        agent,
                            [
                                f"What if {_spoken(blocker)} means something else?",
                                f"Maybe {_spoken(blocker)} has a different meaning.",
                                f"I wonder if we're reading {_spoken(blocker)} right.",
                                f"Let me think about {_spoken(blocker)} one more way first.",
                            ],
                        )
                    return {
                        "type": "say",
                        "actor": agent.public_id,
                        "target": target.public_id,
                        "text": self._build_flow_text(agent, text, item=blocker),
                        "reason": "creative_reframe_delay",
                    }

                target_id = self._best_share_target(agent, blocker, others)
                _share = self._share_event(agent, target_id, blocker)
                if _share is not None:
                    return _share

        # 5) ask correct owner for current blocker
        # Guard: skip if agent already has the item (covers forced-meeting shares that bypass
        # _share_event and therefore don't set _escape_revealed, so known_items is the
        # authoritative check for "I received this already").
        if (not model._escape_revealed.get(blocker, False)
                and agent.public_id != blocker_owner
                and blocker not in getattr(agent, "known_items", set())):
            owner_agent = self._owner_agent(model, blocker)
            if owner_agent is not None and owner_agent != agent:
                # Always target the correct blocker owner for clue-critical actions
                target = owner_agent
                active_requester = self._active_requester_for_item(model, blocker)
                if active_requester and active_requester != agent.public_id:
                    return None

                recent_askers = {
                    e.get("actor")
                    for e in getattr(model, "prev_events", [])[-6:]
                    if e.get("type") == "ask_info"
                    and e.get("target") == owner_agent.public_id
                    and e.get("item") == blocker
                    and e.get("actor") != agent.public_id
                }
                if len(recent_askers) >= 1 and profile != "smooth":
                    current_cp = getattr(model, "coord_pressure_bonus", 0.0)
                    bump = 0.040 if profile == "pressure" else 0.022
                    setattr(model, "coord_pressure_bonus", round(current_cp + bump, 4))

                if self._can_ask_again(model, agent.public_id, target.public_id, blocker):
                    self._note_ask(model, agent.public_id, target.public_id, blocker)
                    model._escape_metrics["probes"] += 1
                    ask_count = self._ask_count(model, agent.public_id, target.public_id, blocker)

                    if profile == "pressure":
                        rush_threshold = 1 if personality in {"Decisive", "Leader"} else 2
                        doubt_threshold = 1
                    elif profile == "smooth":
                        if tick_now <= 4:
                            rush_threshold = 9999
                            doubt_threshold = 9999
                        else:
                            rush_threshold = 6
                            doubt_threshold = 5
                    elif profile == "tension":
                        rush_threshold = 5
                        doubt_threshold = 1
                    else:  # creative
                        rush_threshold = 5
                        doubt_threshold = 3

                    if personality in {"Decisive", "Leader"} and ask_count >= 3 and profile != "smooth":
                        model._escape_metrics["conflicts"] += 1

                    recent_rushes = self._recent_intent_count(model, agent.public_id, "escape_rush", within=4)
                    recent_doubts_for_rush = self._recent_intent_count(model, agent.public_id, "escape_doubt", within=3)

                    if profile == "pressure" and (recent_rushes + recent_doubts_for_rush) >= 1:
                        recent_rushes = 99

                    # Anti-spam: cap escalation on same blocker
                    recent_doubt_events = self._recent_blocker_events(model, blocker, {"challenge"}, window=6)
                    recent_rush_events  = self._recent_blocker_events(model, blocker, {"say"}, window=5)
                    recent_ask_events   = self._recent_blocker_events(model, blocker, {"ask_info"}, window=5)

                    # If owner just refused, give breathing room before rushing
                    owner_just_refused = any(
                        e.get("type") == "refuse" and e.get("actor") == owner_agent.public_id
                        and e.get("item") == blocker
                        for e in getattr(model, "prev_events", [])[-3:]
                    )

                    can_escalate_rush = (
                        target.public_id == owner_agent.public_id
                        and ask_count >= rush_threshold
                        and self._can_rush(agent)
                        and self._can_rush_again(model, agent.public_id, target.public_id, blocker)
                        and recent_rushes < 1
                        and recent_doubt_events < 2   # no rush if team already doubted twice
                        and not owner_just_refused    # give breathing room after refusal
                    )

                    if can_escalate_rush:
                        model._escape_metrics["pressure"] += 1
                        if ask_count >= 2 and profile != "smooth":
                            model._escape_metrics["conflicts"] += 1

                        urgency = self._get_urgency_level(agent, blocker)

                        if personality == "Decisive" and urgency == "low":
                            rush_text = self._pick_fresh_phrase(
                                agent,
                                [
                                    f"{self.role(target.public_id)}, let's lock in the next clue.",
                                    f"We need to keep moving. {self.role(target.public_id)}?",
                                    f"{self.role(target.public_id)}, can you confirm what you have?",
                                ],
                            )
                        elif personality == "Decisive" and urgency == "medium":
                            rush_text = self._pick_fresh_phrase(
                                agent,
                                [
                                    f"{self.role(target.public_id)}, we're stuck here. What do you have?",
                                    f"{self.role(target.public_id)}, no more waiting.",
                                ],
                            )
                        else:
                            # Smooth-team or low-stress agents: don't bark — use the gentler pool
                            _use_gentle = profile == "smooth" and getattr(agent, "stress", 0.5) < 0.35
                            rush_pool_key = "Easygoing" if _use_gentle else personality
                            pool = RUSH_TEXTS.get(rush_pool_key, RUSH_TEXTS["Easygoing"])
                            fmt_pool = [t.format(role=self.role(target.public_id)) for t in pool]
                            rush_text = self._pick_fresh_phrase(agent, fmt_pool)

                        rush_text = self._build_flow_text(agent, rush_text, item=blocker)

                        self._note_rush(model, agent.public_id, target.public_id, blocker)
                        self._note_intent(model, agent.public_id, "escape_rush")
                        return {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": rush_text,
                            "item": blocker,
                            "reason": "escape_rush",
                        }

                    recent_doubts = self._recent_intent_count(model, agent.public_id, "escape_doubt", within=4)
                    recent_rushes_for_doubt = self._recent_intent_count(model, agent.public_id, "escape_rush", within=3)
                    suppress_doubt = profile == "pressure" and recent_rushes_for_doubt >= 1

                    can_escalate_doubt = (
                        target.public_id == owner_agent.public_id
                        and ask_count >= doubt_threshold
                        and self._can_doubt(agent, blocker)
                        and self._can_doubt_again(model, agent.public_id, target.public_id, blocker)
                        and recent_doubts < 1
                        and not suppress_doubt
                        and recent_doubt_events < 2   # cap doubt spam per blocker
                        and not model._escape_confirmed.get(blocker, False)  # already confirmed this tick
                        and self._pending_confirm_for_item(model, blocker) is None  # confirm in flight
                        and not (
                            hasattr(agent, "_item_recently_stabilized")
                            and agent._item_recently_stabilized(blocker, within=3)
                            and getattr(model, "group_tension", 0.0) < 0.65
                            and getattr(model, "progress_stall_ticks", 0) < 4
                        )
                    )

                    if can_escalate_doubt:
                        urgency = self._get_urgency_level(agent, blocker)

                        if personality == "Decisive" and urgency == "low":
                            doubt_text = self._pick_fresh_phrase(
                                agent,
                                [
                                    f"{self.role(target.public_id)}, can you double-check that?",
                                    f"Just confirming — {_spoken(blocker)} is right?",
                                    f"{self.role(target.public_id)}, want to verify {_spoken(blocker)} once more?",
                                ],
                            )
                        else:
                            pool = DOUBT_TEXTS.get(personality, DOUBT_TEXTS["Easygoing"])
                            fmt_pool = [t.format(role=self.role(target.public_id), item=_spoken(blocker)) for t in pool]
                            doubt_text = self._pick_fresh_phrase(agent, fmt_pool)

                        doubt_text = self._build_flow_text(agent, doubt_text, item=blocker)

                        if ask_count >= 2 and profile != "smooth":
                            model._escape_metrics["conflicts"] += 1

                        self._note_doubt(model, agent.public_id, target.public_id, blocker)
                        self._note_intent(model, agent.public_id, "escape_doubt")
                        return {
                            "type": "challenge",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": doubt_text,
                            "item": blocker,
                            "reason": "escape_doubt",
                        }

                    if personality == "Creative" and blocker_age >= 3 and random.random() < 0.08:
                        text = self._pick_fresh_phrase(
                            agent,
                            [
                                f"{_spoken(blocker)} might connect to what we already have.",
                                f"I keep wondering if {_spoken(blocker)} links to the earlier clue.",
                                f"What if {_spoken(blocker)} is connected to the first thing we found?",
                            ],
                        )
                        return {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": self._build_flow_text(agent, text, item=blocker),
                            "item": blocker,
                            "reason": "creative_speculation_delay",
                        }

                    if personality in {"Decisive", "Leader"} and ask_count >= 1 and profile == "pressure":
                        model._escape_metrics["pressure"] += 1
                        current_cp = getattr(model, "coord_pressure_bonus", 0.0)
                        setattr(model, "coord_pressure_bonus", round(current_cp + 0.030, 4))

                    recent_asks = self._recent_intent_count(model, agent.public_id, "escape_ask_owner", within=3)
                    recent_coords = self._recent_intent_count(model, agent.public_id, "escape_coordination", within=4)
                    if recent_asks >= 2 and recent_coords < 1 and random.random() < 0.50:
                        self._note_intent(model, agent.public_id, "escape_coordination")
                        text = self._pick_fresh_phrase(
                            agent,
                            [
                                f"{self.role(target.public_id)}, {_spoken(blocker)} — I need it now.",
                                f"Still waiting on {_spoken(blocker)} — come on.",
                                f"{self.role(target.public_id)}, {_spoken(blocker)} is holding us up.",
                            ],
                        )
                        return {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": self._build_flow_text(agent, text, item=blocker),
                            "item": blocker,
                            "reason": "escape_coordination",
                        }

                    recent_coords2 = self._recent_intent_count(model, agent.public_id, "escape_coordination", within=4)
                    if self._recent_same_ask_count(model, agent.public_id, target.public_id, blocker, within=5) >= 2 and recent_coords2 < 1:
                        self._note_intent(model, agent.public_id, "escape_coordination")
                        text = self._pick_fresh_phrase(
                            agent,
                            [
                                f"{self.role(target.public_id)}, we still need {_spoken(blocker)}.",
                                f"We can't move without {_spoken(blocker)}.",
                                f"{self.role(target.public_id)}, we're waiting on {_spoken(blocker)}.",
                            ],
                        )
                        return {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": self._build_flow_text(agent, text, item=blocker),
                            "item": blocker,
                            "reason": "escape_coordination",
                        }

                    self._note_intent(model, agent.public_id, "escape_ask_owner")
                    return {
                        "type": "ask_info",
                        "actor": agent.public_id,
                        "target": target.public_id,
                        "text": self.generate_ask_text(agent, blocker, target.public_id),
                        "item": blocker,
                        "reason": "escape_ask_owner",
                    }

        # 6) non-owner speculation on current blocker only
        blocker_idx = ESCAPE_PRIORITY.index(blocker) if blocker in ESCAPE_PRIORITY else 0
        items_done = sum(1 for v in model.scenario.tasks.values() if v)
        if not model._escape_revealed.get(blocker, False) and blocker in getattr(agent, "known_items", set()):
            if (
                agent.public_id != blocker_owner
                and blocker_idx <= items_done + 1
                and random.random() < (0.08 if profile == "creative" else 0.04)
            ):
                available = [a for a in others if a != agent]
                if available:
                    target = random.choice(available)
                    text = random.choice(
                        [
                            f"I think I understand {_spoken(blocker)}, but {self.role(blocker_owner)} should confirm it.",
                            f"I can reference {_spoken(blocker)}, but {self.role(blocker_owner)} needs to verify it.",
                            f"I have a lead on {_spoken(blocker)}, but the owner should confirm.",
                        ]
                    )
                    return {
                        "type": "say",
                        "actor": agent.public_id,
                        "target": target.public_id,
                        "text": text,
                        "item": blocker,
                        "reason": "escape_nonowner_speculation",
                    }

        # 7) creative reframing mainly when stuck
        if creativity > 0.68 and blocker_age >= 3 and not model._escape_revealed.get(blocker, False):
            reframe_prob = 0.07 if profile == "creative" else 0.04
            recent_reframes = self._recent_intent_count(model, agent.public_id, "escape_creative_reframe", within=5)
            if recent_reframes < 1 and random.random() < reframe_prob:
                _reframe_candidates = [a for a in others if a != agent]
                if not _reframe_candidates:
                    return None
                target = random.choice(_reframe_candidates)
                others_escalating = any(
                    e.get("reason") in ("escape_rush", "escape_doubt")
                    for e in getattr(model, "prev_events", [])[-4:]
                )
                if others_escalating and profile != "smooth":
                    model._escape_metrics["conflicts"] += 1
                self._note_intent(model, agent.public_id, "escape_creative_reframe")
                text = random.choice(
                    [
                        f"What if {_spoken(blocker)} means something else?",
                        f"Maybe {_spoken(blocker)} has another meaning.",
                        f"What if we read {_spoken(blocker)} differently?",
                        f"I think we're reading {_spoken(blocker)} wrong.",
                    ]
                )
                return {
                    "type": "say",
                    "actor": agent.public_id,
                    "target": target.public_id,
                    "text": text,
                    "reason": "escape_creative_reframe",
                }

        # 8) light coordination — suppressed if agent recently coordinated
        if force_blocker_focus:
            return None

        recent_agent_coords = self._recent_intent_count(model, agent.public_id, "escape_coordination", within=4)
        coord_prob = 0.03 + (0.04 if agent.public_id == "A1" else 0.0) + (0.02 if logic > 0.65 else 0.0)
        if recent_agent_coords < 1 and random.random() < coord_prob:
            available = [a for a in others if a != agent and not a.current_conversation_with]
            if available:
                target = random.choice(available)
                tasks_done = sum(1 for value in model.scenario.tasks.values() if value)

                if tasks_done == 0:
                    stage_opts = [
                        f"{self.role(target.public_id)}, what have you got so far?",
                        "Let's establish what everyone has before we start.",
                        f"{self.role(target.public_id)}, share what you know.",
                        "Let's go through the clues logically.",
                    ]
                elif tasks_done < 4:
                    stage_opts = [
                        f"{self.role(target.public_id)}, what's your status?",
                        "We still need to verify the missing link.",
                        "Can we piece the clues together carefully?",
                        f"{self.role(target.public_id)}, go through it carefully.",
                        "Keep pulling threads — we've got more to find.",
                    ]
                else:
                    # ≥4/5 clues in — it's actually fair to say "last piece".
                    stage_opts = [
                        "We're close — just need the last piece.",
                        "One blocker left. Let's solve it.",
                        f"{self.role(target.public_id)}, we have most of it — what's missing?",
                        "Almost there. Stay focused.",
                    ]

                return {
                    "type": "say",
                    "actor": agent.public_id,
                    "target": target.public_id,
                    "text": self._pick_fresh_phrase(agent, stage_opts),
                    "reason": "escape_coordination",
                }

        # 9) occasional progress filler — suppressed once all clues confirmed
        all_confirmed = all(model._escape_confirmed.get(k, False) for k in ESCAPE_PRIORITY)
        last_progress_tick = getattr(model, "_escape_progress_text_last_tick", -99)
        if not all_confirmed and tick_now - last_progress_tick >= 3 and random.random() < 0.025:
            available = [a for a in others if a != agent and not a.current_conversation_with]
            if available:
                tasks_done_now = sum(1 for v in model.scenario.tasks.values() if v)
                # "One piece down" / "that clears a blocker" only makes sense
                # once at least one task is actually done. Skip filler at 0/5.
                if tasks_done_now == 0:
                    return None
                target = random.choice(available)
                model._escape_progress_text_last_tick = tick_now
                return {
                    "type": "say",
                    "actor": agent.public_id,
                    "target": target.public_id,
                    "text": random.choice(PROGRESS_TEXTS),
                    "reason": "escape_progress_filler",
                }

        return None

    def post_tick(
        self,
        model: "SimModel",
        events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        self._init_state(model)

        if model.scenario.progress_ratio() >= 1.0:
            return []

        tick_now = getattr(model, "tick", 0)
        max_ticks = getattr(model, "episode_max_ticks", 120)
        extra_events: List[Dict[str, Any]] = []

        # If a valid share landed and the intended confirmer stayed quiet,
        # confirm it automatically rather than leaving the blocker hanging.
        for item, pending in list(model._escape_pending_confirm.items()):
            if model._escape_confirmed.get(item, False):
                continue

            share_age = tick_now - pending.get("share_tick", tick_now)
            final_deadline_close = (
                len(self._priority_missing(model)) == 1
                and tick_now >= (max_ticks - 1)
            )
            min_age = 0 if final_deadline_close else 1
            if share_age < min_age:
                continue

            confirmer_id = pending.get("confirmer")
            owner_id = pending.get("owner")
            if not confirmer_id or not owner_id:
                continue

            if (not final_deadline_close) and any(e.get("actor") == confirmer_id for e in events):
                continue

            confirmer = next((a for a in model.agents if a.public_id == confirmer_id), None)
            if confirmer is None:
                continue

            confirm_event = self._confirm_event(confirmer, owner_id, item)
            if confirm_event is not None:
                confirm_event["reason"] = "escape_confirm_fallback"
                extra_events.append(confirm_event)

        # ─── Urgency pulse: time-pressure broadcast that makes escape feel
        # distinctively different from office. Fires on milestone ticks when the
        # room hasn't just wrapped and no recent urgency has aired.
        urgency_milestones = {
            max(3, int(max_ticks * 0.30)),
            max(6, int(max_ticks * 0.50)),
            max(9, int(max_ticks * 0.70)),
            max(12, max_ticks - 3),
        }
        items_done = sum(1 for v in model.scenario.tasks.values() if v)
        items_total = max(1, len(model.scenario.tasks))
        pct_done = items_done / items_total

        if (
            tick_now in urgency_milestones
            and pct_done < 0.75
            and tick_now - getattr(model, "_escape_last_urgency_tick", -99) >= 3
        ):
            # Prefer a pressure-oriented voice, then any available agent
            preferred = [
                a for a in getattr(model, "agents", [])
                if getattr(a, "personality_type", "") in ("Decisive", "Leader")
                and not any(e.get("actor") == a.public_id for e in events)
            ]
            if not preferred:
                preferred = [
                    a for a in getattr(model, "agents", [])
                    if not any(e.get("actor") == a.public_id for e in events)
                ]
            if preferred:
                speaker = random.choice(preferred)
                spk_p = getattr(speaker, "personality_type", "Easygoing")
                pool = URGENCY_PULSES.get(spk_p, URGENCY_PULSES["Easygoing"])
                tgts = [a for a in getattr(model, "agents", []) if a.public_id != speaker.public_id]
                tgt = random.choice(tgts) if tgts else speaker
                # Bump stress on everyone else — it's a passive pressure spike
                from app.sim.agent import clamp
                for a in getattr(model, "agents", []):
                    if a.public_id == speaker.public_id:
                        continue
                    neuro = a.traits.get("N", 0.5)
                    a.stress = clamp(a.stress + 0.020 * (0.6 + neuro), 0.0, 1.0)
                speaker.stress = clamp(speaker.stress + 0.010, 0.0, 1.0)
                model._escape_last_urgency_tick = tick_now
                extra_events.append({
                    "type": "say",
                    "actor": speaker.public_id,
                    "target": tgt.public_id,
                    "text": random.choice(pool),
                    "reason": "escape_urgency_pulse",
                })

        # ─── Re-check / wrong-assumption: Skeptical or Overthinker agents can
        # second-guess an already-solved clue once we have some progress. The
        # clue is NOT un-done, but it forces visible doubt + a stress hit.
        # GATE: only fire when there is a real reason — elevated group tension
        # OR a progress stall. Otherwise a confirmed clue shouldn't randomly
        # come back into doubt and break conversation coherence.
        _tension = float(getattr(model, "group_tension", 0.0) or 0.0)
        _stall = int(getattr(model, "progress_stall_ticks", 0) or 0)
        _recheck_warranted = (_tension >= 0.45) or (_stall >= 3)
        _quiet_active = self._intervention_quiet_active(model)
        if (
            items_done >= 2
            and items_done < items_total  # don't recheck after all tasks complete
            and getattr(model, "_escape_recheck_count", 0) < 2
            and tick_now - getattr(model, "_escape_last_recheck_tick", -99) >= 4
            and tick_now >= 6
            and _recheck_warranted
            and not _quiet_active
            and random.random() < 0.25
        ):
            doubters = [
                a for a in getattr(model, "agents", [])
                if getattr(a, "personality_type", "") in ("Skeptical", "Overthinker", "Creative")
                and not any(e.get("actor") == a.public_id for e in events)
            ]
            completed_items = [k for k, v in model.scenario.tasks.items() if v]
            if doubters and completed_items:
                doubter = random.choice(doubters)
                item_to_recheck = random.choice(completed_items)
                d_p = getattr(doubter, "personality_type", "Skeptical")
                pool = RECHECK_TEXTS.get(d_p, RECHECK_TEXTS["Skeptical"])
                tgts = [a for a in getattr(model, "agents", []) if a.public_id != doubter.public_id]
                tgt = random.choice(tgts) if tgts else doubter
                from app.sim.agent import clamp
                # Re-checks hit everyone's stress — the team has to mentally revisit
                for a in getattr(model, "agents", []):
                    if a.public_id == doubter.public_id:
                        continue
                    neuro = a.traits.get("N", 0.5)
                    a.stress = clamp(a.stress + 0.025 * (0.6 + neuro), 0.0, 1.0)
                doubter.stress = clamp(doubter.stress + 0.015, 0.0, 1.0)
                model._escape_recheck_count = getattr(model, "_escape_recheck_count", 0) + 1
                model._escape_last_recheck_tick = tick_now
                extra_events.append({
                    "type": "challenge",
                    "actor": doubter.public_id,
                    "target": tgt.public_id,
                    "text": random.choice(pool).format(item=_spoken(item_to_recheck)),
                    "item": item_to_recheck,
                    "reason": "escape_recheck",
                })

        # ─── Final unlock sequence: all 4 clues confirmed → three-tick door open.
        # Tick M   → record that the 4th clue just landed (silent, so the confirm
        #            event keeps its own tick and isn't deduped against ENTER).
        # Tick N   → Team Leader says "Entering {code}. Hold." (escape_unlock_attempt)
        # Tick N+1 → Another agent says "Door's open" (escape_door_open), unlock marked done.
        four_clues_done = all(model.scenario.tasks.get(k, False) for k in ESCAPE_PRIORITY)
        unlock_done = model.scenario.tasks.get("unlock", False)
        if four_clues_done and not unlock_done:
            # Stamp the tick on which the 4th clue first completed, so we never
            # try to emit ENTER on the same tick as the confirm (which would be
            # dropped by the same-actor dedupe in SimModel._normalize_events).
            if getattr(model, "_escape_four_clues_tick", None) is None:
                model._escape_four_clues_tick = tick_now

            four_done_tick = model._escape_four_clues_tick

            if not getattr(model, "_escape_unlock_initiated", False):
                # Gate: require strictly at least one tick between the confirm
                # that finished the 4th clue and the ENTER line.
                if tick_now <= four_done_tick:
                    return extra_events

                # Tension team: insert TWO extra beats before ENTER —
                # (1) Skeptical/Overthinker requests a read-back,
                # (2) another agent confirms the code matches.
                # This adds believable delay for tension without breaking logic.
                preset = getattr(model, "team_preset", None)
                if preset == "tension_team" and not getattr(model, "_escape_tension_verified", False):
                    agents = getattr(model, "agents", [])
                    busy_actors = {e.get("actor") for e in events}
                    busy_actors |= {e.get("actor") for e in extra_events}
                    # Prefer a Skeptical / Overthinker voice for the verify beat
                    candidates = [a for a in agents
                                  if a.public_id not in busy_actors
                                  and getattr(a, "personality_type", "") in ("Skeptical", "Overthinker")]
                    if not candidates:
                        candidates = [a for a in agents if a.public_id not in busy_actors]
                    if candidates:
                        verifier = candidates[0]
                        door_code = model._escape_facts.get("_door_code_short", "4-2-7-1")
                        pt = getattr(verifier, "personality_type", "Skeptical")
                        if pt == "Overthinker":
                            txt = f"Wait — before we enter {door_code}, say the code back once. If this is wrong, we lose time."
                        else:
                            txt = f"Hold on — verify the code once. {door_code} — say it back so we know we're aligned."
                        tgt_pool = [a for a in agents if a.public_id != verifier.public_id]
                        tgt = random.choice(tgt_pool) if tgt_pool else verifier
                        model._escape_tension_verified = tick_now
                        model._escape_tension_verifier = verifier.public_id
                        model._escape_tension_confirm_target = tgt.public_id
                        extra_events.append({
                            "type": "say",
                            "actor": verifier.public_id,
                            "target": tgt.public_id,
                            "text": txt,
                            "reason": "escape_coordination",
                        })
                        return extra_events
                    # If no candidates free this tick, defer — still require verify
                    return extra_events
                if preset == "tension_team" and tick_now <= getattr(model, "_escape_tension_verified", 0):
                    return extra_events
                # Second beat: the addressed teammate reads the code back.
                if preset == "tension_team" and not getattr(model, "_escape_tension_confirmed", False):
                    agents = getattr(model, "agents", [])
                    busy_actors = {e.get("actor") for e in events}
                    busy_actors |= {e.get("actor") for e in extra_events}
                    confirm_id = getattr(model, "_escape_tension_confirm_target", None)
                    confirmer = next(
                        (a for a in agents if a.public_id == confirm_id and a.public_id not in busy_actors),
                        None,
                    )
                    if confirmer is None:
                        # Fallback: any free non-verifier agent
                        confirmer = next(
                            (a for a in agents
                             if a.public_id not in busy_actors
                             and a.public_id != getattr(model, "_escape_tension_verifier", None)),
                            None,
                        )
                    if confirmer is not None:
                        door_code = model._escape_facts.get("_door_code_short", "4-2-7-1")
                        verifier_id = getattr(model, "_escape_tension_verifier", None)
                        tgt_id = verifier_id if verifier_id else confirmer.public_id
                        pt = getattr(confirmer, "personality_type", "Decisive")
                        if pt == "Decisive":
                            txt = f"{door_code}. Same read. Do it."
                        elif pt == "Leader":
                            txt = f"Confirmed — {door_code}. We're aligned. Enter it."
                        elif pt == "Skeptical":
                            txt = f"{door_code}. That matches what I've got. Clear to enter."
                        elif pt == "Overthinker":
                            txt = f"{door_code} — yeah, that's what I had too. Okay, go."
                        else:
                            txt = f"{door_code} — same here. Let's enter."
                        model._escape_tension_confirmed = tick_now
                        extra_events.append({
                            "type": "say",
                            "actor": confirmer.public_id,
                            "target": tgt_id,
                            "text": txt,
                            "reason": "escape_coordination",
                        })
                        return extra_events
                    return extra_events
                if preset == "tension_team" and tick_now <= getattr(model, "_escape_tension_confirmed", 0):
                    return extra_events

                # Tick N — leader enters the code. Pick a speaker who has NOT
                # already spoken this tick so ENTER always survives dedupe.
                leader = self._owner_agent(model, "map")  # A1 = Team Leader
                if leader is None:
                    leader = getattr(model, "agents", [])[0]

                busy_actors = {e.get("actor") for e in events}
                busy_actors |= {e.get("actor") for e in extra_events}
                if leader.public_id in busy_actors:
                    free = [a for a in getattr(model, "agents", [])
                            if a.public_id not in busy_actors and a.public_id != leader.public_id]
                    # Prefer a leader/decisive voice for the ENTER moment
                    preferred = [a for a in free
                                 if getattr(a, "personality_type", "") in ("Leader", "Decisive")]
                    if preferred:
                        leader = preferred[0]
                    elif free:
                        leader = free[0]
                    else:
                        # Nobody free — defer one more tick rather than collide
                        return extra_events

                # Use the normalised short numeric form — always "4-2-7-1"
                door_code = model._escape_facts.get("_door_code_short", "4-2-7-1")
                p = getattr(leader, "personality_type", "Leader")
                text = _pick(UNLOCK_ATTEMPT_TEXTS, p, UNLOCK_ATTEMPT_TEXTS["Easygoing"], code=door_code)
                others = [a for a in getattr(model, "agents", []) if a.public_id != leader.public_id]
                tgt = random.choice(others) if others else leader
                model._escape_unlock_initiated = tick_now
                extra_events.append({
                    "type": "say",
                    "actor": leader.public_id,
                    "target": tgt.public_id,
                    "text": text,
                    "reason": "escape_unlock_attempt",
                })
                return extra_events
            elif tick_now > model._escape_unlock_initiated:
                # Tick N+1 — door opens; a non-leader agent calls it out
                agents = getattr(model, "agents", [])
                busy_actors = {e.get("actor") for e in events}
                busy_actors |= {e.get("actor") for e in extra_events}
                non_leaders = [a for a in agents
                               if a.public_id != ESCAPE_CLUE_OWNER.get("map", "A1")
                               and a.public_id not in busy_actors]
                if not non_leaders:
                    non_leaders = [a for a in agents if a.public_id not in busy_actors]
                if not non_leaders:
                    # All actors spoke this tick — defer OPEN one more tick so
                    # same-actor dedupe cannot drop it.
                    return extra_events
                speaker = random.choice(non_leaders)
                p = getattr(speaker, "personality_type", "Easygoing")
                text = _pick(DOOR_OPEN_TEXTS, p, DOOR_OPEN_TEXTS["Easygoing"])
                tgt_pool = [a for a in agents if a.public_id != speaker.public_id]
                tgt = random.choice(tgt_pool) if tgt_pool else speaker
                model.scenario.complete_task("unlock")
                extra_events.append({
                    "type": "say",
                    "actor": speaker.public_id,
                    "target": tgt.public_id,
                    "text": text,
                    "reason": "escape_door_open",
                })
                return extra_events

        missing = self._priority_missing(model)
        if not missing:
            return extra_events

        blocker = missing[0]
        if model._escape_revealed.get(blocker, False):
            return extra_events
        if self._pending_confirm_for_item(model, blocker) is not None:
            return extra_events

        owner = self._owner_agent(model, blocker)
        if owner is None:
            return extra_events
        if any(e.get("actor") == owner.public_id for e in events):
            return extra_events
        if not self._should_force_owner_release(owner, blocker):
            return extra_events

        # Safety: during an active forced meeting, if the owner is one of the paired agents
        # the share_info would be filtered by filter_events (forced-pair agents cannot speak
        # to targets outside the pair).  But _share_event() would have already set
        # _escape_revealed and _escape_pending_confirm, causing the task to appear resolved
        # next tick with no visible dialogue.  Skip the forced_release until the meeting ends.
        _fm_agents = getattr(model, "_forced_meeting_agents", None)
        _fm_until  = getattr(model, "_forced_meeting_until", -1)
        if _fm_agents and tick_now <= _fm_until and owner.public_id in _fm_agents:
            return extra_events

        others = [a for a in getattr(model, "agents", []) if a.public_id != owner.public_id]
        target = self._primary_asker_for_item(owner, others, blocker)
        target_id = target.public_id if target is not None else self._best_share_target(owner, blocker, others)

        forced_event = self._share_event(owner, target_id, blocker)
        if forced_event is not None:
            forced_event["reason"] = "escape_forced_release"
            extra_events.append(forced_event)

        return extra_events

    # ──────────────────────────────────────────────────────────────────
    # text API
    # ──────────────────────────────────────────────────────────────────

    def _refuse_text(self, agent: "SimAgent", item: str) -> str:
        personality = getattr(agent, "personality_type", "Easygoing")
        refusal_pool = REFUSAL_TEXTS.get(personality, REFUSAL_TEXTS["Easygoing"])
        return self._pick_fresh_phrase(agent, [t.format(item=_spoken(item)) for t in refusal_pool])

    def generate_help_text(self, agent, target_id: str, item: str) -> str:
        return random.choice(
            [
                f"We need {_spoken(item)} — I'm on it.",
                f"I'll handle {_spoken(item)}. Stay focused.",
                f"{target_id}, give me a second — I'm sorting {_spoken(item)}.",
                f"Let me check {_spoken(item)} quickly.",
            ]
        )

    def generate_ignore_text(self, agent, target_id: str) -> str:
        return random.choice(
            [
                f"{target_id}, not now — keep moving.",
                "No time. Focus.",
                "Later — we need to solve this first.",
                "Leave that. Keep going.",
            ]
        )

    def generate_insult_text(self, agent, target_id: str) -> str:
        return random.choice(
            [
                f"{target_id}, you're wasting time.",
                "That really didn't help.",
                "We're going in circles because of this.",
                f"{target_id}, you're slowing us down.",
            ]
        )

    def generate_say_text(self, agent, target_id: str) -> str:
        model = agent.model
        missing = self._priority_missing(model)
        blocker = missing[0] if missing else None
        stress = getattr(agent, "stress", 0.3)

        if blocker:
            blocker_label = _spoken(blocker)
            if stress > 0.60:
                options = [
                    f"We're running out of time on {blocker_label}.",
                    f"{target_id}, stay on {blocker_label}.",
                    f"We can't stall on {blocker_label} now.",
                ]
            elif stress > 0.35:
                options = [
                    f"Alright, keep us moving on {blocker_label}.",
                    f"{target_id}, we're close — stay on {blocker_label}.",
                    f"We still need to sort {blocker_label}.",
                ]
            else:
                options = [
                    "Okay, let's keep this moving.",
                    "We're in good shape — stay focused.",
                    "Nice, keep going.",
                ]
        else:
            options = [
                "Okay, that's useful.",
                "Nice work.",
                "We've got it.",
            ]

        return self._build_flow_text(agent, self._pick_fresh_phrase(agent, options), item=blocker)

    def generate_ask_text(self, agent, item: str, target_id: str) -> str:
        personality = getattr(agent, "personality_type", "Easygoing")
        role = self.role(target_id)

        if _stress_profile(agent.model) == "smooth" and personality == "Decisive":
            options = [
                f"{role}, do you have {_spoken(item)}?",
                f"{role}, can you confirm {_spoken(item)}?",
                f"We need {_spoken(item)} next — what have you got?",
            ]
            return _voice(self._build_flow_text(agent, random.choice(options), item=item), personality)

        ask_map = {
            "Leader": [
                f"{role}, we need {_spoken(item)} — what have you got?",
                f"{role}, do you have {_spoken(item)}?",
                f"We're waiting on {_spoken(item)}. Can you confirm?",
                f"{role}, we can't move without {_spoken(item)}. Talk to me.",
            ],
            "Skeptical": [
                f"{role}, can you confirm {_spoken(item)}?",
                f"I want {_spoken(item)} checked properly. What have you got?",
                f"{role}, do you actually have anything on {_spoken(item)}?",
                f"{role}, I need a solid answer on {_spoken(item)}.",
            ],
            "Overthinker": [
                f"{role}, {_spoken(item)} — can you confirm what you have?",
                f"We still need {_spoken(item)} to complete this. Do you have it?",
                f"I want to double-check {_spoken(item)} — what have you got?",
                f"{role}, I keep coming back to {_spoken(item)}. What do you have?",
            ],
            "Creative": [
                f"{role}, do you have anything on {_spoken(item)}?",
                f"What have you got on {_spoken(item)}?",
                f"{role}, {_spoken(item)} — anything there?",
                f"{role}, what does {_spoken(item)} look like from your side?",
            ],
            "Decisive": [
                f"{role}, {_spoken(item)} — I need it now.",
                f"We need {_spoken(item)}. Direct answer.",
                f"{role}, {_spoken(item)}. Now.",
                f"{role}, we're blocked here — what do you have on {_spoken(item)}?",
            ],
            "Easygoing": [
                f"{role}, do you have anything on {_spoken(item)}?",
                f"We're stuck on {_spoken(item)} — can you help?",
                f"{role}, anything on {_spoken(item)}?",
                f"{role}, what have you got on {_spoken(item)}?",
            ],
        }
        return _voice(self._build_flow_text(agent, random.choice(ask_map.get(personality, ask_map["Easygoing"])), item=item), personality)

    def generate_share_text(self, agent, item: str, target_id: str) -> str:
        info = self.info_text(item, model=agent.model) or f"I found something about {_spoken(item)}."
        personality = getattr(agent, "personality_type", "Easygoing")
        return self._build_flow_text(
            agent,
            _pick(SHARE_TEXTS, personality, SHARE_TEXTS["Easygoing"], info=info),
            item=item,
        )

    def reply_to_info_request(
        self,
        agent: "SimAgent",
        target: "SimAgent",
        item: str,
        message_text: str,
    ) -> Optional[Dict[str, Any]]:
        self._init_state(agent.model)
        model = agent.model

        if item not in ESCAPE_PROGRESS_TASKS:
            return None

        missing = self._priority_missing(model)
        blocker = missing[0] if missing else None

        if model.scenario.tasks.get(item, False):
            return None

        if blocker and item != blocker:
            return {
                "type": "say",
                "actor": agent.public_id,
                "target": target.public_id,
                "text": self._pick_fresh_phrase(
                    agent,
                    [
                        f"We need {_spoken(blocker)} first — we'll get to that after.",
                        f"Not yet. Sort {_spoken(blocker)} first.",
                        f"Let's get {_spoken(blocker)} closed before anything else.",
                    ],
                ),
                "item": blocker,
                "reason": "escape_blocker_guard",
            }

        if self._owner_for(item) == agent.public_id:
            pending = self._pending_confirm_for_item(model, item)
            if pending and model._escape_revealed.get(item, False):
                confirmer_id = pending.get("confirmer")
                if confirmer_id == target.public_id:
                    return {
                        "type": "say",
                        "actor": agent.public_id,
                        "target": target.public_id,
                        "text": self._pick_fresh_phrase(
                            agent,
                            [
                                f"You've got {_spoken(item)} — just verify it's right.",
                                f"{_spoken(item).capitalize()} is with you — confirm when ready.",
                                f"You've got {_spoken(item)} — tell me if it holds up.",
                                f"Have a look at {_spoken(item)} and tell me if it looks right.",
                            ],
                        ),
                        "item": item,
                        "reason": "escape_awaiting_confirm",
                    }

                return {
                    "type": "say",
                    "actor": agent.public_id,
                    "target": target.public_id,
                    "text": self._pick_fresh_phrase(
                        agent,
                        [
                            f"{self.role(confirmer_id)} has it — give them a moment.",
                            f"I'm waiting on {self.role(confirmer_id)} to verify that.",
                            f"{self.role(confirmer_id)} is closing that out — let them finish.",
                        ],
                    ),
                    "item": item,
                    "reason": "escape_awaiting_confirm",
                }

            active_requester_id = self._active_requester_for_item(model, item)
            if active_requester_id and active_requester_id != target.public_id:
                return {
                    "type": "say",
                    "actor": agent.public_id,
                    "target": target.public_id,
                    "text": self._pick_fresh_phrase(
                        agent,
                        [
                            f"I'm already working this with {self.role(active_requester_id)}.",
                            f"{self.role(active_requester_id)} asked first — let me close with them.",
                            f"Hold on — I'm already on {_spoken(item)} with {self.role(active_requester_id)}.",
                        ],
                    ),
                    "item": item,
                    "reason": "escape_active_requester_guard",
                }

            if self._should_force_owner_release(agent, item) or self._owner_ready_to_share(agent, item):
                event = self._share_event(agent, target.public_id, item)
                if event is not None:
                    event["reason"] = "escape_reply_owner_share"
                    return event

            if agent._intervention_strategy_active("cooperative"):
                event = self._share_event(agent, target.public_id, item)
                if event is not None:
                    event["reason"] = "escape_reply_owner_share"
                    return event

            return {
                "type": "refuse",
                "actor": agent.public_id,
                "target": target.public_id,
                "text": self._refuse_text(agent, item),
                "item": item,
                "reason": "escape_reply_refusal",
            }

        owner_id = self._owner_for(item)
        return {
            "type": "say",
            "actor": agent.public_id,
            "target": target.public_id,
            "text": self._pick_fresh_phrase(
                agent,
                [
                    f"{self.role(owner_id)}, give us {_spoken(item)}.",
                    f"Go to {self.role(owner_id)} — they have {_spoken(item)}.",
                    f"Ask {self.role(owner_id)} for {_spoken(item)}.",
                ],
            ),
            "item": item,
            "reason": "escape_owner_guard",
        }

    def should_complete_on_agree(self, model: "SimModel", pref: str) -> bool:
        return False

    def task_to_complete(self, model: "SimModel", pref: str) -> Optional[str]:
        return None

    def agree_text(self, agent: "SimAgent", pref: str, target_id: str) -> str:
        personality = getattr(agent, "personality_type", "Easygoing")
        return _pick(CONFIRM_TEXTS, personality, CONFIRM_TEXTS["Easygoing"])

    def suggest_text(self, agent, pref, target_id):
        return f"I think we should try {pref} next."

    def generate_wrapup_text(self, agent, target_id: str) -> str:
        return self._wrapup_text(agent)

    # ──────────────────────────────────────────────────────────────────
    # info text
    # ──────────────────────────────────────────────────────────────────

    def info_text(self, item: str, model: "SimModel" = None) -> Optional[str]:
        # Return the fact fixed at model-init so all presets share the same clue truths.
        # Falls back to a fresh random pick only when called without a model reference.
        if model is not None:
            self._init_state(model)
            return model._escape_facts.get(item)
        # Fallback (should not be hit in normal flow)
        texts = {
            "map":  ["the panel's behind the bookshelf on the east wall.",
                     "east wall — there's a panel behind the bookshelf."],
            "lock": ["triangle, circle, square.",
                     "it's triangle → circle → square, in that order."],
            "key":  ["magnetic, stuck to the metal panel.",
                     "under the loose tile by the door."],
            "door": ["4-2-7-1.", "four, two, seven, one."],
        }
        options = texts.get(item)
        return random.choice(options) if options else None
