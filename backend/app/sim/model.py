"""Main simulation model that owns agents, ticks, and shared group state.

Core simulation state machine.

Useful landmarks in this file:
- __init__()              -> builds one fresh run
- _update_group_state()   -> updates tension/cohesion/progress after each tick
- _build_tick_diff()      -> shapes the frontend/replay payload for one tick
- step()                  -> advances the simulation by one tick
- apply_intervention()    -> accepts a live intervention inside the model
- inject_user_emotion()   -> applies the NLP/rule-based mood effect
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional
import copy
import random
import re

import mesa


from app.sim.game_config import (
    STRESS_CAPS,
    PRESET_INITIAL_STATE,
    PRESET_TRUST_DELTA,
    PRESET_STRESS_SEED,
    TRUST_CAPS,
    PRESET_TENSION_FLOOR,
    SCENARIO_TENSION_FLOOR,
)

# Backward-compatible aliases
STRESS_CAPS_BY_SCENARIO_PRESET = STRESS_CAPS
TRUST_CAPS_BY_SCENARIO = TRUST_CAPS


_LOWERCASE_I_PATTERN = re.compile(r"(?<![A-Za-z'])i(?![A-Za-z'])")
# Do NOT capitalise after an ellipsis (e.g. "Umm... okay" must stay lowercase)
_AFTER_PUNCT_LOWER = re.compile(r"(?<!\.)([.!?]\s+)([a-z])")
_SENTENCE_START_LOWER = re.compile(r"^\s*([a-z])")
_AFTER_COLON_DASH_LOWER = re.compile(r"([:—]\s+)([a-z])")
_COLLAPSE_SPACES = re.compile(r"\s{2,}")


def _polish_dialogue(text: str) -> str:
    """Final cleanup pass for any rendered dialogue text.

    - Capitalises standalone lowercase "i" → "I"
    - Capitalises first letter of each sentence
    - Capitalises after a colon or em-dash when the next char starts a clause
    - Collapses accidental double spaces
    - Removes leftover "Reason: ... ETA: N ticks." debug fragments
    """
    if not text:
        return text

    # Strip debug-style fragments if any slip through
    if "Reason:" in text or " ETA:" in text or "ETA:" in text:
        text = re.sub(r"\s*Reason:\s*[^.]*\.?", "", text)
        text = re.sub(r"\s*ETA:\s*[^.]*\.?", "", text)
        text = re.sub(r"\s*\d+\s*ticks?\.?", "", text)

    # Fix standalone lowercase "i" → "I"
    text = _LOWERCASE_I_PATTERN.sub("I", text)

    # Capitalise first letter of the string
    match = _SENTENCE_START_LOWER.match(text)
    if match:
        idx = match.start(1)
        text = text[:idx] + text[idx].upper() + text[idx + 1 :]

    # Capitalise after sentence-ending punctuation
    def _cap_after_punct(m):
        return m.group(1) + m.group(2).upper()
    text = _AFTER_PUNCT_LOWER.sub(_cap_after_punct, text)

    # Collapse double spaces
    text = _COLLAPSE_SPACES.sub(" ", text).strip()
    return text

from app.sim.agent import SimAgent
from app.sim.environment import Environment
from app.sim.scenario import Scenario
from app.sim.scenario_data import SCENARIOS, resolve_scenario_id
from app.sim.scenario_logic import get_scenario_logic


# ============================================================
# AGENT TRAIT HELPERS
# These helpers turn personality trait scores into starting
# trust and starting strategy before the tick loop begins.
# ============================================================

def _trait_initial_trust(
    agent_traits: Dict[str, float],
    other_traits: Dict[str, float],
) -> float:
    """Calculate the initial trust that one agent has toward another, based on OCEAN traits.

    Agreeableness (A) raises trust — agreeable people extend more good faith.
    Neuroticism (N) lowers trust — anxious/neurotic people are more guarded by default.
    The other agent's traits also matter slightly: a highly agreeable target gets
    a small bonus, and a neurotic one gets a small penalty.

    Result is clamped to [0.05, 0.95] so no agent starts with zero or perfect trust.
    """
    # clamped to [0.05, 0.95] — no agent starts fully trusting or fully suspicious
    base = 0.40
    base += 0.20 * agent_traits.get("A", 0.5)   # agreeable agents trust more easily
    base -= 0.15 * agent_traits.get("N", 0.5)   # neurotic agents are less trusting
    base += 0.10 * other_traits.get("A", 0.5)   # we trust agreeable people a bit more
    base -= 0.05 * other_traits.get("N", 0.5)   # we're slightly wary of neurotic people
    return round(max(0.05, min(0.95, base)), 3)


def _trait_initial_strategy(traits: Dict[str, float]) -> str:
    """Determine the most appropriate starting strategy from an agent's OCEAN traits.

    The rules try to capture the most behaviorally relevant combinations:
    - High Neuroticism → defensive (anxious agents withdraw and guard themselves)
    - High Agreeableness + Extraversion → cooperative (sociable and warm)
    - Low Agreeableness + high Neuroticism → avoidant (reluctant and anxious)
    - High Conscientiousness + Extraversion → assertive (goal-driven and outgoing)
    - Everything else → neutral (baseline, no strong personality pull)
    """
    a_val = traits.get("A", 0.5)
    n_val = traits.get("N", 0.5)
    e_val = traits.get("E", 0.5)
    c_val = traits.get("C", 0.5)

    if n_val > 0.65:
        return "defensive"
    if a_val > 0.70 and e_val > 0.60:
        return "cooperative"
    if a_val < 0.40 and n_val > 0.50:
        return "avoidant"
    if c_val > 0.70 and e_val > 0.55:
        return "assertive"
    return "neutral"


# ============================================================
# SIMULATION MODEL INITIALISATION
# SimModel represents one full run from start to finish.
# __init__ is where a run is assembled before any ticks happen.
# ============================================================

class SimModel(mesa.Model):
    """The top-level simulation model — owns agents, scenario state, and the tick loop.

    On creation it sets up the scenario, environment, four agents (with personality/
    trust/stress seeds based on the team preset), and all the per-run tracking
    variables. The main entry point is step(), which advances one tick.
    """

    def __init__(
        self,
        seed: int,
        min_events_per_tick: int = 2,
        episode_max_ticks: int = 120,
        environment: Optional[str] = None,
        scenario_id: str = "office_proposal",
        use_nlp: bool = False,
        team_type: Optional[str] = None,
        team_preset: Optional[str] = None,
    ) -> None:
        """Set up all simulation state for a new run.

        Parameters
        ----------
        seed : int
            RNG seed for reproducibility.
        min_events_per_tick : int
            Minimum number of events generated each tick (currently advisory).
        episode_max_ticks : int
            Hard tick limit — the run ends when this is reached regardless of outcome.
        environment : str, optional
            Override the scenario's default environment string.
        scenario_id : str
            Which scenario to run (e.g. "office_proposal", "cafe_lunch").
        use_nlp : bool
            If True, NLP-based emotion analysis is active; otherwise rule-based only.
        team_type : str, optional
            Team composition label used to resolve personalities (e.g. "smooth").
        team_preset : str, optional
            Preset label that seeds initial group tension/cohesion/stress.
        """
        super().__init__(seed=seed)

        self.tick = 0
        self.seed_value = seed
        self.use_nlp = use_nlp
        self.skip_emotions = not use_nlp
        self.team_type = team_type
        self.team_preset = team_preset

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

        resolved_scenario_id = resolve_scenario_id(scenario_id)
        raw_scenario = copy.deepcopy(SCENARIOS[resolved_scenario_id])
        scenario_environment = environment or raw_scenario["environment"]
        self.scenario_type = "escape" if scenario_environment == "escape_room" else scenario_environment

        self.scenario = Scenario(id=resolved_scenario_id, **raw_scenario)
        self.environment = Environment(scenario_environment)
        self.behaviour = get_scenario_logic(resolved_scenario_id)
        self.env_mod = self._scenario_modifiers()

        self.group_tension: float = 0.2
        self.group_cohesion: float = 0.5

        # Seed initial group dynamics from team preset so different teams
        # start in visibly different states without touching step logic.
        _init = PRESET_INITIAL_STATE.get(str(self.team_preset or "").lower())
        if _init:
            self.group_tension, self.group_cohesion = _init

        # Apply scenario-specific offsets on top of team seeds
        _t_delta = self.env_mod.get("initial_tension_delta", 0.0)
        _c_delta = self.env_mod.get("initial_cohesion_delta", 0.0)
        self.group_tension = round(max(0.0, min(0.95, self.group_tension + _t_delta)), 3)
        self.group_cohesion = round(max(0.05, min(0.95, self.group_cohesion + _c_delta)), 3)
        self.progress_stall_ticks: int = 0
        self.recent_success_ticks: int = 0
        self.last_progress_ratio: float = 0.0

        self.global_ask_counts: Dict[tuple[str, str, str], int] = {}

        self.bottleneck_item: Optional[str] = None
        self.bottleneck_holder: Optional[str] = None
        self.bottleneck_age: int = 0

        self.total_refusals: int = 0
        self.total_shares: int = 0
        self.total_stalled_ticks: int = 0
        self.total_conflict_events: int = 0  # refuse + challenge + insult + ignore
        self.total_events: int = 0

        self.run_metrics = {
            "emotional": 0.0,
            "coord_pressure": 0.0,
            "conflict": 0.0,
        }
        self.conflict_score = 0.0
        self.coord_pressure_score = 0.0
        self.strategy_history: List[Dict[str, str]] = []
        self.metric_history: List[Dict[str, Any]] = []
        self.history: List[Dict[str, Any]] = []
        self.completion_order: List[str] = []

        # ── Intervention tracking ──────────────────────────────────────────
        # _tick_interventions:   cleared at the start of each step(); holds
        #   interventions applied since the previous step ended.
        #   Each entry is {"type": str, "params": dict} so that per-tick history
        #   snapshots can carry the full detail (item, agent_id, etc.) for replay.
        # _applied_interventions_log: full run-level list (strings only), never
        #   cleared; used by classify_run_outcome() and describe_run().
        self._tick_interventions: List[Dict[str, Any]] = []
        self._applied_interventions_log: List[str] = []
        self._current_tick_interventions: List[Dict[str, Any]] = []  # snapshot for this tick

        self._final_relief_applied = False
        self._final_decision: Optional[str] = None
        self.phrase_cooldowns: Dict[str, Any] = {}
        self._pending_events: List[Dict[str, Any]] = []
        self._tension_impulse_floor: float = 0.0
        self._tension_impulse_remaining: int = 0

        # ── User emotion injection tracking ───────────────────────────────
        # _emotion_log:    every inject_user_emotion() call appended here.
        # _emotion_effect: active decay state; cleared when effect fades.
        self._emotion_log: List[Dict[str, Any]] = []
        self._emotion_effect: Dict[str, Any] = {}

        self.gossip_network: Dict[str, Any] = {}
        self.active_drama = None
        self.drama_intensity = 0.5
        self.secret_knowledge: Dict[str, Any] = {}
        self.relationship_web: Dict[str, Any] = {}

        from app.sim.agent_builder import apply_personality_to_agent, build_agent_traits

        default_personalities = {
            "A1": "Leader",
            "A2": "Easygoing",
            "A3": "Skeptical",
            "A4": "Creative",
        }

        base_agent_meta = {
            "A1": {"speech_style": "formal", "long_goal": "Gain influence"},
            "A2": {"speech_style": "bubbly", "long_goal": "Keep harmony"},
            "A3": {"speech_style": "dry", "long_goal": "Avoid disrespect"},
            "A4": {"speech_style": "neutral", "long_goal": "Understand motives"},
        }

        if team_type:
            from app.services.simulation_config import resolve_team_personalities
            agent_defs = []
            team_personalities = resolve_team_personalities(team_type)
            if not self.team_preset:
                preset_map = {
                    "smooth": "smooth_team",
                    "tension": "tension_team",
                    "creative": "creative_team",
                    "pressure": "pressure_team",
                    "balanced": "balanced_team",
                    "smooth_team": "smooth_team",
                    "tension_team": "tension_team",
                    "creative_team": "creative_team",
                    "pressure_team": "pressure_team",
                    "balanced_team": "balanced_team",
                }
                self.team_preset = preset_map.get(str(team_type).strip().lower(), str(team_type).strip().lower())
            for index, public_id in enumerate(("A1", "A2", "A3", "A4")):
                personality = team_personalities[index]
                traits, resolved_personality = build_agent_traits(
                    scenario_id,
                    agent_id=public_id,
                    personality=personality,
                    add_noise=False,
                )
                meta = base_agent_meta[public_id]
                agent_defs.append(
                    {
                        "public_id": public_id,
                        "traits": traits,
                        "speech_style": meta["speech_style"],
                        "long_goal": meta["long_goal"],
                        "personality": resolved_personality,
                    }
                )
        else:
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

        for definition in agent_defs:
            agent = SimAgent(
                self,
                public_id=definition["public_id"],
                traits=definition["traits"],
                speech_style=definition["speech_style"],
                long_goal=definition["long_goal"],
            )
            agent.strategy = _trait_initial_strategy(definition["traits"])
            # Nudge strategy toward the team preset's expected behavioural profile.
            # Trait-derived strategies are personality-accurate but preset-unaware:
            # a "neutral" agent on a tension team behaves identically to one on a
            # smooth team unless we apply this correction. The nudge is intentionally
            # narrow — it only shifts strategies that would make the team feel wrong
            # given the preset, leaving strongly-typed strategies (defensive on high-N
            # agents, cooperative on high-A/E agents) intact.
            _preset_key = str(self.team_preset or "").lower()
            if _preset_key == "smooth_team":
                if agent.strategy == "neutral":
                    agent.strategy = "cooperative"
                elif agent.strategy == "defensive":
                    agent.strategy = "neutral"
            elif _preset_key == "tension_team":
                n_val = definition["traits"].get("N", 0.5)
                if agent.strategy == "cooperative":
                    # High-N agents become defensive; others become confrontational
                    agent.strategy = "defensive" if n_val > 0.5 else "confrontational"
                elif agent.strategy == "neutral":
                    agent.strategy = "defensive"

            apply_personality_to_agent(
                agent,
                definition.get(
                    "personality",
                    default_personalities.get(definition["public_id"], "Easygoing"),
                ),
            )

        agents_sorted = sorted(list(self.agents), key=lambda a: a.public_id)
        id_to_traits = {a.public_id: a.traits for a in agents_sorted}
        trust_delta = (
            self.env_mod.get("base_trust_delta", 0.0)
            + PRESET_TRUST_DELTA.get(str(self.team_preset or "").lower(), 0.0)
        )

        for agent in agents_sorted:
            agent.trust = {}
            for other in agents_sorted:
                if other is agent:
                    continue
                trust = _trait_initial_trust(
                    agent.traits,
                    id_to_traits[other.public_id],
                )
                agent.trust[other.public_id] = round(
                    max(0.05, min(0.95, trust + trust_delta)),
                    3,
                )

        # Seed initial agent stress from team preset + scenario offset.
        # Agent random init (0.05–0.18) is overridden here so different team/scenario
        # combinations start in clearly different emotional states.
        _base_stress = PRESET_STRESS_SEED.get(str(self.team_preset or "").lower(), 0.11)
        _stress_scenario_delta = self.env_mod.get("initial_stress_delta", 0.0)
        for agent in agents_sorted:
            # Add small per-agent noise so agents aren't identical within a team
            _noise = (hash(agent.public_id) % 7 - 3) * 0.01
            agent.stress = round(
                max(0.02, min(0.75, _base_stress + _stress_scenario_delta + _noise)),
                3,
            )

        for agent in agents_sorted:
            agent.known_items = set(self.scenario.knowledge_map.get(agent.public_id, []))

        if hasattr(self.behaviour, "init_scenario_state"):
            self.behaviour.init_scenario_state(self)

        original_outcome = self.scenario.outcome
        model_ref = self

        def patched_outcome(tick: int) -> str:
            raw = original_outcome(tick)
            if hasattr(model_ref.behaviour, "outcome_for_tick"):
                return model_ref.behaviour.outcome_for_tick(model_ref, tick, raw)
            return raw

        self.scenario.outcome = patched_outcome

    # ============================================================
    # SCENARIO AND TASK HELPERS
    # These helpers answer questions like:
    # - what is the current focus?
    # - what order should tasks resolve in?
    # - which scenario-specific weights/modifiers apply?
    # ============================================================

    def mark_task_complete(self, item: str) -> None:
        if not self.scenario.tasks.get(item, False):
            self.scenario.complete_task(item)
            if item not in self.completion_order:
                self.completion_order.append(item)

    def _priority_missing_items(self, tasks_override: Optional[Dict[str, Any]] = None) -> List[str]:
        if tasks_override is None:
            if getattr(getattr(self, "behaviour", None), "scenario_type", None) == "escape" and hasattr(self.behaviour, "_priority_missing"):
                return list(self.behaviour._priority_missing(self))
            return [task for task, done in self.scenario.tasks.items() if not done]

        scenario_type = getattr(getattr(self, "behaviour", None), "scenario_type", None)
        if scenario_type == "escape":
            order = ["map", "lock", "key", "door", "unlock"]
            return [task for task in order if not tasks_override.get(task, False)]
        if scenario_type == "office":
            order = ["requirements", "design", "tech_specs", "budget"]
            return [task for task in order if not tasks_override.get(task, False)]
        if scenario_type == "cafe":
            order = ["dietary_constraint", "budget_constraint", "location_constraint", "decision"]
            return [task for task in order if not tasks_override.get(task, False)]
        return [task for task, done in tasks_override.items() if not done]

    def _active_blocker_from_tasks(self, tasks_override: Optional[Dict[str, Any]] = None) -> Optional[str]:
        missing = self._priority_missing_items(tasks_override)
        return missing[0] if missing else None

    def _scenario_modifiers(self) -> Dict[str, float]:
        if hasattr(self.behaviour, "scenario_modifiers"):
            return self.behaviour.scenario_modifiers(self)
        return {
            "base_trust_delta": 0.0,
            "arousal_rate": 1.0,
            "refusal_weight": 1.0,
            "cooperation_weight": 1.0,
        }

    def _metric_weights(self) -> Dict[str, float]:
        if hasattr(self.behaviour, "metric_weights"):
            return self.behaviour.metric_weights(self)
        return {
            "challenge": 1.0,
            "refuse": 1.0,
            "stall": 1.0,
            "bottleneck": 1.0,
            "positive": 1.0,
        }

    def _resolve_stress_cap(self) -> Optional[float]:
        preset = getattr(self, "team_preset", None)
        scenario_type = getattr(self, "scenario_type", None)
        if not preset or not scenario_type:
            return None
        return STRESS_CAPS.get((scenario_type, preset))

    def _final_success_relief(self) -> tuple[float, float, float]:
        if hasattr(self.behaviour, "final_success_relief"):
            return self.behaviour.final_success_relief(self)
        return (0.12, 0.07, 0.05)

    def _accumulate_behaviour_metric_deltas(
        self,
        events: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        if hasattr(self.behaviour, "accumulate_run_metrics"):
            return self.behaviour.accumulate_run_metrics(self, events)
        return {"emotional": 0.0, "coord_pressure": 0.0, "conflict": 0.0}

    def _counts_as_share(self, event: Dict[str, Any]) -> bool:
        if hasattr(self.behaviour, "counts_as_share"):
            return bool(self.behaviour.counts_as_share(self, event))
        return event.get("type") == "share_info"

    def _build_reply_inbox(self) -> None:
        inbox: Dict[str, str] = {}
        for event in self.prev_events:
            actor = event.get("actor")
            target = event.get("target")
            if actor and target:
                inbox[target] = actor
        self.reply_inbox = inbox

    def _event_priority(self, event_type: str) -> int:
        # share_info highest — only type that resolves tasks
        priority = {
            "share_info": 9,
            "refuse": 8,
            "challenge": 7,
            "agree": 7,
            "ask_info": 6,
            "suggest": 5,
            "help": 4,
            "say": 3,
            "compliment": 2,
            "ignore": 1,
            "insult": 1,
        }
        return priority.get(event_type, 0)

    def _filter_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        from app.sim.event_pipeline import filter_events
        return filter_events(self, events)

    def _dedupe_same_actor_events(
        self,
        events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        # one event per agent per tick — user-triggered always beats autonomous
        agent_events: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        passthrough: List[Dict[str, Any]] = []

        for event in events:
            actor = str(event.get("actor", ""))
            if actor:
                agent_events[actor].append(event)
            else:
                passthrough.append(event)

        deduped = list(passthrough)
        for actor_event_list in agent_events.values():
            if len(actor_event_list) == 1:
                deduped.append(actor_event_list[0])
            else:
                best = max(
                    actor_event_list,
                    key=lambda ev: (
                        1 if str(ev.get("reason", "")).startswith("user_") else 0,
                        self._event_priority(str(ev.get("type", ""))),
                    ),
                )
                deduped.append(best)

        return deduped

    def _dedupe_by_phrase_and_text(
        self,
        events: List[Dict[str, Any]],
        existing_events: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        seen_agent_phrases: Dict[str, bool] = {}
        seen_texts: set[str] = set()

        for event in existing_events or []:
            actor = str(event.get("actor", ""))
            phrase_key = str(event.get("phrase_key", ""))
            text = str(event.get("text", ""))

            if actor and phrase_key:
                seen_agent_phrases[f"{actor}:{phrase_key}"] = True
            if text:
                seen_texts.add(text)

        final_events: List[Dict[str, Any]] = []

        for event in events:
            actor = str(event.get("actor", ""))
            phrase_key = str(event.get("phrase_key", ""))
            text = str(event.get("text", ""))

            key = f"{actor}:{phrase_key}" if actor and phrase_key else None

            if key and key in seen_agent_phrases:
                continue
            if key:
                seen_agent_phrases[key] = True

            if text and text in seen_texts:
                continue
            if text:
                seen_texts.add(text)

            final_events.append(event)

        return final_events

    def _normalize_events(
        self,
        collected_events: List[Dict[str, Any]],
        existing_events: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        from app.sim.event_pipeline import normalize_events
        return normalize_events(self, collected_events, existing_events)

    # ============================================================
    # GROUP STATE AND DYNAMICS
    # This section keeps the shared team state in sync after
    # each tick: tension, cohesion, stalls, progress, and focus.
    # ============================================================

    def _update_group_state(
        self,
        agents_sorted: List[SimAgent],
        events: List[Dict[str, Any]],
    ) -> None:
        weights = self._metric_weights()

        negative = sum(
            weights["refuse"]
            if event.get("type") == "refuse"
            else weights["challenge"]
            if event.get("type") == "challenge"
            else 1.0
            for event in events
            if event.get("type") in ("ignore", "insult", "refuse", "challenge")
        )

        positive = sum(
            weights["positive"]
            for event in events
            if event.get("type") in ("share_info", "agree", "reassure")
        )

        event_count = max(1, len(events))

        # ── Tension update ────────────────────────────────────────────────────
        # When tension is recovering (positive events dominate → negative delta),
        # use proportional decay so tension asymptotically approaches the floor
        # rather than dropping to exactly 0.00.  Tension increases keep linear
        # addition so injections and conflict events land at their full magnitude.
        _t_raw = (negative - positive) / event_count * 0.12
        if _t_raw < 0:
            # Proportional recovery: reduction scales with current tension level.
            # High tension recovers faster in absolute terms; very low tension
            # barely moves — preventing the metric from hitting 0.00.
            _new_tension = self.group_tension + _t_raw * self.group_tension
        else:
            _new_tension = self.group_tension + _t_raw

        # ── Cohesion update ───────────────────────────────────────────────────
        # Apply diminishing returns on gains so cohesion cannot repeatedly stack
        # to 1.00.  When cohesion is already high, each further improvement adds
        # only a fraction of the raw delta (scaled by remaining headroom).
        # Losses remain linear so conflict events have their intended impact.
        _c_raw = (positive - negative) / event_count * 0.08
        if _c_raw > 0:
            _new_cohesion = self.group_cohesion + _c_raw * (1.0 - self.group_cohesion)
        else:
            _new_cohesion = self.group_cohesion + _c_raw

        # ── Residual tension floor ────────────────────────────────────────────
        # Combine per-team and per-scenario floors so even perfectly calm runs
        # retain a small, realistic nonzero tension (e.g. 0.02 for Café Smooth).
        _team_preset  = str(getattr(self, "team_preset",   "") or "").lower()
        _scenario_env = str(getattr(self, "scenario_type", "") or "").lower()
        _t_floor = max(
            PRESET_TENSION_FLOOR.get(_team_preset,   0.0),
            SCENARIO_TENSION_FLOOR.get(_scenario_env, 0.0),
        )

        self.group_tension  = round(max(_t_floor, min(1.0, _new_tension)),  3)
        self.group_cohesion = round(max(0.0,      min(1.0, _new_cohesion)), 3)

        current_progress = self.scenario.progress_ratio()
        if current_progress > self.last_progress_ratio:
            self.progress_stall_ticks = 0
            self.recent_success_ticks += 1
            self.last_progress_ratio = current_progress
        else:
            self.progress_stall_ticks += 1
            self.recent_success_ticks = 0
            self.total_stalled_ticks += 1

        # Use the scenario behaviour's _priority_missing() when available — it
        # returns items in the canonical chain order (e.g. requirements → design →
        # tech_specs → budget for Office; clue priority order for Escape).
        # Without this, model.bottleneck_item is determined by raw dict iteration
        # which puts "budget" first in the Office tasks dict, causing the whole
        # run to be recorded with bottleneck_item="budget" and the blocker_timeline
        # to show only "Budget" even when all four blockers were resolved.
        if hasattr(getattr(self, "behaviour", None), "_priority_missing"):
            missing_items = list(self.behaviour._priority_missing(self))
        else:
            missing_items = [
                task for task, done in self.scenario.tasks.items() if not done
            ]
        if missing_items:
            new_bottleneck = missing_items[0]
            holder = None
            for agent in list(self.agents):
                if new_bottleneck in getattr(agent, "known_items", set()):
                    holder = agent.public_id
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

        for agent in agents_sorted:
            agent.env_tension_modifier = self.group_tension

    # ============================================================
    # EVENT GENERATION AND NORMALISATION
    # These helpers cover the per-tick event pipeline: collecting
    # raw events from agents, deduplicating, normalising text,
    # running the scenario post_tick hook, filtering redundant
    # asks, and stripping disruptive events after completion.
    # Each covers one logical stage; step() calls them in order.
    # ============================================================

    def _track_ask_pressure(self, events: List[Dict[str, Any]]) -> None:
        """Count repeated asks and accumulate coordination-pressure run metric."""
        for event in events:
            if event.get("type") != "ask_info":
                continue
            asker     = event.get("actor")
            target_id = event.get("target")
            item      = event.get("item")
            if not (asker and target_id and item):
                continue
            key      = (str(asker), str(target_id), str(item))
            previous = self.global_ask_counts.get(key, 0)
            self.global_ask_counts[key] = previous + 1
            self.run_metrics["coord_pressure"] += (
                0.08 + previous * 0.03 if previous >= 1 else 0.02
            )

    def _run_post_tick(
        self,
        agents_sorted: List["SimAgent"],
        events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Run the scenario post_tick hook; normalise and apply any extra events."""
        if not hasattr(self.behaviour, "post_tick"):
            return events

        raw_extra = self.behaviour.post_tick(self, events) or []

        forced_agents = getattr(self, "_forced_meeting_agents", None)
        forced_until  = getattr(self, "_forced_meeting_until", -1)
        if forced_agents and self.tick <= forced_until:
            raw_extra = [
                ev for ev in raw_extra
                if ev.get("actor") in forced_agents
                or (ev.get("target") in forced_agents and ev.get("actor") in forced_agents)
            ]
        elif forced_agents and self.tick > forced_until:
            self._forced_meeting_agents = None
            self._forced_meeting_until  = -1

        if self.tick > getattr(self, "_intervention_focus_until", -1):
            self._intervention_focus_item  = None
            self._intervention_focus_until = -1
        if self.tick > getattr(self, "_intervention_quiet_until", -1):
            self._intervention_quiet_item  = None
            self._intervention_quiet_until = -1

        extra = self._normalize_events(raw_extra, existing_events=events)
        if extra:
            events = list(events) + extra
            for agent in agents_sorted:
                agent.apply_events(extra, tick=self.tick)
        return events

    def _strip_post_completion_events(
        self,
        events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Remove disruptive events once the scenario is done or in its final-unlock window."""
        _block_reasons = {
            "doubt", "post_completion_doubt",
            "escape_recheck", "escape_rush", "escape_ask_owner",
        }
        in_final_unlock = False
        if self.scenario.id and str(self.scenario.id).startswith("escape"):
            tasks = getattr(self.scenario, "tasks", {}) or {}
            core_done   = all(tasks.get(k, False) for k in ("map", "lock", "key", "door"))
            unlock_done = tasks.get("unlock", False)
            in_final_unlock = core_done and not unlock_done

        if self.scenario.progress_ratio() >= 1.0 or in_final_unlock:
            events = [
                e for e in events
                if e.get("type") not in ("refuse", "challenge", "ask_info")
                and e.get("reason") not in _block_reasons
            ]
        return events

    def _apply_event_effects(self, events: List[Dict[str, Any]]) -> None:
        """Per-event counters, trust/stress side-effects, task completion, and success relief."""
        for event in events:
            event_type = event.get("type")

            if event_type == "share_info" and self._counts_as_share(event):
                self.total_shares += 1

            elif event_type == "refuse":
                self.total_refusals       += 1
                self.total_conflict_events += 1
                self.run_metrics["emotional"] += 0.10
                self.run_metrics["conflict"]  += 0.12

            elif event_type == "agree":
                actor_id  = event.get("actor")
                target_id = event.get("target")
                if actor_id and target_id:
                    actor  = next((a for a in list(self.agents) if a.public_id == actor_id),  None)
                    target = next((a for a in list(self.agents) if a.public_id == target_id), None)
                    if actor and target:
                        actor.trust[target_id]  = min(1.0, actor.trust.get(target_id, 0.5)  + 0.04)
                        target.trust[actor_id]  = min(1.0, target.trust.get(actor_id, 0.5)  + 0.04)
                        actor.stress  = max(0.0, actor.stress  - 0.03)
                        target.stress = max(0.0, target.stress - 0.03)
                        self.progress_stall_ticks = max(0, self.progress_stall_ticks - 1)
                pref = event.get("preference") or event.get("item")
                if pref and hasattr(self.behaviour, "should_complete_on_agree"):
                    if self.behaviour.should_complete_on_agree(self, pref):
                        task = self.behaviour.task_to_complete(self, pref)
                        if task:
                            self.mark_task_complete(task)

            elif event_type == "challenge":
                self.total_conflict_events    += 1
                self.run_metrics["conflict"]  += 0.09
                self.run_metrics["emotional"] += 0.04

            elif event_type == "suggest":
                self.progress_stall_ticks = max(0, self.progress_stall_ticks - 1)
                actor_id  = event.get("actor")
                target_id = event.get("target")
                if actor_id and target_id:
                    actor  = next((a for a in list(self.agents) if a.public_id == actor_id),  None)
                    target = next((a for a in list(self.agents) if a.public_id == target_id), None)
                    if actor and target:
                        actor.trust[target_id]  = min(1.0, actor.trust.get(target_id, 0.5)  + 0.02)
                        target.trust[actor_id]  = min(1.0, target.trust.get(actor_id, 0.5)  + 0.02)

            elif event_type == "ignore":
                self.total_conflict_events += 1
                self.progress_stall_ticks  += 1

        # Success relief — applied once when the scenario first reaches 100%
        if self.scenario.progress_ratio() >= 1.0 and not self._final_relief_applied:
            self._final_relief_applied = True
            rs, rv, ra = self._final_success_relief()
            for agent in list(self.agents):
                v = random.uniform(-0.04, 0.04)
                agent.stress  = max(0.08, agent.stress  - rs + v)
                agent.valence = min(1.0,  agent.valence + rv + random.uniform(-0.02, 0.02))
                agent.arousal = max(0.10, agent.arousal - ra)

        # Behaviour-level metric deltas
        deltas = self._accumulate_behaviour_metric_deltas(events)
        for key in ("emotional", "coord_pressure", "conflict"):
            self.run_metrics[key] += float(deltas.get(key, 0.0))

        # Bottleneck pressure contribution
        if self.bottleneck_age >= 2 and self.scenario.progress_ratio() < 1.0:
            self.run_metrics["coord_pressure"] += 0.06 * (1 + self.bottleneck_age * 0.05)

    def _apply_agent_caps(self, events: List[Dict[str, Any]]) -> None:
        """Apply per-preset stress caps, per-scenario trust caps, and success trust floor."""
        # Stress cap
        cap = self._resolve_stress_cap()
        if cap is not None:
            for agent in list(self.agents):
                if agent.stress > cap:
                    agent.stress = cap

        # Trust cap — cafe runs shouldn't reach unrealistically high trust
        trust_cap = TRUST_CAPS_BY_SCENARIO.get(getattr(self, "scenario_type", None))
        if trust_cap is not None:
            for agent in list(self.agents):
                trust_map = getattr(agent, "trust", None)
                if isinstance(trust_map, dict):
                    for other_id, value in list(trust_map.items()):
                        if isinstance(value, (int, float)) and value > trust_cap:
                            trust_map[other_id] = trust_cap

        # Trust floor — a team that just finished together shouldn't end up "guarded"
        try:
            progress_ratio = float(self.scenario.progress_ratio())
        except Exception:
            progress_ratio = 0.0
        if progress_ratio >= 1.0:
            recent_conflict = sum(
                1 for ev in (events[-20:] if events else [])
                if ev.get("type") in ("challenge", "refuse")
            )
            if recent_conflict <= 1:
                for agent in list(self.agents):
                    trust_map = getattr(agent, "trust", None)
                    if isinstance(trust_map, dict):
                        for other_id, value in list(trust_map.items()):
                            if isinstance(value, (int, float)) and value < 0.50:
                                trust_map[other_id] = 0.50

    # ============================================================
    # METRIC UPDATES
    # _apply_event_effects tallies per-event counters (shares,
    # refusals, trust nudges, success relief).
    # _apply_agent_caps enforces preset stress/trust ceilings.
    # _accumulate_run_metrics snapshots the tick into
    # metric_history — the source used by History Inspect charts
    # and the PDF report.
    # ============================================================

    def _accumulate_run_metrics(
        self,
        agents_sorted: List["SimAgent"],
        metrics: Dict[str, Any],
    ) -> None:
        """Accumulate run-level metrics and append tick snapshot to metric_history."""
        stall_pressure     = min(1.0, self.progress_stall_ticks / 10.0)
        bottleneck_pressure = min(1.0, self.bottleneck_age / 8.0)
        weights = self._metric_weights()

        # emotional_memory_pressure: NLP-derived negative emotion ratio from STM.
        # Blended with avg_stress so the "emotional" run metric reflects both
        # event-level conflict AND the accumulated emotional texture agents carry.
        _em_pressure = metrics.get("emotional_memory_pressure", 0.0)
        self.run_metrics["emotional"] += metrics["avg_stress"] * 0.70 + _em_pressure * 0.30
        self.run_metrics["conflict"]  += (
            metrics["refusal_count"] * weights["refuse"] * 0.08
            + metrics["event_counts"].get("challenge", 0) * weights["challenge"] * 0.06
            + metrics["event_counts"].get("insult",   0) * 0.12
        )
        self.run_metrics["coord_pressure"] += min(
            1.0,
            stall_pressure      * 0.5 * weights["stall"]
            + bottleneck_pressure * 0.3 * weights["bottleneck"]
            + self.group_tension  * 0.2,
        )

        self.metric_history.append({
            "tick":                       self.tick,
            "avg_trust":                  metrics["avg_trust"],
            "avg_stress":                 metrics["avg_stress"],
            "conflict_rate":              metrics["conflict_rate"],
            "group_tension":              metrics["group_tension"],
            "group_cohesion":             metrics["group_cohesion"],
            "pressure":                   round(getattr(self.environment, "urgency_modifier", 0.0), 3),
            "share_count":                metrics["share_count"],
            "refusal_count":              metrics["refusal_count"],
            "progress":                   round(self.scenario.progress_ratio(), 3),
            "interventions":              [iv["type"] for iv in self._current_tick_interventions],
            # active_blocker: the constraint/task that was being worked on at the
            # START of this tick (before any task completions).  Use this for the
            # blocker timeline — it correctly records an item that resolved in its
            # first tick (e.g. Café dietary_constraint resolved at tick 1), whereas
            # bottleneck_item reflects the post-resolution state (next blocker up).
            "active_blocker":             getattr(self, "_tick_active_blocker", None),
            "bottleneck_item":            metrics.get("bottleneck_item"),
            "event_counts":               dict(metrics.get("event_counts", {})),
            "emotional_memory_pressure":  round(_em_pressure, 3),
            "emotional_memory_positivity": round(
                metrics.get("emotional_memory_positivity", 0.0), 3
            ),
        })

    # ============================================================
    # COMPLETION AND SUMMARY BUILDING
    # _check_end_conditions evaluates scenario outcome, max-ticks,
    # trust/stress collapse, harmony, and bottleneck deadlock.
    # _build_tick_diff assembles self.last_diff — the canonical
    # per-tick snapshot streamed to the frontend and stored in
    # self.history for replay and PDF export.
    # ============================================================

    def _check_end_conditions(self, metrics: Dict[str, Any]) -> str:
        """Evaluate all end conditions; mutates self.ended / self.end_reason. Returns outcome."""
        outcome = self.scenario.outcome(self.tick)
        if outcome != "running":
            self.ended     = True
            self.end_reason = outcome
        elif self.tick >= self.episode_max_ticks:
            self.ended = True
            progress   = self.scenario.progress_ratio()
            self.end_reason = (
                "success" if progress >= 0.99
                else ("partial" if progress >= 0.30 else "failure")
            )

        if not self.ended:
            self.avg_trust_hist.append(metrics["avg_trust"])
            if len(self.avg_trust_hist) == self.avg_trust_hist.maxlen:
                avg_trust       = sum(self.avg_trust_hist) / len(self.avg_trust_hist)
                avg_stress_hist = metrics.get("avg_stress", 0.5)
                progress        = self.scenario.progress_ratio()

                if avg_trust < 0.30 and avg_stress_hist > 0.65 and self.progress_stall_ticks >= 8:
                    self.ended      = True
                    self.end_reason = "failure" if progress < 0.50 else "partial"
                elif avg_trust > 0.85 and self.group_tension < 0.25 and self.recent_success_ticks >= 6:
                    # harmony: trust high, tension low, and consistent recent wins
                    self.ended      = True
                    self.end_reason = "harmony"
                elif self.bottleneck_age >= 15 and self.progress_stall_ticks >= 15 and progress < 1.0:
                    # deadlock: same item has been stuck for 15+ ticks with no progress
                    self.ended      = True
                    self.end_reason = "failure" if progress < 0.50 else "partial"

        return self.end_reason if self.ended else outcome

    def _build_tick_diff(
        self,
        agents_sorted: List["SimAgent"],
        ties: List[Dict[str, Any]],
        metrics: Dict[str, Any],
        events: List[Dict[str, Any]],
        outcome: str,
    ) -> None:
        """Assemble self.last_diff for this tick and append to self.history."""
        norm        = max(1, self.tick)
        norm_metrics = {
            key: round(min(1.0, value / norm), 3)
            for key, value in self.run_metrics.items()
        }

        self.last_diff = {
            "tick":                self.tick,
            "run_metrics":         norm_metrics,
            "raw_run_metrics":     dict(self.run_metrics),
            "agents":  [agent.to_state() for agent in agents_sorted],
            "ties":    ties,
            "events":  events,
            "metrics": metrics,
            # Interventions applied since the previous tick (set via apply_intervention).
            # Each entry carries full params (item, agent_id, etc.) so that replay
            # and history inspect can reconstruct the Intervention Impact card in full.
            "interventions": [
                {"type": iv_entry["type"], "tick": self.tick, "params": iv_entry.get("params", {})}
                for iv_entry in self._current_tick_interventions
            ],
            "group_state": {
                "tension":          self.group_tension,
                "cohesion":         self.group_cohesion,
                "pressure":         round(getattr(self.environment, "urgency_modifier", 0.0), 3),
                "stall_ticks":      self.progress_stall_ticks,
                "success_streak":   self.recent_success_ticks,
                "active_blocker":   getattr(self, "_tick_active_blocker", None),
                "bottleneck_item":  self.bottleneck_item,
                "bottleneck_holder": self.bottleneck_holder,
                "bottleneck_age":   self.bottleneck_age,
            },
            "scenario": {
                "id":          self.scenario.id,
                "name":        self.scenario.name,
                "description": self.scenario.description,
                "environment": self.scenario.environment,
                # Snapshot per tick so replay doesn't inherit the final completed map.
                "tasks":         copy.deepcopy(self.scenario.tasks),
                "resolved_items": list(getattr(self, "_tick_resolved_items", [])),
                "knowledge_map": copy.deepcopy(self.scenario.knowledge_map),
                "progress":      round(self.scenario.progress_ratio(), 3),
                "urgency_modifier": round(getattr(self.environment, "urgency_modifier", 0.0), 3),
                "outcome":       outcome,
                "final_decision": self._final_decision,
            },
            "ended":      self.ended,
            "end_reason": self.end_reason,
        }
        self.history.append(copy.deepcopy(self.last_diff))

    def _filter_redundant_asks(
        self,
        events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Remove ask_info events for items already being shared this tick.

        When an owner shares their constraint in the same tick that the
        organiser asks about it, both events land in the same tick's list
        because each agent's decide_event() runs before anyone else's result
        is visible.  Keeping both is misleading on the frontend: it looks as
        though the generic ask caused the blocker to resolve, when actually the
        share_info did.  Removing the now-redundant ask produces a cleaner
        causal story: "A2 shared the dietary constraint → it resolved."
        """
        shared_items = {
            e.get("item")
            for e in events
            if e.get("type") == "share_info" and e.get("item")
        }
        if not shared_items:
            return events
        return [
            e for e in events
            if not (e.get("type") == "ask_info" and e.get("item") in shared_items)
        ]

    # ============================================================
    # STEP / TICK LIFECYCLE
    # step() is the main entry point called by RunManager each
    # tick.  Sequence:
    #   1. Snapshot + clear pending interventions
    #   2. Advance tick counter; record active blocker
    #   3. Decay emotion effects from inject_user_emotion()
    #   4. Collect one raw event per agent (decide_event)
    #   5. Drain pending/intervention event queues
    #   6. Normalise → filter redundant asks → track ask pressure
    #   7. Apply events to agents; run scenario post_tick hook
    #   8. Strip post-completion disruptive events
    #   9. _apply_event_effects → _update_group_state → _apply_agent_caps
    #  10. Compute ties and metrics
    #  11. Check end conditions
    #  12. _build_tick_diff → append to self.history
    # ============================================================

    def step(self) -> None:
        self.tick_spoken = False
        self.conversation_ongoing = False

        if self.ended:
            self.prev_events = []
            return

        # Snapshot interventions queued since the previous step, then clear.
        # This records "which interventions were active coming into this tick".
        self._current_tick_interventions = list(self._tick_interventions)
        self._tick_interventions = []

        self.tick += 1
        # snapshot tasks at tick start so we can detect what resolved this tick
        self._tick_start_tasks = copy.deepcopy(getattr(self.scenario, "tasks", {}) or {})
        self._tick_active_blocker = self._active_blocker_from_tasks(self._tick_start_tasks)
        self._tick_resolved_items = []

        # ── Emotion-effect decay ──────────────────────────────────────────
        # I modelled emotion decay as an exponential fade rather than a
        # fixed-duration flat effect, because emotional states in real groups
        # don't switch off sharply — they gradually dissipate as the group
        # refocuses on the task (Barsade, 2002: emotional contagion decays
        # naturally once the source stimulus is removed). The decay_rate of 0.5
        # means 50% of the remaining effect is reversed each tick:
        #   tick 1: 50% of original remains
        #   tick 2: 25% remains
        #   tick 3: 12.5% remains
        # The effect is cleared entirely when the remaining delta drops below
        # 0.002 (< 0.2% of original), which is below any observable threshold.
        # Stacking: if a second injection fires before the first has fully
        # decayed, I add the remainders together (bounded by clamp in apply).
        if self._emotion_effect:
            _eff = self._emotion_effect
            _decay = _eff.get("decay_rate", 0.5)
            _s_rem = _eff.get("stress_remaining", 0.0)
            _v_rem = _eff.get("valence_remaining", 0.0)
            _tr_rem = _eff.get("trust_remaining", 0.0)

            # Portion to reverse this tick
            _s_rev  = _s_rem  * _decay
            _v_rev  = _v_rem  * _decay
            _tr_rev = _tr_rem * _decay

            from app.sim.agent import clamp as _aclamp
            for _a in self.agents:
                if abs(_s_rev) > 0.0:
                    _a.stress  = _aclamp(_a.stress  - _s_rev,  0.0, 1.0)
                if abs(_v_rev) > 0.0:
                    _a.valence = _aclamp(_a.valence - _v_rev, -1.0, 1.0)
                if abs(_tr_rev) > 0.0:
                    for _oid in list(_a.trust.keys()):
                        _a.trust[_oid] = _aclamp(_a.trust[_oid] - _tr_rev, 0.0, 1.0)

            _eff["stress_remaining"]  = _s_rem  - _s_rev
            _eff["valence_remaining"] = _v_rem  - _v_rev
            _eff["trust_remaining"]   = _tr_rem - _tr_rev
            _eff["ticks_elapsed"]     = _eff.get("ticks_elapsed", 0) + 1
            _init_s = abs(_eff.get("initial_stress_delta", 1e-9))
            _eff["current_strength"]  = abs(_eff["stress_remaining"]) / max(_init_s, 1e-9)

            # Clear when negligible (< 0.2% of original)
            if abs(_eff["stress_remaining"]) < 0.002 and abs(_eff["trust_remaining"]) < 0.002:
                self._emotion_effect = {}
        self._build_reply_inbox()
        agents_sorted = sorted(list(self.agents), key=lambda a: a.public_id)

        # each agent produces at most one event — None means they stayed silent this tick
        collected_events: List[Dict[str, Any]] = []
        for agent in agents_sorted:
            others = [other for other in agents_sorted if other is not agent]
            event  = agent.decide_event(others)
            if event is not None:
                collected_events.append(event)

        if self._pending_events:
            collected_events.extend(self._pending_events)
            self._pending_events = []

        if getattr(self, "_pending_intervention_events", None):
            collected_events.extend(self._pending_intervention_events)
            self._pending_intervention_events = []

        events = self._normalize_events(collected_events)
        # First pass: remove asks made redundant by shares in the initial event batch.
        # Must run before _track_ask_pressure so the removed ask is not counted.
        events = self._filter_redundant_asks(events)

        # Track repeated asks; apply events to agents; run scenario post-tick hook
        self._track_ask_pressure(events)
        for agent in agents_sorted:
            agent.apply_events(events, tick=self.tick)
        events = self._run_post_tick(agents_sorted, events)
        # Second pass: post_tick can inject forced share_info events (e.g. deadline
        # forced-share in cafe/office).  Re-run the filter so any ask_info that was
        # already in the list is removed when the same item gets a forced share.
        events = self._filter_redundant_asks(events)
        events = self._strip_post_completion_events(events)
        self.total_events += len(events)

        # Per-event counters/effects → group state → agent caps
        self._apply_event_effects(events)
        self._tick_resolved_items = [
            task for task, done in (getattr(self.scenario, "tasks", {}) or {}).items()
            if done and not self._tick_start_tasks.get(task, False)
        ]
        self._update_group_state(agents_sorted, events)
        if self._tension_impulse_remaining > 0:
            self.group_tension = round(
                max(self.group_tension, self._tension_impulse_floor),
                3,
            )
            for agent in agents_sorted:
                agent.env_tension_modifier = self.group_tension
            self._tension_impulse_remaining -= 1
            if self._tension_impulse_remaining <= 0:
                self._tension_impulse_floor = 0.0
        self._apply_agent_caps(events)

        self.strategy_history.append({
            agent.public_id: getattr(agent, "strategy", "unknown")
            for agent in agents_sorted
        })

        ties    = self._compute_ties(agents_sorted)
        metrics = self._compute_metrics(agents_sorted, events)
        self._accumulate_run_metrics(agents_sorted, metrics)

        outcome = self._check_end_conditions(metrics)
        self.prev_events = events
        self._build_tick_diff(agents_sorted, ties, metrics, events, outcome)

    # ============================================================
    # INTERVENTION INTERFACE
    # apply_intervention() is the public entry point used by the
    # interventions API route.  It delegates to intervention_service,
    # then records the action in both the per-tick log and the
    # full-run log so history and PDF export capture it correctly.
    # ============================================================

    def apply_intervention(
        self,
        intervention_type: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.services.intervention_service import apply_intervention as _apply

        result = _apply(self, intervention_type, params)

        # Track for per-tick history (full detail) and run-level log (type string only).
        # Storing params here means the history snapshot can carry item/agent_id for replay.
        self._tick_interventions.append({"type": intervention_type, "params": dict(params)})
        self._applied_interventions_log.append(intervention_type)

        if self.last_diff is not None:
            self.last_diff.setdefault("interventions", []).append(
                {
                    "tick": self.tick,
                    "type": intervention_type,
                    "params": params,
                    "result": result,
                }
            )

        # Spread all service result fields (success, message, pressure_before,
        # pressure_after, etc.) so callers get the full response.
        return {
            **result,
            "intervention_type": intervention_type,
            "tick_applied": self.tick,
        }

    # ============================================================
    # TIES AND METRICS — CALLS INTO SEPARATE MODULES
    # Keeping the actual computation out of model.py so it stays
    # focused on the tick loop.  ties.py and metrics.py do the
    # number-crunching; model just calls them and stores results.
    # ============================================================

    def _compute_ties(self, agents_sorted: List[SimAgent]) -> List[Dict[str, Any]]:
        from app.sim.ties import compute_ties
        return compute_ties(self, agents_sorted)

    def _compute_metrics(
        self,
        agents_sorted: List[SimAgent],
        events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        from app.sim.metrics import compute_tick_metrics
        return compute_tick_metrics(self, agents_sorted, events)

    def outcome_label(self) -> str:
        """Return the human-readable outcome label for this run."""
        from app.sim.metrics import classify_run_outcome
        return classify_run_outcome(self)

    def run_description(self) -> str:
        """Return a plain-English paragraph describing what happened and why."""
        from app.sim.metrics import describe_run
        return describe_run(self)

    def memory_summary(self) -> dict:
        """Return the memory_summary section for this run's export."""
        from app.sim.metrics import summarize_memory
        return summarize_memory(self)

    # ============================================================
    # NLP / USER EMOTION INJECTION
    # inject_user_emotion() is the bridge between the text
    # classifier (emotions_analyser) and the live simulation.
    # It classifies free-text input, translates the emotion into
    # bounded stress/trust/valence deltas, applies them to every
    # agent immediately, then stores a decay record so the effect
    # fades exponentially over the next several ticks.
    # emotion_summary() is called by run_history_service at save
    # time to include the injection log in the history JSON.
    # ============================================================

    # ── User emotion injection ────────────────────────────────────────────────
    # I designed inject_user_emotion() as the bridge between the classify_user_emotion()
    # function (which only analyses text) and the live simulation state (which tracks
    # per-agent stress, valence, and trust). The method does three things:
    #   1. Classifies the text using the emotion pipeline (ML or rule-based)
    #   2. Translates the detected emotion into bounded stress/trust/valence deltas
    #      using the four-category scheme (neg_high, neg_low, positive, neutral)
    #   3. Applies those deltas immediately to all agents and then stores a decay
    #      record so the effect fades over the following ticks
    # I apply the effect to all agents rather than a single agent because the
    # framing is that the *user* is acting as an external moderator influencing
    # the group atmosphere — analogous to a manager entering a meeting with a
    # particular mood. Emotional contagion research (Barsade, 2002) supports
    # the idea that one person's emotional state rapidly spreads through a group.

    def inject_user_emotion(self, text: str, tick: Optional[int] = None) -> Dict[str, Any]:
        """Classify user-provided emotional text and apply it to all agents.

        The effect is bounded and decays over the following ticks so it does
        not permanently dominate the simulation.

        Parameters
        ----------
        text : str
            Free-text emotion input from the user.
        tick : int, optional
            Tick label to record.  Defaults to the model's current tick.

        Returns
        -------
        dict
            The emotion_injection event that was logged and queued.
        """
        from app.sim.emotions_analyser import classify_user_emotion
        from app.sim.agent import clamp

        applied_tick = tick if tick is not None else self.tick
        classification = classify_user_emotion(text, tick=applied_tick)

        emotion   = classification["top_emotion"]
        valence   = classification["valence"]
        arousal   = classification["arousal"]
        intensity = classification["intensity"]

        # ── Compute bounded deltas ────────────────────────────────────────
        # I derived the delta bounds empirically by running the simulation
        # with extreme emotion inputs and checking that no single injection
        # could dominate the run. The maximum stress increase (+0.12) is large
        # enough to be visible in the charts but small enough that a single
        # angry input doesn't send all agents into permanent high-stress. Trust
        # is only reduced for high-arousal negatives at intensity >= 0.5 because
        # trust is the slowest-moving social variable — a momentary expression
        # of nervousness shouldn't tank relationships the way repeated conflict does.
        # Rules follow the spec categories:
        #   Negative high-arousal → stress +, trust –
        #   Negative low-arousal  → stress + (smaller), no trust hit
        #   Positive              → stress –, trust +
        #   Neutral               → no change

        _neg_high = {"anger", "annoyance", "fear", "nervousness", "disgust", "disapproval"}
        _neg_low  = {"sadness", "disappointment", "remorse", "grief", "embarrassment"}
        _positive = {"joy", "gratitude", "approval", "admiration", "optimism", "relief",
                     "amusement", "excitement", "love", "pride", "caring", "surprise"}

        stress_delta = 0.0
        trust_delta  = 0.0
        valence_delta = valence * 0.08 * intensity   # small mood shift, bounded

        if emotion in _neg_high:
            # +0.05 to +0.12 depending on intensity
            stress_delta = min(0.12, intensity * 0.15)
            trust_delta  = -min(0.04, intensity * 0.055) if intensity >= 0.50 else 0.0
        elif emotion in _neg_low:
            stress_delta = min(0.06, intensity * 0.08)
        elif emotion in _positive:
            stress_delta = -min(0.05, intensity * 0.07)
            trust_delta  = min(0.03, intensity * 0.04)
        # neutral: all deltas stay 0.0

        # ── Snapshot state before ─────────────────────────────────────────
        agents = list(self.agents)
        stress_before = round(
            sum(a.stress for a in agents) / max(1, len(agents)), 3
        )
        all_trust = [v for a in agents for v in a.trust.values()]
        trust_before = round(sum(all_trust) / max(1, len(all_trust)), 3) if all_trust else 0.5

        # ── Apply to all agents ───────────────────────────────────────────
        for agent in agents:
            agent.stress  = clamp(agent.stress  + stress_delta, 0.0,  1.0)
            agent.valence = clamp(agent.valence + valence_delta, -1.0, 1.0)
            if trust_delta != 0.0:
                for oid in list(agent.trust.keys()):
                    agent.trust[oid] = clamp(agent.trust[oid] + trust_delta, 0.0, 1.0)

        # ── Snapshot state after ──────────────────────────────────────────
        stress_after = round(
            sum(a.stress for a in agents) / max(1, len(agents)), 3
        )
        all_trust_after = [v for a in agents for v in a.trust.values()]
        trust_after = round(
            sum(all_trust_after) / max(1, len(all_trust_after)), 3
        ) if all_trust_after else 0.5

        # ── Store decay state ─────────────────────────────────────────────
        # If a previous effect is still active, stack it (within safe bounds).
        prev = self._emotion_effect
        self._emotion_effect = {
            "applied_tick":          applied_tick,
            "duration_ticks":        5,
            "decay_rate":            0.5,
            "ticks_elapsed":         0,
            "current_strength":      1.0,
            "initial_stress_delta":  stress_delta,
            "stress_remaining":      stress_delta  + prev.get("stress_remaining",  0.0),
            "valence_remaining":     valence_delta + prev.get("valence_remaining", 0.0),
            "trust_remaining":       trust_delta   + prev.get("trust_remaining",   0.0),
        }

        # ── Build log entry ───────────────────────────────────────────────
        log_entry: Dict[str, Any] = {
            "tick":             applied_tick,
            "type":             "emotion_injection",
            "text":             text,
            "detected_emotion": emotion,
            "confidence":       classification["confidence"],
            "top_labels":       classification["top_labels"],
            "valence":          valence,
            "arousal":          arousal,
            "intensity":        intensity,
            "fallback_used":    classification["fallback_used"],
            "fallback_reason":  classification.get("fallback_reason"),
            "affected_agents":  [a.public_id for a in agents],
            "stress_before":    stress_before,
            "stress_after":     stress_after,
            "stress_delta":     round(stress_delta, 4),
            "trust_before":     trust_before,
            "trust_after":      trust_after,
            "trust_delta":      round(trust_delta, 4),
            "emotion_effect": {
                "applied_tick":   applied_tick,
                "duration_ticks": 5,
                "decay_rate":     0.5,
                "current_strength": 1.0,
            },
            "explanation":      classification["interpretation"],
        }
        self._emotion_log.append(log_entry)

        # Queue as a pending event so it appears in the tick timeline
        self._pending_events.append(log_entry)

        return log_entry

    def emotion_summary(self) -> Dict[str, Any]:
        """Return the emotion_summary section for this run's export."""
        from app.sim.metrics import summarize_emotions
        return summarize_emotions(self)
