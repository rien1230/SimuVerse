"""
app/sim/scenario_logic/office_logic.py

Office scenario logic for SimuVerse.

This revision tightens the office flow:
- owner full share happens once per item
- progress only completes after a valid owner share creates a pending confirm
- only the intended recipient can confirm that share
- non-owner partial shares require explicit recent delegation
- duplicate owner shares and duplicate delegated partials are blocked
- dialogue is made less meta / robotic and more workplace-natural
"""
from __future__ import annotations

import random
from collections import deque
from typing import TYPE_CHECKING, Optional, List, Dict, Any

from app.sim.scenario_logic.base_logic import BaseLogic, get_env_modifiers
from app.sim.game_config import PRESET_CHALLENGE_BIAS, PRESET_AGREE_BIAS

if TYPE_CHECKING:
    from app.sim.agent import SimAgent
    from app.sim.model import SimModel


def _lbl(item: str) -> str:
    from app.sim.agent import ITEM_LABELS
    return ITEM_LABELS.get(item, item.replace("_", " ").title())


OFFICE_STYLE = {
    "Leader": {
        "ask": 0.90,
        "pressure": 1.40,
        "challenge": 0.85,
        "share": 1.20,
        "hesitate": 0.20,
        "reframe": 0.35,
        "coord": 1.80,
    },
    "Easygoing": {
        "ask": 0.65,
        "pressure": 0.30,
        "challenge": 0.25,
        "share": 1.60,
        "hesitate": 0.40,
        "reframe": 0.45,
        "coord": 1.20,
    },
    "Decisive": {
        "ask": 1.10,
        "pressure": 1.60,
        "challenge": 1.20,
        "share": 1.00,
        "hesitate": 0.15,
        "reframe": 0.20,
        "coord": 0.70,
    },
    "Skeptical": {
        "ask": 1.00,
        "pressure": 1.20,
        "challenge": 1.40,
        "share": 0.55,
        "hesitate": 0.80,
        "reframe": 0.20,
        "coord": 0.60,
    },
    "Overthinker": {
        "ask": 0.70,
        "pressure": 0.50,
        "challenge": 0.70,
        "share": 0.75,
        "hesitate": 1.50,
        "reframe": 0.35,
        "coord": 0.50,
    },
    "Creative": {
        "ask": 0.60,
        "pressure": 0.50,
        "challenge": 0.60,
        "share": 1.10,
        "hesitate": 0.80,
        "reframe": 0.40,
        "coord": 0.80,
    },
}


DOC_OWNER = {
    "budget": "A1",
    "requirements": "A2",
    "design": "A3",
    "tech_specs": "A4",
}

DOC_REQUESTER = {
    "budget": "A4",
    "requirements": "A4",
    "design": "A2",
    "tech_specs": "A1",
}

DOC_ALIAS = {
    "budget": ("the budget", "budget", "the budget"),
    "requirements": ("the requirements", "requirements", "the requirements"),
    "design": ("the design", "design", "the design"),
    "tech_specs": ("the spec doc", "spec doc", "the spec doc"),
}

CHALLENGE_ASK_THRESHOLD = {
    "Easygoing": 6,
    "Creative": 5,
    "Overthinker": 5,
    "Leader": 4,
    "Decisive": 3,
    "Skeptical": 2,
}


_ENV_KEY_MAP = {
    "ask": "ask_bias",
    "pressure": "challenge_bias",
    "challenge": "challenge_bias",
    "share": "share_bias",
    "coord": "confirm_bias",
}


def _style(agent: "SimAgent", key: str, base: float) -> float:
    ptype = getattr(agent, "personality_type", "Easygoing")
    mult = OFFICE_STYLE.get(ptype, {}).get(key, 1.0)
    # Layer on per-personality environment modifier (personality × environment)
    env_key = _ENV_KEY_MAP.get(key)
    if env_key:
        env_mods = get_env_modifiers(agent.model, ptype)
        mult *= env_mods.get(env_key, 1.0)
    return max(0.02, min(0.95, base * mult))


class OfficeProposalLogic(BaseLogic):
    scenario_type = "office"

    ROLES = {
        "A1": "Project Manager",
        "A2": "Developer",
        "A3": "Designer",
        "A4": "Data Analyst",
    }

    def __init__(self):
        super().__init__()
        self._phrase_memory: Dict[str, deque] = {}
        self._global_phrase_memory: deque = deque(maxlen=12)

    # ──────────────────────────────────────────────────────────────────────────
    # Scenario hooks for model.py
    # ──────────────────────────────────────────────────────────────────────────

    def init_scenario_state(self, model: "SimModel") -> None:
        self._init_office_state(model)

    def scenario_modifiers(self, model: "SimModel") -> Dict[str, float]:
        # Office: professional, formal — slightly guarded trust, neutral tension
        return {
            "base_trust_delta": -0.05,
            "arousal_rate": 1.0,
            "refusal_weight": 1.2,
            "cooperation_weight": 0.9,
            "initial_tension_delta": 0.0,
            "initial_cohesion_delta": 0.0,
            "initial_stress_delta": 0.0,
        }

    def metric_weights(self, model: "SimModel") -> Dict[str, float]:
        return {
            "challenge": 1.2,
            "refuse": 1.3,
            "stall": 1.25,
            "bottleneck": 1.3,
            "positive": 0.9,
        }

    def final_success_relief(self, model: "SimModel") -> tuple[float, float, float]:
        return (0.08, 0.05, 0.03)

    def outcome_for_tick(self, model: "SimModel", tick: int, raw: str) -> str:
        if raw == "success":
            return "success"

        at_end = tick >= model.episode_max_ticks or model.ended
        if at_end:
            progress = model.scenario.progress_ratio()
            if progress >= 0.30:
                return "partial"
            return "failure"

        return "running"

    def counts_as_share(self, model: "SimModel", event: Dict[str, Any]) -> bool:
        if event.get("type") != "share_info":
            return False
        if not event.get("item"):
            return False
        if bool(event.get("partial", False)):
            return False
        return True

    def accumulate_run_metrics(
        self,
        model: "SimModel",
        events: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        emotional = 0.0
        coord_pressure = 0.0
        conflict = 0.0

        for event in events:
            event_type = event.get("type", "")
            reason = event.get("reason", "")
            text = str(event.get("text", "")).lower()

            if reason in (
                "overthinker_hesitate",
                "skeptical_delay",
                "structured_refusal",
                "creative_reframe",
            ):
                emotional += 0.06

            if reason in (
                "pressure_escalation",
                "decisive_ultimatum",
                "delegate_cover",
                "managed_non_owner_share",
                "partial_cross_role_reference",
                "ownership_guard",
            ):
                coord_pressure += 0.07

            if text and any(
                phrase in text
                for phrase in (
                    "running out of time",
                    "need this now",
                    "not later",
                    "wasting time",
                    "blocker",
                    "we're stuck",
                    "we are stuck",
                    "keep moving",
                    "keep this moving",
                    "move on",
                    "let's keep",
                    "lets keep",
                    "next piece",
                    "still waiting",
                    "what's the status",
                    "what do you have",
                    "what have you got",
                    "direct answer",
                    "straight answer",
                    "time is tight",
                    "time's tight",
                    "we need",
                    "locked in",
                    "confirmed",
                    "let's push on",
                    "lets push on",
                    "stay tight",
                )
            ):
                coord_pressure += 0.04

            if event_type == "ask_info":
                coord_pressure += 0.015

            if event_type == "agree" and reason == "office_confirm":
                coord_pressure += 0.012

            if event_type == "insult":
                conflict += 0.15
                emotional += 0.08

            if event_type == "challenge":
                conflict += 0.05

            if event_type == "refuse":
                emotional += 0.04
                conflict += 0.03

        for agent in model.agents:
            personality_type = getattr(agent, "personality_type", "Easygoing")
            if personality_type == "Overthinker" and model.bottleneck_age >= 1:
                emotional += 0.03
            elif personality_type == "Skeptical" and model.total_refusals >= 1:
                emotional += 0.02

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
        extra_events: List[Dict[str, Any]] = []

        if model.scenario.progress_ratio() >= 1.0:
            return extra_events

        self._init_office_state(model)

        # Office stress drip by preset — tension/pressure teams should feel
        # observably warmer than smooth. Caps still enforced in model.step().
        preset = getattr(model, "team_preset", None)
        tick_now = getattr(model, "tick", 0)
        if preset == "tension_team" and tick_now >= 2:
            for agent in getattr(model, "agents", []):
                try:
                    agent.stress = min(float(getattr(agent, "stress", 0.0) or 0.0) + 0.017, 1.0)
                except Exception:
                    pass
        elif preset == "pressure_team" and tick_now >= 3:
            for agent in getattr(model, "agents", []):
                try:
                    agent.stress = min(float(getattr(agent, "stress", 0.0) or 0.0) + 0.012, 1.0)
                except Exception:
                    pass

        # Fallback confirmation: if a valid owner share has been sitting for a while,
        # complete it automatically instead of letting the scenario stall out.
        for item, pending in list(model._office_pending_confirm.items()):
            if model._office_confirmed.get(item, False):
                continue

            final_deadline_close = (
                len(self._priority_missing(model)) == 1
                and getattr(model, "tick", 0) >= (getattr(model, "episode_max_ticks", 25) - 1)
            )
            share_age = getattr(model, "tick", 0) - pending.get("share_tick", 0)
            min_share_age = 0 if final_deadline_close else 2
            if share_age < min_share_age:
                continue

            confirmer_id = pending.get("confirmer")
            owner_id = pending.get("owner")
            if not confirmer_id or not owner_id:
                continue

            if (not final_deadline_close) and any(e.get("actor") == confirmer_id for e in events):
                continue

            confirmer = next((a for a in model.agents if a.public_id == confirmer_id), None)
            owner = next((a for a in model.agents if a.public_id == owner_id), None)
            if not confirmer or not owner:
                continue

            confirm_event = self._confirm_event(confirmer, owner, item)
            if confirm_event is not None:
                confirm_event["reason"] = "office_confirm_fallback"
                extra_events.append(confirm_event)

        # Fallback release: if the current blocker has clearly stalled and the owner
        # still has it, force a direct owner share to the most relevant asker.
        missing = self._priority_missing(model)
        if missing:
            current_blocker = missing[0]
            if (
                not model._office_revealed.get(current_blocker, False)
                and self._pending_confirm_for_item(model, current_blocker) is None
            ):
                owner = next(
                    (
                        a for a in model.agents
                        if a.public_id == self._owner_id(current_blocker)
                    ),
                    None,
                )
                if (
                    owner
                    and current_blocker in getattr(owner, "known_items", set())
                    and not any(e.get("actor") == owner.public_id for e in events)
                    and self._should_force_owner_release(owner, current_blocker)
                ):
                    others = [a for a in model.agents if a.public_id != owner.public_id]
                    target = self._primary_asker_for_item(owner, others, current_blocker)
                    if not target:
                        target = self._best_confirmer_for_item(owner, others, current_blocker)
                    if target:
                        forced_event = self._share_event(
                            owner,
                            target,
                            current_blocker,
                            "forced_release_after_stall",
                        )
                        if forced_event is not None:
                            extra_events.append(forced_event)

        for event in events:
            if event.get("type") != "share_info":
                continue

            item = event.get("item")
            actor_id = event.get("actor")
            target_id = event.get("target")
            partial = bool(event.get("partial", False))

            if not item or not actor_id or not target_id:
                continue
            if partial:
                continue

            self._init_office_state(model)
            if model._office_confirmed.get(item, False):
                continue

            if random.random() < 0.15:
                actor = next((a for a in model.agents if a.public_id == actor_id), None)
                target = next((a for a in model.agents if a.public_id == target_id), None)
                if not actor or not target:
                    continue

                doc_def = self._doc_ref(item, definite=True)
                pron = self._doc_pronoun(doc_def)
                ptype_ack = getattr(target, "personality_type", "Easygoing")
                ack_pools = {
                    "Leader": [
                        f"Good. I'll fold {doc_def} into the plan.",
                        f"Got it. {doc_def.capitalize()} fits here.",
                        f"Got {doc_def}. I'll line up the next step.",
                    ],
                    "Decisive": [
                        f"Got {doc_def}. Next item.",
                        f"Received. I'll read {pron} now.",
                        f"Got {doc_def} in hand. Next.",
                    ],
                    "Easygoing": [
                        f"Nice — got {doc_def}. I'll check {pron} now.",
                        f"Perfect, thanks — I'll give {pron} a look now.",
                        f"Lovely, {doc_def} landed. I'll check {pron} over.",
                    ],
                    "Skeptical": [
                        f"I've got {doc_def}, but I want to verify {pron} properly.",
                        f"Received. I'll read {pron} carefully before I confirm it.",
                        f"Got {doc_def}. Let me actually check it stands up.",
                    ],
                    "Overthinker": [
                        f"Okay, I have {doc_def}. I just want to check {pron} once.",
                        f"Got it. Let me go through {doc_def} carefully — I don't want to miss anything.",
                        f"Received. I'll read {pron} through a couple of times just to be sure.",
                    ],
                    "Creative": [
                        f"Got {doc_def}. I can see where it goes.",
                        f"Got {doc_def}. I can see where it fits.",
                        f"Received. Let me see where this fits.",
                    ],
                }
                opts = ack_pools.get(ptype_ack, ack_pools["Easygoing"])

                extra_events.append(
                    {
                        "type": "say",
                        "actor": target_id,
                        "target": actor_id,
                        "text": self._pick_fresh_phrase(target, opts),
                        "reason": "office_share_ack",
                        "phrase_key": f"office_share_ack_{item}_{target_id}",
                    }
                )

        return extra_events

    # ──────────────────────────────────────────────────────────────────────────
    # State helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _init_office_state(self, model: "SimModel") -> None:
        if not hasattr(model, "_office_revealed"):
            model._office_revealed = {
                "budget": False,
                "requirements": False,
                "design": False,
                "tech_specs": False,
            }
        if not hasattr(model, "_office_confirmed"):
            model._office_confirmed = {
                "budget": False,
                "requirements": False,
                "design": False,
                "tech_specs": False,
            }
        if not hasattr(model, "_office_last_share_tick"):
            model._office_last_share_tick = {}
        if not hasattr(model, "_office_last_confirm_tick"):
            model._office_last_confirm_tick = {}
        if not hasattr(model, "_office_recent_shares"):
            model._office_recent_shares = {}
        if not hasattr(model, "_office_guard_lines"):
            model._office_guard_lines = {}
        if not hasattr(model, "_office_delegations"):
            model._office_delegations = {}
        if not hasattr(model, "_office_reframe_counts"):
            model._office_reframe_counts = {}
        if not hasattr(model, "_office_pending_confirm"):
            model._office_pending_confirm = {}
        if not hasattr(model, "_office_partial_done"):
            model._office_partial_done = {}
        if not hasattr(model, "coord_pressure_bonus"):
            model.coord_pressure_bonus = 0.0
        if not hasattr(model, "conflict_bonus"):
            model.conflict_bonus = 0.0
        if not hasattr(model, "total_refusals"):
            model.total_refusals = 0
        if not hasattr(model, "global_ask_counts"):
            model.global_ask_counts = {}
        if not hasattr(model, "_office_blocker_age"):
            model._office_blocker_age = {}
        if not hasattr(model, "_office_last_refusal_tick"):
            model._office_last_refusal_tick = {}

    def _priority_missing(self, model: "SimModel") -> List[str]:
        self._init_office_state(model)
        order = ["requirements", "design", "tech_specs", "budget"]
        missing = [k for k in order if not model.scenario.tasks.get(k, False)]
        focus_item = getattr(model, "_intervention_focus_item", None)
        focus_until = getattr(model, "_intervention_focus_until", -1)
        if (
            focus_item
            and missing
            and focus_item == missing[0]
            and getattr(model, "tick", 0) <= focus_until
        ):
            return [focus_item] + [k for k in missing if k != focus_item]
        return missing

    def _intervention_quiet_active(self, model: "SimModel", item: str) -> bool:
        quiet_item = getattr(model, "_intervention_quiet_item", None)
        quiet_until = getattr(model, "_intervention_quiet_until", -1)
        if quiet_item != item or getattr(model, "tick", 0) > quiet_until:
            return False
        tension = float(getattr(model, "group_tension", 0.0) or 0.0)
        stall = int(getattr(model, "progress_stall_ticks", 0) or 0)
        return tension < 0.80 and stall < 4

    def _item_recently_addressed(self, model: "SimModel", item: str, within: int = 2) -> bool:
        tick_now = getattr(model, "tick", 0)
        pending_events = list(getattr(model, "_pending_events", []) or [])[-8:]
        recent_events = list(getattr(model, "prev_events", []) or [])[-10:]

        if self._intervention_quiet_active(model, item):
            return True

        for event in [*pending_events, *recent_events]:
            event_item = event.get("item") or event.get("preference")
            if event_item != item:
                continue
            event_tick = event.get("tick", tick_now)
            if (tick_now - event_tick) > within:
                continue
            if event.get("type") in {"share_info", "agree", "suggest"}:
                return True

        if item in getattr(model, "_office_pending_confirm", {}):
            return True

        return False

    # ──────────────────────────────────────────────────────────────────────────
    # General helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _role_name(self, agent_id: str) -> str:
        return self.ROLES.get(agent_id, agent_id)

    def _doc_ref(self, item: str, short: bool = False, definite: bool = False) -> str:
        long_name, short_name, definite_name = DOC_ALIAS.get(
            item, (_lbl(item), _lbl(item).lower(), _lbl(item).lower())
        )
        if definite:
            return definite_name
        return short_name if short else long_name

    def _doc_be(self, doc_ref: str) -> str:
        lower = doc_ref.lower()
        if "requirements" in lower or "specifications" in lower:
            return "are"
        return "is"

    def _doc_pronoun(self, doc_ref: str) -> str:
        """Return 'them' for plural doc refs, 'it' for singular."""
        lower = doc_ref.lower()
        if "requirements" in lower or "specifications" in lower:
            return "them"
        return "it"

    def _doc_is_plural(self, doc_ref: str) -> bool:
        lower = doc_ref.lower()
        return "requirements" in lower or "specifications" in lower

    def _doc_verb(self, doc_ref: str, singular_form: str) -> str:
        """Conjugate a 3rd-person-singular verb ('opens', 'gives', 'reads')
        to its bare plural form when the subject is plural ('requirements').
        Falls back to the singular form for anything else."""
        if not self._doc_is_plural(doc_ref):
            return singular_form
        # Irregulars first
        irregulars = {"is": "are", "has": "have", "does": "do", "was": "were"}
        if singular_form in irregulars:
            return irregulars[singular_form]
        # Regular: drop trailing "es" for sibilant-stem verbs ("passes"→"pass"),
        # otherwise drop the trailing "s".
        if singular_form.endswith(("sses", "shes", "ches", "xes", "zes")):
            return singular_form[:-2]
        if singular_form.endswith("ies") and len(singular_form) > 3:
            return singular_form[:-3] + "y"
        if singular_form.endswith("s"):
            return singular_form[:-1]
        return singular_form

    def _preferred_requester_id(self, item: str) -> str:
        return DOC_REQUESTER.get(item, "")

    def _trust_to(self, agent: "SimAgent", other_id: Optional[str]) -> float:
        if not other_id:
            return 0.5
        return float(getattr(agent, "trust", {}).get(other_id, 0.5))

    def _owner_id(self, item: str) -> str:
        return DOC_OWNER.get(item, "")

    def _owner_role(self, item: str) -> str:
        owner_id = self._owner_id(item)
        return self._role_name(owner_id) if owner_id else "the owner"

    def _is_owner(self, agent: "SimAgent", item: str) -> bool:
        return agent.public_id == self._owner_id(item)

    def _is_partial_share(self, agent: "SimAgent", item: str) -> bool:
        return not self._is_owner(agent, item)

    def _ensure_phrase_memory(self, agent: "SimAgent"):
        if agent.public_id not in self._phrase_memory:
            self._phrase_memory[agent.public_id] = deque(maxlen=5)

    _FILLER_BLOCKLIST = frozenset([
        # Generic acknowledgements — sound like system outputs
        "Good. I needed that.",
        "Okay — that actually helps a lot.",
        "That's enough to move.",
        "That helps us move forward.",
        "We can close it from there.",
        "That answers what I needed.",
        "Okay, that answers what I needed",
        "Here's the missing piece",
        "That was the missing piece.",
        "Exactly what we needed for this stage.",
        "We've managed to resolve all outstanding items.",
        "That unblocked us — well done.",
        # Overly soft/padded phrases
        "Right, that makes sense. Thanks.",
        "Sure, that makes sense.",
        "Got it, that works.",
        "Makes sense, thanks.",
        "Okay, it sounds like we've got all the pieces now.",
    ])

    def _pick_fresh_phrase(self, agent: "SimAgent", options: List[str]) -> str:
        self._ensure_phrase_memory(agent)
        recent_agent = self._phrase_memory[agent.public_id]
        recent_global = self._global_phrase_memory
        filtered = [
            o for o in options
            if o not in recent_agent
            and o not in recent_global
            and o not in self._FILLER_BLOCKLIST
        ]
        if not filtered:
            filtered = [o for o in options if o not in recent_agent and o not in self._FILLER_BLOCKLIST]
        chosen = random.choice(
            filtered if filtered else [o for o in options if o not in self._FILLER_BLOCKLIST] or options
        )
        recent_agent.append(chosen)
        recent_global.append(chosen)
        return chosen

    def _last_target_line_exists(self, agent: "SimAgent", target_id: str) -> bool:
        prev = getattr(agent.model, "prev_events", [])
        for e in reversed(prev[-4:]):
            if e.get("actor") == target_id:
                return True
        return False

    def _recent_share_was_partial(self, agent: "SimAgent", target_id: str, within: int = 2) -> bool:
        prev = getattr(agent.model, "prev_events", [])
        tick_now = getattr(agent.model, "tick", 0)
        for e in reversed(prev[-8:]):
            if e.get("type") != "share_info":
                continue
            if e.get("actor") != target_id:
                continue
            if (tick_now - e.get("tick", tick_now)) > within:
                continue
            return e.get("partial", False)
        return False

    def _find_recent_share_item(self, agent: "SimAgent", target_id: str) -> str:
        for e in reversed(getattr(agent.model, "prev_events", [])[-8:]):
            if e.get("type") == "share_info" and e.get("actor") == target_id:
                return e.get("item", "")
        return ""

    def _recent_relevant_share_exists(
        self,
        agent: "SimAgent",
        target_id: str,
        item: Optional[str] = None,
        within: int = 2,
    ) -> bool:
        prev = getattr(agent.model, "prev_events", [])
        tick_now = getattr(agent.model, "tick", 0)
        for e in reversed(prev[-8:]):
            if e.get("type") != "share_info":
                continue
            if e.get("actor") != target_id:
                continue
            event_tick = e.get("tick", tick_now)
            if (tick_now - event_tick) > within:
                continue
            if item is not None and e.get("item") != item:
                continue
            if e.get("partial", False):
                continue
            return True
        return False

    def _get_known_missing(self, model: "SimModel") -> List[str]:
        return [t for t, done in model.scenario.tasks.items() if not done]

    def _get_unknown_missing(self, agent: "SimAgent") -> List[str]:
        return [t for t in self._get_known_missing(agent.model) if t not in agent.known_items]

    def _mark_coord_pressure(self, agent: "SimAgent", amount: float = 0.01):
        current = getattr(agent.model, "coord_pressure_bonus", 0.0)
        setattr(agent.model, "coord_pressure_bonus", round(current + amount, 4))

    def _mark_conflict(self, agent: "SimAgent", amount: float = 0.01):
        current = getattr(agent.model, "conflict_bonus", 0.0)
        setattr(agent.model, "conflict_bonus", round(current + amount, 4))

    def _record_share_tick(self, agent: "SimAgent", item: str):
        cache = getattr(agent.model, "_office_recent_shares", {})
        cache[(agent.public_id, item)] = getattr(agent.model, "tick", 0)
        setattr(agent.model, "_office_recent_shares", cache)

    def _shared_recently(self, agent: "SimAgent", item: str, within: int = 2) -> bool:
        cache = getattr(agent.model, "_office_recent_shares", {})
        last_tick = cache.get((agent.public_id, item), -999)
        return (getattr(agent.model, "tick", 0) - last_tick) <= within

    def _guard_recently(self, agent: "SimAgent", item: str, within: int = 3) -> bool:
        cache = getattr(agent.model, "_office_guard_lines", {})
        last_tick = cache.get((agent.public_id, item), -999)
        return (getattr(agent.model, "tick", 0) - last_tick) <= within

    def _record_guard_line(self, agent: "SimAgent", item: str):
        cache = getattr(agent.model, "_office_guard_lines", {})
        cache[(agent.public_id, item)] = getattr(agent.model, "tick", 0)
        setattr(agent.model, "_office_guard_lines", cache)

    def _recent_requester_id_for_item(
        self,
        model: "SimModel",
        item: str,
        within: int = 3,
    ) -> Optional[str]:
        owner_id = self._owner_id(item)
        if not owner_id:
            return None

        tick_now = getattr(model, "tick", 0)
        for diff in reversed(getattr(model, "history", [])[-(within + 2):]):
            diff_tick = diff.get("tick", tick_now)
            if (tick_now - diff_tick) > within:
                continue
            for e in reversed(diff.get("events", [])):
                if e.get("type") != "ask_info":
                    continue
                if e.get("target") != owner_id or e.get("item") != item:
                    continue
                asker_id = e.get("actor")
                if asker_id and asker_id != owner_id:
                    return asker_id

        for e in reversed(getattr(model, "prev_events", [])[-12:]):
            if e.get("type") != "ask_info":
                continue
            if e.get("target") != owner_id or e.get("item") != item:
                continue
            event_tick = e.get("tick", tick_now)
            if (tick_now - event_tick) > within:
                continue
            asker_id = e.get("actor")
            if asker_id and asker_id != owner_id:
                return asker_id
        return None

    def _primary_asker_for_item(
        self,
        owner: "SimAgent",
        others: List["SimAgent"],
        item: str,
    ) -> Optional["SimAgent"]:
        recent_asker_id = self._recent_requester_id_for_item(owner.model, item, within=3)
        if recent_asker_id:
            for other in others:
                if other.public_id == recent_asker_id:
                    return other

        preferred_requester_id = self._preferred_requester_id(item)
        if preferred_requester_id:
            for other in others:
                if other.public_id == preferred_requester_id:
                    return other

        asks = getattr(owner.model, "global_ask_counts", {})
        counts: Dict[str, int] = {}
        for (asker, target, asked_item), count in asks.items():
            if target == owner.public_id and asked_item == item:
                counts[asker] = counts.get(asker, 0) + count
        if counts:
            best = max(counts, key=counts.get)
            for other in others:
                if other.public_id == best:
                    return other
        for e in reversed(getattr(owner.model, "prev_events", [])[-8:]):
            if e.get("type") == "ask_info" and e.get("target") == owner.public_id and e.get("item") == item:
                asker_id = e.get("actor")
                for other in others:
                    if other.public_id == asker_id:
                        return other
        return None

    def _incoming_ask_count(self, agent: "SimAgent", item: str) -> int:
        asks = getattr(agent.model, "global_ask_counts", {})
        return sum(
            count
            for (asker, target, asked_item), count in asks.items()
            if target == agent.public_id and asked_item == item
        )

    def _delegation_key(self, item: str, helper_id: str) -> tuple:
        return (item, helper_id)

    def _count_recent_doc_mentions(self, model: "SimModel", item: str, within: int = 6) -> int:
        prev = getattr(model, "prev_events", [])
        tick_now = getattr(model, "tick", 0)
        count = 0
        for e in reversed(prev[-12:]):
            event_tick = e.get("tick", tick_now)
            if (tick_now - event_tick) > within:
                continue
            if e.get("item") == item:
                count += 1
        return count

    def _reframe_count(self, agent: "SimAgent", item: str) -> int:
        cache = getattr(agent.model, "_office_reframe_counts", {})
        return cache.get((agent.public_id, item), 0)

    def _increment_reframe(self, agent: "SimAgent", item: str):
        cache = getattr(agent.model, "_office_reframe_counts", {})
        cache[(agent.public_id, item)] = cache.get((agent.public_id, item), 0) + 1
        setattr(agent.model, "_office_reframe_counts", cache)

    def _can_reframe(self, agent: "SimAgent", item: str) -> bool:
        return self._reframe_count(agent, item) < 1

    def _force_direct_text(self, agent: "SimAgent", item: str, target_id: str) -> str:
        doc = self._doc_ref(item)
        role = self._role_name(target_id)
        return self._pick_fresh_phrase(agent, [
            f"{role}, can you confirm {doc} now?",
            f"We need {doc} to move this on.",
            f"{role}, {doc} {self._doc_be(doc)} the blocker. I need your update.",
        ])

    def _record_delegation(self, delegator: "SimAgent", helper_id: str, item: str):
        cache = getattr(delegator.model, "_office_delegations", {})
        cache[self._delegation_key(item, helper_id)] = {
            "tick": getattr(delegator.model, "tick", 0),
            "from": delegator.public_id,
        }
        setattr(delegator.model, "_office_delegations", cache)

    def _delegated_recently(self, agent: "SimAgent", item: str, within: int = 3) -> bool:
        cache = getattr(agent.model, "_office_delegations", {})
        rec = cache.get(self._delegation_key(item, agent.public_id))
        if not rec:
            return False
        return (getattr(agent.model, "tick", 0) - rec.get("tick", -999)) <= within

    def _owner_stalled(self, model: "SimModel", item: str) -> bool:
        owner_id = self._owner_id(item)
        ask_counts = getattr(model, "global_ask_counts", {}) or {}
        asks_to_owner = sum(
            count
            for (asker_id, target_id, asked_item), count in ask_counts.items()
            if target_id == owner_id and asked_item == item and asker_id != owner_id
        )
        return asks_to_owner >= 2

    def _current_blocker_age(self, model: "SimModel", item: str) -> int:
        start_map = getattr(model, "_office_blocker_age", {})
        tick_now = getattr(model, "tick", 0)
        return tick_now - start_map.get(item, tick_now)

    def _rough_cut_requested(self, text: str) -> bool:
        lower = text.lower()
        return any(
            phrase in lower
            for phrase in (
                "rough version",
                "working version",
                "workable cut",
                "usable",
                "what you have",
                "for now",
                "temporary",
            )
        )

    def _should_force_owner_release(self, agent: "SimAgent", item: str) -> bool:
        if not self._is_owner(agent, item):
            return False
        if item not in getattr(agent, "known_items", set()):
            return False
        if agent.model._office_revealed.get(item, False):
            return False

        incoming = self._incoming_ask_count(agent, item)
        blocker_age = self._current_blocker_age(agent.model, item)
        stress = getattr(agent, "stress", 0.0)
        ptype = getattr(agent, "personality_type", "Easygoing")
        others = [a for a in agent.model.agents if a.public_id != agent.public_id]
        primary_asker = self._primary_asker_for_item(agent, others, item)
        trust_to_asker = self._trust_to(agent, getattr(primary_asker, "public_id", None))

        if ptype == "Decisive" and incoming >= 1:
            return True
        if ptype == "Leader" and incoming >= 1 and blocker_age >= 1:
            return True
        if ptype == "Creative" and incoming >= 1 and blocker_age >= 1 and trust_to_asker >= 0.40:
            return True
        if ptype == "Overthinker" and incoming >= 1 and blocker_age >= 2:
            return True
        if ptype == "Skeptical" and incoming >= 2 and blocker_age >= 1:
            return True
        if incoming >= 3:
            return True
        if trust_to_asker >= 0.62 and incoming >= 2 and blocker_age >= 2:
            return True
        if ptype == "Creative" and incoming >= 1 and blocker_age >= 1 and trust_to_asker >= 0.45:
            return True
        if incoming >= 2 and blocker_age >= 3:
            return True
        if incoming >= 1 and stress >= 0.72:
            return True
        if blocker_age >= 5:
            return True
        return False

    def _partial_already_done(self, agent: "SimAgent", item: str) -> bool:
        cache = getattr(agent.model, "_office_partial_done", {})
        return cache.get((agent.public_id, item), False)

    def _record_partial_done(self, agent: "SimAgent", item: str):
        cache = getattr(agent.model, "_office_partial_done", {})
        cache[(agent.public_id, item)] = True
        setattr(agent.model, "_office_partial_done", cache)

    def _can_non_owner_share(self, agent: "SimAgent", item: str) -> bool:
        if self._is_owner(agent, item):
            return True
        if self._partial_already_done(agent, item):
            return False
        if self._delegated_recently(agent, item):
            return True
        if item in getattr(agent, "known_items", set()):
            if self._owner_stalled(agent.model, item) and self._current_blocker_age(agent.model, item) >= 4:
                return True
        return False

    def _pending_confirm_for_item(self, model: "SimModel", item: str) -> Optional[Dict[str, Any]]:
        self._init_office_state(model)
        rec = model._office_pending_confirm.get(item)
        if not rec:
            return None
        tick_now = getattr(model, "tick", 0)
        if (tick_now - rec.get("share_tick", -999)) > 5:
            model._office_pending_confirm.pop(item, None)
            if not model._office_confirmed.get(item, False):
                model._office_revealed[item] = False
            return None
        return rec

    def _pending_confirm_share_is_old_enough(self, model: "SimModel", item: str, min_age: int = 1) -> bool:
        pending = self._pending_confirm_for_item(model, item)
        if not pending:
            return False
        tick_now = getattr(model, "tick", 0)
        return (tick_now - pending.get("share_tick", tick_now)) >= min_age

    def _agent_can_confirm_item(self, agent: "SimAgent", item: str) -> bool:
        pending = self._pending_confirm_for_item(agent.model, item)
        if not pending:
            return False
        if pending.get("confirmer") != agent.public_id:
            return False
        if pending.get("owner") == agent.public_id:
            return False
        return True

    def _best_confirmer_for_item(
        self,
        owner: "SimAgent",
        others: List["SimAgent"],
        item: str,
    ) -> Optional["SimAgent"]:
        asker = self._primary_asker_for_item(owner, others, item)
        if asker and asker.public_id != owner.public_id:
            return asker
        for e in reversed(getattr(owner.model, "prev_events", [])[-10:]):
            if e.get("type") == "ask_info" and e.get("item") == item:
                asker_id = e.get("actor")
                if asker_id != owner.public_id:
                    candidate = next((o for o in others if o.public_id == asker_id), None)
                    if candidate:
                        return candidate
        candidates = [o for o in others if o.public_id != owner.public_id]
        if not candidates:
            return None
        return max(candidates, key=lambda a: owner.trust.get(a.public_id, 0.4))

    def pick_best_target_for_item(
        self,
        agent: "SimAgent",
        item: str,
        others: List["SimAgent"],
    ) -> Optional["SimAgent"]:
        self._init_office_state(agent.model)

        pending = self._pending_confirm_for_item(agent.model, item)
        if pending:
            if pending.get("confirmer") == agent.public_id:
                owner = next((o for o in others if o.public_id == pending.get("owner")), None)
                if owner:
                    return owner

            confirmer = next((o for o in others if o.public_id == pending.get("confirmer")), None)
            if confirmer:
                return confirmer

        owner_id = self._owner_id(item)
        owner = next((o for o in others if o.public_id == owner_id), None)
        if owner:
            return owner

        delegated = [o for o in others if self._delegated_recently(o, item)]
        if delegated:
            return max(delegated, key=lambda o: agent.trust.get(o.public_id, 0.4))

        known = [o for o in others if item in getattr(o, "known_items", set())]
        if known:
            return max(known, key=lambda o: agent.trust.get(o.public_id, 0.4))

        return None

    def _build_non_owner_share_text(
        self,
        agent: "SimAgent",
        item: str,
        target_id: str,
    ) -> str:
        info = self.info_text(item) or f"I have limited information about {_lbl(item)}."
        return self._pick_fresh_phrase(
            agent,
            [
                f"I'm covering {self._doc_ref(item, definite=True)} while we wait on the owner. Here's what I can confirm: {info}",
                f"{self._owner_role(item)} is tied up, but this is the part I can confirm: {info}",
                f"Here's what I have so far: {info}",
            ],
        )

    def _owner_workaround_share_text(
        self,
        agent: "SimAgent",
        item: str,
        target_id: str,
    ) -> str:
        info = self.info_text(item) or f"Here's what I have on {self._doc_ref(item, definite=True)}."
        role = self._role_name(target_id)
        return self._pick_fresh_phrase(
            agent,
            [
                f"{role}, here's the draft: {info}",
                f"I can send what I have at this point: {info}",
                f"Here's the draft version: {info}",
            ],
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Event builders
    # ──────────────────────────────────────────────────────────────────────────

    def _share_event(
        self,
        agent: "SimAgent",
        target: "SimAgent",
        item: str,
        reason: str,
        forced_text: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        self._init_office_state(agent.model)
        model = agent.model
        partial = self._is_partial_share(agent, item)

        if not partial and model._office_revealed.get(item, False):
            return None
        if partial and self._partial_already_done(agent, item):
            return None

        text = forced_text or self.generate_share_text(agent, item, target.public_id)

        if not partial:
            model._office_revealed[item] = True
            model._office_last_share_tick[item] = getattr(model, "tick", 0)
            model._office_pending_confirm[item] = {
                "owner": agent.public_id,
                # Only the direct recipient can confirm the share.
                "confirmer": target.public_id,
                "share_tick": getattr(model, "tick", 0),
            }
        else:
            self._mark_coord_pressure(agent, 0.01)
            self._record_partial_done(agent, item)

        self._record_share_tick(agent, item)

        return {
            "type": "share_info",
            "actor": agent.public_id,
            "target": target.public_id,
            "text": text,
            "item": item,
            "reason": reason,
            "partial": partial,
            "can_complete": False,
        }

    def _confirm_event(
        self,
        agent: "SimAgent",
        target: "SimAgent",
        item: str,
    ) -> Optional[Dict[str, Any]]:
        self._init_office_state(agent.model)
        model = agent.model

        pending = self._pending_confirm_for_item(model, item)
        if not pending:
            return None
        if model._office_confirmed.get(item, False):
            return None
        # Guard: if ANY agent already produced a confirm for this item recently, suppress
        recent_confirms = [e for e in getattr(model, "prev_events", [])[-10:]
                           if e.get("reason") == "office_confirm" and e.get("item") == item]
        if recent_confirms:
            return None
        if self._is_owner(agent, item):
            return None
        if pending.get("confirmer") != agent.public_id:
            return None
        if pending.get("owner") != target.public_id:
            return None

        current_tick = getattr(model, "tick", 0)
        for e in reversed(getattr(model, "prev_events", [])[-6:]):
            if e.get("actor") == agent.public_id and e.get("tick") == current_tick:
                return None

        model._office_confirmed[item] = True
        model._office_last_confirm_tick[item] = current_tick
        model._office_pending_confirm.pop(item, None)

        if not model.scenario.tasks.get(item, False):
            model.mark_task_complete(item)

        doc = self._doc_ref(item, definite=True)
        be = self._doc_be(doc)
        owner_role = self._role_name(target.public_id)
        short_doc = self._doc_ref(item, short=True)
        the_doc = f"the {short_doc}"
        be_doc = self._doc_be(short_doc)  # "is" or "are"

        # Build ordered list of confirmed items for contextual reference
        _confirmed_items = [k for k, v in model._office_confirmed.items() if v and k != item]
        _prior_ref = ""
        if _confirmed_items and len(_confirmed_items) >= 2:
            prev_doc = f"the {self._doc_ref(_confirmed_items[-1], short=True)}"
            _prior_ref = random.choice([
                "We've got both of those now. One thing left.",
                "Okay, that's in. We're close.",
                "Good — that's two sorted. One left.",
            ])

        ptype = getattr(agent, "personality_type", "Easygoing")
        confirm_pools = {
            "Leader": [
                "Good. That's locked in.",
                "Good. Move to the next piece.",
                f"Alright, that's set. What else is left?",
                "Good. One less thing.",
            ],
            "Decisive": [
                f"Got it.",
                f"That's set. Next item.",
                "That's in.",
                f"Right. Next item.",
            ],
            "Easygoing": [
                f"Yeah, that's fine.",
                f"Okay, we can leave {the_doc} there.",
                f"Nice, one less thing.",
                f"Yeah, that's fine there.",
            ],
            "Skeptical": [
                f"Alright, if you're sure.",
                f"Okay — I'll take it. Want to check it again later.",
                "Fine. Looks covered.",
                f"Hm. Okay. Leave it there.",
            ],
            "Overthinker": [
                f"Okay, that holds together.",
                "Alright, I'll go with that.",
                "Right — we don't need to keep circling that.",
                "Yeah... okay. We can leave that there.",
            ],
            "Creative": [
                f"Yeah, that comes together.",
                f"Oh, nice. That's clean.",
                "Nice, that settles it.",
                "Yeah, that lands cleanly.",
            ],
        }
        phrases = confirm_pools.get(ptype, confirm_pools["Easygoing"])
        if _prior_ref:
            phrases = list(phrases) + [_prior_ref]

        return {
            "type": "agree",
            "actor": agent.public_id,
            "target": target.public_id,
            "text": self._pick_fresh_phrase(agent, phrases),
            "item": item,
            "reason": "office_confirm",
        }

    def _delegate_event(
        self,
        agent: "SimAgent",
        helper: "SimAgent",
        item: str,
    ) -> Dict[str, Any]:
        self._record_delegation(agent, helper.public_id, item)
        return {
            "type": "say",
            "actor": agent.public_id,
            "target": helper.public_id,
            "text": self._pick_fresh_phrase(
                agent,
                [
                    f"{self._role_name(helper.public_id)}, cover {self._doc_ref(item, definite=True)} while the owner is tied up. Be clear it's provisional.",
                    f"{self._role_name(helper.public_id)}, give me what you have on {self._doc_ref(item, definite=True)} while {self._owner_role(item)} is tied up.",
                    f"{self._role_name(helper.public_id)}, step in on {self._doc_ref(item, definite=True)} and flag it as temporary.",
                ],
            ),
            "reason": "delegate_cover",
            "partial": True,
            "can_complete_task": False,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # Text helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _refuse_text(self, agent: "SimAgent", item: str) -> str:
        doc = self._doc_ref(item)
        ptype = getattr(agent, "personality_type", "Easygoing")

        reason_bank = {
            "budget": [
                "I'm still waiting on finance to lock the numbers",
                "I need final sign-off on the budget before I send it over",
            ],
            "requirements": [
                "I'm checking one last dependency in the requirements",
                "I want to make sure the scope is clean before I share it",
            ],
            "design": [
                "I'm still tightening the design details",
                "I want to sanity-check the latest design pass first",
            ],
            "tech_specs": [
                "I'm still verifying the technical assumptions",
                "I need one more pass on the implementation details",
            ],
        }
        eta_bank = {
            "Leader": ["Give me a moment.", "I'll update you shortly."],
            "Decisive": ["One moment.", "Shortly."],
            "Skeptical": ["Give me a little longer.", "I'll send it once I've verified it."],
            "Overthinker": ["Give me a little longer — I want to get it right.", "Let me do one more check."],
            "Creative": ["Give me a moment to tidy it up.", "Let me tighten this up first."],
            "Easygoing": ["I'll come back with it shortly.", "Give me a moment and I'll send it over."],
        }

        fallback_reasons = [
            f"I'm still finalising {doc}",
            f"I need one more check before I release {doc}",
            f"I'm not ready to confirm {doc} yet",
        ]
        reasons = reason_bank.get(item, fallback_reasons)
        etas = eta_bank.get(ptype, ["Next update."])
        reason = self._pick_fresh_phrase(agent, reasons)
        eta = self._pick_fresh_phrase(agent, etas)
        return f"{reason}. {eta}"

    def _ack_text(self, agent: "SimAgent") -> str:
        ptype = getattr(agent, "personality_type", "Easygoing")
        pools = {
            "Leader": ["Good. Keep it moving.", "Alright, onto the next piece.", "Fine. We can work with that."],
            "Easygoing": ["Okay, that's clearer.", "Nice, that makes more sense.", "Alright, I've got it."],
            "Decisive": ["Good. Next piece.", "Fine. Move on.", "That's enough to use."],
            "Creative": ["Okay, that gives me the shape of it.", "Good, I can place that now.", "Alright, I can build from that."],
            "Skeptical": ["Alright. That's clearer.", "Fine. That's something solid.", "Okay. That's concrete enough."],
            "Overthinker": ["Okay, that clears it up.", "Right, I can track it now.", "That makes it easier to place."],
        }
        return self._pick_fresh_phrase(agent, pools.get(ptype, pools["Easygoing"]))

    def _tension_recovery_text(self, agent: "SimAgent", target_id: str) -> str:
        ptype = getattr(agent, "personality_type", "Easygoing")
        role = self._role_name(target_id)
        pools = {
            "Leader": [f"Let's park that and keep going, {role}.", "We've said enough. Back to the work.", "Leave it there. We need to move."],
            "Easygoing": [f"It's fine, {role}. Let's just keep this moving.", "That got a bit tense. We're okay.", "No point dragging it out. Let's continue."],
            "Decisive": ["Done. Move on.", "Leave it. Next item.", "We don't need to revisit it right now."],
            "Skeptical": ["Fine. Let's continue.", "Noted. Keep going."],
            "Overthinker": ["Alright. Let's get back on track.", "Okay. I just want us to keep this steady."],
            "Creative": ["Let's reset and keep going.", "Okay, let's turn that into progress."],
        }
        return self._pick_fresh_phrase(agent, pools.get(ptype, pools["Easygoing"]))

    def _wrapup_text(self, agent: "SimAgent") -> str:
        ptype = getattr(agent, "personality_type", "Easygoing")
        peak = max((getattr(a, "stress", 0.0) for a in agent.model.agents), default=0.0)
        conflict = getattr(agent.model, "conflict_bonus", 0.0)
        coord = getattr(agent.model, "coord_pressure_bonus", 0.0)
        total_ticks = getattr(agent.model, "tick", 0)
        refusals = getattr(agent.model, "total_refusals", 0)

        if ptype == "Creative" and peak <= 0.55 and conflict <= 0.04:
            return self._pick_fresh_phrase(agent, [
                "Rough first, refine after — that worked fine.",
                "We kept it moving with workable versions. Good enough.",
                "That landed well. Draft first, polish after.",
            ])
        if ptype == "Leader" and peak <= 0.40 and conflict <= 0.02:
            return self._pick_fresh_phrase(agent, [
                "Nice. Everything's in and we stayed aligned.",
                "Good. The team kept it clean and moving.",
                "That's all in. Solid coordination.",
            ])
        if ptype == "Decisive" and total_ticks <= 12:
            return self._pick_fresh_phrase(agent, [
                "Done. Fast enough. Move to execution.",
                "All in. Keep it moving.",
                "Complete. Push to execution.",
            ])
        if ptype == "Skeptical" and (peak > 0.45 or conflict > 0.03):
            return self._pick_fresh_phrase(agent, [
                "Done, but we should align ownership sooner next time.",
                "Complete, but the handoffs needed tighter checks.",
                "We got there. Next time, verify ownership earlier.",
            ])

        if total_ticks <= 12 and conflict <= 0.01 and peak <= 0.25:
            return self._pick_fresh_phrase(agent, [
                "Clean run. Good pace.", "That moved well. Nice work.",
                "Good tempo all the way through.", "Solid run. No wasted time.",
            ])
        if total_ticks <= 12 and conflict > 0.01:
            return self._pick_fresh_phrase(agent, [
                "Fast finish, but we could make it smoother next time.",
                "We got through it quickly, but there was more friction than needed.",
                "Good pace overall. The pushback slowed us more than it should have.",
            ])
        if peak > 0.45 and conflict > 0.02:
            return self._pick_fresh_phrase(agent, [
                "We got it done, but that was a rough run.",
                "Done, but the coordination was heavy all the way through.",
                "We finished it. Next time, less friction.",
            ])
        if peak > 0.45:
            return self._pick_fresh_phrase(agent, [
                "We got it done, but it was a stressful run.",
                "Finished. That took more out of the team than it should have.",
                "Good job pushing it over the line.",
            ])
        if conflict > 0.02 or refusals >= 2:
            if peak > 0.40:
                return self._pick_fresh_phrase(agent, [
                    "We got there, but it was tense.",
                    "Finished — not pretty, but finished.",
                    "That was demanding, but we closed it out.",
                ])
            return self._pick_fresh_phrase(agent, [
                "We finished it, but the handoffs were rough.",
                "Done. Next time, coordinate it better.",
                "We got there. It should feel smoother than that.",
            ])
        if coord > 0.03:
            return self._pick_fresh_phrase(agent, [
                "We got there, but the handoffs were messy.",
                "Done, though ownership could have been clearer.",
                "Good outcome — the handoffs still need tightening.",
            ])
        return self._pick_fresh_phrase(agent, [
            "Alright, that's everything.",
            "Done. Good work.",
            "That should do it.",
            "Okay, we're finished here.",
        ])

    def _owner_or_delegate_text(self, agent: "SimAgent", item: str) -> str:
        owner_role = self._owner_role(item)
        doc = self._doc_ref(item, definite=True)
        be = self._doc_be(doc)
        self._record_guard_line(agent, item)
        return self._pick_fresh_phrase(agent, [
            f"We need {owner_role} to send {doc} directly.",
            f"Go straight to {owner_role} for {doc}.",
            f"{owner_role} is the one who can clear {doc}.",
            f"Let's get {doc} from {owner_role}.",
            f"{owner_role} needs to share {doc} with us.",
        ])

    def _escalation_text(self, agent: "SimAgent", item: str, target_id: str, stage: int) -> str:
        role = self._role_name(target_id)
        doc = self._doc_ref(item)
        short_doc = self._doc_ref(item, short=True)
        if stage <= 0:
            opts = [
                f"{role}, we're waiting on {doc}. What's the hold-up?",
                f"I still need {doc}, {role}. Where are we on it?",
                f"{role}, talk me through the blocker on {short_doc}.",
            ]
        elif stage == 1:
            opts = [
                f"{role}, I need either {doc} or the dependency holding it up.",
                f"{role}, give me a concrete update on {short_doc}.",
                f"I'm still waiting on {doc}, {role}. What's stopping it?",
            ]
        else:
            opts = [
                f"{role}, I need a straight answer on {doc} this tick.",
                f"{role}, we can't keep this open. I need {short_doc} now.",
                f"{role}, this has dragged long enough. Where is {doc}?",
            ]
        return self._pick_fresh_phrase(agent, opts)

    # ──────────────────────────────────────────────────────────────────────────
    # Main decision logic
    # ──────────────────────────────────────────────────────────────────────────

    def choose_action(
        self,
        agent: "SimAgent",
        others: List["SimAgent"],
    ) -> Optional[Dict[str, Any]]:
        self._init_office_state(agent.model)

        ptype = getattr(agent, "personality_type", "Easygoing")
        tick = getattr(agent.model, "tick", 0)
        urgency = getattr(agent.model.environment, "urgency_modifier", 1.0)
        profile = agent._profile()

        recent_actions = sum(
            1 for e in getattr(agent.model, "prev_events", [])
            if e.get("actor") == agent.public_id
        )
        cooldown_mult = 0.65 if recent_actions >= 2 else (0.80 if recent_actions == 1 else 1.0)
        tension_penalty = agent.env_tension_modifier * 0.3

        # ── Refresh memory impressions every 4 ticks (per-agent) ─────────
        if hasattr(agent, "memory") and agent.memory:
            if tick >= 4 and tick - getattr(agent, "_memory_impression_tick", -99) >= 4:
                try:
                    agent.memory.update_impressions(tick)
                    agent._memory_impression_tick = tick
                    # Feed impression patterns back into trust (subtle drift)
                    from app.sim.agent import clamp as _iclamp
                    for _oid, _imp in (agent.memory.impressions or {}).items():
                        _pats = _imp.get("patterns", {})
                        _td = 0.0
                        if "positive" in _pats:
                            _td += 0.015
                        if "conflict_prone" in _pats or "anger_prone" in _pats:
                            _td -= 0.015
                        if _td != 0.0:
                            agent.trust[_oid] = _iclamp(
                                agent.trust.get(_oid, 0.5) + _td, 0.0, 1.0
                            )
                except Exception:
                    pass

        missing = self._priority_missing(agent.model)
        if not missing:
            return None

        current_blocker = missing[0]

        # ── Smooth/creative team: proactive appreciation after a recent share ─────
        # Fires before any ask/confirm logic so it reads as genuine team warmth, not
        # a post-task ritual.  Only one appreciation agree per item, ever.
        _apprec_preset = getattr(agent.model, "team_preset", "balanced_team") or "balanced_team"
        _apprec_bias = PRESET_AGREE_BIAS.get(_apprec_preset, 1.0)
        if _apprec_bias > 1.0:
            _recent_share_for_me = next(
                (e for e in getattr(agent.model, "prev_events", [])[-5:]
                 if e.get("type") == "share_info"
                 and e.get("target") == agent.public_id
                 and e.get("item") in agent.model.scenario.tasks),
                None,
            )
            if _recent_share_for_me:
                _sitem = _recent_share_for_me.get("item")
                _sactor = _recent_share_for_me.get("actor")
                _apprec_key = f"_office_appreciated_{_sitem}"
                _share_agent = next((o for o in others if o.public_id == _sactor), None)
                if (
                    _share_agent
                    and not getattr(agent.model, _apprec_key, False)
                    and random.random() < (_apprec_bias - 1.0) * 0.55
                ):
                    setattr(agent.model, _apprec_key, True)
                    _apprec_pools = {
                        "Leader":      [f"Good. That puts {self._doc_ref(_sitem, short=True)} in order.",
                                        f"Right. {self._doc_ref(_sitem, definite=True).capitalize()} — that's what we needed."],
                        "Easygoing":   [f"Thanks, {self._role_name(_sactor)} — that's exactly what I needed.",
                                        f"Good, that clears up {self._doc_ref(_sitem, short=True)}."],
                        "Creative":    [f"Nice — {self._doc_ref(_sitem, short=True)} makes a lot more sense now.",
                                        f"Thanks, that helps. {self._doc_ref(_sitem, definite=True).capitalize()} fits."],
                        "Decisive":    [f"Good. {self._doc_ref(_sitem, short=True)} confirmed.",
                                        f"That's it for {self._doc_ref(_sitem, short=True)}. Thanks."],
                        "Skeptical":   [f"Alright — that finally makes {self._doc_ref(_sitem, short=True)} clear.",
                                        f"Okay. That lines up with what I needed on {self._doc_ref(_sitem, short=True)}."],
                        "Overthinker": [f"Good — I kept second-guessing {self._doc_ref(_sitem, short=True)}, but that settles it.",
                                        f"Okay, that makes {self._doc_ref(_sitem, short=True)} clearer. Thanks."],
                    }
                    _apprec_text = random.choice(_apprec_pools.get(ptype, [
                        f"Thanks — {self._doc_ref(_sitem, short=True)} is clear now.",
                    ]))
                    return {
                        "type": "agree",
                        "actor": agent.public_id,
                        "target": _sactor,
                        "text": _apprec_text,
                        "item": _sitem,
                        "reason": "cooperative_appreciation",
                    }

        # Track how long the current blocker has been stuck (for final-item fast release)
        _bac = getattr(agent.model, "_office_blocker_age", {})
        if current_blocker not in _bac:
            _bac[current_blocker] = tick
            agent.model._office_blocker_age = _bac
        blocker_age = tick - _bac.get(current_blocker, tick)

        # 1) Confirm pending owner share — check current blocker first, then any other missing item
        _confirm_preset = getattr(agent.model, "team_preset", "balanced_team") or "balanced_team"
        _scrutiny_chal_bias = PRESET_CHALLENGE_BIAS.get(_confirm_preset, 1.0)

        for _ci in ([current_blocker] + [m for m in missing if m != current_blocker]):
            _cp = self._pending_confirm_for_item(agent.model, _ci)
            confirmer_owner_id = _cp.get("owner") if _cp else None
            trust_to_owner = self._trust_to(agent, confirmer_owner_id)
            min_confirm_age = 2 if trust_to_owner < 0.34 else 1
            if (
                _cp
                and self._agent_can_confirm_item(agent, _ci)
                and self._pending_confirm_share_is_old_enough(agent.model, _ci, min_age=min_confirm_age)
            ):
                _ct = next((o for o in others if o.public_id == _cp.get("owner")), None)
                if _ct:
                    # ── Tension/pressure teams scrutinize before accepting ──────────
                    # Fire a challenge instead of a confirm (once per item), then let
                    # the confirm proceed on the next tick.  Progress never permanently
                    # stalls — the scrutiny just adds one tick of friction.
                    _scrutiny_key = f"_office_scrutinized_{_ci}"
                    if (
                        not getattr(agent.model, _scrutiny_key, False)
                        and _scrutiny_chal_bias > 1.0
                        and random.random() < (_scrutiny_chal_bias - 1.0) * 0.35
                    ):
                        setattr(agent.model, _scrutiny_key, True)
                        self._mark_conflict(agent, 0.01)
                        _scrutiny_pools = {
                            "Skeptical":   [f"Before we lock {self._doc_ref(_ci, short=True)} in — has everyone actually checked this?",
                                            f"I need more convincing on {self._doc_ref(_ci, short=True)}. Does this really hold?"],
                            "Decisive":    [f"Let's not rush {self._doc_ref(_ci, short=True)} — I want to validate it first.",
                                            f"{self._doc_ref(_ci, definite=True).capitalize()} needs one more look before we confirm it."],
                            "Overthinker": [f"I keep second-guessing {self._doc_ref(_ci, short=True)}. Can we just confirm it's right?",
                                            f"Something about {self._doc_ref(_ci, short=True)} still feels unresolved to me."],
                            "Leader":      [f"Hold on — {self._doc_ref(_ci, short=True)} needs to be solid before we move on.",
                                            f"I want the team to challenge {self._doc_ref(_ci, short=True)} before we confirm it."],
                        }
                        _scrutiny_text = random.choice(_scrutiny_pools.get(ptype, [
                            f"Let's double-check {self._doc_ref(_ci, short=True)} before confirming.",
                        ]))
                        return {
                            "type": "challenge",
                            "actor": agent.public_id,
                            "target": _ct.public_id,
                            "text": _scrutiny_text,
                            "item": _ci,
                            "reason": "pre_confirm_scrutiny",
                        }

                    _ce = self._confirm_event(agent, _ct, _ci)
                    if _ce:
                        return _ce

        # 1b) Forced release for the blocker if the team has stalled on it.
        if (
            self._is_owner(agent, current_blocker)
            and current_blocker in getattr(agent, "known_items", set())
            and not agent.model._office_revealed.get(current_blocker, False)
            and self._should_force_owner_release(agent, current_blocker)
        ):
            cands = [a for a in others if a.public_id != agent.public_id]
            if cands:
                target = self._best_confirmer_for_item(agent, cands, current_blocker) or cands[0]
                event = self._share_event(agent, target, current_blocker, "forced_release_after_stall")
                if event:
                    return event

        # 1c) After a refusal, bias hard toward a fast recovery share instead of another loop.
        if (
            self._is_owner(agent, current_blocker)
            and current_blocker in getattr(agent, "known_items", set())
            and not agent.model._office_revealed.get(current_blocker, False)
        ):
            last_refusal_tick = getattr(agent.model, "_office_last_refusal_tick", {}).get(current_blocker, -99)
            if 1 <= (tick - last_refusal_tick) <= 2:
                cands = [a for a in others if a.public_id != agent.public_id]
                if cands:
                    target = self._best_confirmer_for_item(agent, cands, current_blocker) or cands[0]
                    forced_text = None
                    if ptype in ("Creative", "Easygoing"):
                        forced_text = self._owner_workaround_share_text(agent, current_blocker, target.public_id)
                    event = self._share_event(
                        agent,
                        target,
                        current_blocker,
                        "post_refusal_recovery_share",
                        forced_text=forced_text,
                    )
                    if event:
                        return event

        # 2) Owner structured refusal intercept
        for item in missing:
            if item != current_blocker:
                continue
            if not self._is_owner(agent, item):
                continue
            if item not in getattr(agent, "known_items", set()):
                continue
            if agent.model._office_revealed.get(item, False):
                continue
            if self._shared_recently(agent, item, within=2):
                continue

            incoming = self._incoming_ask_count(agent, item)
            primary_asker = self._primary_asker_for_item(agent, others, item)
            trust_to_asker = self._trust_to(agent, getattr(primary_asker, "public_id", None))
            if tick > 4 and incoming < 1:
                continue

            hesitate_key = f"_refused_{agent.public_id}_{item}"
            last_refused = getattr(agent.model, hesitate_key, -99)
            if (tick - last_refused) < 2:
                continue

            if incoming >= 2:
                base_refuse_prob = min(0.92, _style(agent, "hesitate", 0.75))
            elif incoming == 1:
                base_refuse_prob = _style(agent, "hesitate", 0.45)
            else:
                base_refuse_prob = _style(agent, "hesitate", 0.18)

            if agent._intervention_strategy_active("cooperative"):
                base_refuse_prob *= 0.08

            # Final-item fast release: sharply lower refusal when only 1 task left and it's been stuck
            if len(missing) == 1 and blocker_age >= 3:
                base_refuse_prob *= 0.18
            elif len(missing) == 1 and blocker_age >= 2:
                base_refuse_prob *= 0.40

            if trust_to_asker >= 0.68:
                base_refuse_prob *= 0.72
            elif trust_to_asker <= 0.32:
                base_refuse_prob *= 1.20

            # ── Memory: impression of the asker modulates refusal ──────────
            if hasattr(agent, "memory") and agent.memory:
                try:
                    _asker_id = getattr(primary_asker, "public_id", None)
                    if _asker_id:
                        _imp = agent.memory.get_impression(_asker_id)
                        if _imp:
                            if "positive" in _imp.get("patterns", {}):
                                base_refuse_prob *= 0.75  # familiar helper → less reluctant
                            if "conflict_prone" in _imp.get("patterns", {}):
                                base_refuse_prob *= 1.20  # friction history → more resistant
                except Exception:
                    pass

            # Post-refusal recovery: boost share probability in the 2 ticks after owner refused
            _lrt = getattr(agent.model, "_office_last_refusal_tick", {}).get(item, -99)
            if 1 <= (tick - _lrt) <= 2:
                base_refuse_prob *= 0.28

            if random.random() < base_refuse_prob:
                asker = primary_asker
                if not asker and incoming >= 1:
                    for e in reversed(getattr(agent.model, "prev_events", [])[-8:]):
                        if e.get("type") == "ask_info" and e.get("target") == agent.public_id:
                            asker = next((o for o in others if o.public_id == e.get("actor")), None)
                            if asker:
                                break
                if not asker:
                    asker = max(others, key=lambda o: agent.trust.get(o.public_id, 0.4), default=None)
                if asker:
                    setattr(agent.model, hesitate_key, tick)
                    agent.model.total_refusals = getattr(agent.model, "total_refusals", 0) + 1
                    _lrt_cache = getattr(agent.model, "_office_last_refusal_tick", {})
                    _lrt_cache[item] = tick
                    agent.model._office_last_refusal_tick = _lrt_cache
                    self._mark_conflict(agent, 0.01)
                    return {
                        "type": "refuse",
                        "actor": agent.public_id,
                        "target": asker.public_id,
                        "text": self._refuse_text(agent, item),
                        "item": item,
                        "reason": "structured_refusal",
                    }

        # 3) Early coordination opener
        if tick <= 3:
            if ptype == "Leader" and tick == 1 and random.random() < 0.90 and others:
                tgt = random.choice([a for a in others if a.public_id != agent.public_id])
                return {
                    "type": "say",
                    "actor": agent.public_id,
                    "target": tgt.public_id,
                    "text": self._pick_fresh_phrase(agent, [
                        "Let's split this up. Everyone bring their piece in.",
                        "Quick pass round the table — if you own it, call it out.",
                        "Let's get the key docs on the table and move.",
                    ]),
                    "reason": "leader_coord_opening",
                }

            if ptype in ("Leader", "Easygoing", "Decisive", "Creative"):
                own_items = [
                    t for t in agent.known_items
                    if t == current_blocker
                    and t in agent.model.scenario.tasks
                    and not agent.model.scenario.tasks.get(t, False)
                    and self._is_owner(agent, t)
                    and not agent.model._office_revealed.get(t, False)
                ]
                if own_items and random.random() < _style(agent, "share", 0.72):
                    item = random.choice(own_items)
                    cands = [a for a in others if a.public_id != agent.public_id]
                    if cands:
                        tgt = self._best_confirmer_for_item(agent, cands, item) or random.choice(cands)
                        event = self._share_event(agent, tgt, item, "coord_phase_share")
                        if event:
                            return event

        # 4) Ask/share loop focused on current blocker
        unknown = [current_blocker] if current_blocker not in agent.known_items else []
        if unknown:
            needed = current_blocker

            # If the item was already shared this tick (by another agent before us),
            # _office_revealed is already True — don't ask for something just shared.
            if agent.model._office_revealed.get(needed, False):
                return None

            if self._item_recently_addressed(agent.model, needed):
                return None

            # If a valid pending confirm already exists and I'm not the confirmer, back off.
            # Let the confirmer do their job — extra asks and guard lines only add noise.
            _pc_now = self._pending_confirm_for_item(agent.model, needed)
            if _pc_now and not self._agent_can_confirm_item(agent, needed):
                return None

            target = agent._pick_best_target_for_item(needed, others)

            if target and target.public_id != agent.public_id:
                owner_id = self._owner_id(needed)
                preferred_requester_id = self._preferred_requester_id(needed)
                active_requester_id = self._recent_requester_id_for_item(agent.model, needed, within=2)
                if (
                    target.public_id == owner_id
                    and not active_requester_id
                    and preferred_requester_id
                    and agent.public_id != preferred_requester_id
                ):
                    return None
                if (
                    target.public_id == owner_id
                    and active_requester_id
                    and active_requester_id != agent.public_id
                ):
                    return None

                ask_key = (agent.public_id, target.public_id, needed)
                ask_count = getattr(agent.model, "global_ask_counts", {}).get(ask_key, 0)
                trust_to_target = self._trust_to(agent, target.public_id)

                if target.public_id != owner_id and agent.public_id != "A1":
                    self._mark_coord_pressure(agent, 0.012)
                if ask_count >= 1:
                    self._mark_coord_pressure(agent, 0.005 * ask_count)

                owner_ask_total = sum(
                    c for (a, t, it), c in getattr(agent.model, "global_ask_counts", {}).items()
                    if t == owner_id and it == needed
                )
                if owner_ask_total >= 2 and not agent.model._office_revealed.get(needed, False):
                    self._mark_coord_pressure(agent, 0.020)

                cooldown_key = f"_ask_cd_{agent.public_id}_{needed}"
                last_asked = getattr(agent.model, cooldown_key, -99)

                recent_doc_pressure = self._count_recent_doc_mentions(agent.model, needed, within=6)
                if recent_doc_pressure >= 3:
                    self._mark_coord_pressure(agent, 0.005 * min(recent_doc_pressure, 6))
                if ask_count >= 2:
                    self._mark_coord_pressure(agent, 0.008 * (ask_count - 1))

                if (tick - last_asked) < 3:
                    if target.public_id == owner_id and agent.public_id == preferred_requester_id:
                        return None
                    # Suppress guard lines when: pending confirm exists, fired recently, or random gate
                    _pc_guard = self._pending_confirm_for_item(agent.model, needed) is not None
                    if not _pc_guard and not self._guard_recently(agent, needed, within=6) and random.random() < 0.45:
                        return {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": self._owner_or_delegate_text(agent, needed),
                            "reason": "ownership_guard",
                        }
                    return None

                overthinker_hesitate_prob = 0.32
                if agent.public_id == preferred_requester_id:
                    overthinker_hesitate_prob = 0.10
                if ptype == "Overthinker" and ask_count == 0 and random.random() < overthinker_hesitate_prob:
                    return {
                        "type": "say",
                        "actor": agent.public_id,
                        "target": target.public_id,
                        "text": self._pick_fresh_phrase(agent, [
                            f"I keep circling back to {self._doc_ref(needed, definite=True)}. Do we already have a version of it?",
                            f"Before I chase anything else — does anyone have {self._doc_ref(needed, definite=True)} ready?",
                            f"I'm still waiting for {self._doc_ref(needed, definite=True)} to land.",
                        ]),
                        "reason": "overthinker_hesitate",
                    }

                skeptical_delay_prob = 0.22
                if agent.public_id == preferred_requester_id:
                    skeptical_delay_prob = 0.08
                if ptype == "Skeptical" and ask_count == 0 and random.random() < skeptical_delay_prob:
                    return {
                        "type": "say",
                        "actor": agent.public_id,
                        "target": target.public_id,
                        "text": self._pick_fresh_phrase(agent, [
                            f"Before we keep chasing this, who's actually holding {self._doc_ref(needed, definite=True)}?",
                            f"I want to make sure {self._doc_ref(needed, definite=True)} is with the right owner first.",
                            f"Let's be clear on ownership for {self._doc_ref(needed, short=True)}.",
                        ]),
                        "reason": "skeptical_delay",
                    }

                threshold = CHALLENGE_ASK_THRESHOLD.get(ptype, 4)
                # Team preset: tension/pressure teams challenge after fewer asks;
                # smooth teams are patient and need more asks before escalating.
                _chal_preset_bias = PRESET_CHALLENGE_BIAS.get(
                    getattr(agent.model, "team_preset", "balanced_team") or "balanced_team", 1.0
                )
                if _chal_preset_bias > 1.2:
                    threshold = max(1, threshold - 2)   # tension: challenge sooner
                elif _chal_preset_bias > 1.0:
                    threshold = max(1, threshold - 1)   # pressure: challenge a bit sooner
                elif _chal_preset_bias < 0.8:
                    threshold = threshold + 1           # smooth: patient, more asks needed
                if trust_to_target <= 0.32:
                    threshold = max(1, threshold - 1)
                elif trust_to_target >= 0.68:
                    threshold += 1
                if ask_count >= threshold and random.random() < _style(agent, "challenge", 0.12 * _chal_preset_bias):
                    self._mark_conflict(agent, 0.01)
                    return {
                        "type": "challenge",
                        "actor": agent.public_id,
                        "target": target.public_id,
                        "text": self._challenge_text(agent, ptype, needed, target.public_id),
                        "preference": needed,
                        "reason": "escalation",
                    }

                if ptype == "Leader" and ask_count >= 2:
                    owner_id = self._owner_id(needed)
                    if target.public_id == owner_id:
                        stage = min(2, ask_count - 2)
                        return {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": self._escalation_text(agent, needed, target.public_id, stage),
                            "reason": "pressure_escalation",
                        }
                    delegate_candidates = [
                        a for a in others
                        if a.public_id != owner_id
                        and a.public_id != agent.public_id
                        and needed in getattr(a, "known_items", set())
                        and not self._partial_already_done(a, needed)
                    ]
                    if (
                        delegate_candidates
                        and self._owner_stalled(agent.model, needed)
                        and ask_count >= 2
                        and not agent.model._office_revealed.get(needed, False)
                    ):
                        helper = max(
                            delegate_candidates,
                            key=lambda a: agent.trust.get(a.public_id, 0.4),
                        )
                        self._mark_coord_pressure(agent, 0.01)
                        return self._delegate_event(agent, helper, needed)

                if ptype == "Decisive" and ask_count >= 3:
                    self._mark_conflict(agent, 0.01)
                    return {
                        "type": "say",
                        "actor": agent.public_id,
                        "target": target.public_id,
                        "text": self._pick_fresh_phrase(agent, [
                            f"I need {self._doc_ref(needed)} now.",
                            f"We're stuck until {self._doc_ref(needed)} lands.",
                            f"No more circling — I need {self._doc_ref(needed)}.",
                        ]),
                        "reason": "decisive_ultimatum",
                    }

                creative_reframe_prob = _style(agent, "reframe", 0.20)
                if blocker_age >= 1:
                    creative_reframe_prob += 0.10
                if trust_to_target >= 0.58:
                    creative_reframe_prob += 0.08
                if target.public_id == self._owner_id(needed):
                    creative_reframe_prob += 0.04

                if ptype == "Creative" and ask_count >= 1 and random.random() < min(0.85, creative_reframe_prob):
                    if self._can_reframe(agent, needed):
                        self._increment_reframe(agent, needed)
                        return {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": self._pick_fresh_phrase(agent, [
                                f"Could we unblock {self._doc_ref(needed, definite=True)} with a rough version first?",
                                f"If the final version isn't ready, can we at least get a working cut of {self._doc_ref(needed, definite=True)}?",
                                f"Can we get something usable on {self._doc_ref(needed, short=True)} and tighten it after?",
                                f"Let's use the draft of {self._doc_ref(needed, definite=True)} and refine after.",
                                f"Can you send the current cut of {self._doc_ref(needed, definite=True)} so we can keep moving?",
                            ]),
                            "reason": "creative_reframe",
                        }
                    return {
                        "type": "ask_info",
                        "actor": agent.public_id,
                        "target": target.public_id,
                        "text": self._force_direct_text(agent, needed, target.public_id),
                        "item": needed,
                        "reason": "creative_forced_direct",
                    }

                initiate_prob = _style(
                    agent,
                    "ask",
                    0.80 * profile["initiate_chance_mult"] * cooldown_mult
                    - tension_penalty
                    + (urgency * 0.15),
                )
                initiate_prob += (trust_to_target - 0.5) * 0.22
                if active_requester_id and active_requester_id != agent.public_id and target.public_id == owner_id:
                    initiate_prob *= 0.25
                initiate_prob = max(0.02, min(0.95, initiate_prob))
                if random.random() < initiate_prob:
                    setattr(agent.model, cooldown_key, tick)
                    return {
                        "type": "ask_info",
                        "actor": agent.public_id,
                        "target": target.public_id,
                        "text": self.generate_ask_text(agent, needed, target.public_id),
                        "item": needed,
                        "reason": "need information",
                    }

        # 5) Proactive owner share
        own_incomplete = [
            i for i in agent.known_items
            if i == current_blocker
            and i in agent.model.scenario.tasks
            and not agent.model.scenario.tasks.get(i, False)
            and self._is_owner(agent, i)
            and not agent.model._office_revealed.get(i, False)
        ]
        proactive_share_prob = _style(
            agent, "share",
            (0.07 + 0.20 * urgency) * profile["initiate_chance_mult"] - tension_penalty,
        )
        recent_requester_id = self._recent_requester_id_for_item(agent.model, current_blocker, within=3)
        preferred_requester_id = self._preferred_requester_id(current_blocker)
        preferred_requester = next(
            (a for a in others if a.public_id == preferred_requester_id),
            None,
        )
        trust_to_preferred = self._trust_to(agent, getattr(preferred_requester, "public_id", None))

        if ptype in ("Leader", "Decisive"):
            proactive_share_prob += 0.12
        if ptype == "Creative" and blocker_age >= 1:
            proactive_share_prob += 0.18
        if ptype == "Overthinker" and recent_requester_id:
            proactive_share_prob += 0.14
        if ptype == "Skeptical" and recent_requester_id:
            proactive_share_prob += 0.08
        if recent_requester_id and ptype in ("Creative", "Easygoing"):
            proactive_share_prob += 0.08
        if trust_to_preferred >= 0.58:
            proactive_share_prob += 0.08
        # boost_urgency intervention: raise the chance the owner shares now
        _urgency_boost = getattr(agent.model, "_urgency_share_boost", 0.0)
        _urgency_until = getattr(agent.model, "_urgency_share_boost_until", -1)
        if _urgency_boost > 0 and getattr(agent.model, "tick", 0) <= _urgency_until:
            proactive_share_prob += _urgency_boost * 0.45
        proactive_share_prob = max(0.02, min(0.95, proactive_share_prob))

        if own_incomplete and random.random() < proactive_share_prob:
            item = random.choice(own_incomplete)
            cands = [a for a in others if a.public_id != agent.public_id]
            if cands:
                tgt = self._best_confirmer_for_item(agent, cands, item) or random.choice(cands)
                forced_text = None
                if ptype == "Creative" and (blocker_age >= 1 or recent_requester_id):
                    forced_text = self._owner_workaround_share_text(agent, item, tgt.public_id)
                event = self._share_event(
                    agent,
                    tgt,
                    item,
                    "proactive_owner_share",
                    forced_text=forced_text,
                )
                if event:
                    return event

        # 6) Managed partial share
        partial_items = [
            i for i in agent.known_items
            if i in agent.model.scenario.tasks
            and not agent.model.scenario.tasks.get(i, False)
            and not self._is_owner(agent, i)
            and not self._partial_already_done(agent, i)
        ]
        if partial_items and current_blocker in partial_items and random.random() < 0.012:
            item = current_blocker
            if self._can_non_owner_share(agent, item):
                cands = [a for a in others if a.public_id != agent.public_id]
                if cands:
                    tgt = random.choice(cands)
                    self._mark_coord_pressure(agent, 0.01)
                    event = self._share_event(
                        agent, tgt, item, "managed_non_owner_share",
                        forced_text=self._build_non_owner_share_text(agent, item, tgt.public_id),
                    )
                    if event:
                        return event
            if (
                self._delegated_recently(agent, item)
                and not self._guard_recently(agent, item, within=4)
                and random.random() < 0.45
            ):
                tgt = random.choice([a for a in others if a.public_id != agent.public_id])
                self._mark_coord_pressure(agent, 0.015)
                return {
                    "type": "say",
                    "actor": agent.public_id,
                    "target": tgt.public_id,
                    "text": self._owner_or_delegate_text(agent, item),
                    "reason": "partial_cross_role_reference",
                }

        # 7) Light social
        return self._social_action(agent, others)

    # ──────────────────────────────────────────────────────────────────────────
    # Pivot / challenge / social
    # ──────────────────────────────────────────────────────────────────────────

    def _pivot_action(self, agent: "SimAgent", others: List["SimAgent"], needed: str):
        return None

    def _challenge_text(self, agent: "SimAgent", ptype: str, needed: str, target_id: str) -> str:
        role = self._role_name(target_id)
        doc = self._doc_ref(needed)
        if ptype == "Decisive":
            return self._pick_fresh_phrase(agent, [
                f"{role}, I've asked more than once. Where is {doc}?",
                f"{role}, I need a clear answer on {doc} now.",
                f"I've been waiting on {doc}, {role}. What's the hold-up?",
            ])
        if ptype == "Skeptical":
            return self._pick_fresh_phrase(agent, [
                f"{role}, I'm still not convinced {doc} {self._doc_be(doc)} actually ready.",
                f"{role}, I need a straight answer on {doc}.",
                f"I need to know where {doc} actually stand{self._doc_verb(doc, 's')}, {role}.",
            ])
        return self._pick_fresh_phrase(agent, [
            f"{role}, I've asked about {doc} more than once. What's going on?",
            f"We're burning time on {doc}, {role}.",
        ])

    def _social_action(self, agent: "SimAgent", others: List["SimAgent"]):
        urgency = getattr(agent.model.environment, "urgency_modifier", 1.0)
        if urgency > 0.7:
            return None

        missing = self._priority_missing(agent.model)
        if missing:
            blocker = missing[0]
            pending = self._pending_confirm_for_item(agent.model, blocker)
            if pending is not None:
                return None

        available = [a for a in others if a.public_id != agent.public_id]
        if not available:
            return None

        soc = random.choice(available)
        trust = agent.trust.get(soc.public_id, 0.5)

        recent_helpful = any(
            m.get("kind") in ("share_info", "help") and m.get("from") == soc.public_id
            for m in list(agent.stm)[-3:]
        )
        recent_full_share = self._recent_relevant_share_exists(agent, soc.public_id)
        recent_share_was_partial = self._recent_share_was_partial(agent, soc.public_id)

        if trust > 0.60 and recent_helpful and random.random() < 0.04:
            if recent_share_was_partial:
                item = self._find_recent_share_item(agent, soc.public_id)
                return {
                    "type": "say",
                    "actor": agent.public_id,
                    "target": soc.public_id,
                    "text": self._pick_fresh_phrase(agent, [
                        f"That helps — I still need {self._owner_role(item)} to sign it off." if item else "That helps.",
                        "Okay, that's enough to work from temporarily.",
                        "Okay, that's enough to work from temporarily.",
                    ]),
                    "reason": "soft_ack_partial_share",
                }
            if recent_full_share:
                return {
                    "type": "compliment",
                    "actor": agent.public_id,
                    "target": soc.public_id,
                    "text": self._pick_fresh_phrase(agent, [
                        f"Good handoff, {self._role_name(soc.public_id)}.",
                        "Nice — that moved us forward.",
                        "Good, that landed well.",
                        f"Solid update, {self._role_name(soc.public_id)}.",
                    ]),
                    "reason": "positive_reinforcement",
                }

        conflict_bonus = getattr(agent.model, "conflict_bonus", 0.0)
        recent_conflict = any(
            e.get("type") in ("challenge", "refuse") and e.get("actor") == soc.public_id
            for e in getattr(agent.model, "prev_events", [])[-3:]
        )
        if conflict_bonus > 0.03 and recent_conflict and random.random() < 0.04:
            return {
                "type": "say",
                "actor": agent.public_id,
                "target": soc.public_id,
                "text": self._tension_recovery_text(agent, soc.public_id),
                "reason": "tension_recovery",
            }

        if (
            self._last_target_line_exists(agent, soc.public_id)
            and (
                self._recent_relevant_share_exists(agent, soc.public_id, within=2)
                or self._recent_share_was_partial(agent, soc.public_id, within=2)
            )
            and random.random() < 0.01
        ):
            return {
                "type": "say",
                "actor": agent.public_id,
                "target": soc.public_id,
                "text": self._ack_text(agent),
                "reason": "contextual_ack",
            }

        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Base overrides
    # ──────────────────────────────────────────────────────────────────────────

    def should_share(
        self,
        agent: "SimAgent",
        target: "SimAgent",
        item: str,
        message_text: str = "",
    ) -> Optional[bool]:
        # The office scenario uses its own share pipeline so tasks do not bypass
        # pending-confirm, ownership, and partial-share rules via generic agent logic.
        return False

    def reply_to_info_request(
        self,
        agent: "SimAgent",
        target: "SimAgent",
        item: str,
        message_text: str,
    ) -> Optional[Dict[str, Any]]:
        self._init_office_state(agent.model)
        model = agent.model

        if model.scenario.tasks.get(item, False):
            return None

        if self._is_owner(agent, item):
            if model._office_revealed.get(item, False):
                pending = self._pending_confirm_for_item(model, item)
                if pending:
                    confirmer_id = pending.get("confirmer")
                    share_tick = pending.get("share_tick", -99)
                    current_tick = getattr(model, "tick", 0)
                    # Only remind the actual confirmer, and only after a 2-tick gap
                    if confirmer_id == target.public_id and current_tick - share_tick >= 2:
                        doc = self._doc_ref(item, definite=True)
                        be = self._doc_be(doc)
                        return {
                            "type": "say",
                            "actor": agent.public_id,
                            "target": target.public_id,
                            "text": self._pick_fresh_phrase(
                                agent,
                                [
                                    f"You've got {doc} — once you've given {self._doc_pronoun(doc)} a look, we're done.",
                                    f"{doc} {be} with you now. Ping me when it's sorted.",
                                    f"That's {doc} over to you — just sign {self._doc_pronoun(doc)} off when you can.",
                                    f"Take a look at {doc} when you get a moment and we'll close {self._doc_pronoun(doc)} out.",
                                ],
                            ),
                            "reason": "awaiting_confirm",
                        }
                # Already shared — don't refuse or produce noise for other requesters
                return None

            others = [a for a in model.agents if a.public_id != agent.public_id]
            primary_requester = self._primary_asker_for_item(agent, others, item)
            primary_requester_id = getattr(primary_requester, "public_id", None)
            active_requester_id = self._recent_requester_id_for_item(model, item, within=2)
            preferred_requester_id = self._preferred_requester_id(item)
            if (
                primary_requester_id
                and active_requester_id == primary_requester_id
                and target.public_id != primary_requester_id
            ):
                return {
                    "type": "say",
                    "actor": agent.public_id,
                    "target": target.public_id,
                    "text": self._pick_fresh_phrase(
                        agent,
                        [
                            f"{self._role_name(primary_requester_id)} is already closing {self._doc_ref(item, definite=True)} with me.",
                            f"I'm sending {self._doc_ref(item, definite=True)} through {self._role_name(primary_requester_id)} so the handoff stays clean.",
                            f"{self._role_name(primary_requester_id)} has the thread on {self._doc_ref(item, definite=True)}. I'll close it there.",
                        ],
                    ),
                    "reason": "active_requester_loop",
                }

            if (
                preferred_requester_id
                and target.public_id == preferred_requester_id
                and primary_requester_id != preferred_requester_id
            ):
                primary_requester_id = preferred_requester_id

            incoming = self._incoming_ask_count(agent, item)
            blocker_age = self._current_blocker_age(model, item)
            rough_cut = self._rough_cut_requested(message_text)
            ptype = getattr(agent, "personality_type", "Easygoing")
            trust_to_target = self._trust_to(agent, target.public_id)

            release_prob = 0.30
            release_prob += min(incoming, 3) * 0.16
            if blocker_age >= 2:
                release_prob += 0.14
            if rough_cut:
                release_prob += 0.16
            if getattr(agent, "stress", 0.0) >= 0.55:
                release_prob += 0.10
            if target.public_id == primary_requester_id:
                release_prob += 0.18
            if trust_to_target >= 0.70:
                release_prob += 0.14
            elif trust_to_target >= 0.58:
                release_prob += 0.07
            elif trust_to_target <= 0.32:
                release_prob -= 0.14
            elif trust_to_target <= 0.42:
                release_prob -= 0.06

            release_prob += {
                "Leader": 0.08,
                "Decisive": 0.10,
                "Easygoing": 0.12,
                "Creative": 0.12,
                "Skeptical": -0.05,
                "Overthinker": -0.08,
            }.get(ptype, 0.0)

            # Pressure-team office: after a single refusal on an item, the
            # owner should stop stalling. Pressure teams should feel like
            # "more urgency, fewer delays" rather than "high pressure but
            # everyone still waits around."
            if getattr(model, "team_preset", None) == "pressure_team":
                prior_refusals = sum(
                    1
                    for ev in (getattr(model, "prev_events", []) or [])
                    if ev.get("type") == "refuse"
                    and ev.get("actor") == agent.public_id
                    and ev.get("item") == item
                )
                if prior_refusals >= 1:
                    release_prob = max(release_prob, 0.92)

            if self._should_force_owner_release(agent, item):
                release_prob = 1.0
            if agent._intervention_strategy_active("cooperative"):
                release_prob = max(release_prob, 0.98)

            release_prob = max(0.05, min(1.0, release_prob))
            if random.random() < release_prob:
                forced_text = None
                if (rough_cut or (ptype == "Creative" and blocker_age >= 1)) and ptype in ("Creative", "Easygoing"):
                    forced_text = self._owner_workaround_share_text(agent, item, target.public_id)
                event = self._share_event(
                    agent,
                    target,
                    item,
                    "reply_owner_share",
                    forced_text=forced_text,
                )
                if event:
                    return event

            return {
                "type": "refuse",
                "actor": agent.public_id,
                "target": target.public_id,
                "text": self._refuse_text(agent, item),
                "item": item,
                "reason": "structured_refusal",
            }

        if self._can_non_owner_share(agent, item):
            event = self._share_event(
                agent,
                target,
                item,
                "managed_non_owner_share",
                forced_text=self._build_non_owner_share_text(agent, item, target.public_id),
            )
            if event:
                return event

        return {
            "type": "say",
            "actor": agent.public_id,
            "target": target.public_id,
            "text": self._owner_or_delegate_text(agent, item),
            "reason": "ownership_guard",
        }

    def should_complete_on_agree(self, model: "SimModel", preference: str) -> bool:
        return False

    def task_to_complete(self, model: "SimModel", preference: str):
        return None

    def build_final_decision(self, model: "SimModel") -> str:
        return ""

    # ──────────────────────────────────────────────────────────────────────────
    # Scenario info text
    # ──────────────────────────────────────────────────────────────────────────

    def info_text(self, item: str) -> Optional[str]:
        texts = {
            "budget": [
                "$50k total, with 10% held back.",
                "$50k overall, with a small buffer for extra costs.",
                "$50,000 total. We are keeping 10% back just in case.",
            ],
            "requirements": [
                "it needs mobile access and offline mode.",
                "the key requirements are mobile use and offline support.",
                "it has to work on mobile and offline.",
                "the client needs mobile support, and it also has to work offline.",
                "the main requirements are mobile access and offline use.",
                "the proposal needs to cover mobile support and offline use.",
            ],
            "design": [
                "we're going with a flat, modern UI — blue colour scheme throughout.",
                "flat design, clean layout, and the primary colour is blue.",
                "modern flat UI with a blue theme — nothing too complicated visually.",
            ],
            "tech_specs": [
                "the stack is React on the frontend, Node for the backend, PostgreSQL for the database.",
                "React, Node.js, and PostgreSQL — that's the stack.",
                "frontend in React, backend in Node, and PostgreSQL handling the data layer.",
            ],
            "frontend": ["the frontend role is mainly UI and UX — someone who knows their way around design systems."],
            "backend": ["backend needs someone comfortable with APIs and database design."],
            "testing": ["testing is QA and automation — we need someone who can write test suites."],
            "documentation": ["documentation covers the technical specs and user-facing guides."],
        }
        opts = texts.get(item)
        return random.choice(opts) if opts else None

    # ──────────────────────────────────────────────────────────────────────────
    # Text generation
    # ──────────────────────────────────────────────────────────────────────────

    def generate_ask_text(self, agent: "SimAgent", item: str, target_id: str) -> str:
        urgency = getattr(agent.model.environment, "urgency_modifier", 1.0)
        ptype = getattr(agent, "personality_type", "Easygoing")
        ask_key = (agent.public_id, target_id, item)
        ask_count = getattr(agent.model, "global_ask_counts", {}).get(ask_key, 0)
        role = self._role_name(target_id)
        doc = self._doc_ref(item)
        short_doc = self._doc_ref(item, short=True)

        pools = {
            "Leader": {
                0: [f"{role}, what do you have on {short_doc}?", f"{role}, I need {doc}. Do you have it?"],
                1: [f"I'm still waiting on {short_doc}, {role}. What's the status?", f"{role}, I need {doc} or the blocker that's holding it up."],
                2: [f"{role}, give me a concrete update on {short_doc}.", f"{role}, I need a straight answer on {doc}."],
            },
            "Decisive": {
                0: [f"{role} — do you have {doc}?", f"Quick one: {short_doc}, do you have it?"],
                1: [f"Still waiting on {doc}, {role}. Can we close it?", f"Still need {short_doc}, {role}."],
                2: [f"{role}, I need {doc} now.", f"{role}, we are stuck until {short_doc} lands."],
            },
            "Easygoing": {
                0: [f"Hey {role}, do you have {self._doc_ref(item, definite=True)}?", f"When you get a second, could you send over {self._doc_ref(item, definite=True)}?"],
                1: [f"Still missing {self._doc_ref(item, definite=True)} — do you have it handy?", f"{role}, could you send {self._doc_ref(item, definite=True)} across?"],
                2: [f"We're nearly there — I just need {self._doc_ref(item, definite=True)} from you.", f"Still waiting on {short_doc}, {role}."],
            },
            "Skeptical": {
                0: [f"{role}, do you actually have {self._doc_ref(item, definite=True)} ready?", f"I need to know whether {self._doc_ref(item, definite=True)} {self._doc_be(doc)} real or still in progress."],
                1: [f"I'm asking again because I still don't know if {short_doc} {self._doc_verb(short_doc, 'is')} actually covered.", f"I need to know where {short_doc} stand{self._doc_verb(short_doc, 's')}, {role}."],
                2: [f"{role}, I need a clear answer on {doc}.", f"I'm still not convinced {doc} {self._doc_be(doc)} in hand, {role}."],
            },
            "Overthinker": {
                0: [f"{role}, do you maybe have {short_doc} ready?", f"I think we're still waiting on {self._doc_ref(item, definite=True)} — is that with you?"],
                1: [f"Sorry to come back to it — {self._doc_be(doc)} {self._doc_ref(item, definite=True)} still with you?", f"We might still be waiting on {self._doc_ref(item, definite=True)} — can you confirm?"],
                2: [f"I feel like we're stuck on {self._doc_ref(item, definite=True)}.", f"Can we just close {self._doc_ref(item, definite=True)} out so we can move on?"],
            },
            "Creative": {
                0: [f"{role}, can you share {self._doc_ref(item, definite=True)}?", f"What's the latest on {doc}, {role}?"],
                1: [f"Still waiting on {self._doc_ref(item, definite=True)}. Can you send what you have?", f"{role}, can we use what you have so far on {self._doc_ref(item, short=True)}?"],
                2: [f"If the final version isn't ready, can you send what you have on {doc}?", f"{role}, can we get something usable on {short_doc} now and tidy it up later?"],
            },
        }

        pool = pools.get(ptype, pools["Easygoing"])
        stage = min(ask_count, 2)
        opts = pool.get(stage, pool.get(0, [f"Do you have {doc}, {role}?"]))

        if urgency > 0.75:
            opts = [f"{role}, I need {doc} now.", f"We're running short on time — do you have {short_doc}?", f"{role}, quick one: {short_doc}?"] + opts

        return self._pick_fresh_phrase(agent, opts)

    def generate_share_text(self, agent: "SimAgent", item: str, target_id: str) -> str:
        urgency = getattr(agent.model.environment, "urgency_modifier", 1.0)
        ptype = getattr(agent, "personality_type", "Easygoing")
        info = self.info_text(item) or f"I have information about {_lbl(item)}."
        info_cap = info[:1].upper() + info[1:] if info else info

        first_share_pools = {
            "Leader":     [f"Here it is: {info}", f"Here: {info}", f"This is the latest: {info}"],
            "Decisive":   [f"Here: {info}", f"Take this: {info}", f"{info_cap}"],
            "Easygoing":  [f"Yep, here: {info}", f"Sure, here you go: {info}", f"Here's what I've got: {info}"],
            "Skeptical":  [f"Here. Give it another look: {info}", f"Sending it, but look it over: {info}", f"Run your eye over this: {info}"],
            "Overthinker":[f"Okay, sending it: {info}", f"This looks right: {info}", f"Here, unless I've missed something: {info}"],
            "Creative":   [f"Try this: {info}", f"Here's my pass: {info}", f"This should work: {info}"],
        }

        if not self._is_owner(agent, item):
            opts = [self._build_non_owner_share_text(agent, item, target_id)] if self._can_non_owner_share(agent, item) else [self._owner_or_delegate_text(agent, item)]
        else:
            opts = first_share_pools.get(ptype, first_share_pools["Easygoing"])

        if urgency > 0.75:
            opts = [f"Short version: {info}", f"No delay. {info}"] + opts

        return self._pick_fresh_phrase(agent, opts)

    def generate_say_text(self, agent: "SimAgent", target_id: str) -> str:
        target_role = self._role_name(target_id)
        urgency = getattr(agent.model.environment, "urgency_modifier", 1.0)
        avg_trust = sum(agent.trust.values()) / max(1, len(agent.trust))

        if agent.stress > 0.60 or urgency > 0.70:
            opts = [f"{target_role}, we need a straight answer.", "We're blocked until this closes.", f"{target_role}, this has to land.", "Clock's tight — move."]
        elif agent.stress < 0.25 and avg_trust > 0.55:
            opts = [f"{target_role}, we're tracking well.", "Let's keep the pace.", f"Solid so far, {target_role}.", "Steady — keep going."]
        else:
            opts = [f"{target_role}, let's keep this moving.", f"Stay tight on the remaining items, {target_role}.", "Still waiting on a couple of pieces.", "Let's not drop the thread."]

        return self._pick_fresh_phrase(agent, opts)

    def generate_help_text(self, agent: "SimAgent", target_id: str, item: str) -> str:
        target_role = self._role_name(target_id)
        opts = [
            f"{target_role}, I'm on {self._doc_ref(item)} — give me a sec.",
            f"I'll close out {self._doc_ref(item)}, {target_role}.",
            f"{target_role}, {self._doc_ref(item)} is with me — nearly there.",
            f"I've got {self._doc_ref(item)}, {target_role}. Pushing it across.",
            f"{target_role}, not dropped — working through {self._doc_ref(item)} now.",
        ]
        return self._pick_fresh_phrase(agent, opts)

    def generate_ignore_text(self, agent: "SimAgent", target_id: str) -> str:
        target_role = self._role_name(target_id)
        opts = [f"{target_role}, I'll loop back.", "Can't split focus right now.", "Not the moment — hold that."]
        return self._pick_fresh_phrase(agent, opts)

    def generate_insult_text(self, agent: "SimAgent", target_id: str) -> str:
        target_role = self._role_name(target_id)
        opts = [f"{target_role}, you're making this harder than it needs to be.", f"This is why we're stuck, {target_role}.", f"{target_role}, that didn't help.", f"You're the handoff holding us up, {target_role}."]
        return self._pick_fresh_phrase(agent, opts)
