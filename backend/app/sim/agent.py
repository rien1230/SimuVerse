"""Core agent behaviour: choices, event handling, and per-tick updates."""

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Set, TypedDict


class AgentState(TypedDict):
    id: str
    name: str
    role: str
    personality: str
    strategy: str
    trust: Dict[str, float]
    known_items: List[str]
    mood: Dict[str, float]
    stress: float
    emotional_stress: float
    coord_pressure: float
    conflict_level: float
    last_detected_emotion: Optional[str]
    goal_progress: float
    in_conversation_with: Optional[str]
    last_thought: Optional[str]

import random
import mesa

from app.sim.scenario_data import ITEM_LABELS, ITEM_INFO_TEMPLATES, SCENARIO_ROLES
from app.sim.emotions_analyser import EmotionAnalyser
from app.sim.memory import EmotionalMemory
from app.sim.scenario_logic.base_logic import get_env_rules, get_env_dialogue, ENVIRONMENT_DIALOGUE
from app.sim.dialogue_banks import pick_line, get_tone


def _lbl(item: str) -> str:
    return ITEM_LABELS.get(item, item.replace("_", " ").title())


def _role(agent_id: str, scenario_id: str) -> str:
    roles = SCENARIO_ROLES.get(scenario_id, {})
    return roles.get(agent_id, agent_id)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


TRUST_DELTA_BASE = {
    "say": +0.01,
    "help": +0.15,
    "compliment": +0.10,
    "ignore": -0.09,
    "insult": -0.18,
    "ask_info": +0.02,
    "share_info": +0.12,
    "refuse": -0.22,
    "agree": +0.08,
    "challenge": -0.10,
    "suggest": +0.05,
}

TRUST_DELTA_REASON = {
    "block_release": +0.10,
    "coord_phase_share": +0.08,
    "proactive": +0.08,
    "easygoing_proactive_early": +0.10,
    "help_followthrough": +0.12,
    "promise_fulfilled": +0.15,
    "task completion praise": +0.06,
    "decisive_ultimatum": -0.05,
    "escalation": -0.08,
    "deadline_forced_share": -0.05,
    "skeptical_delay": -0.06,
    "overthinker_hesitate": -0.03,
    "micro_drama_response": -0.04,
    "user_reveal_info": +0.10,
    "user_nudge_strategy": +0.02,
    "user_boost_urgency": -0.01,
    "user_inject_tension": -0.06,
    "user_force_meeting": +0.03,
}

VALENCE_DELTA = {
    "say": +0.01,
    "help": +0.18,
    "compliment": +0.12,
    "ignore": -0.10,
    "insult": -0.22,
    "ask_info": 0.0,
    "share_info": +0.07,
    "refuse": -0.10,
    "agree": +0.06,
    "challenge": -0.11,
    "suggest": +0.04,
}

STRATEGY_PROFILES: Dict[str, Dict[str, float]] = {
    "cooperative": {
        "initiate_chance_mult": 1.50,
        "reply_chance_mult": 1.30,
        "share_prob_mult": 1.20,
        "trust_recovery_rate": 0.03,
        "stress_sensitivity": 0.70,
        "conversation_continue": 0.50,
    },
    "defensive": {
        "initiate_chance_mult": 0.60,
        "reply_chance_mult": 0.75,
        "share_prob_mult": 0.55,
        "trust_recovery_rate": 0.00,
        "stress_sensitivity": 1.40,
        "conversation_continue": 0.25,
    },
    "confrontational": {
        "initiate_chance_mult": 1.10,
        "reply_chance_mult": 1.20,
        "share_prob_mult": 0.45,
        "trust_recovery_rate": -0.02,
        "stress_sensitivity": 1.20,
        "conversation_continue": 0.35,
    },
    "avoidant": {
        "initiate_chance_mult": 0.55,
        "reply_chance_mult": 0.70,
        "share_prob_mult": 0.80,
        "trust_recovery_rate": 0.01,
        "stress_sensitivity": 1.10,
        "conversation_continue": 0.30,
    },
    "neutral": {
        "initiate_chance_mult": 1.00,
        "reply_chance_mult": 1.00,
        "share_prob_mult": 1.00,
        "trust_recovery_rate": 0.01,
        "stress_sensitivity": 1.00,
        "conversation_continue": 0.35,
    },
    "assertive": {
        "initiate_chance_mult": 1.30,
        "reply_chance_mult": 1.20,
        "share_prob_mult": 0.90,
        "trust_recovery_rate": 0.01,
        "stress_sensitivity": 0.85,
        "conversation_continue": 0.45,
    },
}


class SimAgent(mesa.Agent):
    def __init__(
        self,
        model: mesa.Model,
        public_id: str,
        traits: Dict[str, float],
        speech_style: str,
        long_goal: str,
    ) -> None:
        super().__init__(public_id, model)
        self.public_id = public_id
        self.traits = traits
        self.speech_style = speech_style

        self.E = traits.get("E", 0.5)
        self.A = traits.get("A", 0.5)
        self.N = traits.get("N", 0.5)
        self.C = traits.get("C", 0.5)
        self.O = traits.get("O", 0.5)

        self.valence = random.uniform(-0.05, 0.08)
        self.arousal = 0.3
        self.energy = 100
        self.stress = random.uniform(0.05, 0.18)
        self.long_goal = long_goal
        self.goal_progress = 0.0

        self.last_detected_emotion = "none"
        self.request_history: Dict[tuple, int] = {}

        self.memory = EmotionalMemory(self.public_id, max_stm_size=60)
        self.stm = self.memory.stm
        self.ltm = self.memory.ltm

        self.current_conversation_with: Optional[str] = None
        self.conversation_turn = 0
        self.awaiting_reply_from: Optional[str] = None
        self.last_message_received: Optional[str] = None
        self.last_speaker: Optional[str] = None
        self.conversation_thread = deque(maxlen=25)
        self.last_reply_tick = 0

        self.trust: Dict[str, float] = {}
        self.relationship_status: Dict[str, str] = {}
        self.allies: List[str] = []
        self.rivals: List[str] = []

        self.strategy = "neutral"
        self.strategy_locked_until = -1
        self.strategy_lock_source = None
        self.intervention_reveal_ticks: Dict[str, int] = {}
        self.forced_topic_item: Optional[str] = None
        self.forced_topic_until: int = -1

        self.emotion_analyser = EmotionAnalyser()
        self.last_thought = ""

        self.known_items: Set[str] = set()
        self.env_tension_modifier: float = 0.2

        self.promised_item: str = ""
        self.promised_deadline: int = -1
        self.recent_utterances: deque = deque(maxlen=6)
        self.helped_by: str = ""
        self.helped_item: str = ""
        self.help_expiry_tick: int = -1

        self.personality_type: str = "Easygoing"
        self.personality_bias: dict = {}

        self.emotional_stress: float = 0.0
        self.coord_pressure: float = 0.0
        self.conflict_level: float = 0.0

        self.crushes: List[str] = []
        self.grudge_against: Optional[str] = None
        self.secrets: Dict[str, str] = {}

    def update_strategy(self) -> None:
        current_tick = getattr(self.model, "tick", 0)
        if current_tick <= getattr(self, "strategy_locked_until", -1):
            return

        if not self.trust:
            return

        avg_trust = sum(self.trust.values()) / len(self.trust)
        high_stress = self.stress > 0.75
        low_trust = avg_trust < 0.30
        very_negative = self.valence < -0.55
        high_agree = self.A > 0.68 and avg_trust > 0.58 and self.stress < 0.55
        high_neuro = self.N > 0.72 and self.valence < -0.25

        if self.strategy == "avoidant" and self.stress < 0.15:
            if random.random() < 0.45:
                self.strategy = "neutral"
                self.last_thought = (
                    f"Feeling calmer — returning to neutral "
                    f"(stress:{self.stress:.2f})"
                )
                return

        if high_stress or very_negative:
            candidate = "defensive"
        elif low_trust and self.stress > 0.35:
            candidate = "defensive"
        elif high_neuro:
            candidate = "confrontational"
        elif high_agree:
            candidate = "cooperative"
        elif avg_trust > 0.5 and self.stress < 0.25:
            candidate = "cooperative"
        else:
            candidate = "avoidant"

        if candidate != self.strategy:
            if random.random() < 0.70:
                return
            self.strategy = candidate
            self.last_thought = (
                f"Strategy → {self.strategy} "
                f"(trust:{avg_trust:.2f}, stress:{self.stress:.2f})"
            )

    def _profile(self) -> Dict[str, float]:
        return STRATEGY_PROFILES.get(self.strategy, STRATEGY_PROFILES["neutral"])

    def _get_env_rules(self) -> Dict[str, float]:
        """Return environment physics rules for the current scenario."""
        return get_env_rules(self.model)

    def _r(self, agent_id: str) -> str:
        logic = getattr(self.model, "behaviour", None)
        if logic and hasattr(logic, "role"):
            return logic.role(agent_id)
        sid = getattr(self.model.scenario, "id", "")
        return _role(agent_id, sid)

    def _queue_pending_event(self, event: Dict[str, Any]) -> None:
        if not hasattr(self.model, "_pending_events"):
            self.model._pending_events = []
        self.model._pending_events.append(event)

    def decide_event(self, others: List["SimAgent"]) -> Optional[Dict[str, Any]]:
        env = self.model.environment
        urgency = getattr(env, "urgency_modifier", 1.0)
        tick = getattr(self.model, "tick", 0)
        profile = self._profile()
        forced_agents = getattr(self.model, "_forced_meeting_agents", None)
        forced_until = getattr(self.model, "_forced_meeting_until", -1)
        forced_pair_active = bool(
            forced_agents
            and tick <= forced_until
            and self.public_id in forced_agents
        )

        logic = getattr(self.model, "behaviour", None)

        if forced_agents and tick <= forced_until and self.public_id not in forced_agents:
            return None

        if forced_pair_active:
            others = [
                other
                for other in others
                if other.public_id in forced_agents and other.public_id != self.public_id
            ]
            if not others:
                return None
            forced_partner = others[0]
            if self.current_conversation_with != forced_partner.public_id:
                self.current_conversation_with = forced_partner.public_id
                self.awaiting_reply_from = None
                self.conversation_turn = max(1, self.conversation_turn)
                self.last_reply_tick = tick
        else:
            forced_partner = None

        if self.model.scenario.progress_ratio() >= 1.0:
            if logic and hasattr(logic, "post_completion_action"):
                action = logic.post_completion_action(self, others)
                if action is not None:
                    return action

            if random.random() < 0.20:
                available = [ag for ag in self.model.agents if ag != self]
                if available:
                    tgt = random.choice(available)
                    ptype = getattr(self, "personality_type", "Easygoing")
                    wrapup_pools = {
                        "Leader":      ["Good. That's everything.", "All done. Nice work.", "Completed. Good work."],
                        "Decisive":    ["Done. That's it.", "Finished. Move on.", "All set. Next."],
                        "Easygoing":   ["Nice, we got there.", "Good, all sorted.", "That worked out well."],
                        "Skeptical":   ["Well. We got there.", "Done. That should do it.", "Alright. Looks right."],
                        "Overthinker": ["I think that's everything.", "Okay, I'm pretty sure we're done.", "Alright, I think we got there."],
                        "Creative":    ["That came together nicely.", "Good, we got it.", "Done. That turned out well."],
                    }
                    txt = random.choice(wrapup_pools.get(ptype, wrapup_pools["Easygoing"]))
                    return {
                        "type": "say",
                        "actor": self.public_id,
                        "target": tgt.public_id,
                        "text": txt,
                        "reason": "post_completion_wrapup",
                    }
            return None

        timeout = 6
        if self.current_conversation_with:
            bottleneck = getattr(self.model, "bottleneck_holder", None)
            if bottleneck and self.current_conversation_with == bottleneck:
                timeout = 10
        if self.current_conversation_with and tick - self.last_reply_tick > timeout:
            self._end_conversation()
            return None

        if (
            self.awaiting_reply_from
            and logic
            and getattr(logic, "scenario_type", "") == "office"
        ):
            office_pending = getattr(self.model, "_office_pending_confirm", {}) or {}
            if any(
                rec.get("confirmer") == self.public_id
                for rec in office_pending.values()
            ):
                self.awaiting_reply_from = None
                self.current_conversation_with = None

        if self.awaiting_reply_from:
            reply_prob = profile["reply_chance_mult"] * 0.4
            if logic and getattr(logic, "scenario_type", "") == "office":
                reply_prob = max(0.82, min(0.98, reply_prob + 0.42))
            if (
                self._active_forced_topic()
                and self.awaiting_reply_from == self.current_conversation_with
            ):
                reply_prob = max(reply_prob, 0.98)
            if random.random() < reply_prob:
                target = next(
                    (a for a in others if a.public_id == self.awaiting_reply_from),
                    None,
                )
                if target:
                    self.awaiting_reply_from = None
                    self.current_conversation_with = target.public_id
                    self.conversation_turn += 1
                    self.last_reply_tick = tick
                    return self._generate_reply(target)
            else:
                self.awaiting_reply_from = None
                return None

        if self.current_conversation_with:
            target = next(
                (a for a in others if a.public_id == self.current_conversation_with),
                None,
            )
            if target and target.current_conversation_with == self.public_id:
                self.conversation_turn += 1
                self.last_reply_tick = tick
                return self._continue_conversation(target)
            self._end_conversation()

        if forced_pair_active and forced_partner is not None:
            focus_item = (
                self._active_forced_topic()
                or forced_partner._active_forced_topic()
                or getattr(self.model, "_forced_meeting_item", None)
            )
            started_tick = getattr(self.model, "_forced_meeting_started_tick", tick)
            if (
                focus_item
                and tick >= started_tick + 2
                and not self.model.scenario.tasks.get(focus_item, False)
            ):
                event = self._forced_topic_followup_event(
                    forced_partner,
                    focus_item,
                    reason="forced_meeting_followthrough",
                )
                if event is not None:
                    return event

        if any(
            a.current_conversation_with and a.current_conversation_with != self.public_id
            for a in others if a != self
        ):
            return None

        if logic:
            result = logic.choose_action(self, others)
            if result is not None:
                return result

        if logic and hasattr(logic, "fallback_action"):
            result = logic.fallback_action(self, others)
            if result is not None:
                return result

        return None

    def _intervention_strategy_active(self, strategy: Optional[str] = None) -> bool:
        current_tick = getattr(self.model, "tick", 0)
        if getattr(self, "strategy_lock_source", None) != "intervention":
            return False
        if current_tick > getattr(self, "strategy_locked_until", -1):
            return False
        if strategy is not None and self.strategy != strategy:
            return False
        return True

    def _active_forced_topic(self) -> Optional[str]:
        item = getattr(self, "forced_topic_item", None)
        if not item:
            return None

        current_tick = getattr(self.model, "tick", 0)
        if (
            current_tick > getattr(self, "forced_topic_until", -1)
            or self.model.scenario.tasks.get(item, False)
        ):
            self.forced_topic_item = None
            self.forced_topic_until = -1
            return None
        return item

    def _recent_item_share_count(self, item: str, within: int = 2) -> int:
        current_tick = getattr(self.model, "tick", 0)
        count = 0
        for snap in reversed(getattr(self.model, "history", [])[-(within + 2):]):
            snap_tick = snap.get("tick", current_tick)
            if current_tick - snap_tick > within:
                continue
            for event in snap.get("events", []) or []:
                if event.get("type") == "share_info" and event.get("item") == item:
                    count += 1
        return count

    def _item_knowledge_count(self, item: str) -> int:
        return sum(
            1
            for agent in getattr(self.model, "agents", [])
            if item in getattr(agent, "known_items", set())
        )

    def _item_recently_revealed(self, item: str, within: int = 1) -> bool:
        current_tick = getattr(self.model, "tick", 0)
        for agent in getattr(self.model, "agents", []):
            reveal_tick = getattr(agent, "intervention_reveal_ticks", {}).get(item)
            if reveal_tick is not None and (current_tick - reveal_tick) <= within:
                return True
        return False

    def _recent_item_event_count(
        self,
        item: str,
        event_types: Optional[set[str]] = None,
        within: int = 3,
    ) -> int:
        current_tick = getattr(self.model, "tick", 0)
        count = 0

        for snap in reversed(getattr(self.model, "history", [])[-(within + 3):]):
            snap_tick = snap.get("tick", current_tick)
            if current_tick - snap_tick > within:
                continue
            for event in snap.get("events", []) or []:
                event_item = event.get("item") or event.get("preference")
                if event_item != item:
                    continue
                if event_types and event.get("type") not in event_types:
                    continue
                count += 1

        for event in getattr(self.model, "prev_events", []) or []:
            event_item = event.get("item") or event.get("preference")
            if event_item != item:
                continue
            if event_types and event.get("type") not in event_types:
                continue
            count += 1

        return count

    def _item_recently_stabilized(self, item: str, within: int = 3) -> bool:
        share_or_confirm = self._recent_item_event_count(
            item,
            event_types={"share_info", "agree"},
            within=within,
        )
        if share_or_confirm > 0:
            return True

        pending_office = getattr(self.model, "_office_pending_confirm", {}) or {}
        pending_escape = getattr(self.model, "_escape_pending_confirm", {}) or {}
        if item in pending_office or item in pending_escape:
            return True

        return False

    def _should_share(self, item: str, target: "SimAgent", message_text: str = "") -> bool:
        if self.model.scenario.tasks.get(item, False):
            return False
        if item in target.known_items:
            return False

        current_tick = getattr(self.model, "tick", 0)
        proactive_share = not bool(message_text)
        target_forced_topic = (
            target._active_forced_topic() if hasattr(target, "_active_forced_topic") else None
        )
        forced_topic = item == self._active_forced_topic() or item == target_forced_topic
        focus_item = getattr(self.model, "_intervention_focus_item", None)
        focus_until = getattr(self.model, "_intervention_focus_until", -1)
        focus_active = (
            focus_item
            and current_tick <= focus_until
            and not self.model.scenario.tasks.get(focus_item, False)
        )

        reveal_tick = self.intervention_reveal_ticks.get(item)
        if (
            reveal_tick is not None
            and proactive_share
            and not forced_topic
            and (current_tick - reveal_tick) <= 1
        ):
            return False
        if (
            proactive_share
            and focus_active
            and item != focus_item
            and not forced_topic
            and getattr(self.model, "group_tension", 0.0) < 0.85
            and getattr(self.model, "progress_stall_ticks", 0) < 6
        ):
            return False

        knowledge_count = self._item_knowledge_count(item)
        recent_share_count = self._recent_item_share_count(item, within=2)
        bottleneck_item = getattr(self.model, "bottleneck_item", None)
        if (
            proactive_share
            and recent_share_count >= 1
            and item != bottleneck_item
            and not forced_topic
        ):
            return False
        if (
            proactive_share
            and knowledge_count >= 3
            and item != bottleneck_item
            and not forced_topic
        ):
            return False
        if (
            proactive_share
            and item == bottleneck_item
            and recent_share_count >= 2
            and self._item_recently_stabilized(item, within=2)
            and not forced_topic
            and getattr(self.model, "group_tension", 0.0) < 0.70
            and getattr(self.model, "progress_stall_ticks", 0) < 4
        ):
            return False

        logic = getattr(self.model, "behaviour", None)
        if logic and hasattr(logic, "should_share"):
            decided = logic.should_share(self, target, item, message_text)
            if decided is not None:
                return bool(decided)

        req_key = (target.public_id, item)
        req_count = self.request_history.get(req_key, 0)
        global_key = (target.public_id, self.public_id, item)
        global_count = getattr(self.model, "global_ask_counts", {}).get(global_key, 0)
        effective_count = max(req_count, global_count)

        if effective_count >= 2:
            self.request_history[req_key] = effective_count + 1
            return True

        refusal_gate = 0.15
        if self.strategy == "defensive":
            refusal_gate = 0.28
        elif self.strategy == "confrontational":
            refusal_gate = 0.22
        elif self.strategy == "cooperative":
            refusal_gate = 0.05
        # Contradiction guard: when a cooperative nudge is still in effect
        # (intervention locked the strategy), clamp refusals hard so the very
        # next tick cannot produce a defensive/avoidant line that would make
        # the intervention feel cosmetic.
        if (
            self.strategy == "cooperative"
            and getattr(self, "strategy_lock_source", None) == "intervention"
            and getattr(self, "strategy_locked_until", 0) >= getattr(self.model, "tick", 0)
        ):
            refusal_gate = min(refusal_gate, 0.02)
        if random.random() < refusal_gate:
            return False

        trust = self.trust.get(target.public_id, 0.5)
        env = self.model.environment
        env_urgency = getattr(env, "urgency_modifier", 1.0)
        cooperation = getattr(env, "cooperation_modifier", 1.0)

        base = 0.18 + (self.A * 0.62) - (self.N * 0.42)
        trust_effect = (trust - 0.5) * 1.65
        mem_penalty = self._count_recent_refusals_from(target, 6) * 0.08

        personality_share_mod = {
            "Leader": +0.08,
            "Decisive": +0.05,
            "Easygoing": +0.20,
            "Skeptical": -0.22,
            "Overthinker": -0.10,
            "Creative": +0.05,
        }.get(getattr(self, "personality_type", "Easygoing"), 0.0)

        owns_item = item in self.model.scenario.knowledge_map.get(self.public_id, set())
        learned_via_intervention = reveal_tick is not None and not owns_item
        owner_bonus = 0.25 if owns_item else (0.08 if learned_via_intervention else 0.0)
        env_urg_bonus = env_urgency * 0.12
        tension_pen = self.env_tension_modifier * 0.18

        progress = self.model.scenario.progress_ratio()
        if progress < 0.50:
            task_urgency = 0.30
        elif progress < 0.75:
            task_urgency = 0.20
        else:
            task_urgency = 0.10

        tick = getattr(self.model, "tick", 0)
        max_ticks = getattr(self.model, "episode_max_ticks", 120)
        deadline_bonus = 0.75 if tick > max_ticks * 0.70 else 0.0

        repeat_pressure = min(effective_count * 0.10, 0.30)
        self.request_history[req_key] = effective_count + 1

        politeness_bonus = 0.0
        if message_text:
            lower = message_text.lower()
            if any(
                p in lower
                for p in [
                    "sorry",
                    "please",
                    "i don't want to bother",
                    "could you",
                    "if you don't mind",
                    "would you",
                ]
            ):
                politeness_bonus = 0.15

        strat_mult = self._profile()["share_prob_mult"]
        env_coop = getattr(self.model, "env_mod", {}).get("cooperation_weight", 1.0)

        additive = (
            base
            + trust_effect
            - mem_penalty
            + owner_bonus
            + env_urg_bonus
            - tension_pen
            + task_urgency
            + repeat_pressure
            + politeness_bonus
            + deadline_bonus
            + personality_share_mod
        )

        if owns_item and progress < 0.5:
            additive += 0.25
        if self._intervention_strategy_active("cooperative"):
            additive += 0.18

        if getattr(self.model, "progress_stall_ticks", 0) >= 6:
            additive += 0.18
        if self.public_id == getattr(self.model, "bottleneck_holder", None):
            additive += 0.10

        final_prob = additive * strat_mult * cooperation * env_coop
        final_prob = clamp(final_prob, 0.10, 0.94)
        return random.random() < final_prob

    def _should_refuse(self, requester: "SimAgent", item: str) -> bool:
        return not self._should_share(item, requester)

    def _pick_best_target_for_item(self, item: str, others: List["SimAgent"]) -> Optional["SimAgent"]:
        logic = getattr(self.model, "behaviour", None)
        if logic and hasattr(logic, "pick_best_target_for_item"):
            picked = logic.pick_best_target_for_item(self, item, others)
            if picked is not None:
                return picked

        scored = []
        for agent in others:
            if agent == self or agent.current_conversation_with:
                continue
            trust = self.trust.get(agent.public_id, 0.5)
            if self._was_recently_refused_by(agent, item):
                trust *= 0.18
            if item in self.model.scenario.knowledge_map.get(agent.public_id, set()):
                trust += 0.60
            scored.append((trust, agent))

        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def _was_recently_refused_by(
        self,
        agent: "SimAgent",
        item: str,
        lookback_ticks: int = 5,
    ) -> bool:
        cutoff = getattr(self.model, "tick", 0) - lookback_ticks
        for mem in self.stm:
            if (
                mem.get("tick", 0) >= cutoff
                and mem.get("from") == agent.public_id
                and mem.get("kind") == "refuse"
                and mem.get("item") == item
            ):
                return True
        return False

    def _count_recent_refusals_from(self, agent: "SimAgent", lookback: int = 6) -> int:
        count = 0
        for mem in list(self.stm)[-lookback:]:
            if mem.get("from") == agent.public_id and mem.get("kind") == "refuse":
                count += 1
        return count

    def _count_recent_refusals_for_item(self, item: str, lookback: int = 8) -> int:
        count = 0
        for mem in list(self.stm)[-lookback:]:
            if mem.get("kind") == "refuse" and mem.get("item") == item:
                count += 1
        return count

    def _generate_reply(self, target: "SimAgent") -> Optional[Dict[str, Any]]:
        msg = self.last_message_received or ""
        interp = self._interpret_message(msg)
        intent = interp["intent"]
        key = interp.get("item") or interp.get("preference")
        focus_item = self._active_forced_topic() or target._active_forced_topic()

        if not intent or not key:
            if focus_item and not self.model.scenario.tasks.get(focus_item, False):
                event = self._forced_topic_followup_event(
                    target,
                    focus_item,
                    reason="forced_meeting_reply",
                )
                if event is not None:
                    return event
            self._end_conversation()
            return None

        if intent == "ask_info":
            if key not in self.known_items:
                self._end_conversation()
                return None

            if self.model.scenario.tasks.get(key, False):
                return None

            if focus_item and key == focus_item:
                event = self._forced_topic_followup_event(
                    target,
                    key,
                    reason="forced_meeting_reply",
                )
                if event is not None:
                    return event

            rep_ask_key = (target.public_id, self.public_id, key)
            rep_ask_count = getattr(self.model, "global_ask_counts", {}).get(rep_ask_key, 0)
            if rep_ask_count >= 2 and random.random() < 0.35:
                text = random.choice([
                    f"{self._r(target.public_id)}, you're putting me under pressure about {_lbl(key)}.",
                    f"I've heard you ask about {_lbl(key)} more than once now, {self._r(target.public_id)}.",
                    f"{self._r(target.public_id)}, repeatedly pushing me on {_lbl(key)} is not helping.",
                ])
                return {
                    "type": "challenge",
                    "actor": self.public_id,
                    "target": target.public_id,
                    "text": text,
                    "preference": key,
                    "reason": "defensive_escalation_reply",
                }

            logic = getattr(self.model, "behaviour", None)
            if logic and hasattr(logic, "reply_to_info_request"):
                scenario_reply = logic.reply_to_info_request(self, target, key, msg)
                if scenario_reply is not None:
                    return scenario_reply
                # Scenario logic returned None — it has handled the silence.
                # Don't fall through to generic REFUSE; that would contradict scenario state.
                return None

            if self._should_share(key, target, message_text=msg):
                text = self._generate_share_text(key, target.public_id)
                return {
                    "type": "share_info",
                    "actor": self.public_id,
                    "target": target.public_id,
                    "text": text,
                    "item": key,
                    "reason": "decided to share",
                }

            text = self._generate_refuse_text(key, target.public_id)
            self.trust[target.public_id] = clamp(
                self.trust.get(target.public_id, 0.5) - 0.08,
                0.0,
                1.0,
            )
            self.stress = clamp(self.stress + 0.05, 0.0, 1.0)
            return {
                "type": "refuse",
                "actor": self.public_id,
                "target": target.public_id,
                "text": text,
                "item": key,
                "reason": "low trust",
            }

        if intent == "suggest":
            recent_suggests = sum(
                1 for m in list(self.stm)[-6:]
                if m.get("kind") == "suggest" and m.get("from") == target.public_id
            )
            agree_base = 0.68 + 0.25 * self.A - 0.08 * self.N
            if recent_suggests >= 2:
                agree_base += 0.35

            trust_to_target_ag = self.trust.get(target.public_id, 0.5)
            if trust_to_target_ag > 0.55:
                agree_base += 0.15

            prog_now_ag = self.model.scenario.progress_ratio()
            if prog_now_ag > 0.40:
                agree_base += 0.15

            tick_now = getattr(self.model, "tick", 0)
            max_ticks_v = getattr(self.model, "episode_max_ticks", 120)
            if tick_now > max_ticks_v * 0.75:
                agree_base += 0.15

            if self.strategy == "cooperative":
                agree_base += 0.20
            elif self.strategy == "avoidant":
                agree_base -= 0.05
            elif self.strategy == "confrontational":
                agree_base -= 0.15

            agree_base = min(agree_base, 0.97)

            if random.random() < agree_base:
                text = self._generate_agree_text(target.public_id, key)
                return {
                    "type": "agree",
                    "actor": self.public_id,
                    "target": target.public_id,
                    "text": text,
                    "preference": key,
                }

            text = self._generate_challenge_text(target.public_id, key)
            return {
                "type": "challenge",
                "actor": self.public_id,
                "target": target.public_id,
                "text": text,
                "preference": key,
            }

        self._end_conversation()
        return None

    def _continue_conversation(self, target: "SimAgent") -> Optional[Dict[str, Any]]:
        profile = self._profile()
        continue_threshold = profile["conversation_continue"]
        tick = getattr(self.model, "tick", 0)
        forced_agents = getattr(self.model, "_forced_meeting_agents", None)
        forced_until = getattr(self.model, "_forced_meeting_until", -1)
        forced_pair_active = bool(
            forced_agents
            and tick <= forced_until
            and self.public_id in forced_agents
            and target.public_id in forced_agents
        )

        if forced_pair_active:
            if self.conversation_turn >= 4:
                self._end_conversation()
                return None
        elif self.conversation_turn >= 6 or random.random() < (1.0 - continue_threshold):
            self._end_conversation()
            return None

        missing = [t for t, done in self.model.scenario.tasks.items() if not done]
        if not missing:
            self._end_conversation()
            return None

        focus_item = self._active_forced_topic() or target._active_forced_topic()
        if focus_item and focus_item in missing:
            event = self._forced_topic_followup_event(target, focus_item)
            if event is not None:
                return event

        can_share = [t for t in missing if t in self.known_items and t not in target.known_items]
        if can_share and random.random() < 0.68:
            item = random.choice(can_share)
            if self._should_share(item, target, message_text=""):
                text = f"While we're talking — I know about {item}: {self._generate_info_text(item)}"
                return {
                    "type": "share_info",
                    "actor": self.public_id,
                    "target": target.public_id,
                    "text": text,
                    "item": item,
                }

        self._end_conversation()
        return None

    def _forced_topic_followup_event(
        self,
        target: "SimAgent",
        focus_item: str,
        reason: str = "forced_meeting_followthrough",
    ) -> Optional[Dict[str, Any]]:
        if focus_item in self.known_items and focus_item not in target.known_items:
            if self._should_share(focus_item, target, message_text=f"focus:{focus_item}"):
                text = self._generate_share_text(focus_item, target.public_id)
                return {
                    "type": "share_info",
                    "actor": self.public_id,
                    "target": target.public_id,
                    "text": text,
                    "item": focus_item,
                    "reason": reason,
                }

        if focus_item not in self.known_items and focus_item in target.known_items:
            return {
                "type": "ask_info",
                "actor": self.public_id,
                "target": target.public_id,
                "text": self._generate_ask_text(focus_item, target.public_id),
                "item": focus_item,
                "reason": reason,
            }

        spoken = _lbl(focus_item)
        scenario_type = getattr(getattr(self.model, "behaviour", None), "scenario_type", "office")
        if focus_item in self.known_items and focus_item in target.known_items:
            if scenario_type == "escape":
                text = self._pick_fresh([
                    f"We've got {spoken}. Use it now.",
                    f"{spoken.title()} is clear enough. Put it to work.",
                    f"That's {spoken}. Move straight on it.",
                ])
            elif scenario_type == "cafe":
                text = self._pick_fresh([
                    f"We've got the {spoken} part. Let's settle it.",
                    f"That covers {spoken}. Let's make the call.",
                    f"{spoken.title()} is clear enough now. Let's choose.",
                ])
            else:
                text = self._pick_fresh([
                    f"We've got {spoken}. Let's lock it in.",
                    f"{spoken.title()} is covered. Use it.",
                    f"That settles {spoken}. Let's move.",
                ])
            return {
                "type": "suggest",
                "actor": self.public_id,
                "target": target.public_id,
                "text": text,
                "preference": focus_item,
                "reason": reason,
            }

        if scenario_type == "escape":
            text = self._pick_fresh([
                f"We still need {spoken}. Let's pin down who has it.",
                f"{spoken.title()} is still the hold-up. Who's closest to it?",
                f"We're stuck on {spoken}. Let's sort that first.",
            ])
        elif scenario_type == "cafe":
            text = self._pick_fresh([
                f"We still need the {spoken} part. Let's sort that out.",
                f"The {spoken} bit is still open. Let's settle it.",
                f"We haven't closed {spoken} yet. Let's do that.",
            ])
        else:
            text = self._pick_fresh([
                f"We still need {spoken}. Let's close it between us.",
                f"{spoken.title()} is still open. Let's settle it.",
                f"We haven't closed {spoken} yet. Let's fix that first.",
            ])
        return {
            "type": "say",
            "actor": self.public_id,
            "target": target.public_id,
            "text": text,
            "item": focus_item,
            "reason": reason,
        }

    def _end_conversation(self) -> None:
        if self.current_conversation_with:
            target = next(
                (a for a in self.model.agents if a.public_id == self.current_conversation_with),
                None,
            )
            if target:
                target.current_conversation_with = None
                target.conversation_turn = 0
            self.current_conversation_with = None
            self.conversation_turn = 0
            if hasattr(self.model, "conversation_ongoing"):
                self.model.conversation_ongoing = False

    def _interpret_message(self, text: str) -> Dict[str, Any]:
        lower = text.lower()
        result: Dict[str, Any] = {"intent": "unknown", "item": None, "preference": None}

        possible = set(self.model.scenario.tasks.keys())
        for it in possible:
            if it in lower:
                result["item"] = it
                result["preference"] = it
                break

        if result["preference"] is None:
            behaviour = getattr(self.model, "behaviour", None)
            if behaviour and hasattr(behaviour, "preference_options"):
                pref_options = behaviour.preference_options(self)
            else:
                pref_options = [
                    "italian",
                    "vegan",
                    "cheap",
                    "fancy",
                    "frontend",
                    "backend",
                    "testing",
                    "documentation",
                    "option a",
                    "option b",
                ]
            for opt in pref_options:
                if opt in lower:
                    result["preference"] = opt
                    break

        ask_phrases = [
            "do you know",
            "can you tell me",
            "i need to know",
            "could you share",
            "i'm missing",
            "i'm stuck on",
            "do you have",
            "can you help me with",
            "i need",
            "could you help",
            "what do you know about",
            "i can't move forward without",
            "any info on",
            "can you fill me in",
            "could you fill me in",
            "what's the",
            "do you know anything about",
        ]
        refuse_phrases = [
            "i'm not comfortable",
            "i'd rather not",
            "not right now",
            "i don't feel ready",
            "i'd prefer not to share",
            "i'm not sharing",
            "i can't share",
            "i won't share",
            "not a good idea to share",
            "not sure i trust",
            "rather keep",
            "prefer to keep",
            "no way",
        ]
        agree_phrases = [
            "i agree",
            "that sounds good",
            "i'm on board",
            "yes let's",
            "good idea",
            "that makes sense",
            "i think you're right",
            "sounds like a plan",
            "i support that",
            "let's go with",
        ]
        challenge_phrases = [
            "i disagree",
            "i'm not convinced",
            "that doesn't work",
            "i don't think that",
            "bad idea",
            "i'd go another way",
            "not the best choice",
            "that feels risky",
            "i have concerns",
            "i'm not sure about",
        ]
        suggest_phrases = [
            "i suggest",
            "i propose",
            "i think we should",
            "why don't we",
            "what if we",
            "let's go with",
            "my recommendation is",
            "i'd recommend",
            "we should consider",
            "how about",
            "maybe we should",
        ]

        if any(p in lower for p in ask_phrases):
            result["intent"] = "ask_info"
        elif any(p in lower for p in refuse_phrases):
            result["intent"] = "refuse"
        elif any(p in lower for p in agree_phrases):
            result["intent"] = "agree"
        elif any(p in lower for p in challenge_phrases):
            result["intent"] = "challenge"
        elif any(p in lower for p in suggest_phrases):
            result["intent"] = "suggest"
        elif "?" in lower:
            result["intent"] = "ask_info"

        return result

    def _recent_event_count(self, kind: str, lookback: int = 8) -> int:
        return sum(1 for m in list(self.stm)[-lookback:] if m.get("kind") == kind)

    # ── Text generation — delegated to agent_text.py ────────────────────────
    def _recently_said(self, text: str) -> bool:
        from app.sim.agent_text import recently_said
        return recently_said(self, text)

    def _phrase_on_cooldown(self, phrase_key: str) -> bool:
        from app.sim.agent_text import phrase_on_cooldown
        return phrase_on_cooldown(self, phrase_key)

    def _register_phrase(self, phrase_key: str, cooldown_ticks: int = 4) -> None:
        from app.sim.agent_text import register_phrase
        register_phrase(self, phrase_key, cooldown_ticks)

    def _unique_say(self, pool: list, phrase_key: str, cooldown: int = 4) -> str:
        from app.sim.agent_text import unique_say
        return unique_say(self, pool, phrase_key, cooldown)

    def _phrase_used_recently(self, phrase_key: str, lookback: int = 3) -> bool:
        from app.sim.agent_text import phrase_used_recently
        return phrase_used_recently(self, phrase_key, lookback)

    def _pick_fresh(self, options: list) -> str:
        from app.sim.agent_text import pick_fresh
        return pick_fresh(self, options)

    def _generate_help_text(self, target_id: str, item: str) -> str:
        from app.sim.agent_text import generate_help_text
        return generate_help_text(self, target_id, item)

    def _generate_compliment_text(self, target_id: str) -> str:
        from app.sim.agent_text import generate_compliment_text
        return generate_compliment_text(self, target_id)

    def _generate_ignore_text(self, target_id: str) -> str:
        from app.sim.agent_text import generate_ignore_text
        return generate_ignore_text(self, target_id)

    def _generate_insult_text(self, target_id: str) -> str:
        from app.sim.agent_text import generate_insult_text
        return generate_insult_text(self, target_id)

    def _generate_say_text(self, target_id: str) -> str:
        from app.sim.agent_text import generate_say_text
        return generate_say_text(self, target_id)

    def _generate_ask_text(self, item: str, target_id: str) -> str:
        from app.sim.agent_text import generate_ask_text
        return generate_ask_text(self, item, target_id)

    def _generate_share_text(self, item: str, target_id: str) -> str:
        from app.sim.agent_text import generate_share_text
        return generate_share_text(self, item, target_id)

    def _generate_refuse_text(self, item: str, target_id: str) -> str:
        from app.sim.agent_text import generate_refuse_text
        return generate_refuse_text(self, item, target_id)

    def _generate_agree_text(self, target_id: str, pref: str) -> str:
        from app.sim.agent_text import generate_agree_text
        return generate_agree_text(self, target_id, pref)

    def _generate_challenge_text(self, target_id: str, pref: str) -> str:
        from app.sim.agent_text import generate_challenge_text
        return generate_challenge_text(self, target_id, pref)

    def _generate_info_text(self, item: str) -> str:
        from app.sim.agent_text import generate_info_text
        return generate_info_text(self, item)

    def _apply_tick_stress(self, env_rules: dict) -> None:
        from app.sim.agent_stress import apply_tick_stress
        apply_tick_stress(self, env_rules, self.model)

    def apply_events(self, events: List[Dict[str, Any]], tick: int) -> None:
        self.energy = max(0, self.energy - 1)

        # ── Environment-modulated recovery ──────────────────────────────────
        # recovery_multiplier > 1 = faster decay back to baseline (e.g. cafe)
        # recovery_multiplier < 1 = slower recovery, sustained tension (e.g. escape)
        env_rules = self._get_env_rules()
        stress_mult = env_rules.get("stress_multiplier", 1.0)
        trust_gain_mult = env_rules.get("trust_gain_multiplier", 1.0)
        refusal_penalty = env_rules.get("refusal_penalty", 1.0)
        conflict_mult = env_rules.get("conflict_multiplier", 1.0)

        # Passive tick stress: valence/arousal decay, personality modifiers, bottleneck pressure
        self._apply_tick_stress(env_rules)

        logic = getattr(self.model, "behaviour", None)
        office_mode = bool(logic and getattr(logic, "scenario_type", "") == "office")

        for event in events:
            if (
                event.get("type") == "share_info"
                and event.get("actor")
                and self.model.scenario.tasks.get(event.get("item", ""), False)
            ):
                sharer = event.get("actor")
                if sharer != self.public_id:
                    self.trust[sharer] = clamp(self.trust.get(sharer, 0.5) + 0.05, 0.0, 1.0)

        trust_recovery = self._profile().get("trust_recovery_rate", 0.0)
        if trust_recovery != 0.0:
            for pid in self.trust:
                self.trust[pid] = clamp(self.trust[pid] + trust_recovery * 0.01, 0.0, 1.0)

        for event in events:
            actor_id = event.get("actor", "")
            target_id = event.get("target", "")
            etype = event.get("type", "")
            text = event.get("text", "")
            item = event.get("item") or event.get("preference")

            if target_id == self.public_id:
                self.awaiting_reply_from = actor_id
                self.last_message_received = text
                self.last_speaker = actor_id

                dt = TRUST_DELTA_BASE.get(etype, 0.0)
                if etype == "refuse":
                    dt *= (1.0 + self.N * 0.50)
                elif etype == "share_info":
                    dt *= (0.9 + self.A * 0.40)

                # Scale trust deltas by environment rules
                if dt > 0:
                    dt *= trust_gain_mult
                elif etype == "refuse":
                    dt *= refusal_penalty
                elif etype in ("insult", "challenge", "ignore"):
                    dt *= conflict_mult

                reason_dt = TRUST_DELTA_REASON.get(event.get("reason", ""), 0.0)
                if reason_dt > 0:
                    reason_dt *= trust_gain_mult
                dt += reason_dt
                self.trust[actor_id] = clamp(self.trust.get(actor_id, 0.5) + dt, 0.0, 1.0)

                dv = VALENCE_DELTA.get(etype, 0.0) * 0.45
                self.valence = clamp(self.valence + dv, -1.0, 1.0)
                self.arousal = clamp(self.arousal + abs(dv) * 0.12, 0.0, 1.0)

                stress_sens = self._profile()["stress_sensitivity"]
                if etype == "insult":
                    self.stress = clamp(self.stress + 0.11 * stress_sens * stress_mult, 0.0, 1.0)
                    self.conflict_level = clamp(self.conflict_level + 0.12 * conflict_mult, 0.0, 1.0)
                elif etype == "challenge":
                    self.stress = clamp(self.stress + 0.09 * stress_sens * stress_mult, 0.0, 1.0)
                    self.conflict_level = clamp(self.conflict_level + 0.08 * conflict_mult, 0.0, 1.0)
                elif etype == "refuse":
                    self.stress = clamp(self.stress + 0.08 * stress_sens * stress_mult * refusal_penalty, 0.0, 1.0)
                    self.conflict_level = clamp(self.conflict_level + 0.06 * conflict_mult, 0.0, 1.0)
                elif etype == "ignore":
                    self.stress = clamp(self.stress + 0.06 * stress_sens * stress_mult, 0.0, 1.0)
                elif etype == "help":
                    self.stress = clamp(self.stress - 0.06, 0.0, 1.0)
                    if item:
                        self.helped_by = actor_id
                        self.helped_item = item
                        tick_now = getattr(self.model, "tick", 0)
                        self.help_expiry_tick = tick_now + 2
                elif etype == "compliment":
                    self.stress = clamp(self.stress - 0.012 / stress_sens, 0.0, 1.0)
                elif etype in ("share_info", "agree"):
                    self.stress = clamp(self.stress - 0.008 / stress_sens, 0.0, 1.0)

                if etype == "ask_info" and item:
                    ask_key = (actor_id, self.public_id, item)
                    ask_count = getattr(self.model, "global_ask_counts", {}).get(ask_key, 0)
                    self.stress = clamp(self.stress + min(ask_count * 0.018, 0.08), 0.0, 1.0)
                    if ask_count >= 2:
                        asker_agent = next(
                            (ag for ag in self.model.agents if ag.public_id == actor_id),
                            None,
                        )
                        if asker_agent and item in self.known_items:
                            asker_agent.trust[self.public_id] = clamp(
                                asker_agent.trust.get(self.public_id, 0.5) - 0.04,
                                0.0,
                                1.0,
                            )

                if etype == "share_info" and item and item not in self.known_items:
                    self.known_items.add(item)
                    was_task = item in self.model.scenario.tasks
                    if was_task:
                        self.trust[actor_id] = clamp(self.trust.get(actor_id, 0.5) + 0.10, 0.0, 1.0)

                    if (not office_mode) and random.random() < 0.30:
                        scenario_type = getattr(self.model, "scenario_type", "office")
                        ptype = getattr(self, "personality_type", "Easygoing")
                        item_lbl = _lbl(item).lower() if item else "that"
                        neutral_reactions = {
                            "cafe": {
                                "Leader": [f"Good, that gives us something concrete on {item_lbl}.", f"Right, that narrows the {item_lbl} call down.", f"Alright, that gives us a clearer call on {item_lbl}."],
                                "Decisive": ["Good. That's enough to choose with.", "Fine. We've got something usable now.", "Alright. That gives us a real answer."],
                                "Easygoing": ["Okay, that clears it up.", "Nice, that makes the choice easier.", "Alright, that helps a lot more."],
                                "Skeptical": ["Alright, that's clearer.", "Okay, that's something solid.", "Fine, that's more concrete."],
                                "Overthinker": ["Okay, that makes it easier to follow.", "Right, that clears one part up.", "Alright, that helps me track it."],
                                "Creative": ["Okay, I can see that now.", "Nice, I can picture it now.", "Alright, that clicks better."],
                            },
                            "escape": {
                                "Leader": [f"Good. {item_lbl.title()} is clearer now. Keep moving.", f"Alright, use {item_lbl} and keep moving.", f"Good. {item_lbl.title()} is in — push the next clue."],
                                "Decisive": ["Good. Onward.", "Right. Use it.", "Fine. Move."],
                                "Easygoing": ["Okay, got it.", "Nice, that helps.", "Alright, keep it moving."],
                                "Skeptical": ["Alright, that's clearer.", "Fine, use it.", "Okay, that's enough to go on."],
                                "Overthinker": [f"Okay, I can follow {item_lbl} now.", f"Right, that gives us something solid on {item_lbl}.", f"Alright, I think that's enough on {item_lbl} to use."],
                                "Creative": [f"Okay, {item_lbl} clicks now.", "Nice, that lines up with the last clue.", "Alright, I can see the path now."],
                            },
                        }
                        if scenario_type in neutral_reactions:
                            reaction_text = random.choice(
                                neutral_reactions[scenario_type].get(
                                    ptype,
                                    neutral_reactions[scenario_type]["Easygoing"],
                                )
                            )
                        elif self.stress > 0.60:
                            reaction_text = random.choice([
                                "Okay, that helps — but we're still not done.",
                                "Fine. What else are we missing?",
                                "Okay. Good.",
                            ])
                        else:
                            reaction_text = random.choice([
                                "Right, that makes sense.",
                                "Okay, that's clearer now.",
                                "Good, that gives us something solid.",
                            ])
                        self._queue_pending_event({
                            "type": "say",
                            "actor": self.public_id,
                            "target": actor_id,
                            "text": reaction_text,
                            "reason": "micro_reaction_to_share",
                        })

                if etype == "share_info" and item:
                    self.stress = clamp(self.stress - 0.06, 0.0, 1.0)
                    self.coord_pressure = clamp(self.coord_pressure - 0.08, 0.0, 1.0)
                    self.emotional_stress = clamp(self.emotional_stress - 0.04, 0.0, 1.0)
                    self.valence = clamp(self.valence + 0.06, -1.0, 1.0)
                    if self.model.scenario.tasks.get(item, False):
                        self.stress = clamp(self.stress - 0.10, 0.0, 1.0)
                        self.valence = clamp(self.valence + 0.08, -1.0, 1.0)

                if text:
                    self.process_emotional_message(text, actor_id, tick)

                mem = {
                    "tick": tick,
                    "kind": etype,
                    "from": actor_id,
                    "text": text,
                    "item": item,
                    "importance": clamp(abs(VALENCE_DELTA.get(etype, 0.0)) + abs(dt), 0.0, 1.0),
                }
                self.stm.append(mem)
                if mem["importance"] >= 0.48:
                    self.ltm.append(mem)

            if actor_id == self.public_id:
                actor_stress = 0.0
                # stress_mult is already in scope from top of apply_events
                # env-scale actor-side stress for negative actions

                if etype == "share_info" and item:
                    if self.model.scenario.tasks.get(item, False):
                        ptype_rel = getattr(self, "personality_type", "Easygoing")
                        relief = {
                            "Decisive": 0.25,
                            "Leader": 0.22,
                            "Skeptical": 0.20,
                            "Overthinker": 0.18,
                            "Easygoing": 0.15,
                            "Creative": 0.16,
                        }.get(ptype_rel, 0.18)
                        self.stress = clamp(self.stress - relief, 0.0, 1.0)
                        self.valence = clamp(self.valence + 0.14, -1.0, 1.0)

                        if (not office_mode) and random.random() < 0.70:
                            # Generate praise from the RECEIVER's perspective (target_id),
                            # not the sharer's — the receiver is the one saying "thanks".
                            target_agent = next(
                                (a for a in self.model.agents if a.public_id == target_id),
                                None,
                            )
                            praise_source = target_agent if target_agent else self
                            ptype = getattr(praise_source, "personality_type", "Easygoing")
                            scenario_type = getattr(self.model, "scenario_type", None)
                            if scenario_type == "cafe":
                                # Cafe is a social conversation — warmer register,
                                # no office/project-management phrasing like
                                # "clean handoff" or "next piece".
                                item_lbl = _lbl(item).lower() if item else "that"
                                praise_pools = {
                                    "Leader":      [f"Good, that narrows {item_lbl} down.", "Okay, that helps us decide.", f"Right, that clears one more thing up on {item_lbl}."],
                                    "Decisive":    ["Good. That's enough to choose with.", "Fine. That does it.", "Alright. That's settled."],
                                    "Easygoing":   ["Nice, thanks.", "Perfect, appreciate that.", "Oh good, that helps."],
                                    "Skeptical":   ["Alright. That holds up.", "Fine — I can go with that.", "Okay. That's clearer."],
                                    "Overthinker": ["Okay, I think that covers it.", "Got it. We probably don't need to loop back.", "Alright, that makes it easier to follow."],
                                    "Creative":    ["Oh, I can see it now.", "That gets us closer.", "Yeah, that sounds better."],
                                }
                            else:
                                # Escape / fallback — taut, task-completion register.
                                item_lbl = _lbl(item).lower() if item else "that"
                                praise_pools = {
                                    "Leader":      [f"Good. That's what we needed on {item_lbl}.", f"Right. Move on {item_lbl}.", "Good. Next clue."],
                                    "Decisive":    ["Good. Next.", "That's it.", "Fine. That's confirmed."],
                                    "Easygoing":   ["Nice, thanks.", "Perfect, appreciate that.", "Oh good, that's useful."],
                                    "Skeptical":   ["Alright. I can buy that.", "Fine — that holds up.", "Okay. That's clearer."],
                                    "Overthinker": ["Okay, I think that covers it.", "Got it. I think that's enough to use.", "Alright, that's enough to go on."],
                                    "Creative":    ["Good, that clicks.", "Good, that matches the last clue.", "Nice, that's the answer then."],
                                }
                            praise_options = praise_pools.get(ptype, praise_pools["Easygoing"])
                            if hasattr(praise_source, "_pick_fresh"):
                                praise = praise_source._pick_fresh(list(praise_options))
                            else:
                                praise = random.choice(praise_options)

                            self._queue_pending_event({
                                "type": "compliment",
                                "actor": target_id,
                                "target": actor_id,
                                "text": praise,
                                "reason": "task completed reinforcement",
                            })

                if etype == "ask_info":
                    actor_stress += 0.035 * stress_mult
                elif etype == "refuse":
                    actor_stress += 0.055 * stress_mult
                elif etype == "challenge":
                    actor_stress += 0.060 * stress_mult * conflict_mult
                elif etype == "insult":
                    actor_stress += 0.075 * stress_mult * conflict_mult
                elif etype == "ignore":
                    actor_stress += 0.030 * stress_mult
                elif etype == "suggest":
                    actor_stress += 0.015
                elif etype == "help":
                    actor_stress -= 0.010
                    if target_id:
                        self.trust[target_id] = clamp(self.trust.get(target_id, 0.5) + 0.05 * trust_gain_mult, 0.0, 1.0)
                elif etype == "compliment":
                    actor_stress -= 0.004
                elif etype == "share_info":
                    actor_stress -= 0.005
                elif etype == "agree":
                    actor_stress -= 0.004

                if etype == "ask_info" and item and target_id:
                    ask_key = (self.public_id, target_id, item)
                    ask_count = getattr(self.model, "global_ask_counts", {}).get(ask_key, 0)
                    ptype_ask = getattr(self, "personality_type", "Easygoing")
                    ask_stress_mult = {
                        "Decisive": 1.8,
                        "Skeptical": 1.5,
                        "Leader": 1.3,
                        "Overthinker": 0.8,
                        "Easygoing": 0.6,
                        "Creative": 0.7,
                    }.get(ptype_ask, 1.0)
                    actor_stress += min(ask_count * 0.020 * ask_stress_mult, 0.10)

                self.stress = clamp(self.stress + actor_stress, 0.0, 1.0)

                if etype in ("refuse", "challenge", "insult", "ignore"):
                    self.valence = clamp(self.valence - 0.03, -1.0, 1.0)
                    self.arousal = clamp(self.arousal + 0.03, 0.0, 1.0)
                elif etype in ("share_info", "agree", "help", "compliment"):
                    self.valence = clamp(self.valence + 0.02, -1.0, 1.0)
                    self.arousal = clamp(self.arousal - 0.01, 0.0, 1.0)

                if etype == "refuse" and target_id:
                    self.trust[target_id] = clamp(
                        self.trust.get(target_id, 0.5) - 0.06 * refusal_penalty,
                        0.0,
                        1.0,
                    )
                    self.valence = clamp(self.valence - 0.04, -1.0, 1.0)

                if (
                    self.public_id == getattr(self.model, "bottleneck_holder", None)
                    and getattr(self.model, "bottleneck_age", 0) >= 6
                ):
                    for other_ag in list(self.model.agents):
                        if other_ag.public_id != self.public_id:
                            other_ag.trust[self.public_id] = clamp(
                                other_ag.trust.get(self.public_id, 0.5) - 0.012,
                                0.0,
                                1.0,
                            )

            if actor_id == self.public_id or target_id == self.public_id:
                self.update_relationships(tick)
                self.update_strategy()
                self.goal_progress = clamp(
                    self.goal_progress + 0.013 * (1 + max(0.0, self.valence)),
                    0.0,
                    1.0,
                )

    def process_emotional_message(self, text: str, speaker: str, tick: int) -> Dict[str, float]:
        if not text or getattr(self.model, "skip_emotions", False):
            return {}

        emotions = self.emotion_analyser.analyse(text)
        if not emotions:
            return {}

        lower = text.lower()

        if any(
            p in lower
            for p in [
                "i'm blocked",
                "i hate to keep asking",
                "i need to know",
                "i can't move forward without",
                "still stuck",
                "running out of time",
                "i wouldn't ask if i wasn't stuck",
                "i'm done waiting",
                "we're going nowhere",
                "we're wasting time",
            ]
        ):
            self.stress = clamp(self.stress + 0.05, 0.0, 1.0)

        if any(p in lower for p in ["not comfortable sharing", "rather keep", "prefer to keep"]):
            emotions["disappointment"] = max(emotions.get("disappointment", 0), 0.55)
        if any(p in lower for p in ["don't think it's a good idea", "not sure i trust", "have concerns about"]):
            emotions["disapproval"] = max(emotions.get("disapproval", 0), 0.60)
        if any(
            p in lower
            for p in ["this will help", "let me help you out", "i trust you with this", "happy to help", "of course"]
        ):
            emotions["approval"] = max(emotions.get("approval", 0), 0.60)
            emotions["optimism"] = max(emotions.get("optimism", 0), 0.45)
        if any(p in lower for p in ["i strongly disagree", "that's a mistake", "wrong move"]):
            emotions["anger"] = max(emotions.get("anger", 0), 0.55)
            emotions["disapproval"] = max(emotions.get("disapproval", 0), 0.50)
        if any(p in lower for p in ["completely agree", "great suggestion", "fully on board"]):
            emotions["joy"] = max(emotions.get("joy", 0), 0.50)
            emotions["approval"] = max(emotions.get("approval", 0), 0.55)

        if "neutral" in emotions and len(emotions) > 1:
            emotions["neutral"] *= 0.55

        va = self.emotion_analyser.get_valence_arousal(text)

        top_emotions = sorted(emotions.items(), key=lambda x: x[1], reverse=True)[:3]
        primary_emotion = top_emotions[0][0] if top_emotions else va.get("primary_emotion", "neutral")
        self.last_detected_emotion = primary_emotion

        self.valence = clamp(self.valence + (va.get("valence", 0.0) * 0.06), -1.0, 1.0)
        self.arousal = clamp(self.arousal + (va.get("arousal", 0.0) * 0.05), 0.0, 1.0)

        stress_delta = 0.0
        if va.get("valence", 0.0) < 0:
            stress_delta += abs(va["valence"]) * 0.07
        if va.get("arousal", 0.0) > 0.55:
            stress_delta += (va["arousal"] - 0.55) * 0.10
        self.stress = clamp(self.stress + stress_delta, 0.0, 1.0)

        negative_high = {"anger", "annoyance", "disapproval", "disgust"}
        negative_low = {"sadness", "disappointment", "remorse", "grief"}
        uncertain = {"confusion", "curiosity", "nervousness", "fear"}
        positive = {"joy", "gratitude", "approval", "admiration", "optimism", "relief"}

        for emotion, score in top_emotions:
            if emotion in negative_high:
                self.trust[speaker] = clamp(self.trust.get(speaker, 0.5) - 0.04 * score, 0.0, 1.0)
                self.stress = clamp(self.stress + 0.05 * score, 0.0, 1.0)
                self.valence = clamp(self.valence - 0.06 * score, -1.0, 1.0)
            elif emotion in negative_low:
                self.stress = clamp(self.stress + 0.04 * score, 0.0, 1.0)
                self.valence = clamp(self.valence - 0.05 * score, -1.0, 1.0)
            elif emotion in uncertain:
                self.stress = clamp(self.stress + 0.02 * score, 0.0, 1.0)
                self.arousal = clamp(self.arousal + 0.03 * score, 0.0, 1.0)
            elif emotion in positive:
                self.trust[speaker] = clamp(self.trust.get(speaker, 0.5) + 0.03 * score, 0.0, 1.0)
                self.stress = clamp(self.stress - 0.012 * score, 0.0, 1.0)
                self.valence = clamp(self.valence + 0.05 * score, -1.0, 1.0)

        tone = "more tense" if self.stress > 0.2 else "okay"
        self.last_thought = f"{speaker} came across as {primary_emotion}; I feel {tone}."

        mem = {
            "tick": tick,
            "kind": "emotion_analysis",
            "from": speaker,
            "text": text,
            "primary_emotion": primary_emotion,
            "valence": va.get("valence", 0.0),
            "arousal": va.get("arousal", 0.0),
            "all_emotions": emotions,
            "importance": clamp(
                abs(va.get("valence", 0.0)) + abs(va.get("arousal", 0.3) - 0.3),
                0.0,
                1.0,
            ),
        }
        self.stm.append(mem)
        if mem["importance"] >= 0.48:
            self.ltm.append(mem)

        return emotions

    def update_relationships(self, tick: int) -> None:
        for oid, tv in list(self.trust.items()):
            if tv > 0.83:
                self.relationship_status[oid] = "ally"
                if oid not in self.allies:
                    self.allies.append(oid)
            elif tv < 0.24:
                self.relationship_status[oid] = "rival"
                if oid not in self.rivals:
                    self.rivals.append(oid)

    def to_state(self) -> AgentState:
        return {
            "id": self.public_id,
            "name": self.public_id,
            "role": _role(self.public_id, getattr(self.model.scenario, "environment", "")),
            "personality": self.personality_type,
            "strategy": self.strategy,
            "trust": {k: round(v, 3) for k, v in self.trust.items()},
            "known_items": list(self.known_items),
            "mood": {
                "valence": round(self.valence, 3),
                "arousal": round(self.arousal, 3),
            },
            "stress": round(self.stress, 3),
            "emotional_stress": round(self.emotional_stress, 3),
            "coord_pressure": round(self.coord_pressure, 3),
            "conflict_level": round(self.conflict_level, 3),
            "last_detected_emotion": self.last_detected_emotion,
            "goal_progress": round(self.goal_progress, 3),
            "in_conversation_with": self.current_conversation_with,
            "last_thought": self.last_thought,
        }
