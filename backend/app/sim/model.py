from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional
import mesa
import random
import copy

from app.sim.agent import SimAgent
from app.sim.environment import Environment
from app.sim.scenario import Scenario
from app.sim.scenario_data import SCENARIOS


# ---------------------------------------------------------------------------
# Helpers: trait-based seeding
# ---------------------------------------------------------------------------

def _trait_initial_trust(agent_traits: Dict[str, float], other_traits: Dict[str, float]) -> float:
    """
    Seed pairwise trust from personality traits.
    High Agreeableness → gives more trust.
    High Neuroticism   → gives less trust.
    High other-A       → receives more trust.
    """
    base = 0.40
    base += 0.20 * agent_traits.get("A", 0.5)   # agreeable agents start open
    base -= 0.15 * agent_traits.get("N", 0.5)   # neurotic agents start guarded
    base += 0.10 * other_traits.get("A", 0.5)   # trust agreeable peers more
    base -= 0.05 * other_traits.get("N", 0.5)   # trust neurotic peers slightly less
    return round(max(0.05, min(0.95, base)), 3)


def _trait_initial_strategy(traits: Dict[str, float]) -> str:
    """
    Map Big Five traits to an initial behavioural strategy so agents feel
    like distinct personalities from tick 1.
    """
    A = traits.get("A", 0.5)
    N = traits.get("N", 0.5)
    E = traits.get("E", 0.5)
    C = traits.get("C", 0.5)

    if N > 0.65:
        return "defensive"
    if A > 0.70 and E > 0.60:
        return "cooperative"
    if A < 0.40 and N > 0.50:
        return "avoidant"
    if C > 0.70 and E > 0.55:
        return "assertive"
    return "neutral"


# ---------------------------------------------------------------------------
# Scenario-specific dynamics modifiers
# ---------------------------------------------------------------------------

SCENARIO_MODIFIERS: Dict[str, Dict[str, float]] = {
    "office": {
        "base_trust_delta":    -0.05,   # colder start
        "arousal_rate":         1.0,
        "refusal_weight":       1.2,    # more defensive sharing
        "cooperation_weight":   0.9,
    },
    "cafe": {
        "base_trust_delta":     0.08,   # warmer start
        "arousal_rate":         0.8,
        "refusal_weight":       0.7,    # softer refusals
        "cooperation_weight":   1.3,
    },
    "escape": {
        "base_trust_delta":     0.00,
        "arousal_rate":         1.5,    # urgency rises faster
        "refusal_weight":       0.6,    # eventually forced to cooperate
        "cooperation_weight":   1.1,
    },
}


class SimModel(mesa.Model):
    def __init__(
        self,
        seed: int,
        min_events_per_tick: int = 2,
        episode_max_ticks: int = 120,
        environment: str = "office",
        scenario_id: str = "office_proposal",
    ) -> None:
        super().__init__(seed=seed)

        self.tick = 0
        self.seed_value = seed

        # Fix randomness for full reproducibility across runs
        import random as _random
        _random.seed(seed)
        try:
            import numpy as np
            np.random.seed(seed)
        except ImportError:
            pass
        self.min_events_per_tick = min_events_per_tick
        self.episode_max_ticks = episode_max_ticks
        self.tick_spoken = False
        self.conversation_ongoing = False

        self.last_diff: Optional[Dict[str, Any]] = None
        self.prev_events: List[Dict[str, Any]] = []
        self.reply_inbox: Dict[str, str] = {}
        self.ended = False
        self.end_reason = ""
        self.avg_trust_hist = deque(maxlen=10)

        # ----------------------------------------------------------------
        # Load scenario & environment
        # ----------------------------------------------------------------
        raw_scenario = copy.deepcopy(SCENARIOS[scenario_id])
        self.scenario = Scenario(id=scenario_id, **raw_scenario)
        self.environment = Environment(raw_scenario["environment"])

        # Scenario-level dynamics modifier
        env_type = self.environment.type
        self.env_mod: Dict[str, float] = SCENARIO_MODIFIERS.get(env_type, SCENARIO_MODIFIERS["office"])

        # ----------------------------------------------------------------
        # Group-level state variables
        # ----------------------------------------------------------------
        self.group_tension: float = 0.2          # 0 = calm, 1 = explosive
        self.group_cohesion: float = 0.5         # 0 = fragmented, 1 = united
        self.progress_stall_ticks: int = 0       # consecutive ticks with no new share
        self.recent_success_ticks: int = 0       # consecutive ticks with a share
        self.last_progress_ratio: float = 0.0

        # Global ask tracker: (asker_id, holder_id, item) → count
        # Persists across conversation timeouts — fixes force-share not triggering.
        self.global_ask_counts: Dict[tuple, int] = {}

        # Bottleneck tracking
        self.bottleneck_item: Optional[str] = None
        self.bottleneck_holder: Optional[str] = None
        self.bottleneck_age: int = 0             # ticks item has been blocking

        # Cumulative metrics (for evaluation)
        self.total_refusals: int = 0
        self.total_shares: int = 0
        self.total_stalled_ticks: int = 0
        self.strategy_history: List[Dict[str, str]] = []  # per-tick snapshot

        # Per-tick metric history — used by experiment service for whole-run averages
        # rather than relying on last-tick values only
        self.metric_history: List[Dict[str, Any]] = []

        # Full tick-by-tick state history for replay
        # Each entry is a copy of last_diff — agents, events, metrics, group_state
        self.history: List[Dict[str, Any]] = []

        # Order tasks were completed — useful for cross-run strategy analysis
        self.completion_order: List[str] = []

        # Optional drama/gossip
        self.gossip_network = {}
        self.active_drama = None
        self.drama_intensity = 0.5
        self.secret_knowledge = {}
        self.relationship_web = {}

        # ----------------------------------------------------------------
        # Create 4 agents
        # ----------------------------------------------------------------
        agent_defs = [
            {
                "public_id": "A1",
                "traits": {"E": 0.55, "A": 0.35, "N": 0.30, "C": 0.70, "O": 0.60},
                "speech_style": "formal",
                "long_goal": "Gain influence",
            },
            {
                "public_id": "A2",
                "traits": {"E": 0.85, "A": 0.75, "N": 0.20, "C": 0.65, "O": 0.55},
                "speech_style": "bubbly",
                "long_goal": "Keep harmony",
            },
            {
                "public_id": "A3",
                "traits": {"E": 0.35, "A": 0.30, "N": 0.70, "C": 0.80, "O": 0.50},
                "speech_style": "dry",
                "long_goal": "Avoid disrespect",
            },
            {
                "public_id": "A4",
                "traits": {"E": 0.60, "A": 0.55, "N": 0.40, "C": 0.55, "O": 0.75},
                "speech_style": "neutral",
                "long_goal": "Understand motives",
            },
        ]

        for defn in agent_defs:
            agent = SimAgent(
                self,
                public_id=defn["public_id"],
                traits=defn["traits"],
                speech_style=defn["speech_style"],
                long_goal=defn["long_goal"],
            )
            # Seed initial strategy from traits
            agent.strategy = _trait_initial_strategy(defn["traits"])

        # ----------------------------------------------------------------
        # Initialise pairwise trust from personality traits
        # ----------------------------------------------------------------
        agents_sorted = sorted(list(self.agents), key=lambda a: a.public_id)
        id_to_traits = {a.public_id: a.traits for a in agents_sorted}
        trust_delta = self.env_mod.get("base_trust_delta", 0.0)

        for a in agents_sorted:
            a.trust = {}
            for other in agents_sorted:
                if other is a:
                    continue
                t = _trait_initial_trust(a.traits, id_to_traits[other.public_id])
                t = round(max(0.05, min(0.95, t + trust_delta)), 3)
                a.trust[other.public_id] = t

        # ----------------------------------------------------------------
        # Assign initial knowledge from scenario
        # ----------------------------------------------------------------
        for a in agents_sorted:
            a.known_items = set(self.scenario.knowledge_map.get(a.public_id, []))

        # ----------------------------------------------------------------
        # Optional drama
        # ----------------------------------------------------------------
        self._initialize_drama()

    # ------------------------------------------------------------------
    # Drama initialisation (unchanged logic, kept intact)
    # ------------------------------------------------------------------
    def _initialize_drama(self):
        agents_list = list(self.agents)
        if self.environment.type == "cafe":
            for agent in agents_list:
                if random.random() < 0.4:
                    potential = [a for a in agents_list if a != agent]
                    if potential:
                        agent.crushes.append(random.choice(potential).public_id)
        elif self.environment.type == "office":
            for agent in agents_list:
                if random.random() < 0.3:
                    potential = [a for a in agents_list if a != agent]
                    if potential:
                        agent.grudge_against = random.choice(potential).public_id
        elif self.environment.type == "escape":
            secret_topics = ["found a key", "knows the code", "saw something", "hidden message"]
            for i, agent in enumerate(agents_list):
                if i < len(secret_topics):
                    agent.secrets[agent.public_id] = secret_topics[i]

    # ------------------------------------------------------------------
    # Reply inbox
    # ------------------------------------------------------------------
    def _build_reply_inbox(self) -> None:
        inbox: Dict[str, str] = {}
        for e in self.prev_events:
            actor = e.get("actor")
            target = e.get("target")
            if actor and target:
                inbox[target] = actor
        self.reply_inbox = inbox

    # ------------------------------------------------------------------
    # Group-level state update
    # ------------------------------------------------------------------
    def _update_group_state(self, agents_sorted: list, events: List[Dict[str, Any]]) -> None:
        """
        Recompute group_tension, group_cohesion, stall tracking, and
        bottleneck information after each tick.
        """
        # --- tension: rises with conflict events, falls with shares/agrees ---
        negative = sum(
            1 for e in events
            if e.get("type") in ("ignore", "insult", "refuse", "challenge")
        )
        positive = sum(
            1 for e in events
            if e.get("type") in ("share_info", "agree", "reassure")
        )
        n_events = max(1, len(events))
        tension_delta = (negative - positive) / n_events * 0.12
        self.group_tension = round(
            max(0.0, min(1.0, self.group_tension + tension_delta)), 3
        )

        # --- cohesion: rises with positive events, falls with conflict ---
        cohesion_delta = (positive - negative) / n_events * 0.08
        self.group_cohesion = round(
            max(0.0, min(1.0, self.group_cohesion + cohesion_delta)), 3
        )

        # --- stall / success streak ---
        current_progress = self.scenario.progress_ratio()
        if current_progress > self.last_progress_ratio:
            self.progress_stall_ticks = 0
            self.recent_success_ticks += 1
            self.last_progress_ratio = current_progress
        else:
            self.progress_stall_ticks += 1
            self.recent_success_ticks = 0
            self.total_stalled_ticks += 1

        # --- bottleneck: find the knowledge item blocking progress longest ---
        missing_items = [
            task for task, done in self.scenario.tasks.items()
            if not done
        ]
        if missing_items:
            # Find who holds each missing item
            agents_list = list(self.agents)
            new_bottleneck = missing_items[0]  # first uncompleted item
            holder = None
            for a in agents_list:
                if new_bottleneck in getattr(a, "known_items", set()):
                    holder = a.public_id
                    break

            if new_bottleneck == self.bottleneck_item:
                self.bottleneck_age += 1
            else:
                self.bottleneck_item = new_bottleneck
                self.bottleneck_holder = holder
                self.bottleneck_age = 1
        else:
            self.bottleneck_item = None
            self.bottleneck_holder = None
            self.bottleneck_age = 0

        # --- apply group tension as environment modifier on agents ---
        # High tension suppresses willingness to share
        for a in agents_sorted:
            a.env_tension_modifier = self.group_tension  # agent.py can read this

    # ------------------------------------------------------------------
    # Main step
    # ------------------------------------------------------------------
    def step(self) -> None:
        self.tick_spoken = False
        self.conversation_ongoing = False
        if self.ended:
            return

        self.tick += 1
        self._build_reply_inbox()

        agents_sorted = sorted(list(self.agents), key=lambda a: a.public_id)

        # 1) Decide events
        events: List[Dict[str, Any]] = []
        for a in agents_sorted:
            others = [o for o in agents_sorted if o is not a]
            e = a.decide_event(others)
            if e is not None:
                events.append(e)

        # 2) Apply events
        for a in agents_sorted:
            a.apply_events(events, tick=self.tick)

        # 3) Update scenario tasks + global ask tracker
        for e in events:
            if e.get("type") == "ask_info":
                # Track globally so force-share survives conversation timeouts
                item      = e.get("item")
                asker     = e.get("actor")
                target_id = e.get("target")
                if asker and target_id and item:
                    key = (asker, target_id, item)
                    self.global_ask_counts[key] = self.global_ask_counts.get(key, 0) + 1
        for e in events:
            if e.get("type") == "share_info":
                item = e.get("item")
                if item:
                    self.scenario.complete_task(item)
                    self.total_shares += 1
                    if item not in self.completion_order:
                        self.completion_order.append(item)
            if e.get("type") == "refuse":
                self.total_refusals += 1
            if e.get("type") == "agree" and self.scenario.name == "Choose Restaurant":
                self.scenario.complete_task("decision")

        # 4) Update group-level state & bottleneck
        self._update_group_state(agents_sorted, events)

        # 5) Snapshot strategy distribution this tick
        self.strategy_history.append(
            {a.public_id: getattr(a, "strategy", "unknown") for a in agents_sorted}
        )

        # 6) Build ties and metrics
        ties = self._compute_ties(agents_sorted)
        metrics = self._compute_metrics(agents_sorted, events)

        # Append snapshot to per-tick history for whole-run analysis
        self.metric_history.append({
            "tick":           self.tick,
            "avg_trust":      metrics["avg_trust"],
            "avg_stress":     metrics["avg_stress"],
            "conflict_rate":  metrics["conflict_rate"],
            "group_tension":  metrics["group_tension"],
            "group_cohesion": metrics["group_cohesion"],
            "share_count":    metrics["share_count"],
            "refusal_count":  metrics["refusal_count"],
        })

        # 7) Check scenario outcome
        outcome = self.scenario.outcome(self.tick)
        if outcome != "running":
            self.ended = True
            self.end_reason = outcome

        elif self.tick >= self.episode_max_ticks:
            self.ended = True
            self.end_reason = "max_ticks"

        # 8) Intelligent compound end conditions
        if not self.ended:
            self.avg_trust_hist.append(metrics["avg_trust"])
            if len(self.avg_trust_hist) == self.avg_trust_hist.maxlen:
                avg_t = sum(self.avg_trust_hist) / len(self.avg_trust_hist)
                avg_stress = metrics.get("avg_stress", 0.5)
                progress = self.scenario.progress_ratio()

                # Meltdown: low trust + high stress + no progress for 8+ ticks
                if (
                    avg_t < 0.30
                    and avg_stress > 0.65
                    and self.progress_stall_ticks >= 8
                ):
                    self.ended = True
                    self.end_reason = "meltdown"

                # Harmony: high trust + low conflict + steady progress 6+ ticks
                elif (
                    avg_t > 0.85
                    and self.group_tension < 0.25
                    and self.recent_success_ticks >= 6
                ):
                    self.ended = True
                    self.end_reason = "harmony"

                # Deadlock: same item blocked for 15+ ticks despite asks
                elif (
                    self.bottleneck_age >= 15
                    and self.progress_stall_ticks >= 15
                    and progress < 1.0
                ):
                    self.ended = True
                    self.end_reason = "deadlock"

        # Save events for next tick
        self.prev_events = events

        # 9) Build diff
        self.last_diff = {
            "tick": self.tick,
            "agents": [a.to_state() for a in agents_sorted],
            "ties": ties,
            "events": events,
            "metrics": metrics,
            "group_state": {
                "tension": self.group_tension,
                "cohesion": self.group_cohesion,
                "stall_ticks": self.progress_stall_ticks,
                "success_streak": self.recent_success_ticks,
                "bottleneck_item": self.bottleneck_item,
                "bottleneck_holder": self.bottleneck_holder,
                "bottleneck_age": self.bottleneck_age,
            },
            "scenario": {
                "id": self.scenario.id,
                "name": self.scenario.name,
                "description": self.scenario.description,
                "tasks": self.scenario.tasks,
                "progress": round(self.scenario.progress_ratio(), 3),
                "outcome": outcome,
            },
            "ended": self.ended,
            "end_reason": self.end_reason,
        }

        # Append a copy to history for replay support.
        # Using dict copy rather than deepcopy for performance — events and
        # agent states are already freshly constructed each tick.
        self.history.append(dict(self.last_diff))

    # ------------------------------------------------------------------
    # Intervention entry point
    # ------------------------------------------------------------------
    def apply_intervention(self, intervention_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply a user intervention to the running simulation.
        Delegates to intervention_service which routes to interventions.py.
        Called by the API layer — never from within step().
        """
        from app.services.intervention_service import apply_intervention as _apply
        result = _apply(self, intervention_type, params)

        # Log the intervention in last_diff so the frontend can show feedback
        if self.last_diff is not None:
            self.last_diff.setdefault("interventions", []).append({
                "tick": self.tick,
                "type": intervention_type,
                "params": params,
                "result": result,
            })
        return result

    def _compute_ties(self, agents_sorted):
        ties = []
        id_to_agent = {a.public_id: a for a in agents_sorted}
        ids = [a.public_id for a in agents_sorted]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a_id, b_id = ids[i], ids[j]
                aa = id_to_agent[a_id]
                bb = id_to_agent[b_id]
                trust = (aa.trust.get(b_id, 0.5) + bb.trust.get(a_id, 0.5)) / 2.0
                ties.append({"a": a_id, "b": b_id, "trust": round(trust, 3)})
        return ties

    # ------------------------------------------------------------------
    # Metrics (now richer)
    # ------------------------------------------------------------------
    def _compute_metrics(self, agents_sorted, events) -> Dict[str, Any]:
        ties = self._compute_ties(agents_sorted)
        avg_trust = (
            sum(t["trust"] for t in ties) / len(ties) if ties else 0.5
        )
        mean_valence = sum(a.valence for a in agents_sorted) / len(agents_sorted)
        mean_arousal = sum(a.arousal for a in agents_sorted) / len(agents_sorted)

        stresses = [getattr(a, "stress", 0.5) for a in agents_sorted]
        avg_stress = sum(stresses) / len(stresses)
        stress_variance = (
            sum((s - avg_stress) ** 2 for s in stresses) / len(stresses)
        )

        negative_types = ("ignore", "insult", "refuse", "challenge")
        negative_events = sum(1 for e in events if e.get("type") in negative_types)
        conflict_rate = negative_events / max(1, len(events))

        # Per-tick counts
        refusal_count = sum(1 for e in events if e.get("type") == "refuse")
        share_count   = sum(1 for e in events if e.get("type") == "share_info")

        event_counts: Dict[str, int] = {}
        for e in events:
            et = str(e.get("type", ""))
            event_counts[et] = event_counts.get(et, 0) + 1

        # Strategy distribution this tick
        strategy_distribution: Dict[str, int] = {}
        for a in agents_sorted:
            s = getattr(a, "strategy", "unknown")
            strategy_distribution[s] = strategy_distribution.get(s, 0) + 1

        # Progress delta vs last tick
        current_progress = self.scenario.progress_ratio()
        progress_delta = round(current_progress - self.last_progress_ratio, 3)

        return {
            # Core
            "avg_trust":            round(avg_trust, 3),
            "mean_valence":         round(mean_valence, 3),
            "mean_arousal":         round(mean_arousal, 3),
            "conflict_rate":        round(conflict_rate, 3),
            # Stress
            "avg_stress":           round(avg_stress, 3),
            "stress_variance":      round(stress_variance, 4),
            # Activity
            "refusal_count":        refusal_count,
            "share_count":          share_count,
            "event_counts":         event_counts,
            # Progress
            "progress_delta":       progress_delta,
            "stalled_ticks":        self.progress_stall_ticks,
            # Bottleneck
            "bottleneck_item":      self.bottleneck_item,
            "bottleneck_holder":    self.bottleneck_holder,
            "bottleneck_age":       self.bottleneck_age,
            # Strategy snapshot
            "strategy_distribution": strategy_distribution,
            # Cumulative (useful for experiment analysis)
            "cumulative_refusals":  self.total_refusals,
            "cumulative_shares":    self.total_shares,
            "cumulative_stalled":   self.total_stalled_ticks,
            # Group
            "group_tension":        self.group_tension,
            "group_cohesion":       self.group_cohesion,
        }