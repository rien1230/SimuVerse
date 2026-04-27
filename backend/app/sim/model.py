"""Main simulation model that owns agents, ticks, and shared group state."""

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
    PRESET_STRESS_SEED,    TRUST_CAPS,
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


def _trait_initial_trust(
    agent_traits: Dict[str, float],
    other_traits: Dict[str, float],
) -> float:
    base = 0.40
    base += 0.20 * agent_traits.get("A", 0.5)
    base -= 0.15 * agent_traits.get("N", 0.5)
    base += 0.10 * other_traits.get("A", 0.5)
    base -= 0.05 * other_traits.get("N", 0.5)
    return round(max(0.05, min(0.95, base)), 3)


def _trait_initial_strategy(traits: Dict[str, float]) -> str:
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


class SimModel(mesa.Model):
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

        self._final_relief_applied = False
        self._final_decision: Optional[str] = None
        self.phrase_cooldowns: Dict[str, Any] = {}
        self._pending_events: List[Dict[str, Any]] = []

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

    def mark_task_complete(self, item: str) -> None:
        if not self.scenario.tasks.get(item, False):
            self.scenario.complete_task(item)
            if item not in self.completion_order:
                self.completion_order.append(item)

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

        self.group_tension = round(
            max(
                0.0,
                min(
                    1.0,
                    self.group_tension + (negative - positive) / event_count * 0.12,
                ),
            ),
            3,
        )
        self.group_cohesion = round(
            max(
                0.0,
                min(
                    1.0,
                    self.group_cohesion + (positive - negative) / event_count * 0.08,
                ),
            ),
            3,
        )

        current_progress = self.scenario.progress_ratio()
        if current_progress > self.last_progress_ratio:
            self.progress_stall_ticks = 0
            self.recent_success_ticks += 1
            self.last_progress_ratio = current_progress
        else:
            self.progress_stall_ticks += 1
            self.recent_success_ticks = 0
            self.total_stalled_ticks += 1

        if getattr(getattr(self, "behaviour", None), "scenario_type", None) == "escape" and hasattr(self.behaviour, "_priority_missing"):
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

    # ── step() helpers ────────────────────────────────────────────────────────
    # Each covers one logical stage of the tick loop; step() calls them in order.

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

    def _accumulate_run_metrics(
        self,
        agents_sorted: List["SimAgent"],
        metrics: Dict[str, Any],
    ) -> None:
        """Accumulate run-level metrics and append tick snapshot to metric_history."""
        stall_pressure     = min(1.0, self.progress_stall_ticks / 10.0)
        bottleneck_pressure = min(1.0, self.bottleneck_age / 8.0)
        weights = self._metric_weights()

        self.run_metrics["emotional"] += metrics["avg_stress"]
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
            "tick":          self.tick,
            "avg_trust":     metrics["avg_trust"],
            "avg_stress":    metrics["avg_stress"],
            "conflict_rate": metrics["conflict_rate"],
            "group_tension": metrics["group_tension"],
            "group_cohesion": metrics["group_cohesion"],
            "share_count":   metrics["share_count"],
            "refusal_count": metrics["refusal_count"],
        })

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
                    self.ended      = True
                    self.end_reason = "harmony"
                elif self.bottleneck_age >= 15 and self.progress_stall_ticks >= 15 and progress < 1.0:
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
            "tick":            self.tick,
            "run_metrics":     norm_metrics,
            "raw_run_metrics": dict(self.run_metrics),
            "agents":  [agent.to_state() for agent in agents_sorted],
            "ties":    ties,
            "events":  events,
            "metrics": metrics,
            "group_state": {
                "tension":          self.group_tension,
                "cohesion":         self.group_cohesion,
                "stall_ticks":      self.progress_stall_ticks,
                "success_streak":   self.recent_success_ticks,
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
                "knowledge_map": copy.deepcopy(self.scenario.knowledge_map),
                "progress":      round(self.scenario.progress_ratio(), 3),
                "outcome":       outcome,
                "final_decision": self._final_decision,
            },
            "ended":      self.ended,
            "end_reason": self.end_reason,
        }
        self.history.append(copy.deepcopy(self.last_diff))

    # ── Main tick loop ────────────────────────────────────────────────────────

    def step(self) -> None:
        self.tick_spoken = False
        self.conversation_ongoing = False

        if self.ended:
            self.prev_events = []
            return

        self.tick += 1
        self._build_reply_inbox()
        agents_sorted = sorted(list(self.agents), key=lambda a: a.public_id)

        # Collect raw events from every agent
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

        # Track repeated asks; apply events to agents; run scenario post-tick hook
        self._track_ask_pressure(events)
        for agent in agents_sorted:
            agent.apply_events(events, tick=self.tick)
        events = self._run_post_tick(agents_sorted, events)
        events = self._strip_post_completion_events(events)
        self.total_events += len(events)

        # Per-event counters/effects → group state → agent caps
        self._apply_event_effects(events)
        self._update_group_state(agents_sorted, events)
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

    def apply_intervention(
        self,
        intervention_type: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.services.intervention_service import apply_intervention as _apply

        result = _apply(self, intervention_type, params)

        if self.last_diff is not None:
            self.last_diff.setdefault("interventions", []).append(
                {
                    "tick": self.tick,
                    "type": intervention_type,
                    "params": params,
                    "result": result,
                }
            )

        return {
            "success": result.get("success", False),
            "message": result.get("message", ""),
            "intervention_type": intervention_type,
            "tick_applied": self.tick,
        }

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
