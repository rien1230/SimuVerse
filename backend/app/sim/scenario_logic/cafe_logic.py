"""
app/sim/scenario_logic/cafe_logic.py

Cafe scenario logic with:
- explicit constraint ownership
- repeated-ask cooldowns
- structured refusals with ETA
- pressure/challenge escalation
- sub-task progress tracking
- summary before finalise
- deadlock-break fallback
- softer overall stress/tension than office
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, Optional, List, Dict, Any

from app.sim.scenario_logic.base_logic import BaseLogic, get_env_modifiers

if TYPE_CHECKING:
    from app.sim.agent import SimAgent
    from app.sim.model import SimModel


CUISINE_OPTIONS = ["italian", "vegan"]
BUDGET_OPTIONS = ["cheap", "fancy"]
ALL_PREFS = CUISINE_OPTIONS + BUDGET_OPTIONS

CONSTRAINT_ITEMS = [
    "dietary_constraint",
    "budget_constraint",
    "location_constraint",
]

CONSTRAINT_OWNER = {
    "dietary_constraint": "A2",   # Food Expert
    "budget_constraint": "A3",    # Navigator
    "location_constraint": "A4",  # Researcher
}

ROLE_TO_CONSTRAINT = {
    "A2": "dietary_constraint",
    "A3": "budget_constraint",
    "A4": "location_constraint",
}

CONSTRAINT_LABELS = {
    "dietary_constraint": "dietary constraint",
    "budget_constraint": "budget constraint",
    "location_constraint": "location constraint",
}

CONSTRAINT_TEXT = {
    "dietary_constraint": [
        "we need proper vegan options, not just one salad.",
        "we need somewhere with proper vegan options.",
        "someone needs proper vegan food, so that matters.",
    ],
    "budget_constraint": [
        "we should keep it under about £15 per person.",
        "we need to keep it affordable, around £15 each at most.",
        "let's keep it cheap, nothing pricey.",
    ],
    "location_constraint": [
        "somewhere close would be better.",
        "distance matters, so it should be easy to get to.",
        "somewhere nearby sounds best, maybe just a short walk away.",
    ],
}

STRUCTURED_REFUSALS = {
    "dietary_constraint": [
        "I'm not ready to lock that in yet — I want to hear the other constraints first.",
        "Give me a sec — I want to hear the money and how far people want to go first.",
    ],
    "budget_constraint": [
        "Let me hear what kind of place we're after first, then I can give a real budget.",
        "Not yet — I need to know what kind of place we're after first.",
    ],
    "location_constraint": [
        "Give me a second — I need to see whether food or budget is driving the choice.",
        "Holding that for a moment — location depends on what kind of place we're actually going for.",
    ],
}

PRESSURE_TEXTS = {
    "dietary_constraint": [
        "Food Expert, what are the dietary constraints? I need a concrete answer now.",
        "Food Expert, this is the blocker right now — give me the dietary constraint clearly.",
    ],
    "budget_constraint": [
        "Navigator, give me the budget constraint. I need a concrete answer now.",
        "Navigator, this is the blocker right now — give me the budget clearly.",
    ],
    "location_constraint": [
        "Researcher, I still need the location constraint. What is it?",
        "Researcher, location constraint — give me something concrete.",
    ],
}

ASK_TEXTS = {
    "dietary_constraint": [
        "Before we decide anything else — what are the actual dietary requirements here?",
        "Do we need to account for a dietary constraint before we lock anything in?",
        "Food Expert, are there any must-have dietary requirements?",
        "What dietary restrictions are we working around? I need that first.",
        "Are there dietary needs we haven't locked down yet?",
    ],
    "budget_constraint": [
        "What budget are we actually working with here?",
        "Before we go further — what's the realistic spend per person?",
        "What's our ceiling on cost? I need that before we narrow this down.",
        "Give me a number — what are we targeting budget-wise?",
        "Navigator, what's the upper limit on spend?",
    ],
    "location_constraint": [
        "Do we need something nearby, or is distance not the main issue?",
        "What's the actual location constraint here — does it need to be close?",
        "How far is too far? I need to know before we commit to anything.",
        "Researcher, are there location restrictions I should factor in?",
        "Is proximity a real constraint, or are we flexible on distance?",
    ],
}

# Follow-up asks — used when the organiser has already asked about this
# constraint once, or when a related preference (e.g. vegan) has already
# surfaced in conversation. Sharper, more specific than a cold re-ask so
# cafe doesn't loop "are there dietary needs?" with the same wording.
FOLLOWUP_ASK_TEXTS = {
    "dietary_constraint": [
        "Food Expert — do we actually have enough vegan options, or is it more of a preference?",
        "Is the dietary thing a hard must-have, or just something we'd prefer?",
        "Food Expert, vegan came up — is that a requirement or just a preference?",
        "Can you be specific on the dietary side — is it strict vegan, vegetarian, or flexible?",
    ],
    "budget_constraint": [
        "Navigator — we've floated cheap, but what's the actual ceiling in pounds?",
        "Is the budget point a firm cap, or more of a guideline?",
        "Navigator, can you give me a concrete number rather than 'affordable'?",
    ],
    "location_constraint": [
        "Researcher — when you say nearby, are we talking walking distance or a short tube ride?",
        "Is the distance thing a hard limit, or can we stretch it for the right place?",
        "Researcher, can you pin down what 'close' actually means here?",
    ],
}

SUGGEST_POOLS = {
    "Leader": {
        "vegan": [
            "We need vegan-friendly options covered.",
            "Let's make sure vegan options are covered.",
        ],
        "cheap": [
            "Let's keep it affordable.",
            "Keep it cheap. No need to overspend on lunch.",
        ],
        "fancy": [
            "If we're going out, a nicer place is fine if it's worth it.",
            "Somewhere decent could work if everyone is up for it.",
        ],
        "italian": [
            "Italian works for most people.",
            "Italian is the easy call.",
        ],
    },
    "Skeptical": {
        "vegan": [
            "Is vegan actually necessary here? I'm not fully convinced.",
            "Are we sure vegan needs to drive the whole choice?",
        ],
        "cheap": [
            "Cheap can be rough. Let's be careful.",
            "Cheap is fine, but I don't want somewhere bad.",
        ],
        "fancy": [
            "Fancy only works if it's actually worth the money.",
            "I don't want to pay extra for no reason.",
        ],
        "italian": [
            "Italian is safe, but I don't want us defaulting without thinking.",
            "Italian is fine, I just want to know it really fits.",
        ],
    },
    "Overthinker": {
        "vegan": [
            "Vegan could work, but I want to know it works for everyone.",
            "Vegan could work, but I want to know it covers everyone.",
        ],
        "cheap": [
            "We need to watch for hidden costs. Cheap isn't always cheap.",
            "I keep worrying about value. Cheap doesn't always mean good.",
        ],
        "fancy": [
            "I get the nicer-place idea, but I keep coming back to cost and distance.",
            "Somewhere nice sounds good, but I'm not sure it's the right call here.",
        ],
        "italian": [
            "Italian could work, but I want to know it covers everything.",
            "Italian has range, but I want us to think it through first.",
        ],
    },
    "Creative": {
        "vegan": [
            "A good vegan place could be fun.",
            "I'd be up for a vegan spot if it's good.",
            "We don't go vegan often. Could be nice.",
            "A vegan menu could work really well here.",
        ],
        "cheap": [
            "Cheap doesn't have to be boring.",
            "We can do cheap and still pick somewhere good.",
            "Budget doesn't have to mean bland.",
            "Some of the best places are cheap.",
        ],
        "fancy": [
            "I'd like somewhere with a bit of character.",
            "Let's pick somewhere that feels nice, not just random.",
            "I'd rather pick somewhere that feels like an actual choice.",
            "If we're going out, let's pick somewhere worth it.",
        ],
        "italian": [
            "Italian gives us a lot to work with.",
            "Italian covers most tastes.",
            "Italian is a safe bet, but that's not a bad thing.",
            "Italian gives everyone something.",
        ],
    },
    "Easygoing": {
        "vegan": [
            "I'm happy with vegan if it works for everyone.",
            "Vegan sounds fine to me.",
            "Yeah, vegan works for me.",
            "Vegan's good. Doesn't bother me.",
        ],
        "cheap": [
            "Cheap works for me as long as it's still decent.",
            "Something affordable is fine by me.",
            "I'm not fussed on price as long as the food's alright.",
            "Affordable sounds good to me.",
        ],
        "fancy": [
            "I don't mind something nicer if everyone's up for it.",
            "Somewhere a bit nicer sounds good, but I'm flexible.",
        ],
        "italian": [
            "Italian sounds good to me.",
            "Italian's always a safe bet.",
        ],
    },
    "Decisive": {
        "vegan": [
            "Vegan-friendly. That's what we need.",
            "Vegan it is. Done.",
        ],
        "cheap": [
            "Keep it cheap.",
            "Budget is budget. Keep it affordable.",
        ],
        "fancy": [
            "If we're going out, pick somewhere decent.",
            "Somewhere good. Not cheap, not flashy.",
        ],
        "italian": [
            "Italian is the straight call.",
            "Italian. It works. Let's go.",
        ],
    },
}

_SUGGEST_FALLBACK = {
    "italian": [
        "Italian makes the most sense to me.",
        "If we're being practical, Italian covers most tastes.",
    ],
    "vegan": [
        "Vegan options matter — let's make sure they're covered.",
        "I'd push for somewhere vegan-friendly.",
    ],
    "cheap": [
        "Let's keep it affordable.",
        "Something reasonable price-wise — nothing fancy.",
    ],
    "fancy": [
        "I'd prefer somewhere with a bit of atmosphere.",
        "Somewhere with actual ambiance would be better.",
    ],
}

# Early/mid filler — safe at any progress level (no "almost done" implications).
EARLY_CHAT_PHRASES = [
    "Still weighing it up.",
    "Just thinking it through.",
    "Trying to figure out what works for everyone.",
    "Okay — let's keep it moving.",
    "Let's hear what people want.",
    "Let's hear what everyone needs.",
]

# Late-stage filler — only used once the group is ≥75% of the way there
# (most constraints on the table). These imply the end is in sight, so they
# sound absurd at 0/4 or 1/4 progress.
LATE_PROGRESS_PHRASES = [
    "Getting closer.",
    "We're almost there.",
    "One more piece and we're set.",
    "Nearly done — just need this last bit.",
    "Feels like we've almost got it.",
    "Good progress — one thing left.",
    "Almost got everything on the table.",
    "That helps — we're close now.",
]

# Kept as a legacy alias; callers should prefer the bucketed lists above.
PROGRESS_PHRASES = LATE_PROGRESS_PHRASES

SOFTEN_TEXTS = {
    ("cheap", "fancy"): [
        "I get wanting somewhere nicer — I just don't want it to get expensive.",
        "I'm fine with somewhere nice, I just don't want it getting expensive.",
    ],
    ("fancy", "cheap"): [
        "Cheap is fine in theory, I just don't want somewhere that feels dead.",
        "I get the budget point — I just still want it to feel worth going out.",
    ],
    ("italian", "vegan"): [
        "Italian could work for me if there are proper vegan options.",
        "I'm okay with Italian, but vegan-friendly matters.",
    ],
    ("vegan", "italian"): [
        "Vegan matters more to me, but Italian works if the place is flexible.",
        "Italian is okay as long as the vegan options are actually decent.",
    ],
}

CHALLENGE_TEXTS = {
    ("fancy", "cheap"): [
        "Fancy sounds nice, but I don't want to spend that much.",
        "I'd rather keep it cheap than pay for atmosphere.",
        "If it's just lunch, I don't see the point in going fancy.",
    ],
    ("cheap", "fancy"): [
        "Cheap is fine, but I don't want somewhere dead.",
        "I get the budget point, but I still want somewhere decent.",
        "Affordable is fine — I just don't want it to feel basic.",
    ],
    ("italian", "vegan"): [
        "That only works for me if there are vegan options.",
        "I'm okay with Italian, but it needs to be vegan-friendly.",
    ],
    ("vegan", "italian"): [
        "Italian's fine too, but vegan options matter more to me.",
        "As long as the place has vegan options, Italian works.",
    ],
}

COMPROMISE_TEXTS = [
    "Fine. I can drop the fancy idea if the place is still nice enough.",
    "I'm okay with vegan if we keep it affordable.",
    "Cheap works for me as long as the food is actually good.",
    "Affordable and vegan-friendly sounds like a fair call.",
    "We don't need fancy if the place has proper vegan options.",
    "Fair enough — I can work with that.",
    "Yeah, I can go with that.",
    "Alright, I can go with that.",
    "That feels like a decent middle ground.",
    "Good enough. Let's pick it.",
]

SUMMARY_TEXTS = [
    "Alright, sounds like {direction} then.",
    "Okay, {direction} then.",
    "So {direction} sounds like the best bet.",
    "Right, so we're leaning toward {direction}.",
    "Sounds like {direction} covers it. Shall we go with that?",
    "Honestly, {direction} sounds best.",
    "Feels like {direction} sounds best.",
    "If we want cheap and easy, {direction} is probably it.",
    "Honestly, {direction} feels like the best shout.",
    "{direction}. That feels like the one.",
]

FINALISE_TEXTS = [
    "Alright, let's go with {decision}.",
    "Okay, let's do {decision}.",
    "Done. Let's do {decision}.",
    "{decision} feels right.",
    "{decision} it is.",
    "That sounds like {decision}.",
    "{decision} feels like the best fit.",
    "Let's do {decision}.",
    "{decision} sounds like the best shout.",
    "We're doing {decision}.",
]


def _lbl(item: str) -> str:
    return CONSTRAINT_LABELS.get(item, item.replace("_", " ").title())


def _suggest(pref: str, personality: str = "neutral") -> str:
    ptype_pool = SUGGEST_POOLS.get(personality, {})
    opts = ptype_pool.get(pref) or _SUGGEST_FALLBACK.get(pref) or [f"I suggest {pref}."]
    return random.choice(opts)


def _challenge(my_pref: str, their_pref: str) -> str:
    pool = CHALLENGE_TEXTS.get((my_pref, their_pref))
    if pool:
        return random.choice(pool)
    return f"I'm not sure {their_pref} is the right call — have we considered {my_pref}?"


def _soften(my_pref: str, their_pref: str) -> str:
    pool = SOFTEN_TEXTS.get((my_pref, their_pref))
    if pool:
        return random.choice(pool)
    return f"I can work with {their_pref}, but {my_pref} still matters to me."


class CafeRestaurantLogic(BaseLogic):
    scenario_type = "cafe"

    ROLES = {
        "A1": "Organiser",
        "A2": "Food Expert",
        "A3": "Navigator",
        "A4": "Researcher",
    }

    def role(self, agent_id: str) -> str:
        return self.ROLES.get(agent_id, agent_id)

    def _apply_personality_stress(self, agent: "SimAgent", model: "SimModel") -> None:
        """
        Cafe should stay calmer than office.
        This is a soft background drift, not a hard escalation.
        """
        p = getattr(agent, "personality_type", "Easygoing")

        base = {
            "Easygoing": 0.0,
            "Leader": 0.003,
            "Decisive": 0.004,
            "Creative": 0.007,
            "Skeptical": 0.013,
            "Overthinker": 0.016,
        }.get(p, 0.005)

        tick = getattr(model, "tick", 0)
        if tick >= 6 and p in ("Skeptical", "Overthinker"):
            base += 0.003
        if tick >= 10:
            base += 0.003
        if tick >= 14:
            base += 0.003

        # Once the constraints are known, personalities should diverge in how
        # they carry the final decision: pressure-oriented roles push to close,
        # skeptical/overthinking ones still run hotter.
        if self._all_constraints_revealed(model) and not getattr(model, "_cafe_finalised", False):
            base += {
                "Leader": 0.005,
                "Decisive": 0.006,
                "Creative": 0.004,
                "Easygoing": 0.002,
                "Skeptical": 0.008,
                "Overthinker": 0.010,
            }.get(p, 0.003)

        # Keep cafe notably softer than office
        agent.stress = min(0.72, agent.stress + base)

    def _reduce_stress_after_progress(self, model: "SimModel", amount: float = 0.08) -> None:
        for a in getattr(model, "agents", []):
            recovery = {
                "Easygoing": 1.10,
                "Creative": 0.95,
                "Leader": 0.85,
                "Decisive": 0.78,
                "Skeptical": 0.62,
                "Overthinker": 0.55,
            }.get(getattr(a, "personality_type", "Easygoing"), 0.80)
            a.stress = max(0.0, a.stress - (amount * recovery))

    def _clamp_cafe_state(self, model: "SimModel") -> None:
        """
        Safety clamp so cafe never runs hotter than intended.
        """
        for a in getattr(model, "agents", []):
            a.stress = min(a.stress, 0.68)

    def scenario_modifiers(self, model: "SimModel") -> Dict[str, float]:
        # Cafe: casual social setting — warm trust, low tension, high cohesion
        return {
            "base_trust_delta": 0.10,
            "arousal_rate": 0.8,
            "refusal_weight": 0.8,
            "cooperation_weight": 1.2,
            "initial_tension_delta": -0.06,
            "initial_cohesion_delta": 0.10,
            "initial_stress_delta": -0.04,
        }

    def final_success_relief(self, model: "SimModel") -> tuple[float, float, float]:
        # Preserve more of the preset-specific end-state so the benchmark can
        # show meaningful differences instead of flattening every successful run.
        return (0.01, 0.05, 0.04)

    def _add_conflict(self, model: "SimModel", amount: int = 1) -> None:
        model._cafe_metrics["conflicts"] += amount
        model._cafe_conflict_count += amount

    # ──────────────────────────────────────────────────────────────────────────
    # state
    # ──────────────────────────────────────────────────────────────────────────

    def _init_state(self, model: "SimModel") -> None:
        if not hasattr(model, "_cafe_decision_state"):
            model._cafe_decision_state = {
                "cuisine": None,
                "budget": None,
            }

        if not hasattr(model, "_cafe_pref_counts"):
            model._cafe_pref_counts = {p: 0 for p in ALL_PREFS}

        if not hasattr(model, "_cafe_pref_supporters"):
            model._cafe_pref_supporters = {p: set() for p in ALL_PREFS}

        if not hasattr(model, "_cafe_summary_done"):
            model._cafe_summary_done = False

        if not hasattr(model, "_cafe_summary_tick"):
            model._cafe_summary_tick = None

        if not hasattr(model, "_cafe_finalised"):
            model._cafe_finalised = False

        if not hasattr(model, "_cafe_metrics"):
            model._cafe_metrics = {}

        for _k in ("conflicts", "agreements", "compromises", "probes", "pressure", "refusals"):
            model._cafe_metrics.setdefault(_k, 0)

        if not hasattr(model, "_cafe_conflict_count"):
            model._cafe_conflict_count = 0

        if not hasattr(model, "_cafe_participation"):
            model._cafe_participation = set()

        if not hasattr(model, "_cafe_agent_commitment"):
            model._cafe_agent_commitment = {
                a.public_id: random.uniform(0.45, 0.85)
                for a in getattr(model, "agents", [])
            }

        if not hasattr(model, "_cafe_agent_last_pref"):
            model._cafe_agent_last_pref = {}

        if not hasattr(model, "_cafe_last_ask_tick"):
            model._cafe_last_ask_tick = {}

        if not hasattr(model, "_cafe_last_ask_text"):
            model._cafe_last_ask_text = {}

        if not hasattr(model, "_cafe_ask_count"):
            model._cafe_ask_count = {}

        if not hasattr(model, "_cafe_revealed_constraints"):
            model._cafe_revealed_constraints = {
                item: False for item in CONSTRAINT_ITEMS
            }

        if not hasattr(model, "_cafe_refusal_until"):
            model._cafe_refusal_until = {}

        if not hasattr(model, "_cafe_owner_last_share_tick"):
            model._cafe_owner_last_share_tick = {}

        if not hasattr(model, "_cafe_last_pressure_tick"):
            model._cafe_last_pressure_tick = {}

        self._ensure_progress_tasks(model)

    def _ensure_progress_tasks(self, model: "SimModel") -> None:
        desired = {
            "dietary_constraint": False,
            "budget_constraint": False,
            "location_constraint": False,
            "decision": False,
        }

        if set(getattr(model.scenario, "tasks", {}).keys()) != set(desired.keys()):
            model.scenario.tasks = desired.copy()
        else:
            for key in desired:
                model.scenario.tasks.setdefault(key, False)

    def _state(self, model: "SimModel") -> Dict[str, Optional[str]]:
        self._init_state(model)
        return model._cafe_decision_state

    def _counts(self, model: "SimModel") -> Dict[str, int]:
        self._init_state(model)
        return model._cafe_pref_counts

    def _supporters(self, model: "SimModel") -> Dict[str, set]:
        self._init_state(model)
        return model._cafe_pref_supporters

    def _commitment(self, model: "SimModel", agent_id: str) -> float:
        self._init_state(model)
        return model._cafe_agent_commitment.get(agent_id, 0.6)

    def _mark_participation(self, model: "SimModel", agent_id: str) -> None:
        self._init_state(model)
        model._cafe_participation.add(agent_id)

    def _participation_count(self, model: "SimModel") -> int:
        self._init_state(model)
        return len(model._cafe_participation)

    def _dimension_of(self, pref: str) -> Optional[str]:
        if pref in CUISINE_OPTIONS:
            return "cuisine"
        if pref in BUDGET_OPTIONS:
            return "budget"
        return None

    def _winning_pref(self, model: "SimModel", options: List[str]) -> str:
        supporters = self._supporters(model)
        counts = self._counts(model)
        return max(options, key=lambda p: (len(supporters[p]), counts[p]))

    def _refresh_candidates(self, model: "SimModel") -> None:
        state = self._state(model)
        supporters = self._supporters(model)
        counts = self._counts(model)
        tick_now = getattr(model, "tick", 0)

        cuisine_scores = {p: (len(supporters[p]), counts[p]) for p in CUISINE_OPTIONS}
        budget_scores = {p: (len(supporters[p]), counts[p]) for p in BUDGET_OPTIONS}

        best_cuisine = max(cuisine_scores, key=cuisine_scores.get)
        best_budget = max(budget_scores, key=budget_scores.get)

        cuisine_threshold = (1 if tick_now >= 10 else 2, 2 if tick_now >= 10 else 3)
        budget_threshold = (1 if tick_now >= 10 else 2, 2 if tick_now >= 10 else 3)

        if len(supporters[best_cuisine]) >= cuisine_threshold[0] or counts[best_cuisine] >= cuisine_threshold[1]:
            state["cuisine"] = best_cuisine

        if len(supporters[best_budget]) >= budget_threshold[0] or counts[best_budget] >= budget_threshold[1]:
            state["budget"] = best_budget

        # Hard consistency: explicit cheap budget constraint should dominate fancy
        if model._cafe_revealed_constraints.get("budget_constraint", False):
            state["budget"] = "cheap"

        # Dietary constraint text is explicitly vegan-related, so avoid ending on italian
        # unless vegan support is basically absent.
        if model._cafe_revealed_constraints.get("dietary_constraint", False):
            vegan_support = len(supporters["vegan"]) + counts["vegan"]
            italian_support = len(supporters["italian"]) + counts["italian"]
            if vegan_support >= italian_support:
                state["cuisine"] = "vegan"

    def _register_pref_expression(self, model: "SimModel", agent_id: str, pref: str) -> None:
        if pref not in ALL_PREFS:
            return
        counts = self._counts(model)
        supporters = self._supporters(model)
        counts[pref] += 1
        supporters[pref].add(agent_id)
        model._cafe_agent_last_pref[agent_id] = pref
        self._mark_participation(model, agent_id)
        self._refresh_candidates(model)

    def _all_constraints_revealed(self, model: "SimModel") -> bool:
        self._init_state(model)
        return all(model._cafe_revealed_constraints.values())

    def _mark_constraint_revealed(self, model: "SimModel", item: str) -> None:
        self._init_state(model)
        if item in model._cafe_revealed_constraints:
            model._cafe_revealed_constraints[item] = True
        if item in model.scenario.tasks and not model.scenario.tasks[item]:
            model.scenario.complete_task(item)
        self._reduce_stress_after_progress(model, amount=0.09)
        self._clamp_cafe_state(model)

    def _can_ask_again(
        self,
        model: "SimModel",
        asker: str,
        target: str,
        item: str,
        personality: str = "Easygoing",
    ) -> bool:
        self._init_state(model)
        last_tick = model._cafe_last_ask_tick.get((asker, target, item), -999)
        cooldown = {
            "Leader": 2,
            "Decisive": 2,
            "Easygoing": 3,
            "Creative": 3,
            "Skeptical": 3,
            "Overthinker": 4,
        }.get(personality, 3)
        if getattr(model, "tick", 0) - last_tick < cooldown:
            return False
        tension = float(getattr(model, "group_tension", 0.0) or 0.0)
        stall = int(getattr(model, "progress_stall_ticks", 0) or 0)
        quiet_item = getattr(model, "_intervention_quiet_item", None)
        quiet_until = getattr(model, "_intervention_quiet_until", -1)
        if (
            quiet_item == item
            and getattr(model, "tick", 0) <= quiet_until
            and tension < 0.80
            and stall < 4
        ):
            return False
        pending_events = getattr(model, "_pending_events", []) or []
        recent_resolution = any(
            e.get("item") == item and e.get("type") in {"share_info", "agree"}
            for e in [*(pending_events[-6:]), *((getattr(model, "prev_events", []) or [])[-6:])]
        )
        if recent_resolution and tension < 0.80 and stall < 4:
            return False
        # Don't re-ask if the same ask appears in recent event history (wider window)
        recent = getattr(model, "prev_events", [])[-6:]
        already_asked_recently = any(
            e.get("type") == "ask_info"
            and e.get("actor") == asker
            and e.get("item") == item
            for e in recent
        )
        return not already_asked_recently

    def _pick_ask_text(self, model: "SimModel", asker: str, item: str) -> str:
        """Pick an ask text, avoiding the last used one for this asker+item pair.
        After the first ask — or after a related preference has been floated in
        conversation — switch to the sharper follow-up pool so cafe doesn't loop
        the same 'are there dietary needs?' wording."""
        self._init_state(model)
        owner_id = CONSTRAINT_OWNER.get(item)
        prior_asks = model._cafe_ask_count.get((asker, owner_id, item), 0) if owner_id else 0
        # Has anyone floated a related preference (e.g. "vegan") already?
        pref_floated = False
        related_prefs = {
            "dietary_constraint": ("vegan",),
            "budget_constraint": ("cheap",),
            "location_constraint": ("nearby", "close"),
        }.get(item, ())
        if related_prefs:
            for ev in (getattr(model, "prev_events", []) or [])[-12:]:
                text = str(ev.get("text", "")).lower()
                if any(p in text for p in related_prefs):
                    pref_floated = True
                    break
        use_followup = (prior_asks >= 1) or pref_floated
        if use_followup and item in FOLLOWUP_ASK_TEXTS:
            pool = FOLLOWUP_ASK_TEXTS[item]
        else:
            pool = ASK_TEXTS.get(item, [f"What about {item}?"])
        last = model._cafe_last_ask_text.get((asker, item))
        choices = [t for t in pool if t != last] or pool
        chosen = random.choice(choices)
        model._cafe_last_ask_text[(asker, item)] = chosen
        return chosen

    def _note_ask(self, model: "SimModel", asker: str, target: str, item: str) -> None:
        self._init_state(model)
        key = (asker, target, item)
        model._cafe_last_ask_tick[key] = getattr(model, "tick", 0)
        model._cafe_ask_count[key] = model._cafe_ask_count.get(key, 0) + 1

    def _ask_count(self, model: "SimModel", asker: str, target: str, item: str) -> int:
        self._init_state(model)
        return model._cafe_ask_count.get((asker, target, item), 0)

    def _organiser_ask_total(self, model: "SimModel", item: str) -> int:
        self._init_state(model)
        owner_id = CONSTRAINT_OWNER.get(item)
        if not owner_id:
            return 0
        return model._cafe_ask_count.get(("A1", owner_id, item), 0)

    def _choose_missing_constraint(self, model: "SimModel") -> Optional[str]:
        self._init_state(model)
        focus_item = getattr(model, "_intervention_focus_item", None)
        focus_until = getattr(model, "_intervention_focus_until", -1)
        if (
            focus_item in CONSTRAINT_ITEMS
            and not model._cafe_revealed_constraints.get(focus_item, False)
            and getattr(model, "tick", 0) <= focus_until
        ):
            return focus_item
        for item in CONSTRAINT_ITEMS:
            if not model._cafe_revealed_constraints.get(item, False):
                return item
        return None

    def _owner_ready_to_share(self, agent: "SimAgent", item: str) -> bool:
        model = agent.model
        self._init_state(model)

        tick_now = getattr(model, "tick", 0)
        refusal_until = model._cafe_refusal_until.get((agent.public_id, item), -1)
        if tick_now < refusal_until:
            return False

        owner = CONSTRAINT_OWNER.get(item)
        if owner != agent.public_id:
            return False

        total_asks = 0
        for (asker, target, asked_item), count in model._cafe_ask_count.items():
            if target == agent.public_id and asked_item == item:
                total_asks += count

        personality = getattr(agent, "personality_type", "Easygoing")
        base = {
            "Easygoing": 0.90,
            "Decisive": 0.84,
            "Leader": 0.80,
            "Creative": 0.72,
            "Skeptical": 0.42,
            "Overthinker": 0.32,
        }.get(personality, 0.68)

        if total_asks >= 2:
            base += 0.20
        if total_asks >= 4:
            base += 0.20
        if total_asks >= 1 and item == "budget_constraint" and personality == "Skeptical":
            base += 0.12
        if total_asks >= 1 and item == "location_constraint" and personality == "Overthinker":
            base += 0.08
        if agent._intervention_strategy_active("cooperative") and total_asks >= 1:
            base += 0.28
        if tick_now >= 8:
            base += 0.15
        if tick_now >= 12:
            base += 0.25
        # After tick 14, reluctant personalities should still hand it over —
        # otherwise the late forced-share in post_tick is the only escape hatch.
        if tick_now >= 14 and personality in ("Skeptical", "Overthinker"):
            base += 0.30

        return random.random() < min(base, 0.98)

    def _maybe_refuse(self, agent: "SimAgent", asker_id: str, item: str) -> Optional[Dict[str, Any]]:
        model = agent.model
        self._init_state(model)

        if CONSTRAINT_OWNER.get(item) != agent.public_id:
            return None
        if model._cafe_revealed_constraints.get(item, False):
            return None

        tick_now = getattr(model, "tick", 0)
        refusal_until = model._cafe_refusal_until.get((agent.public_id, item), -1)
        if tick_now < refusal_until:
            return None

        personality = getattr(agent, "personality_type", "Easygoing")
        ask_volume = sum(
            count
            for (asker, target, asked_item), count in model._cafe_ask_count.items()
            if target == agent.public_id and asked_item == item
        )

        refuse_prob = {
            "Easygoing": 0.04,
            "Decisive": 0.04,
            "Leader": 0.08,
            "Creative": 0.12,
            "Skeptical": 0.28,
            "Overthinker": 0.38,
        }.get(personality, 0.14)

        if agent._intervention_strategy_active("cooperative"):
            refuse_prob *= 0.10

        if personality in ("Skeptical", "Overthinker"):
            if ask_volume >= 2:
                refuse_prob -= 0.05
            if tick_now >= 8:
                refuse_prob -= 0.06
            if tick_now >= 14:
                refuse_prob = 0.0
        else:
            if ask_volume >= 2:
                refuse_prob -= 0.08
            if tick_now >= 8:
                refuse_prob -= 0.10
            if tick_now >= 12:
                refuse_prob = 0.0

        if random.random() < max(0.0, refuse_prob):
            model._cafe_metrics["refusals"] += 1
            self._add_conflict(model, 1)
            model._cafe_refusal_until[(agent.public_id, item)] = tick_now + 2
            agent.stress = min(0.60, agent.stress + 0.04)
            return {
                "type": "refuse",
                "actor": agent.public_id,
                "target": asker_id,
                "text": random.choice(STRUCTURED_REFUSALS[item]),
                "item": item,
                "reason": "structured_refusal",
            }

        return None

    def _share_constraint_event(
        self,
        agent: "SimAgent",
        target_id: str,
        item: str,
        forced: bool = False,
    ) -> Optional[Dict[str, Any]]:
        model = agent.model
        tick_now = getattr(model, "tick", 0)

        # Pacing gate: only one new constraint may be revealed per tick.
        # This applies to forced reveals too — the cafe should feel like a
        # group reaching agreement, not a checklist being speedrun.
        if getattr(model, "_cafe_last_constraint_tick", -1) == tick_now:
            return None  # another constraint already shared this tick

        model._cafe_last_constraint_tick = tick_now
        self._mark_constraint_revealed(model, item)
        model._cafe_owner_last_share_tick[(agent.public_id, item)] = tick_now

        constraint_fact = random.choice(CONSTRAINT_TEXT[item])
        share_intros = {
            "dietary_constraint": [
                f"Right, {constraint_fact}",
                f"The thing is, {constraint_fact}",
                f"I should say, {constraint_fact}",
            ],
            "budget_constraint": [
                f"Right, {constraint_fact}",
                f"Budget-wise, {constraint_fact}",
                f"Look, {constraint_fact}",
            ],
            "location_constraint": [
                f"Right, {constraint_fact}",
                f"Okay, {constraint_fact}",
                f"Actually, {constraint_fact}",
            ],
        }
        intros = share_intros.get(item, [f"Okay, {constraint_fact}"])
        return {
            "type": "share_info",
            "actor": agent.public_id,
            "target": target_id,
            "text": random.choice(intros),
            "item": item,
            "reason": "constraint_share_forced" if forced else "constraint_share",
            "partial": False,
            "can_complete": True,
        }

    def _enough_for_summary(self, model: "SimModel") -> bool:
        state = self._state(model)
        if not self._all_constraints_revealed(model):
            return False

        organiser = next((a for a in getattr(model, "agents", []) if a.public_id == "A1"), None)
        org_ptype = getattr(organiser, "personality_type", "Easygoing") if organiser else "Easygoing"
        tick_now = getattr(model, "tick", 0)

        # Minimum tick floor: even if all constraints land early, the conversation
        # needs breathing room before wrapping up. A 3-tick run feels pre-solved.
        if tick_now < 4:
            return False

        # Organiser counts as participant (they drove the discussion by asking).
        participation_total = self._participation_count(model)
        if organiser and "A1" not in model._cafe_participation:
            participation_total += 1

        # Relax participation requirements as ticks progress — otherwise high-refusal
        # mixes (Skeptical/Overthinker) never satisfy a strict 3-person minimum
        # before the episode caps.
        if tick_now >= 12:
            min_participants = 2
        elif org_ptype in ("Decisive", "Leader"):
            min_participants = 2
        else:
            min_participants = 3

        if participation_total < min_participants:
            return False
        return state["cuisine"] is not None and state["budget"] is not None

    def _ready_to_finalise(self, model: "SimModel") -> bool:
        if not self._all_constraints_revealed(model):
            return False
        if not getattr(model, "_cafe_summary_done", False):
            return False
        summary_tick = getattr(model, "_cafe_summary_tick", None)
        if summary_tick is not None:
            current_tick = getattr(model, "tick", 0)
            if current_tick - summary_tick < 1:
                return False

        resolved = self._resolved_final_state(model)
        if not resolved["cuisine"] or not resolved["budget"]:
            return False

        return True

    def _resolved_final_state(self, model: "SimModel") -> Dict[str, str]:
        self._refresh_candidates(model)
        state = self._state(model)

        cuisine = state.get("cuisine") or self._winning_pref(model, CUISINE_OPTIONS)
        budget = state.get("budget") or self._winning_pref(model, BUDGET_OPTIONS)

        if model._cafe_revealed_constraints.get("budget_constraint", False):
            budget = "cheap"
        if model._cafe_revealed_constraints.get("dietary_constraint", False):
            cuisine = "vegan"

        state["cuisine"] = cuisine
        state["budget"] = budget
        return {"cuisine": cuisine, "budget": budget}

    def _budget_display_label(self, budget: str) -> str:
        return {
            "cheap": "affordable",
            "fancy": "upscale",
        }.get(budget, budget)

    def _summary_direction(self, model: "SimModel") -> str:
        resolved = self._resolved_final_state(model)
        budget_label = resolved["budget"]
        cuisine_label = resolved["cuisine"]
        location_revealed = model._cafe_revealed_constraints.get("location_constraint", False)

        if cuisine_label == "vegan":
            cuisine_phrase = "with good vegan food"
        elif cuisine_label == "italian":
            cuisine_phrase = "with good Italian food"
        elif cuisine_label:
            cuisine_phrase = f"with good {cuisine_label} food"
        else:
            cuisine_phrase = ""

        if budget_label == "cheap":
            if cuisine_phrase and location_revealed:
                return f"somewhere nearby {cuisine_phrase} that won't cost much"
            if cuisine_phrase:
                return f"somewhere {cuisine_phrase} that won't cost much"
            if location_revealed:
                return "somewhere nearby that won't cost much"
            return "somewhere that won't cost much"

        if budget_label == "fancy":
            if cuisine_phrase and location_revealed:
                return f"somewhere nearby {cuisine_phrase} that's a bit nicer"
            if cuisine_phrase:
                return f"somewhere {cuisine_phrase} that's a bit nicer"
            if location_revealed:
                return "somewhere nearby that's a bit nicer"
            return "somewhere a bit nicer"

        if cuisine_phrase and location_revealed:
            return f"somewhere nearby {cuisine_phrase}"
        if cuisine_phrase:
            return f"somewhere {cuisine_phrase}"
        if location_revealed:
            return "somewhere nearby"
        return "somewhere decent"

    def _finalise_text(self, agent: "SimAgent", decision: str) -> str:
        finalise_pools = {
            "Leader": [
                f"Alright, let's do {decision}.",
                f"Okay, let's go with {decision}.",
            ],
            "Decisive": [
                f"{decision.capitalize()}. That's it.",
                f"Let's do {decision}.",
            ],
            "Easygoing": [
                f"Sounds good — let's do {decision}.",
                f"Happy with {decision}. Let's go.",
            ],
            "Creative": [
                f"Okay, {decision} — I like that.",
                f"Good call. {decision.capitalize()} feels right.",
            ],
            "Skeptical": [
                f"Fine — let's do {decision}.",
                f"Alright, {decision}. I can live with that.",
            ],
            "Overthinker": [
                f"Okay — let's go with {decision}.",
                f"I've gone back and forth, but {decision} feels right.",
                f"I keep circling back to {decision}. Let's do that.",
            ],
        }
        ptype = getattr(agent, "personality_type", "Easygoing")
        text = random.choice(finalise_pools.get(ptype, FINALISE_TEXTS))
        if "{decision}" in text:
            return text.format(decision=decision)
        return text

    # ────────────────────────────────────────────────────────────────────
    # Metrics — keep cafe conflict non-zero when mild disagreement surfaces.
    # ────────────────────────────────────────────────────────────────────
    _CAFE_CONFLICT_PHRASES = (
        "not ready",
        "low quality",
        "not convinced",
        "i keep thinking",
        "i'm not sure",
        "not sure",
        "be careful",
        "not my first choice",
        "not really a fan",
        "i don't love",
        "i don't want",
        "i don't think",
        "second-guess",
        "not yet",
        "hold on",
        "wait —",
        "i'm hesitant",
        "are we sure",
        "is that really",
        "doesn't quite",
        "doesn't feel right",
        "i'd rather",
        "not keen",
        "bit concerned",
        "i worry",
        "i'm worried",
        "push back",
        "pushing back",
        "not how i'd",
        "usually means",
        "keep going back",
        "going back and forth",
        "red flag",
        # Soft-disagreement phrases that slipped past the first pass.
        "not the right call",
        "right call here",
        "i need more",
        "need a little more",
        "more context",
        "i'm not against",
        "not against",
        "however",
        "lock that in",
        "lock it in",
        "not lock",
        "usually low",
        "usually cheap",
    )
    # Soft contrastive markers — only count if the line also carries hedging
    # so we don't flag innocuous uses of "but".
    _CAFE_SOFT_CONTRAST_PHRASES = (
        "sounds good, but",
        "sounds good but",
        "works, but",
        "works but",
        "fine, but",
        "fine but",
        "okay, but",
        "okay but",
        "yeah, but",
        "yeah but",
        ", but i",
        ", but it",
        ", but that",
        ", but we",
    )

    def accumulate_run_metrics(
        self,
        model: "SimModel",
        events: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        emotional = 0.0
        coord_pressure = 0.0
        conflict = 0.0

        for event in events:
            etype = event.get("type", "")
            reason = event.get("reason", "")
            text = str(event.get("text", "")).lower()

            if etype == "refuse":
                conflict += 0.04
                emotional += 0.03
            if etype == "challenge":
                conflict += 0.05
            if text and any(p in text for p in self._CAFE_CONFLICT_PHRASES):
                conflict += 0.03
                emotional += 0.015
            elif text and any(p in text for p in self._CAFE_SOFT_CONTRAST_PHRASES):
                # Softer weight for contrastive "but" clauses so light pushback
                # still registers on the conflict metric.
                conflict += 0.02
                emotional += 0.01
            if reason in ("cafe_summary", "cafe_finalise", "pull_quiet_member_in"):
                coord_pressure += 0.04

        return {
            "emotional": emotional,
            "coord_pressure": coord_pressure,
            "conflict": conflict,
        }

    def post_tick(
        self,
        model: "SimModel",
        events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        self._init_state(model)

        if model.scenario.progress_ratio() >= 1.0:
            return []

        organiser = next((a for a in getattr(model, "agents", []) if a.public_id == "A1"), None)
        if organiser is None:
            return []

        others = [a for a in getattr(model, "agents", []) if a.public_id != organiser.public_id]
        if not others:
            return []

        tick_now = getattr(model, "tick", 0)
        extra_events: List[Dict[str, Any]] = []

        # Per-preset stress drips. Tension cafe should usually have the
        # highest peak stress (clashing personalities create friction), with
        # pressure cafe a close second (external clock, but a calmer group).
        preset = getattr(model, "team_preset", None)
        if preset == "tension_team" and tick_now >= 2:
            for agent in getattr(model, "agents", []):
                current = getattr(agent, "stress", 0.0) or 0.0
                try:
                    agent.stress = min(float(current) + 0.024, 1.0)
                except Exception:
                    pass
        elif preset == "pressure_team" and tick_now >= 3:
            for agent in getattr(model, "agents", []):
                current = getattr(agent, "stress", 0.0) or 0.0
                try:
                    agent.stress = min(float(current) + 0.010, 1.0)
                except Exception:
                    pass

        missing = self._choose_missing_constraint(model)
        if missing and not model._cafe_revealed_constraints.get(missing, False):
            owner_id = CONSTRAINT_OWNER.get(missing)
            owner = next((a for a in getattr(model, "agents", []) if a.public_id == owner_id), None)
            organiser_style = getattr(organiser, "personality_type", "Easygoing")
            force_threshold = {
                "Leader": 2,
                "Decisive": 2,
                "Easygoing": 2,
                "Creative": 2,
                "Skeptical": 2,
                "Overthinker": 3,
            }.get(organiser_style, 2)
            organiser_asks = self._organiser_ask_total(model, missing)

            # Hard forced reveal: once we're past tick 10, don't let any single
            # constraint block the episode — one ask is enough, and beyond tick
            # 12 reveal it unconditionally on the next post_tick.
            if tick_now >= 12:
                force_threshold = 0
            elif tick_now >= 10:
                force_threshold = min(force_threshold, 1)

            if (
                owner
                and organiser_asks >= force_threshold
                and not any(e.get("actor") == owner.public_id for e in events)
            ):
                forced_ev = self._share_constraint_event(
                    owner,
                    organiser.public_id,
                    missing,
                    forced=True,
                )
                if forced_ev:
                    extra_events.append(forced_ev)
                return extra_events

        # Late-tick forced summary: if constraints are revealed but the participation
        # gate is still blocking, shortcut the requirement so the decision can close.
        should_force_summary = (
            self._all_constraints_revealed(model)
            and not model._cafe_summary_done
            and tick_now >= 14
        )

        if (self._enough_for_summary(model) or should_force_summary) and not model._cafe_summary_done:
            model._cafe_summary_done = True
            model._cafe_summary_tick = tick_now
            # Ensure decision state is resolved even if supporter counts were thin
            self._resolved_final_state(model)
            direction = self._summary_direction(model)
            summary_target = random.choice(others)

            cafe_conflicts = getattr(model, "_cafe_conflict_count", 0)
            if cafe_conflicts >= 2:
                summary_opts = [
                    "We've got dietary, budget, and location sorted — though it took some back-and-forth. The best fit is {direction}.",
                    "Right — constraints are all on the table now. It wasn't entirely smooth, but {direction} is the clearest direction.",
                    "Okay — despite some disagreement, {direction} covers what everyone raised.",
                ]
            else:
                summary_opts = SUMMARY_TEXTS

            extra_events.append({
                "type": "say",
                "actor": organiser.public_id,
                "target": summary_target.public_id,
                "text": random.choice(summary_opts).format(direction=direction),
                "reason": "cafe_summary",
            })

        # Minimum-tick gate: cafe scenes shouldn't finalise before tick 7, otherwise
        # the flow feels too quick to read in a demo.
        cafe_min_tick = 7
        if self._ready_to_finalise(model) and not model._cafe_finalised and tick_now >= cafe_min_tick:
            model._cafe_finalised = True
            model.mark_task_complete("decision")
            decision = self.build_final_decision(model)
            closer = max(
                others,
                key=lambda a: self._commitment(model, a.public_id) + a.trust.get(organiser.public_id, 0.5),
            )
            self._reduce_stress_after_progress(model, amount=0.10)
            self._clamp_cafe_state(model)
            extra_events.append({
                "type": "agree",
                "actor": closer.public_id,
                "target": organiser.public_id,
                "text": self._finalise_text(closer, decision),
                "preference": "_finalise_",
                "reason": "cafe_finalise",
            })

        # Safety net: if we're late in the episode and constraints are on the
        # table but the decision still hasn't closed, force the finalise so
        # high-refusal mixes don't run out of ticks.
        if (
            not model._cafe_finalised
            and self._all_constraints_revealed(model)
            and tick_now >= 17
        ):
            model._cafe_summary_done = True
            model._cafe_finalised = True
            self._resolved_final_state(model)
            model.mark_task_complete("decision")
            decision = self.build_final_decision(model)
            closer = max(
                others,
                key=lambda a: self._commitment(model, a.public_id) + a.trust.get(organiser.public_id, 0.5),
            )
            self._reduce_stress_after_progress(model, amount=0.10)
            self._clamp_cafe_state(model)
            extra_events.append({
                "type": "agree",
                "actor": closer.public_id,
                "target": organiser.public_id,
                "text": self._finalise_text(closer, decision),
                "preference": "_finalise_",
                "reason": "cafe_finalise",
            })

        return extra_events

    # ──────────────────────────────────────────────────────────────────────────
    # text api used by agent
    # ──────────────────────────────────────────────────────────────────────────

    def generate_help_text(self, agent, target_id: str, item: str) -> str:
        return random.choice([
            f"Yeah, I've got {_lbl(item)}.",
            f"Leave {_lbl(item)} with me.",
            f"I can take that, {agent._r(target_id)}.",
            "Yeah, easy — I'll do it.",
        ])

    def generate_ignore_text(self, agent, target_id: str) -> str:
        return random.choice([
            f"{agent._r(target_id)}, one sec.",
            "Hang on — still thinking.",
            "Give me a minute on that.",
        ])

    def generate_insult_text(self, agent, target_id: str) -> str:
        return random.choice([
            f"{agent._r(target_id)}, this really doesn't need to be this complicated.",
            "Come on — that's not helping.",
            "We keep going in circles because of this.",
            "You're making a lunch choice harder than it needs to be.",
        ])

    def generate_say_text(self, agent, target_id: str) -> str:
        avg_trust = sum(agent.trust.values()) / max(1, len(agent.trust))
        if agent.stress > 0.60:
            options = [
                f"{agent._r(target_id)}, this is dragging.",
                "We just need to pick something.",
                f"Getting stuck here, {agent._r(target_id)}.",
                "Let's not overthink lunch.",
            ]
        elif agent.stress < 0.25 and avg_trust > 0.55:
            options = [
                f"This is coming together, {agent._r(target_id)}.",
                "Yeah, I like where it's heading.",
                "Feels like we're nearly there.",
                "Whatever we land on is fine with me.",
            ]
        else:
            options = [
                "Should probably pick soon.",
                f"{agent._r(target_id)}, what are we thinking?",
                "Still a couple of things to settle.",
                "Let's not overthink it.",
            ]
        return random.choice(options)

    def generate_ask_text(self, agent, item: str, target_id: str) -> str:
        if item in ASK_TEXTS:
            return self._pick_ask_text(agent.model, agent.public_id, item)
        return random.choice([
            f"{agent._r(target_id)}, what do you think about {_lbl(item)}?",
            f"Any thoughts on {_lbl(item)}, {agent._r(target_id)}?",
            f"{agent._r(target_id)}, do you have a preference on {_lbl(item)}?",
        ])

    def generate_share_text(self, agent, item: str, target_id: str) -> str:
        if item in CONSTRAINT_TEXT:
            fact = random.choice(CONSTRAINT_TEXT[item])
            return random.choice([
                f"So, {fact}",
                f"Right, {fact}",
                f"Okay, {fact}",
                f"One thing, {fact}",
            ])
        info = self.info_text(item)
        # If this agent owns a constraint that they haven't revealed yet,
        # framing their preference share as a confident info dump clashes
        # with a subsequent REFUSE on the constraint. Hedge the share so the
        # two events read coherently: "I have a lean, but I want to hear
        # everyone else's constraints first."
        model = getattr(agent, "model", None)
        owns_unrevealed_constraint = False
        if model is not None:
            self._init_state(model)
            owner_constraint = None
            for c_item, c_owner in CONSTRAINT_OWNER.items():
                if c_owner == agent.public_id:
                    owner_constraint = c_item
                    break
            if owner_constraint and not model._cafe_revealed_constraints.get(owner_constraint, False):
                owns_unrevealed_constraint = True
        # Trim trailing sentence punctuation so we can chain a " — but..." clause
        # without producing the ". — " artefact.
        info_chain = info.rstrip(" .")
        if owns_unrevealed_constraint:
            return random.choice([
                f"I know about {info_chain}, but I want to hear the money and location side first.",
                f"I've seen {info_chain}, though I'd rather compare it against the other constraints first.",
                f"Maybe {info_chain}, but I'm not locking it in until we've heard everyone.",
                f"I've got {info_chain} in mind, but let's pin down the other constraints first.",
            ])
        return random.choice([
            f"Okay, {info}",
            f"Honestly, {info}",
            f"For what it's worth, {info}",
            f"Here's what I've got: {info}",
        ])

    # ──────────────────────────────────────────────────────────────────────────
    # main logic
    # ──────────────────────────────────────────────────────────────────────────

    def choose_action(self, agent: "SimAgent", others: List["SimAgent"]) -> Optional[Dict[str, Any]]:
        model = agent.model

        # Soft cafe-specific background stress
        self._apply_personality_stress(agent, model)

        self._init_state(model)
        self._clamp_cafe_state(model)

        state = self._state(model)
        tick_now = getattr(model, "tick", 0)
        role_constraint = ROLE_TO_CONSTRAINT.get(agent.public_id)
        own_pref = next((p for p in ALL_PREFS if p in getattr(agent, "known_items", set())), None)
        personality = getattr(agent, "personality_type", "Easygoing")

        # 1) Respond to direct asks/challenges about owned constraint
        # Prefer the organiser's ask (A1) over any other recent ask
        _stm_recent = list(agent.stm)[-8:]
        _organiser_ask = next(
            (m for m in reversed(_stm_recent)
             if m.get("from") == "A1"
             and m.get("item") == role_constraint
             and m.get("kind") in {"ask_info", "challenge"}),
            None,
        )
        recent_targeted = _organiser_ask or next(
            (m for m in reversed(_stm_recent)
             if m.get("from")
             and m.get("item") == role_constraint
             and m.get("kind") in {"ask_info", "challenge"}),
            None,
        )

        if role_constraint and recent_targeted and not model._cafe_revealed_constraints.get(role_constraint, False):
            asker_id = recent_targeted.get("from")

            refusal = self._maybe_refuse(agent, asker_id, role_constraint)
            if refusal is not None:
                return refusal

            if self._owner_ready_to_share(agent, role_constraint):
                return self._share_constraint_event(agent, asker_id, role_constraint)

        # 2) Organiser actively drives missing constraints, but with pivot logic
        if agent.public_id == "A1":
            missing = self._choose_missing_constraint(model)

            if missing:
                owner_id = CONSTRAINT_OWNER[missing]
                ask_count = self._ask_count(model, agent.public_id, owner_id, missing)

                if self._can_ask_again(
                    model,
                    agent.public_id,
                    owner_id,
                    missing,
                    personality=personality,
                ):
                    self._note_ask(model, agent.public_id, owner_id, missing)

                    # Softer cafe escalation than office
                    challenge_threshold = 4 if personality in ("Leader", "Creative") else 3
                    last_pressure = model._cafe_last_pressure_tick.get(missing, -999)
                    can_pressure_now = (tick_now - last_pressure) >= 2
                    if ask_count >= challenge_threshold and can_pressure_now:
                        if not model._cafe_revealed_constraints.get(missing, False):
                            model._cafe_metrics["pressure"] += 1
                            self._add_conflict(model, 1)
                            agent.stress = min(0.60, agent.stress + 0.03)
                            model._cafe_last_pressure_tick[missing] = tick_now
                            return {
                                "type": "challenge",
                                "actor": agent.public_id,
                                "target": owner_id,
                                "text": random.choice(PRESSURE_TEXTS[missing]),
                                "item": missing,
                                "reason": "cafe_pressure",
                            }

                    model._cafe_metrics["probes"] += 1
                    return {
                        "type": "ask_info",
                        "actor": agent.public_id,
                        "target": owner_id,
                        "text": self._pick_ask_text(model, agent.public_id, missing),
                        "item": missing,
                        "reason": "organiser_probe_constraint",
                    }

                # deadlock break
                if ask_count >= 5 and tick_now >= 12:
                    fallback_target = next((x for x in others if x.public_id != owner_id), None)
                    if fallback_target:
                        return {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": fallback_target.public_id,
                            "text": f"We're stuck on {_lbl(missing)} — use whatever you know that helps us move.",
                            "item": missing,
                            "reason": "deadlock_break_prompt",
                        }

        # 3) Owners may proactively share their owned constraint after some time
        if role_constraint and not model._cafe_revealed_constraints.get(role_constraint, False):
            proactive_prob = {
                "Easygoing": 0.30,
                "Decisive": 0.28,
                "Leader": 0.22,
                "Creative": 0.16,
                "Skeptical": 0.05,
                "Overthinker": 0.03,
            }.get(personality, 0.14)

            if tick_now >= 6:
                proactive_prob += 0.15
            if tick_now >= 10:
                proactive_prob += 0.20

            if random.random() < proactive_prob:
                # Always direct proactive shares to the organiser — they drive the conversation
                _organiser = next((a for a in others if a.public_id == "A1"), None)
                _tgt = _organiser or random.choice([a for a in others if a != agent])
                return self._share_constraint_event(agent, _tgt.public_id, role_constraint)

        # 4) Suggest stable preferences
        if own_pref:
            dim = self._dimension_of(own_pref)
            # Check full session history so the same agent doesn't repeat their suggestion
            _all_past_events = [e for tick_snap in getattr(model, "history", []) for e in tick_snap.get("events", [])]
            already_suggested = any(
                e.get("type") == "suggest"
                and e.get("preference") == own_pref
                and e.get("actor") == agent.public_id
                for e in _all_past_events
            )

            # Once an agent has expressed their preference, don't repeat it
            if already_suggested:
                return None

            personality_suggest_mult = {
                "Easygoing": 1.10,
                "Decisive": 1.05,
                "Leader": 1.00,
                "Creative": 0.95,
                "Skeptical": 0.80,
                "Overthinker": 0.65,
            }.get(personality, 1.0)

            if tick_now <= 3 and personality in ("Easygoing", "Decisive", "Leader"):
                suggest_prob = 0.80
            else:
                suggest_prob = 0.50 * personality_suggest_mult
                if tick_now >= 10:
                    suggest_prob *= 0.80

            # If dietary/budget constraints are revealed, keep suggestions aligned with them
            if model._cafe_revealed_constraints.get("dietary_constraint", False) and own_pref == "italian":
                suggest_prob *= 0.35
            if model._cafe_revealed_constraints.get("budget_constraint", False) and own_pref == "fancy":
                suggest_prob *= 0.15

            if random.random() < suggest_prob and (state[dim] is None or random.random() < 0.30):
                tgt = random.choice([a for a in others if a != agent])
                self._register_pref_expression(model, agent.public_id, own_pref)
                return {
                    "type": "suggest",
                    "actor": agent.public_id,
                    "target": tgt.public_id,
                    "text": _suggest(own_pref, personality),
                    "preference": own_pref,
                    "reason": "preference_suggestion",
                }

        # 5) Respond to recent suggestions
        recent_suggest = next(
            (m for m in reversed(list(agent.stm)[-8:]) if m.get("kind") == "suggest"),
            None,
        )

        if recent_suggest and own_pref:
            their_pref = recent_suggest.get("preference", "")
            other_id = recent_suggest.get("from")

            same_dim = (
                (their_pref in CUISINE_OPTIONS and own_pref in CUISINE_OPTIONS)
                or (their_pref in BUDGET_OPTIONS and own_pref in BUDGET_OPTIONS)
            )

            if their_pref and other_id and their_pref != own_pref and same_dim:
                if personality == "Creative" and tick_now >= 8 and random.random() < 0.55:
                    self._register_pref_expression(model, agent.public_id, their_pref)
                    model._cafe_metrics["compromises"] += 1
                    return {
                        "type": "agree",
                        "actor": agent.public_id,
                        "target": other_id,
                        "text": random.choice([
                            f"Actually, {their_pref} could work for me too.",
                            f"I can get behind {their_pref}. Let's go with that.",
                            f"Yeah, {their_pref} is a good call.",
                        ]),
                        "preference": their_pref,
                        "reason": "creative_late_convergence",
                    }

                # Cafe should stay softer than office — also modulated by env modifiers
                personality_challenge_mult = {
                    "Skeptical": 1.2,
                    "Decisive": 0.7,
                    "Leader": 0.5,
                    "Overthinker": 0.5,
                    "Creative": 0.35,
                    "Easygoing": 0.15,
                }.get(personality, 0.6)
                env_mods = get_env_modifiers(agent.model, personality)
                personality_challenge_mult *= env_mods.get("challenge_bias", 1.0)

                if random.random() < 0.12 * personality_challenge_mult:
                    self._add_conflict(model, 1)
                    agent.stress = min(0.58, agent.stress + 0.025)
                    return {
                        "type": "challenge",
                        "actor": agent.public_id,
                        "target": other_id,
                        "text": _challenge(own_pref, their_pref),
                        "preference": their_pref,
                        "reason": "preference_conflict",
                    }

                personality_compromise_mult = {
                    "Easygoing": 2.0,
                    "Creative": 1.5,
                    "Leader": 1.2,
                    "Decisive": 0.9,
                    "Overthinker": 0.8,
                    "Skeptical": 0.5,
                }.get(personality, 1.0)
                # env confirm_bias reflects how readily agents agree in this environment
                personality_compromise_mult *= env_mods.get("confirm_bias", 1.0)

                _post_summary = getattr(model, "_cafe_summary_done", False)
                _compromise_prob = 0.30 * personality_compromise_mult
                if not _post_summary and tick_now >= 10:
                    _compromise_prob = max(_compromise_prob, 0.60)
                elif _post_summary:
                    _compromise_prob *= 0.35
                if random.random() < _compromise_prob:
                    self._register_pref_expression(model, agent.public_id, their_pref)
                    model._cafe_metrics["compromises"] += 1
                    return {
                        "type": "agree",
                        "actor": agent.public_id,
                        "target": other_id,
                        "text": random.choice(COMPROMISE_TEXTS),
                        "preference": their_pref,
                        "reason": "compromise",
                    }

                if random.random() < 0.25:
                    return {
                        "type": "say",
                        "actor": agent.public_id,
                        "target": other_id,
                        "text": _soften(own_pref, their_pref),
                        "reason": "soft_resistance",
                    }

            elif their_pref and other_id and their_pref == own_pref:
                _agree_prob = 0.15 if getattr(model, "_cafe_summary_done", False) else 0.50
                if random.random() < _agree_prob:
                    self._register_pref_expression(model, agent.public_id, own_pref)
                    model._cafe_metrics["agreements"] += 1
                    return {
                        "type": "agree",
                        "actor": agent.public_id,
                        "target": other_id,
                        "text": self.agree_text(agent, own_pref, other_id),
                        "preference": own_pref,
                        "reason": "preference_support",
                    }

        # 6) Late fallback: if all constraints are revealed, non-organisers converge
        # Suppress after summary to avoid padded agree loops before finalise
        if getattr(model, "_cafe_summary_done", False):
            return None
        late_prob = 0.35 if personality == "Creative" and tick_now >= 10 else 0.20
        if self._all_constraints_revealed(model) and tick_now >= 10 and own_pref and random.random() < late_prob:
            if own_pref in CUISINE_OPTIONS:
                winner = self._winning_pref(model, CUISINE_OPTIONS)
            else:
                winner = self._winning_pref(model, BUDGET_OPTIONS)

            if winner:
                tgt = random.choice([a for a in others if a != agent])
                self._register_pref_expression(model, agent.public_id, winner)
                return {
                    "type": "agree",
                    "actor": agent.public_id,
                    "target": tgt.public_id,
                    "text": random.choice(COMPROMISE_TEXTS),
                    "preference": winner,
                    "reason": "late_deadlock_compromise",
                }

        # 7) light filler
        available = [a for a in others if a != agent and not a.current_conversation_with]
        filler_prob = {
            "Creative": 0.10,
            "Easygoing": 0.08,
            "Overthinker": 0.07,
            "Skeptical": 0.06,
            "Leader": 0.05,
            "Decisive": 0.04,
        }.get(personality, 0.06)
        if self._all_constraints_revealed(model):
            filler_prob *= 0.20
        if getattr(model, "_cafe_summary_done", False):
            filler_prob = 0.0
        if available and random.random() < filler_prob:
            tgt = random.choice(available)
            revealed_n = sum(1 for v in getattr(model, "_cafe_revealed_constraints", {}).values() if v)
            total_n = max(1, len(getattr(model, "_cafe_revealed_constraints", {})) or 4)
            progress_ratio = revealed_n / total_n
            # Only use "nearly done" style lines once ≥75% of constraints are
            # revealed — otherwise they sound absurd at 0/4 or 1/4 progress.
            if progress_ratio >= 0.75:
                opts = LATE_PROGRESS_PHRASES + [f"Getting closer, {agent._r(tgt.public_id)}."]
            else:
                opts = EARLY_CHAT_PHRASES
            return {
                "type": "say",
                "actor": agent.public_id,
                "target": tgt.public_id,
                "text": random.choice(opts),
                "reason": "cafe_general_chat",
            }

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # completion hooks
    # ──────────────────────────────────────────────────────────────────────────

    def should_complete_on_agree(self, model: "SimModel", pref: str) -> bool:
        return pref == "_finalise_"

    def task_to_complete(self, model: "SimModel", pref: str) -> Optional[str]:
        if pref == "_finalise_":
            return "decision"
        return None

    def agree_text(self, agent: "SimAgent", pref: str, target_id: str) -> str:
        if not pref or pref in ("unknown", "_finalise_"):
            return random.choice([
                "Sounds good — let's go with that.",
                "Happy with that.",
                "Yeah, that sounds good.",
                "Okay — that's the one.",
            ])
        ptype = getattr(agent, "personality_type", "Easygoing")
        pools = {
            "Leader": [
                f"Okay — {pref} is the call.",
                f"Yeah, {pref} covers it. I'm in.",
                f"{pref.capitalize()} makes sense. Let's go with that.",
            ],
            "Decisive": [
                f"{pref.capitalize()}. That's the pick.",
                f"{pref.capitalize()}. That's the one.",
                f"Fine — {pref}. Go with that.",
            ],
            "Easygoing": [
                f"Yeah, {pref} sounds good to me.",
                f"No stress, {pref} works for me.",
                f"I'm happy with {pref}.",
                f"That keeps it simple. {pref} it is.",
                f"Oh, {pref}'s fine by me.",
            ],
            "Skeptical": [
                f"I suppose {pref} is the right call.",
                f"Alright — {pref}, if that's what we're going with.",
                f"Fine — {pref}. I can live with it.",
            ],
            "Overthinker": [
                f"Okay, {pref}. That works.",
                f"Alright, I'll commit. {pref} it is.",
                f"{pref.capitalize()} is probably the best call here. Let's go.",
                f"Right — {pref}. Honestly, I'm glad we've picked something.",
            ],
            "Creative": [
                f"Oh, {pref} could be fun.",
                f"{pref.capitalize()} isn't the obvious pick, but I like it.",
                f"What if we lean into {pref}?",
                f"Cheap doesn't have to mean boring. {pref} could still work well.",
                f"Yeah, {pref}. I can see that working.",
            ],
        }
        opts = pools.get(ptype, [f"Yeah — {pref} works for me."])
        return random.choice(opts)

    def suggestion_options(self, agent: "SimAgent") -> List[str]:
        own = [p for p in ALL_PREFS if p in getattr(agent, "known_items", set())]
        return own if own else ALL_PREFS

    def suggest_text(self, agent: "SimAgent", pref: str, target_id: str) -> str:
        personality = getattr(agent, "personality_type", "Easygoing")
        return _suggest(pref, personality)

    def info_text(self, item: str) -> Optional[str]:
        texts = {
            "italian": [
                "nice Italian place nearby. Good pasta, not too pricey.",
                "Italian spot nearby. Solid reviews.",
            ],
            "vegan": [
                "a vegan place with great reviews. Plant-based and meant to be good.",
                "a couple of vegan-friendly options nearby.",
            ],
            "cheap": [
                "affordable option close by. Fast and decent.",
                "a few places under £15 a head nearby.",
            ],
            "fancy": [
                "nicer restaurant if we want something a bit better.",
                "upscale option. Worth it if we want a proper team lunch.",
            ],
            "dietary_constraint": CONSTRAINT_TEXT["dietary_constraint"],
            "budget_constraint": CONSTRAINT_TEXT["budget_constraint"],
            "location_constraint": CONSTRAINT_TEXT["location_constraint"],
        }
        opts = texts.get(item)
        return random.choice(opts) if opts else None

    def build_final_decision(self, model: "SimModel") -> str:
        resolved = self._resolved_final_state(model)
        budget_label = resolved["budget"]
        cuisine_label = resolved["cuisine"]
        location_revealed = model._cafe_revealed_constraints.get("location_constraint", False)

        if cuisine_label == "vegan":
            cuisine_phrase = "with good vegan food"
        elif cuisine_label == "italian":
            cuisine_phrase = "with good Italian food"
        elif cuisine_label:
            cuisine_phrase = f"with good {cuisine_label} food"
        else:
            cuisine_phrase = ""

        if budget_label == "cheap":
            if cuisine_phrase and location_revealed:
                return f"somewhere nearby {cuisine_phrase} that won't cost much"
            if cuisine_phrase:
                return f"somewhere {cuisine_phrase} that won't cost much"
            if location_revealed:
                return "somewhere nearby that won't cost much"
            return "somewhere that won't cost much"

        if budget_label == "fancy":
            if cuisine_phrase and location_revealed:
                return f"somewhere nearby {cuisine_phrase} that's a bit nicer"
            if cuisine_phrase:
                return f"somewhere {cuisine_phrase} that's a bit nicer"
            if location_revealed:
                return "somewhere nearby that's a bit nicer"
            return "somewhere a bit nicer"

        if cuisine_phrase and location_revealed:
            return f"somewhere nearby {cuisine_phrase}"
        if cuisine_phrase:
            return f"somewhere {cuisine_phrase}"
        if location_revealed:
            return "somewhere nearby"
        return "somewhere decent"
