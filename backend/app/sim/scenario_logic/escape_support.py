"""
escape_support.py
=================
Low-risk support code for the escape-room scenario:

  - Item display labels and spoken aliases
  - Ownership / progress constants
  - Trait accessor helpers
  - Dialogue / template pools
  - Small pure text helpers (_pick, _context_bridge_prefix, _voice)

Imported by escape_logic.py and escape_actions.py.  Nothing here has
side-effects or depends on simulation state at import time.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from app.sim.agent import SimAgent


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
