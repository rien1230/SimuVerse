"""
app/sim/personality_maps.py

Three-layer personality system:
  1. PERSONALITIES              — user-selectable personality deltas over OCEAN
  2. PERSONALITY_ACTION_BIAS    — lightweight bias on action selection
  3. PERSONALITY_PHRASES        — language style overlays

Scenario-specific base maps:
  - OFFICE_ROLE_MAP
  - CAFE_PREF_MAP
  - ESCAPE_ARCHETYPE_MAP

User picks personality only.
System fixes roles (office), preferences (cafe), archetypes (escape).
"""
from __future__ import annotations

from typing import Dict, List
import random


TRAIT_KEYS = ("E", "A", "N", "C", "O")


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ── 1. Six personality types as OCEAN deltas ─────────────────────────────────

PERSONALITIES = {
    "Leader": {
        "E": 0.18, "A": -0.04, "N": -0.04, "C": 0.18, "O": 0.04,
    },
    "Decisive": {
        "E": 0.08, "A": -0.08, "N": 0.06, "C": 0.10, "O": -0.04,
    },
    "Easygoing": {
        "E": 0.00, "A": 0.18, "N": -0.18, "C": -0.04, "O": 0.04,
    },
    "Skeptical": {
        "E": -0.08, "A": -0.18, "N": 0.08, "C": 0.12, "O": -0.08,
    },
    "Overthinker": {
        "E": -0.16, "A": 0.00, "N": 0.24, "C": 0.08, "O": 0.16,
    },
    "Creative": {
        "E": 0.04, "A": 0.00, "N": 0.00, "C": -0.04, "O": 0.24,
    },
}

PERSONALITY_DESCRIPTIONS = {
    "Leader": "Directive, coordinates the group, pushes toward closure.",
    "Decisive": "Commits quickly, dislikes prolonged back-and-forth.",
    "Easygoing": "Reduces tension, compromises easily, keeps things calm.",
    "Skeptical": "Questions weak claims and looks for verification.",
    "Overthinker": "Hesitates, re-checks, and worries about missing something.",
    "Creative": "Reframes problems and generates alternative ideas.",
}


# ── 2. Action probability biases per personality ─────────────────────────────

PERSONALITY_ACTION_BIAS = {
    "Leader": {
        "ask": 0.10, "suggest": 0.08, "challenge": 0.04, "agree": 0.08,
        "theory": 0.00, "coord": 0.16, "finalise": 0.18, "hesitate": -0.10,
    },
    "Decisive": {
        "ask": 0.04, "suggest": 0.12, "challenge": 0.04, "agree": 0.12,
        "theory": -0.04, "coord": 0.04, "finalise": 0.14, "hesitate": -0.08,
    },
    "Easygoing": {
        "ask": -0.08, "suggest": 0.00, "challenge": -0.16, "agree": 0.18,
        "theory": 0.00, "coord": 0.06, "finalise": 0.04, "hesitate": -0.04,
    },
    "Skeptical": {
        "ask": 0.10, "suggest": -0.06, "challenge": 0.18, "agree": -0.12,
        "theory": 0.02, "coord": -0.02, "finalise": -0.08, "hesitate": 0.06,
    },
    "Overthinker": {
        "ask": 0.05, "suggest": -0.06, "challenge": 0.06, "agree": -0.08,
        "theory": 0.12, "coord": -0.06, "finalise": -0.14, "hesitate": 0.20,
    },
    "Creative": {
        "ask": 0.00, "suggest": 0.08, "challenge": 0.00, "agree": -0.04,
        "theory": 0.18, "coord": 0.00, "finalise": -0.04, "hesitate": 0.04,
    },
}


# ── 3. Phrase pools per personality per action type ──────────────────────────

PERSONALITY_PHRASES = {
    "Leader": {
        "suggest": [
            "Let's go with this.",
            "We're going with this option.",
            "This is the best move right now.",
            "I think this gives us the clearest path forward.",
            "This is the most workable option.",
        ],
        "ask": [
            "What are we still missing?",
            "Who has the final piece?",
            "What's blocking us?",
            "What do we still need before we can move?",
            "Where exactly are we stuck?",
        ],
        "coord": [
            "We need to keep moving.",
            "Let's focus on the blocker.",
            "That's enough — let's act on it.",
            "Let's keep this tight and organised.",
            "Let's stay on the next step.",
        ],
        "agree": [
            "Good — that's settled.",
            "We're back on track.",
            "Let's lock that in.",
            "That works. Move forward with it.",
            "Fine — let's commit to that.",
        ],
        "finalise": [
            "That settles it.",
            "Decision made.",
            "We're going with that.",
            "Alright, that's the call.",
            "Let's close this out there.",
        ],
    },

    "Decisive": {
        "suggest": [
            "This makes the most sense.",
            "We should go with this.",
            "That's the obvious choice.",
            "I don't think we need to drag this out.",
            "This is good enough — let's move.",
        ],
        "agree": [
            "That's enough — let's go.",
            "No need to overthink this.",
            "We've got what we need.",
            "Fine, that works — move on.",
            "Yep, good. Let's commit.",
        ],
        "finalise": [
            "Done. Let's move.",
            "That's it — no more debating.",
            "We've decided. Let's go.",
            "Call made. Move.",
            "Good enough — lock it in.",
        ],
        "coord": [
            "We're wasting time here.",
            "Let's just commit.",
            "Pick something and stick to it.",
            "We need momentum here.",
            "Let's stop circling and choose.",
        ],
    },

    "Easygoing": {
        "agree": [
            "No worries, that works for me.",
            "Yeah, I'm happy with that, honestly.",
            "Fair enough — that keeps things simple.",
            "I'm easy either way, but that makes sense.",
            "Sounds grand to me.",
            "All good — I'm on board.",
            "No stress from me — let's just go with it.",
        ],
        "suggest": [
            "I mean, this feels like the painless option.",
            "Could go either way — but this keeps it simple.",
            "This is fine with me, honestly.",
            "I'm easy, but this seems reasonable enough.",
            "I'd be alright with this — no drama.",
            "Happy to go with whatever's least painful.",
        ],
        "coord": [
            "Whatever keeps everyone comfortable.",
            "I'm easy — what's everyone else thinking?",
            "Let's just land on something — no pressure.",
            "I'm good as long as everyone's okay.",
            "We can make either work, honestly.",
            "No worries either way — just give me a shout.",
        ],
    },

    "Skeptical": {
        "challenge": [
            "Are we sure about that?",
            "I'm not convinced yet.",
            "What are we basing that on?",
            "That needs more evidence.",
            "I think we should verify that first.",
        ],
        "ask": [
            "Can you clarify that?",
            "What's the reasoning?",
            "Before we commit — what do we actually know?",
            "How certain are we on that?",
            "What's the evidence for that step?",
        ],
        "hesitate": [
            "I'd want to verify that first.",
            "Something doesn't add up.",
            "Let's not jump to conclusions.",
            "I think we're missing a piece here.",
            "That feels a bit premature to me.",
        ],
    },

    "Overthinker": {
        "hesitate": [
            "Wait — what if that's wrong?",
            "I'm not fully sure yet.",
            "Can we double-check that?",
            "I just want to make sure we're not missing anything.",
            "This feels a bit too quick for me.",
        ],
        "ask": [
            "Can we just confirm once more?",
            "I know I keep asking, but — are we certain?",
            "Something's still nagging at me.",
            "Can we verify that before moving on?",
            "I just want to be sure we're not overlooking something.",
        ],
        "theory": [
            "What if we're approaching this wrong?",
            "I keep thinking there's something we've missed.",
            "What if the answer is less obvious than it seems?",
            "Could there be another interpretation here?",
            "I wonder if we're locking in too early.",
        ],
    },

    "Creative": {
        "theory": [
            "What if there's another interpretation?",
            "Could these things connect differently?",
            "What if we're looking at it wrong?",
            "Maybe there's a pattern here.",
            "I think there may be another angle to this.",
            "What if we connect those two constraints instead of treating them separately?",
            "Could the thing we're avoiding actually be the hinge?",
        ],
        "suggest": [
            "Here's an idea — what if we tried this?",
            "What if we combined the safe option with something more interesting?",
            "What if we went a completely different direction?",
            "This might sound odd, but hear me out — it reframes the problem.",
            "I think we could frame this differently entirely.",
            "What if we flipped it — solve the later piece first, then backfill?",
            "Here's an angle: treat the limit as the feature, not the blocker.",
        ],
        "coord": [
            "Think — what connects all of this?",
            "Is there a pattern we're missing?",
            "Let's look at it from a different angle.",
            "There might be a bigger pattern here.",
            "Can we step back and connect the pieces?",
        ],
        "agree": [
            "Yeah — that gives us a cleaner direction.",
            "That opens another route. I'm in.",
            "Good — there's a pattern there, I can see it now.",
            "That reframes it nicely. Let's run with that.",
            "Okay, I can build on that.",
        ],
    },
}


# ── Role / preference / archetype base maps ──────────────────────────────────

OFFICE_ROLE_MAP = {
    "Project Manager": {"E": 0.68, "A": 0.52, "N": 0.48, "C": 0.72, "O": 0.52},
    "Developer":       {"E": 0.42, "A": 0.58, "N": 0.56, "C": 0.82, "O": 0.54},
    "Designer":        {"E": 0.60, "A": 0.56, "N": 0.38, "C": 0.62, "O": 0.78},
    "Data Analyst":    {"E": 0.38, "A": 0.46, "N": 0.46, "C": 0.84, "O": 0.56},
}

CAFE_PREF_MAP = {
    "Vegan Priority":   {"E": 0.44, "A": 0.40, "N": 0.50, "C": 0.60, "O": 0.68},
    "Budget Saver":     {"E": 0.54, "A": 0.52, "N": 0.38, "C": 0.66, "O": 0.44},
    "Food Enthusiast":  {"E": 0.68, "A": 0.54, "N": 0.30, "C": 0.50, "O": 0.72},
    "Flexible Diner":   {"E": 0.52, "A": 0.70, "N": 0.24, "C": 0.54, "O": 0.54},
}

ESCAPE_ARCHETYPE_MAP = {
    "Takes Charge":   {"E": 0.76, "A": 0.42, "N": 0.46, "C": 0.70, "O": 0.46},
    "Cautious Solver": {"E": 0.34, "A": 0.58, "N": 0.72, "C": 0.58, "O": 0.80},
    "Doubter":        {"E": 0.40, "A": 0.24, "N": 0.60, "C": 0.72, "O": 0.50},
    "Calm One":       {"E": 0.54, "A": 0.72, "N": 0.22, "C": 0.78, "O": 0.58},
}


# ── Default assignments ──────────────────────────────────────────────────────

OFFICE_DEFAULT_ROLES = {
    "A1": "Project Manager",
    "A2": "Developer",
    "A3": "Designer",
    "A4": "Data Analyst",
}

CAFE_DEFAULT_PREFS = {
    "A1": "Flexible Diner",
    "A2": "Vegan Priority",
    "A3": "Budget Saver",
    "A4": "Food Enthusiast",
}

ESCAPE_DEFAULT_ARCHETYPES = {
    "A1": "Takes Charge",
    "A2": "Cautious Solver",
    "A3": "Doubter",
    "A4": "Calm One",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def merge_traits(base_traits: Dict[str, float], personality_name: str) -> Dict[str, float]:
    """
    Merge a scenario base map with user-selected personality deltas.
    Output is clamped to [0.0, 1.0].
    """
    deltas = PERSONALITIES.get(personality_name, {})
    merged = {}
    for key in TRAIT_KEYS:
        merged[key] = clamp01(base_traits.get(key, 0.5) + deltas.get(key, 0.0))
    return merged


def get_personality_bias(personality_name: str, action_name: str) -> float:
    """Safe lookup for action bias."""
    return PERSONALITY_ACTION_BIAS.get(personality_name, {}).get(action_name, 0.0)


def get_personality_phrase(personality_name: str, action_name: str) -> str | None:
    """Return a random phrase for a personality/action pair, or None."""
    pool = PERSONALITY_PHRASES.get(personality_name, {}).get(action_name, [])
    return random.choice(pool) if pool else None


def get_personality_description(personality_name: str) -> str:
    return PERSONALITY_DESCRIPTIONS.get(personality_name, "")