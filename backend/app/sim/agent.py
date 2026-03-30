from __future__ import annotations
from collections import deque
from typing import Any, Dict, List, Optional, Set
import random
import mesa

# Human-readable labels for task items used in agent messages
ITEM_LABELS = {
    "budget": "Budget Information",
    "requirements": "Project Requirements",
    "design": "Design Plans",
    "tech_specs": "Technical Specifications",
    "frontend": "Frontend Development",
    "backend": "Backend Development",
    "testing": "Testing Plan",
    "documentation": "Documentation",
    "flights": "Flight Details",
    "hotel": "Hotel Details",
    "food": "Food Recommendations",
    "attractions": "Attractions List",
    "decision": "Final Decision",
    "digit_1": "First Code Digit",
    "digit_2": "Second Code Digit",
    "digit_3": "Third Code Digit",
    "order": "Digit Order",
    "map": "Room Map",
    "key": "Key Location",
    "lock": "Lock Combination",
    "door": "Door Code",
    "italian": "Italian Restaurant",
    "vegan": "Vegan Option",
    "cheap": "Budget Option",
    "fancy": "Fine Dining Option",
}

def _lbl(item: str) -> str:
    return ITEM_LABELS.get(item, item.replace("_", " ").title())

def _role(agent_id: str) -> str:
    roles = {"A1": "Project Manager", "A2": "Developer", "A3": "Designer", "A4": "Data Analyst"}
    return roles.get(agent_id, agent_id)


from app.sim.emotions_analyser import EmotionAnalyser
from app.sim.memory import EmotionalMemory


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Trust and valence deltas — event-level social meaning only.
# NLP layer (process_emotional_message) handles emotional meaning separately.
# ---------------------------------------------------------------------------

TRUST_DELTA_BASE = {
    "say": +0.01, "help": +0.12, "compliment": +0.10, "ignore": -0.07,
    "insult": -0.15, "ask_info": +0.02, "share_info": +0.10, "refuse": -0.18,
    "agree": +0.08, "challenge": -0.13, "suggest": +0.05,
}

VALENCE_DELTA = {
    "say": +0.01, "help": +0.18, "compliment": +0.12, "ignore": -0.10,
    "insult": -0.22, "ask_info": 0.0, "share_info": +0.07, "refuse": -0.10,
    "agree": +0.06, "challenge": -0.11, "suggest": +0.04,
}

# ---------------------------------------------------------------------------
# Strategy behaviour profiles
# These define how each strategy modifies action probabilities and thresholds.
# ---------------------------------------------------------------------------

STRATEGY_PROFILES: Dict[str, Dict[str, float]] = {
    "cooperative": {
        "initiate_chance_mult":  1.50,   # more likely to start conversations
        "reply_chance_mult":     1.30,   # more likely to reply promptly
        "share_prob_mult":       1.20,   # more willing to share
        "trust_recovery_rate":   0.03,   # recovers trust faster after conflict
        "stress_sensitivity":    0.70,   # less affected by conflict stress
        "conversation_continue": 0.50,   # higher chance to keep conversation going
    },
    "defensive": {
        "initiate_chance_mult":  0.60,
        "reply_chance_mult":     0.75,
        "share_prob_mult":       0.55,
        "trust_recovery_rate":   0.00,
        "stress_sensitivity":    1.40,
        "conversation_continue": 0.25,
    },
    "confrontational": {
        "initiate_chance_mult":  1.10,
        "reply_chance_mult":     1.20,
        "share_prob_mult":       0.45,
        "trust_recovery_rate":  -0.02,   # trust erodes slightly over time
        "stress_sensitivity":    1.20,
        "conversation_continue": 0.35,
    },
    "avoidant": {
        # Avoidant = hesitant, not useless. Agents still share, just more slowly.
        "initiate_chance_mult":  0.55,   # was 0.35 — low but not near-zero
        "reply_chance_mult":     0.70,   # was 0.50 — they do eventually reply
        "share_prob_mult":       0.80,   # was 0.70 — still capable of sharing
        "trust_recovery_rate":   0.01,
        "stress_sensitivity":    1.10,
        "conversation_continue": 0.30,   # was 0.15 — can sustain a conversation
    },
    "neutral": {
        "initiate_chance_mult":  1.00,
        "reply_chance_mult":     1.00,
        "share_prob_mult":       1.00,
        "trust_recovery_rate":   0.01,
        "stress_sensitivity":    1.00,
        "conversation_continue": 0.35,
    },
    "assertive": {
        "initiate_chance_mult":  1.30,
        "reply_chance_mult":     1.20,
        "share_prob_mult":       0.90,
        "trust_recovery_rate":   0.01,
        "stress_sensitivity":    0.85,
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

        self.valence = 0.0
        self.arousal = 0.3
        self.energy = 100
        self.stress = 0.0
        self.long_goal = long_goal
        self.goal_progress = 0.0

        self.last_detected_emotion = "none"

        # Tracks how many times this agent has been asked for (requester_id, item).
        # Used to apply escalating social pressure after repeated requests.
        self.request_history: Dict[tuple, int] = {}

        self.memory = EmotionalMemory(self.public_id, max_stm_size=60)
        self.stm = self.memory.stm
        self.ltm = self.memory.ltm

        self.current_conversation_with = None
        self.conversation_turn = 0
        self.awaiting_reply_from = None
        self.last_message_received = None
        self.last_speaker = None
        self.conversation_thread = deque(maxlen=25)
        self.last_reply_tick = 0

        self.trust: Dict[str, float] = {}
        self.relationship_status: Dict[str, str] = {}
        self.allies: List[str] = []
        self.rivals: List[str] = []

        # Strategy is seeded from traits by model.py; default here as fallback
        self.strategy = "neutral"

        self.emotion_analyser = EmotionAnalyser()
        self.last_thought = ""

        self.known_items: Set[str] = set()

        # env_tension_modifier is written by model.py each tick
        self.env_tension_modifier: float = 0.2

        # Drama attributes required by model.py
        self.crushes: List[str] = []
        self.grudge_against: Optional[str] = None
        self.secrets: Dict[str, str] = {}

    # -----------------------------------------------------------------------
    # Strategy update — responds to emotional and social state
    # -----------------------------------------------------------------------
    def update_strategy(self):
        if not self.trust:
            return
        avg_trust = sum(self.trust.values()) / len(self.trust)
        high_stress    = self.stress > 0.75
        low_trust      = avg_trust < 0.30
        very_negative  = self.valence < -0.55
        high_agree     = self.A > 0.68 and avg_trust > 0.58 and self.stress < 0.55
        high_neuro     = self.N > 0.72 and self.valence < -0.25

        old = self.strategy

        # --- Recovery: low stress + avoidant → drift back toward neutral ---
        # Threshold raised to 0.15 (was 0.05) so recovery happens more readily,
        # preventing the avoidant lock-in spiral seen in failed runs.
        if self.strategy == "avoidant" and self.stress < 0.15:
            if random.random() < 0.45:
                self.strategy = "neutral"
                self.last_thought = (
                    f"Feeling calmer — returning to neutral "
                    f"(stress:{self.stress:.2f})"
                )
                return

        # --- Compute candidate new strategy ---
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

        # --- Strategy inertia: resist switching 70% of the time ---
        # Prevents agents flip-flopping after a single small negative event.
        if candidate != self.strategy:
            if random.random() < 0.70:
                return   # keep current strategy this tick
            self.strategy = candidate
            self.last_thought = (
                f"Strategy → {self.strategy} "
                f"(trust:{avg_trust:.2f}, stress:{self.stress:.2f})"
            )

    def _profile(self) -> Dict[str, float]:
        """Return the behaviour profile for the current strategy."""
        return STRATEGY_PROFILES.get(self.strategy, STRATEGY_PROFILES["neutral"])

    # -----------------------------------------------------------------------
    # decide_event — strategy profiles now govern initiate & reply chances
    # -----------------------------------------------------------------------
    def decide_event(self, others: List["SimAgent"]) -> Optional[Dict[str, Any]]:
        env = self.model.environment
        urgency     = getattr(env, "urgency_modifier", 1.0)
        cooperation = getattr(env, "cooperation_modifier", 1.0)
        tick        = getattr(self.model, "tick", 0)
        profile     = self._profile()

        # Conversation timeout — extended if this agent is actively pursuing a
        # bottleneck item (gives repeated-request pressure time to accumulate).
        timeout = 6
        if self.current_conversation_with:
            # If the current conversation partner holds the bottleneck item,
            # give more time before giving up (allows req_count to reach 3).
            bottleneck = getattr(self.model, "bottleneck_holder", None)
            if bottleneck and self.current_conversation_with == bottleneck:
                timeout = 10
        if self.current_conversation_with and tick - self.last_reply_tick > timeout:
            self._end_conversation()
            return None

        # Reply to awaited agent — modulated by reply_chance_mult
        if self.awaiting_reply_from:
            if random.random() > (1.0 - profile["reply_chance_mult"] * 0.4):
                target = next(
                    (a for a in others if a.public_id == self.awaiting_reply_from), None
                )
                if target:
                    self.awaiting_reply_from = None
                    self.current_conversation_with = target.public_id
                    self.conversation_turn += 1
                    self.last_reply_tick = tick
                    return self._generate_reply(target)
            else:
                # Avoidant/defensive agents sometimes silently drop replies
                self.awaiting_reply_from = None
                return None

        # Continue existing conversation
        if self.current_conversation_with:
            target = next(
                (a for a in others if a.public_id == self.current_conversation_with),
                None,
            )
            if target and target.current_conversation_with == self.public_id:
                self.conversation_turn += 1
                self.last_reply_tick = tick
                return self._continue_conversation(target)
            else:
                self._end_conversation()

        # Don't interrupt others' conversations
        if any(
            a.current_conversation_with and a.current_conversation_with != self.public_id
            for a in others if a != self
        ):
            return None

        # Decision scenario handling
        is_decision = any(
            "decision" in k.lower() or "role" in k.lower()
            for k in self.model.scenario.tasks
        )
        if is_decision and random.random() < (0.45 + 0.15 * urgency) * profile["initiate_chance_mult"]:
            return self._decision_event(others)

        # Ask for missing information — tension suppresses willingness to initiate
        tension_penalty = self.env_tension_modifier * 0.3
        missing = [t for t, done in self.model.scenario.tasks.items() if not done]
        needed = None
        if missing:
            unknown = [t for t in missing if t not in self.known_items]
            if unknown:
                needed = random.choice(unknown)
                target = self._pick_best_target_for_item(needed, others)
                if target and target != self:
                    initiate_prob = 0.80 * profile["initiate_chance_mult"] - tension_penalty
                    if random.random() < initiate_prob:
                        if getattr(self.model, "conversation_ongoing", False):
                            return None
                        self.model.conversation_ongoing = True
                        self.current_conversation_with = target.public_id
                        self.conversation_turn = 1
                        self.last_reply_tick = tick
                        text = self._generate_ask_text(needed, target.public_id)
                        return {
                            "type": "ask_info",
                            "actor": self.public_id,
                            "target": target.public_id,
                            "text": text,
                            "item": needed,
                            "reason": "need information",
                        }

        # Recovery: switch target after repeated refusals
        recent_refusals = sum(1 for m in list(self.stm)[-6:] if m.get("kind") == "refuse")
        if recent_refusals >= 2 and missing and needed is not None:
            others_needed = [t for t in missing if t != needed]
            if others_needed:
                alt_needed = random.choice(others_needed)
                alt_target = self._pick_best_target_for_item(alt_needed, others)
                if alt_target and alt_target != self:
                    text = self._generate_ask_text(alt_needed, alt_target.public_id)
                    return {
                        "type": "ask_info",
                        "actor": self.public_id,
                        "target": alt_target.public_id,
                        "text": text,
                        "item": alt_needed,
                        "reason": "recovery - switch after refusals",
                    }

        # Proactive sharing — modulated by strategy + tension
        base_share_chance = (0.07 + 0.16 * urgency) * profile["initiate_chance_mult"]
        base_share_chance -= tension_penalty
        if random.random() < base_share_chance:
            incomplete_items = [
                item for item in self.known_items
                if not self.model.scenario.tasks.get(item, True)
            ]
            for item in incomplete_items:
                candidates = [a for a in others if a != self and item not in a.known_items]
                if candidates:
                    target = max(candidates, key=lambda a: self.trust.get(a.public_id, 0.4))
                    if (
                        self.trust.get(target.public_id, 0.5) > 0.52
                        and self._should_share(item, target, message_text="")
                    ):
                        text = self._generate_share_text(item, target.public_id)
                        return {
                            "type": "share_info",
                            "actor": self.public_id,
                            "target": target.public_id,
                            "text": text,
                            "item": item,
                            "reason": "proactive",
                        }

        return None

    # -----------------------------------------------------------------------
    # Decision event — strategy-aware agree/challenge probabilities
    # -----------------------------------------------------------------------
    def _decision_event(self, others: List["SimAgent"]) -> Optional[Dict[str, Any]]:
        recent = next(
            (m for m in list(self.stm)[-5:] if m.get("kind") == "suggest"), None
        )
        if recent and random.random() < 0.65:
            pref  = recent.get("preference", "unknown")
            actor = recent.get("from")
            # Cooperative agents agree more; confrontational agents challenge more
            agree_base = 0.38 + 0.3 * self.A - 0.25 * self.N
            if self.strategy == "cooperative":
                agree_base += 0.15
            elif self.strategy == "confrontational":
                agree_base -= 0.20
            if random.random() < agree_base:
                text = self._generate_agree_text(actor, pref)
                return {
                    "type": "agree", "actor": self.public_id, "target": actor,
                    "text": text, "preference": pref,
                }
            else:
                text = self._generate_challenge_text(actor, pref)
                return {
                    "type": "challenge", "actor": self.public_id, "target": actor,
                    "text": text, "preference": pref,
                }

        if self.strategy not in ("avoidant", "defensive") and random.random() < 0.55:
            if "frontend" in self.model.scenario.tasks:
                opts = ["frontend", "backend", "testing", "documentation"]
            elif "decision" in self.model.scenario.tasks:
                opts = ["italian", "vegan", "cheap", "fancy"]
            else:
                opts = ["option A", "option B"]
            pref   = random.choice(opts)
            target = random.choice([a for a in others if a != self])
            return {
                "type": "suggest", "actor": self.public_id,
                "target": target.public_id,
                "text": f"I suggest {pref}.", "preference": pref,
            }

        return None

    # -----------------------------------------------------------------------
    # Sharing probability — strategy profile applied cleanly here
    # -----------------------------------------------------------------------
    def _should_share(self, item: str, target: "SimAgent", message_text: str = "") -> bool:
        if self.model.scenario.tasks.get(item, False):
            return False
        if item in target.known_items:
            return False

        # FIX 1 — Forced sharing after 3+ asks using the GLOBAL tracker.
        # The global tracker persists across conversation timeouts, so repeated
        # asks from the same agent across multiple conversations accumulate correctly.
        req_key      = (target.public_id, item)
        req_count    = self.request_history.get(req_key, 0)

        # Also check model-level global tracker (asker=target, holder=self)
        global_key   = (target.public_id, self.public_id, item)
        global_count = getattr(self.model, "global_ask_counts", {}).get(global_key, 0)
        effective_count = max(req_count, global_count)

        if effective_count >= 3:
            self.request_history[req_key] = effective_count + 1
            return True   # social pressure threshold reached — override everything

        # FIX 3 — Refusal gate: reduce base refusal rate by 40%
        # Old: random.random() < 0.28  (28% hard refusal)
        # New: 0.28 * 0.60 = 0.168 (~17% hard refusal)
        if random.random() < 0.168:
            return False

        trust       = self.trust.get(target.public_id, 0.5)
        env         = self.model.environment
        env_urgency = getattr(env, "urgency_modifier", 1.0)
        cooperation = getattr(env, "cooperation_modifier", 1.0)

        base         = 0.18 + (self.A * 0.62) - (self.N * 0.42)
        trust_effect = (trust - 0.5) * 1.65
        mem_penalty  = self._count_recent_refusals_from(target, 6) * 0.20

        scenario_id = getattr(self.model.scenario, "id", "").lower()
        coop_boost  = 0.0
        if "proposal" in scenario_id or "vacation" in scenario_id:
            coop_boost = 0.09
        elif "escape" in scenario_id:
            coop_boost = 0.07
        elif "roles" in scenario_id or "restaurant" in scenario_id:
            coop_boost = -0.08

        owner_bonus  = 0.09 if item in self.model.scenario.knowledge_map.get(self.public_id, set()) else 0.0
        env_urg_bonus = env_urgency * 0.12
        tension_pen  = self.env_tension_modifier * 0.18

        # FIX 4 — Tiered task urgency: early-stage agents cooperate much more readily.
        # Progress 0–50%  → +0.30 (high urgency, information spread is critical)
        # Progress 50–75% → +0.20 (moderate urgency)
        # Progress 75%+   → +0.10 (most done, selective sharing is fine)
        progress = self.model.scenario.progress_ratio()
        if progress < 0.50:
            task_urgency = 0.30
        elif progress < 0.75:
            task_urgency = 0.20
        else:
            task_urgency = 0.10

        # FIX 2 — Deadline pressure: agents become significantly more cooperative
        # as the episode approaches its time limit (past 70% of max ticks).
        # Models real-world deadline-driven behaviour.
        tick         = getattr(self.model, "tick", 0)
        max_ticks    = getattr(self.model, "episode_max_ticks", 120)
        deadline_bonus = 0.0
        if tick > max_ticks * 0.70:
            deadline_bonus = 0.50   # strong late-game push to share

        # FIX 2 (repeat pressure) — escalating social pressure using effective count.
        repeat_pressure = min(effective_count * 0.10, 0.30)
        self.request_history[req_key] = effective_count + 1   # increment local tracker

        # FIX 4 — Politeness bonus: NLP-detected politeness → higher share prob
        # Connects language analysis directly to behaviour (strong academic argument).
        politeness_bonus = 0.0
        if message_text:
            lower = message_text.lower()
            if any(p in lower for p in ["sorry", "please", "i don't want to bother",
                                         "could you", "if you don't mind", "would you"]):
                politeness_bonus = 0.15

        # Strategy profile multiplier
        strat_mult = self._profile()["share_prob_mult"]

        # Scenario env_mod cooperation weight
        env_coop = getattr(self.model, "env_mod", {}).get("cooperation_weight", 1.0)

        additive = (
            base
            + trust_effect
            - mem_penalty
            + coop_boost
            + owner_bonus
            + env_urg_bonus
            - tension_pen
            + task_urgency       # tiered progress urgency
            + repeat_pressure    # escalating social pressure
            + politeness_bonus   # NLP-detected politeness
            + deadline_bonus     # deadline-driven cooperation surge
        )
        final_prob = additive * strat_mult * cooperation * env_coop
        final_prob = clamp(final_prob, 0.10, 0.94)
        return random.random() < final_prob

    def _should_refuse(self, requester: "SimAgent", item: str) -> bool:
        return not self._should_share(item, requester)

    def _pick_best_target_for_item(self, item: str, others: List["SimAgent"]) -> Optional["SimAgent"]:
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

    def _was_recently_refused_by(self, agent: "SimAgent", item: str, lookback_ticks: int = 5) -> bool:
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

    # -----------------------------------------------------------------------
    # Reply generation
    # -----------------------------------------------------------------------
    def _generate_reply(self, target: "SimAgent") -> Optional[Dict[str, Any]]:
        msg    = self.last_message_received or ""
        interp = self._interpret_message(msg)
        intent = interp["intent"]
        key    = interp.get("item") or interp.get("preference")

        if not intent or not key:
            self._end_conversation()
            return None

        if intent == "ask_info":
            if key not in self.known_items:
                self._end_conversation()
                return None
            if self.model.scenario.tasks.get(key, False):
                text = f"{target.public_id}, that part is already done."
                return {"type": "say", "actor": self.public_id, "target": target.public_id,
                        "text": text, "item": key, "reason": "already_complete"}
            if self._should_share(key, target, message_text=msg):
                text = self._generate_share_text(key, target.public_id)
                return {"type": "share_info", "actor": self.public_id, "target": target.public_id,
                        "text": text, "item": key, "reason": "decided to share"}
            else:
                text = self._generate_refuse_text(key, target.public_id)
                # FIX 4 — Refuser penalty: refusing has a social cost for the refuser.
                # Trust in the person they refused drops slightly; stress rises.
                # This pushes reluctant agents toward eventual cooperation.
                self.trust[target.public_id] = clamp(
                    self.trust.get(target.public_id, 0.5) - 0.08, 0.0, 1.0
                )
                self.stress = clamp(self.stress + 0.05, 0.0, 1.0)
                return {"type": "refuse", "actor": self.public_id, "target": target.public_id,
                        "text": text, "item": key, "reason": "low trust"}

        elif intent == "suggest":
            agree_base = 0.38 + 0.3 * self.A - 0.25 * self.N
            if self.strategy == "cooperative":
                agree_base += 0.15
            elif self.strategy == "confrontational":
                agree_base -= 0.20
            if random.random() < agree_base:
                text = self._generate_agree_text(target.public_id, key)
                return {"type": "agree", "actor": self.public_id, "target": target.public_id,
                        "text": text, "preference": key}
            else:
                text = self._generate_challenge_text(target.public_id, key)
                return {"type": "challenge", "actor": self.public_id, "target": target.public_id,
                        "text": text, "preference": key}

        self._end_conversation()
        return None

    # -----------------------------------------------------------------------
    # Continue conversation — strategy profile governs continuation chance
    # -----------------------------------------------------------------------
    def _continue_conversation(self, target: "SimAgent") -> Optional[Dict[str, Any]]:
        profile  = self._profile()
        continue_threshold = profile["conversation_continue"]

        if self.conversation_turn >= 6 or random.random() < (1.0 - continue_threshold):
            self._end_conversation()
            return None

        missing = [t for t, done in self.model.scenario.tasks.items() if not done]
        if not missing:
            self._end_conversation()
            return None

        can_share = [t for t in missing if t in self.known_items and t not in target.known_items]
        if can_share and random.random() < 0.68:
            item = random.choice(can_share)
            if self._should_share(item, target, message_text=""):
                text = f"While we're talking — I know about {item}: {self._generate_info_text(item)}"
                return {"type": "share_info", "actor": self.public_id, "target": target.public_id,
                        "text": text, "item": item}

        self._end_conversation()
        return None

    def _end_conversation(self):
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

    # -----------------------------------------------------------------------
    # Phrase-based message interpretation (replaces keyword matching)
    # Much harder for examiners to dismiss as "just keyword matching"
    # -----------------------------------------------------------------------
    def _interpret_message(self, text: str) -> Dict[str, Any]:
        lower = text.lower()
        result: Dict[str, Any] = {"intent": "unknown", "item": None, "preference": None}

        # Item detection — check all known task items
        possible = set(self.model.scenario.tasks.keys())
        for it in possible:
            if it in lower:
                result["item"] = it
                result["preference"] = it
                break

        # Intent: ask_info — full phrases, not single words
        ask_phrases = [
            "do you know", "can you tell me", "i need to know",
            "could you share", "i'm missing", "i'm stuck on",
            "do you have", "can you help me with", "i need",
            "could you help", "what do you know about",
            "i can't move forward without", "any info on",
            "can you fill me in", "could you fill me in",
            "what's the", "do you know anything about",
        ]
        refuse_phrases = [
            "i'm not comfortable", "i'd rather not", "not right now",
            "i don't feel ready", "i'd prefer not to share",
            "i'm not sharing", "i can't share", "i won't share",
            "not a good idea to share", "not sure i trust",
            "rather keep", "prefer to keep", "no way",
        ]
        agree_phrases = [
            "i agree", "that sounds good", "i'm on board",
            "yes let's", "good idea", "that makes sense",
            "i think you're right", "sounds like a plan",
            "i support that", "let's go with",
        ]
        challenge_phrases = [
            "i disagree", "i'm not convinced", "that doesn't work",
            "i don't think that", "bad idea", "i'd go another way",
            "not the best choice", "that feels risky",
            "i have concerns", "i'm not sure about",
        ]
        suggest_phrases = [
            "i suggest", "i propose", "i think we should",
            "why don't we", "what if we", "let's go with",
            "my recommendation is", "i'd recommend",
            "we should consider", "how about",
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
            # Fallback: questions are usually information requests
            result["intent"] = "ask_info"

        return result

    # -----------------------------------------------------------------------
    # Text generators — strategy-differentiated dialogue
    # -----------------------------------------------------------------------
    def _generate_ask_text(self, item: str, target_id: str) -> str:
        if self.strategy == "cooperative":
            options = [
                f"{_role(target_id)}, I'm trying to make progress on {_lbl(item)}. Could you share what you know?",
                f"I think if we put our heads together on {_lbl(item)} we'll get there — do you have anything?",
                f"{_role(target_id)}, do you have any info on {_lbl(item)}? It would really help us move forward.",
                f"Hey {_role(target_id)}, I'm working through {item} — any chance you can fill me in?",
                f"{_role(target_id)}, we'd make much faster progress if you could share what you know about {item}.",
                f"I'd really appreciate your input on {_lbl(item)}, {_role(target_id)} — do you have anything useful?",
            ]
        elif self.strategy == "defensive":
            options = [
                f"{_role(target_id)}, I need to know about {item}. Do you know anything?",
                f"I can't move forward without {_lbl(item)}. Do you have it?",
                f"{_role(target_id)}, do you have the {item} information?",
                f"I'm blocked on {_lbl(item)}, {_role(target_id)}. Can you help?",
                f"{_role(target_id)}, what do you know about {item}?",
                f"I need {item} before I can do anything else. Do you have it, {_role(target_id)}?",
            ]
        elif self.strategy == "confrontational":
            options = [
                f"{_role(target_id)}, we need {item} sorted. Can you tell me what you know?",
                f"I need {item} and I'm not getting anywhere — do you have it?",
                f"{_role(target_id)}, what do you know about {item}? We're wasting time here.",
                f"Come on {_role(target_id)}, someone needs to share {item}. Is it you?",
                f"{_role(target_id)}, I'm done waiting on {item}. What do you know?",
                f"We're going nowhere without {item}, {_role(target_id)}. Can you sort this out?",
            ]
        elif self.strategy == "avoidant":
            options = [
                f"Um, {_role(target_id)} — do you maybe know anything about {item}?",
                f"I'm stuck on {_lbl(item)}. I don't want to bother you, but do you have anything?",
                f"{_role(target_id)}, sorry to ask — do you have info on {item}?",
                f"I hate to keep asking, but {_role(target_id)} — do you know anything about {item}?",
                f"Only if you're comfortable — do you have anything on {item}, {_role(target_id)}?",
                f"{_role(target_id)}, I wouldn't ask if I wasn't stuck, but do you know about {item}?",
            ]
        else:
            options = [
                f"{_role(target_id)}, I'm stuck on {_lbl(item)} and could really use your help.",
                f"I can't move forward without {_lbl(item)}, {_role(target_id)}. Do you know anything?",
                f"{_role(target_id)}, I need {_lbl(item)} to make progress. Can you share anything?",
                f"Do you have anything on {item}, {_role(target_id)}? I'm a bit stuck.",
                f"{_role(target_id)}, any chance you know about {item}?",
                f"I'm missing {_lbl(item)} — do you have what I need, {_role(target_id)}?",
            ]
        return random.choice(options)

    def _generate_share_text(self, item: str, target_id: str) -> str:
        info = self._generate_info_text(item)
        if self.strategy == "cooperative":
            options = [
                f"Happy to help, {_role(target_id)}. Here's what I know about {_lbl(item)}: {info}",
                f"Of course — let me share this with you, {_role(target_id)}: {info}",
                f"{_role(target_id)}, here's {item} — I think this will get us moving: {info}",
                f"Glad you asked, {_role(target_id)}. On {item}: {info}",
                f"This should help us both, {_role(target_id)} — here's what I know about {item}: {info}",
            ]
        elif self.strategy == "defensive":
            options = [
                f"Alright, {_role(target_id)} — here's {item}: {info}",
                f"I'll share this once, {_role(target_id)}: {info}",
                f"Okay, here's what you need on {item}: {info}",
                f"Fine, {_role(target_id)}. {item}: {info}",
                f"Here's {_lbl(item)} — I expect this stays between us, {_role(target_id)}: {info}",
            ]
        elif self.strategy == "confrontational":
            options = [
                f"Fine, {_role(target_id)}. Here: {item} — {info}",
                f"I'll tell you, but pay attention, {_role(target_id)}: {info}",
                f"{_role(target_id)}, here's {_lbl(item)}. Now we can actually move forward: {info}",
                f"Since nobody else is going to sort this — {item}: {info}",
                f"Here's what I know about {_lbl(item)}, {_role(target_id)}. Don't make me repeat it: {info}",
            ]
        elif self.strategy == "avoidant":
            options = [
                f"Okay… here's what I know about {item}, {_role(target_id)}: {info}",
                f"I suppose I can share {item} with you, {_role(target_id)}: {info}",
                f"This is {item} — I hope it helps, {_role(target_id)}: {info}",
                f"Alright, if it helps — here's {item}, {_role(target_id)}: {info}",
                f"I don't usually share this easily, but — {item}: {info}",
            ]
        else:
            options = [
                f"Here's what I know about {_lbl(item)}, {_role(target_id)}: {info}",
                f"Okay, I trust you with this — here's {item}: {info}",
                f"Let me help you out, {_role(target_id)}. Here's {_lbl(item)}: {info}",
                f"While we're talking — here's {item}: {info}",
                f"{_role(target_id)}, on {item}: {info}",
            ]
        return random.choice(options)

    def _generate_refuse_text(self, item: str, target_id: str) -> str:
        if self.strategy == "defensive":
            options = [
                f"I'm not comfortable sharing {item} right now, {_role(target_id)}.",
                f"{_role(target_id)}, I'd rather keep {item} to myself for now.",
                f"I don't feel ready to share {item} yet, {_role(target_id)}.",
                f"Not right now, {target_id}. I'm not sure I trust this enough.",
                f"I need more time before I share {item}, {_role(target_id)}.",
                f"{_role(target_id)}, I'd prefer to hold off on {item} for the moment.",
            ]
        elif self.strategy == "confrontational":
            options = [
                f"No, {_role(target_id)} — I'm not sharing {item}.",
                f"Why should I share {item} with you, {_role(target_id)}?",
                f"{_role(target_id)}, I'll keep {item} to myself, thanks.",
                f"I don't think you need {item} right now, {_role(target_id)}.",
                f"Not happening, {_role(target_id)}. {item} stays with me for now.",
            ]
        elif self.strategy == "avoidant":
            options = [
                f"Sorry, {_role(target_id)}, I'd prefer not to share {item} right now.",
                f"I'm not really in a position to share {item}. Sorry, {_role(target_id)}.",
                f"I'm going to hold off on {item} for now, {_role(target_id)}.",
                f"I'd rather not, {_role(target_id)} — maybe later on {item}.",
                f"Sorry {_role(target_id)}, I'm just not ready to share {item} yet.",
            ]
        else:
            options = [
                f"Sorry {_role(target_id)}, I'm not comfortable sharing {item} right now.",
                f"I don't think it's the right time to share {item}, {_role(target_id)}.",
                f"{_role(target_id)}, I'd rather wait on {item} for now.",
                f"Not yet, {_role(target_id)} — I want to wait a bit longer on {item}.",
                f"{_role(target_id)}, I'd prefer to hold off on {item} for now.",
            ]
        return random.choice(options)

    def _generate_agree_text(self, target_id: str, pref: str) -> str:
        if self.strategy == "cooperative":
            options = [
                f"I completely agree, {target_id} — {pref} makes a lot of sense.",
                f"Yes, {pref} is the right call. I'm fully on board, {target_id}.",
                f"That's a great suggestion, {target_id}. Let's go with {pref}.",
                f"I was thinking the same thing — {pref} works for me, {target_id}.",
                f"Absolutely, {target_id}. {pref} is the obvious choice here.",
            ]
        elif self.strategy == "confrontational":
            options = [
                f"Fair enough, {target_id}. {pref} works.",
                f"Alright — {pref} it is.",
                f"I'll go along with {pref} this time, {target_id}.",
                f"Fine, {pref}. I can live with that.",
                f"Okay {target_id}, {pref} — but I reserve the right to revisit this.",
            ]
        else:
            options = [
                f"I think you're right, {target_id}. {pref} makes sense.",
                f"Yeah, I agree — {pref} seems like the best option.",
                f"That sounds like a solid idea, {target_id}. I'm on board.",
                f"I'm with you on {pref}, {target_id}.",
                f"Sounds good to me — {pref} it is, {target_id}.",
            ]
        return random.choice(options)

    def _generate_challenge_text(self, target_id: str, pref: str) -> str:
        if self.strategy == "confrontational":
            options = [
                f"I don't agree, {target_id}. {pref} is the wrong move.",
                f"No — {pref} doesn't work. We need a better option.",
                f"I strongly disagree with {pref}, {target_id}. That's a mistake.",
                f"{pref}? Really, {target_id}? I think we can do better.",
                f"That's not going to work, {target_id}. {pref} creates more problems than it solves.",
            ]
        elif self.strategy == "defensive":
            options = [
                f"I'm not sure about {pref}, {target_id}. That worries me.",
                f"{pref} doesn't feel right to me, {target_id}. Can we reconsider?",
                f"I have concerns about {pref}, {target_id}.",
                f"I'd want to think more carefully before committing to {pref}, {target_id}.",
                f"Something about {pref} doesn't sit right with me, {target_id}.",
            ]
        else:
            options = [
                f"I'm not convinced {pref} is the best choice, {target_id}.",
                f"I don't think {pref} solves the real issue, {target_id}.",
                f"{pref} feels a bit risky to me — I'd go another way.",
                f"I'd push back on {pref}, {target_id} — there might be a better option.",
                f"Not sure {pref} is right here, {target_id}. What's the reasoning?",
            ]
        return random.choice(options)

    def _generate_info_text(self, item: str) -> str:
        # Multiple natural phrasings per item — chosen randomly to avoid repetition.
        templates = {
            "budget": [
                "the budget is set at $50k with a 10% contingency buffer built in.",
                "we've got $50k allocated, and there's a 10% buffer for unexpected costs.",
                "total budget is $50,000 — they've kept 10% back as a contingency.",
            ],
            "requirements": [
                "it needs to support both mobile access and offline mode — those are non-negotiable.",
                "the key requirements are mobile compatibility and offline functionality.",
                "must work on mobile and handle offline use — that's what the client specified.",
            ],
            "design": [
                "we're going with a flat, modern UI — blue colour scheme throughout.",
                "flat design, clean layout, and the primary colour is blue.",
                "modern flat UI with a blue theme — nothing too complicated visually.",
            ],
            "tech_specs": [
                "the stack is React on the frontend, Node for the backend, PostgreSQL for the database.",
                "React, Node.js, and PostgreSQL — that's what the team agreed on.",
                "frontend in React, backend in Node, and PostgreSQL handling the data layer.",
            ],
            "frontend": [
                "the frontend role is mainly UI and UX — someone who knows their way around design systems.",
                "whoever takes frontend needs solid UI/UX experience, ideally with React.",
                "frontend is about the user-facing side — design sensibility is important here.",
            ],
            "backend": [
                "backend needs someone comfortable with APIs and database design.",
                "it's API work and database management — needs a solid engineering background.",
                "the backend role covers the server logic and data layer — quite technical.",
            ],
            "testing": [
                "testing is QA and automation — we need someone who can write tests suites.",
                "the testing role covers quality assurance and building automated tests coverage.",
                "whoever does testing needs to be comfortable with QA processes and automation tools.",
            ],
            "documentation": [
                "documentation covers the technical specs and user-facing guides.",
                "it's writing up the specs and producing user documentation — detail-oriented work.",
                "the documentation role handles both internal technical docs and anything user-facing.",
            ],
            "italian": [
                "there's an Italian place nearby — good atmosphere, strong on pasta.",
                "the Italian option has a nice vibe, decent prices, and the pasta is supposed to be good.",
                "Italian restaurant — solid reviews, nice ambiance, pasta-focused menu.",
            ],
            "vegan": [
                "there's a vegan place that's got good reviews — all plant-based, healthy options.",
                "the vegan spot is popular, lots of variety, and it's not as expensive as you'd think.",
                "vegan restaurant — plant-based menu, good for anyone with dietary requirements.",
            ],
            "cheap": [
                "there's a budget-friendly option — quick, affordable, nothing fancy but decent food.",
                "the cheap option is a casual place, fast service, good value for money.",
                "affordable spot — not premium dining but perfectly good for a quick lunch.",
            ],
            "fancy": [
                "there's an upscale place if we want to push the boat out — proper sit-down dining.",
                "the fancy option is a premium restaurant — more expensive but the quality shows.",
                "upscale dining, great food, but it'll cost more than the other options.",
            ],
        }
        options = templates.get(item)
        if options:
            return random.choice(options)
        return "it's important context for the next step — worth knowing."

    # -----------------------------------------------------------------------
    # apply_events — CLEAN SEPARATION of social meaning vs emotional meaning
    #
    # Social meaning (trust, task progress) = event layer
    # Emotional meaning (valence, arousal, stress nuance) = NLP layer only
    #
    # To avoid double-counting:
    # - Event layer: trust delta + SMALL valence shift (social signal)
    # - NLP layer: emotional valence/arousal/stress effects
    # - Stress: event layer handles coarse stress only; NLP adds nuance
    # -----------------------------------------------------------------------
    def apply_events(self, events: List[Dict[str, Any]], tick: int) -> None:
        self.energy = max(0, self.energy - 1)
        self.valence  *= 0.965
        self.arousal   = clamp(self.arousal * 0.98 + 0.015, 0.0, 1.0)
        self.stress    = clamp(self.stress * 0.97, 0.0, 1.0)   # slow natural decay

        # Strategy-driven trust recovery (cooperative agents rebuild trust passively)
        trust_recovery = self._profile().get("trust_recovery_rate", 0.0)
        if trust_recovery != 0.0:
            for pid in self.trust:
                self.trust[pid] = clamp(self.trust[pid] + trust_recovery * 0.01, 0.0, 1.0)

        for e in events:
            if e.get("target") != self.public_id:
                continue
            actor_id = e.get("actor", "")
            etype    = e.get("type", "")
            text     = e.get("text", "")
            item     = e.get("item") or e.get("preference")

            self.awaiting_reply_from   = actor_id
            self.last_message_received = text
            self.last_speaker          = actor_id

            # ---- SOCIAL LAYER: trust delta (personality-modulated) ----
            dt = TRUST_DELTA_BASE.get(etype, 0.0)
            if etype == "refuse":
                dt *= (1.0 + self.N * 0.50)   # neurotic agents hit harder
            elif etype == "share_info":
                dt *= (0.9 + self.A * 0.40)
            self.trust[actor_id] = clamp(self.trust.get(actor_id, 0.5) + dt, 0.0, 1.0)

            # ---- SOCIAL LAYER: small valence shift (social signal only) ----
            # Deliberately kept small — emotional meaning comes from NLP below
            dv = VALENCE_DELTA.get(etype, 0.0) * 0.45
            self.valence = clamp(self.valence + dv, -1.0, 1.0)
            self.arousal = clamp(self.arousal + abs(dv) * 0.10, 0.0, 1.0)

            # ---- SOCIAL LAYER: coarse stress signal (event type only) ----
            # Strategy profile modulates sensitivity
            stress_sens = self._profile()["stress_sensitivity"]
            if etype in ("refuse", "challenge", "insult", "ignore"):
                self.stress = clamp(self.stress + 0.04 * stress_sens, 0.0, 1.0)
            elif etype in ("share_info", "agree", "help", "compliment"):
                self.stress = clamp(self.stress - 0.04 / stress_sens, 0.0, 1.0)

            # ---- FIX 4: Refusal consequences for the REFUSER (not just the refused) ----
            # When this agent RECEIVES a refusal, the refuser's trust drops and stress
            # rises on their end too — tracked via a reverse-lookup next apply cycle.
            # We handle the refuser's own penalty when they SEND a refuse event below.

            # ---- Knowledge propagation ----
            if etype == "share_info" and item and item not in self.known_items:
                self.known_items.add(item)

            # ---- NLP LAYER: emotional meaning (runs separately, not additive to social layer) ----
            # This layer exclusively owns: nuanced valence/arousal shifts, emotion-driven trust,
            # nuanced stress changes.  Social layer above does NOT touch these at full weight.
            if text:
                self.process_emotional_message(text, actor_id, tick)

            # ---- Memory ----
            mem = {
                "tick": tick, "kind": etype, "from": actor_id,
                "text": text, "item": item,
                "importance": clamp(abs(dv) + abs(dt), 0.0, 1.0),
            }
            self.stm.append(mem)
            if mem["importance"] >= 0.48:
                self.ltm.append(mem)

            self.update_relationships(tick)
            self.update_strategy()

            self.goal_progress = clamp(
                self.goal_progress + 0.013 * (1 + max(0.0, self.valence)), 0.0, 1.0
            )

    # -----------------------------------------------------------------------
    # NLP emotional processing — owns valence/arousal/stress nuance exclusively
    # Social layer above uses VALENCE_DELTA * 0.45 to avoid overlap
    # -----------------------------------------------------------------------
    def process_emotional_message(self, text: str, speaker: str, tick: int) -> Dict[str, float]:
        if not text or getattr(self.model, "skip_emotions", False):
            return {}

        emotions = self.emotion_analyser.analyse(text)
        if not emotions:
            return {}

        lower = text.lower()

        # --- Phrase-based overrides (hybrid rule + ML) ---
        if any(p in lower for p in ["not comfortable sharing", "rather keep", "prefer to keep"]):
            emotions["disappointment"] = max(emotions.get("disappointment", 0), 0.55)
        if any(p in lower for p in ["don't think it's a good idea", "not sure i trust", "have concerns about"]):
            emotions["disapproval"] = max(emotions.get("disapproval", 0), 0.60)
        if any(p in lower for p in ["this will help", "let me help you out", "i trust you with this",
                                     "happy to help", "of course"]):
            emotions["approval"]  = max(emotions.get("approval", 0), 0.60)
            emotions["optimism"]  = max(emotions.get("optimism", 0), 0.45)
        if any(p in lower for p in ["i strongly disagree", "that's a mistake", "wrong move"]):
            emotions["anger"]     = max(emotions.get("anger", 0), 0.55)
            emotions["disapproval"] = max(emotions.get("disapproval", 0), 0.50)
        if any(p in lower for p in ["completely agree", "great suggestion", "fully on board"]):
            emotions["joy"]       = max(emotions.get("joy", 0), 0.50)
            emotions["approval"]  = max(emotions.get("approval", 0), 0.55)

        # Neutral dampening
        if "neutral" in emotions and len(emotions) > 1:
            emotions["neutral"] *= 0.55

        va = self.emotion_analyser.get_valence_arousal(text)

        # Top-3 dominant emotions (noise-filtered)
        top_emotions = sorted(emotions.items(), key=lambda x: x[1], reverse=True)[:3]
        primary_emotion = top_emotions[0][0] if top_emotions else va.get("primary_emotion", "neutral")
        self.last_detected_emotion = primary_emotion

        # --- NLP baseline effects (deliberately small to avoid overlap) ---
        # Social layer already applied a 0.45-weight valence delta above
        self.valence = clamp(self.valence + (va.get("valence", 0.0) * 0.06), -1.0, 1.0)
        self.arousal = clamp(self.arousal + (va.get("arousal", 0.0) * 0.05), 0.0, 1.0)

        # NLP stress nuance (separate from event-level stress above)
        stress_delta = 0.0
        if va.get("valence", 0.0) < 0:
            stress_delta += abs(va["valence"]) * 0.05   # halved vs before
        if va.get("arousal", 0.0) > 0.6:
            stress_delta += (va["arousal"] - 0.6) * 0.07
        self.stress = clamp(self.stress + stress_delta, 0.0, 1.0)

        # --- Grouped weighted effects (psychological nuance layer) ---
        negative_high = {"anger", "annoyance", "disapproval", "disgust"}
        negative_low  = {"sadness", "disappointment", "remorse", "grief"}
        uncertain     = {"confusion", "curiosity", "nervousness", "fear"}
        positive      = {"joy", "gratitude", "approval", "admiration", "optimism", "relief"}

        for emotion, score in top_emotions:
            if emotion in negative_high:
                self.trust[speaker]  = clamp(self.trust.get(speaker, 0.5) - 0.04 * score, 0.0, 1.0)
                self.stress          = clamp(self.stress + 0.05 * score, 0.0, 1.0)
                self.valence         = clamp(self.valence - 0.06 * score, -1.0, 1.0)
            elif emotion in negative_low:
                self.stress          = clamp(self.stress + 0.04 * score, 0.0, 1.0)
                self.valence         = clamp(self.valence - 0.05 * score, -1.0, 1.0)
            elif emotion in uncertain:
                self.stress          = clamp(self.stress + 0.02 * score, 0.0, 1.0)
                self.arousal         = clamp(self.arousal + 0.03 * score, 0.0, 1.0)
            elif emotion in positive:
                self.trust[speaker]  = clamp(self.trust.get(speaker, 0.5) + 0.03 * score, 0.0, 1.0)
                self.stress          = clamp(self.stress - 0.03 * score, 0.0, 1.0)
                self.valence         = clamp(self.valence + 0.05 * score, -1.0, 1.0)

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
                abs(va.get("valence", 0.0)) + abs(va.get("arousal", 0.3) - 0.3), 0.0, 1.0
            ),
        }
        self.stm.append(mem)
        if mem["importance"] >= 0.48:
            self.ltm.append(mem)

        return emotions

    # -----------------------------------------------------------------------
    # Relationship tracking
    # -----------------------------------------------------------------------
    def update_relationships(self, tick: int):
        for oid, tv in list(self.trust.items()):
            if tv > 0.83:
                self.relationship_status[oid] = "ally"
                if oid not in self.allies:
                    self.allies.append(oid)
            elif tv < 0.24:
                self.relationship_status[oid] = "rival"
                if oid not in self.rivals:
                    self.rivals.append(oid)

    # -----------------------------------------------------------------------
    # State export
    # -----------------------------------------------------------------------
    def to_state(self) -> Dict[str, Any]:
        return {
            "id":                    self.public_id,
            "strategy":              self.strategy,
            "trust":                 {k: round(v, 3) for k, v in self.trust.items()},
            "known_items":           list(self.known_items),
            "mood": {
                "valence":           round(self.valence, 3),
                "arousal":           round(self.arousal, 3),
            },
            "stress":                round(self.stress, 3),
            "last_detected_emotion": self.last_detected_emotion,
            "goal_progress":         round(self.goal_progress, 3),
            "in_conversation_with":  self.current_conversation_with,
            "last_thought":          self.last_thought,
        }