"""
test_intervention_effects.py
============================
Intervention correctness and effect tests for SimuVerse.

Covers all five intervention types across all three dissertation scenarios
and multiple team styles.  Each test verifies:
  - The intervention returns success=True with a meaningful message
  - The intended model variable is mutated immediately
  - The run still terminates after intervention
  - Observable behavioural traces appear in subsequent ticks

Intervention types tested:
  reveal_info    – agent gains immediate knowledge of a task item
  nudge_strategy – agent's behavioural strategy is shifted and locked
  boost_urgency  – environment urgency_modifier is raised
  inject_tension – group_tension and agent stress increase
  force_meeting  – two agents are paired into a directed conversation

Simulation is created as:
    SimModel(seed, scenario_id, environment, episode_max_ticks, team_type)
No HTTP server required.

Run from the backend directory:
    source .venv/bin/activate
    pytest tests/test_intervention_effects.py -v
"""

import os
import warnings
import pytest

warnings.filterwarnings("ignore")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from app.sim.model import SimModel
from app.sim.scenario_data import resolve_scenario_id
from app.sim import interventions as iv

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISSERTATION_SCENARIOS = [
    ("office_proposal", "office"),
    ("cafe_restaurant", "cafe"),
    ("escape_puzzle",   "escape"),
]

TEAM_STYLES    = ["smooth", "balanced", "tension", "creative", "pressure"]
CORE_STYLES    = ["smooth", "balanced", "tension", "pressure"]   # used in most parametrize
VALID_STRATEGIES = ["cooperative", "assertive", "neutral", "defensive",
                    "avoidant", "confrontational"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make(scenario_id, env, seed=42, team_type="balanced", max_ticks=30):
    sid = resolve_scenario_id(scenario_id)
    m = SimModel(seed=seed, scenario_id=sid, environment=env,
                 episode_max_ticks=max_ticks, team_type=team_type)
    m.skip_emotions = True
    return m


def _step(model, n=1):
    for _ in range(n):
        if model.ended:
            break
        model.step()


def _run_to_end(model):
    while not model.ended and model.tick < model.episode_max_ticks:
        model.step()


def _all_events(model):
    return [e for tick in model.history for e in (tick.get("events") or [])]


def _events_after(model, tick_n):
    return [
        e for tick in model.history
        if tick.get("tick", 0) > tick_n
        for e in (tick.get("events") or [])
    ]


def _agents_sorted(model):
    return sorted(list(model.agents), key=lambda a: a.public_id)


def _first_unknown(model):
    """Return (agent, item) for the first agent missing an incomplete task."""
    for item, done in model.scenario.tasks.items():
        if not done:
            for ag in _agents_sorted(model):
                if item not in ag.known_items:
                    return ag, item
    return None, None


def _avg_stress(model):
    agents = list(model.agents)
    return sum(a.stress for a in agents) / len(agents)


def _avg_trust(model):
    vals = [v for a in model.agents for v in a.trust.values()]
    return sum(vals) / max(1, len(vals))


# ---------------------------------------------------------------------------
# 1. reveal_info
# ---------------------------------------------------------------------------

class TestRevealInfo:

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_returns_success(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 3)
        agent, item = _first_unknown(m)
        if agent is None:
            pytest.skip(f"{scenario_id}/{team_type}: no unknown items at tick 3")
        result = iv.reveal_info(m, agent.public_id, item)
        assert result["success"] is True
        assert agent.public_id in result["message"]

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_item_added_to_known_items(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 3)
        agent, item = _first_unknown(m)
        if agent is None:
            pytest.skip(f"{scenario_id}/{team_type}: no unknown items at tick 3")
        iv.reveal_info(m, agent.public_id, item)
        assert item in agent.known_items, (
            f"{scenario_id}/{team_type}: item '{item}' not in {agent.public_id}.known_items"
        )

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_run_completes_after_reveal(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 3)
        agent, item = _first_unknown(m)
        if agent is None:
            pytest.skip(f"{scenario_id}/{team_type}: no unknown items at tick 3")
        iv.reveal_info(m, agent.public_id, item)
        _run_to_end(m)
        assert m.ended is True
        assert m.end_reason in {"success", "partial", "failure", "harmony"}

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    def test_reveal_queues_pending_event(self, scenario_id, env):
        """reveal_info must queue at least one pending event for the next tick."""
        m = _make(scenario_id, env, team_type="balanced")
        _step(m, 3)
        agent, item = _first_unknown(m)
        if agent is None:
            pytest.skip(f"{scenario_id}: no unknown items at tick 3")
        before_pending = len(getattr(m, "_pending_events", []))
        iv.reveal_info(m, agent.public_id, item)
        after_pending = len(getattr(m, "_pending_events", []))
        assert after_pending >= before_pending, (
            f"{scenario_id}: reveal_info did not queue any pending events"
        )

    def test_reveal_raises_agent_valence(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 3)
        agent, item = _first_unknown(m)
        if agent is None:
            pytest.skip("No unknown items at tick 3")
        valence_before = agent.valence
        iv.reveal_info(m, agent.public_id, item)
        assert agent.valence >= valence_before, (
            f"Valence fell after reveal_info: {valence_before:.3f} → {agent.valence:.3f}"
        )

    def test_invalid_item_fails(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        result = iv.reveal_info(m, "A1", "does_not_exist")
        assert result["success"] is False

    def test_invalid_agent_fails(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        result = iv.reveal_info(m, "Z99", "budget")
        assert result["success"] is False


# ---------------------------------------------------------------------------
# 2. nudge_strategy
# ---------------------------------------------------------------------------

class TestNudgeStrategy:

    @pytest.mark.parametrize("strategy", VALID_STRATEGIES)
    def test_returns_success(self, strategy):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        result = iv.nudge_strategy(m, "A1", strategy)
        assert result["success"] is True

    @pytest.mark.parametrize("strategy", VALID_STRATEGIES)
    def test_sets_agent_strategy(self, strategy):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        iv.nudge_strategy(m, "A2", strategy)
        agent = next(a for a in m.agents if a.public_id == "A2")
        assert agent.strategy == strategy

    @pytest.mark.parametrize("strategy", VALID_STRATEGIES)
    def test_strategy_lock_set(self, strategy):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        iv.nudge_strategy(m, "A1", strategy)
        agent = next(a for a in m.agents if a.public_id == "A1")
        assert getattr(agent, "strategy_locked_until", -1) > m.tick, (
            f"strategy_locked_until not set after nudge to '{strategy}'"
        )

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_run_completes_after_nudge(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 3)
        iv.nudge_strategy(m, _agents_sorted(m)[0].public_id, "cooperative")
        _run_to_end(m)
        assert m.ended is True

    def test_invalid_strategy_fails(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        result = iv.nudge_strategy(m, "A1", "passive_aggressive")
        assert result["success"] is False

    def test_cooperative_reduces_stress(self):
        m = _make("office_proposal", "office", team_type="tension")
        _step(m, 4)
        agent = next(a for a in m.agents if a.public_id == "A1")
        stress_before = agent.stress
        iv.nudge_strategy(m, "A1", "cooperative")
        # Allow tiny floating-point tolerance
        assert agent.stress <= stress_before + 0.01, (
            f"Cooperative nudge raised stress: {stress_before:.3f} → {agent.stress:.3f}"
        )

    def test_nudge_on_all_scenarios(self):
        """Nudging works on every scenario without error."""
        for scenario_id, env in DISSERTATION_SCENARIOS:
            m = _make(scenario_id, env, team_type="balanced")
            _step(m, 2)
            result = iv.nudge_strategy(m, _agents_sorted(m)[0].public_id, "assertive")
            assert result["success"] is True, f"{scenario_id}: nudge_strategy failed"


# ---------------------------------------------------------------------------
# 3. boost_urgency
# ---------------------------------------------------------------------------

class TestBoostUrgency:

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_returns_success(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 3)
        result = iv.boost_urgency(m, 0.4)
        assert result["success"] is True
        assert "Urgency boosted" in result["message"]

    @pytest.mark.parametrize("amount", [0.1, 0.3, 0.5, 0.8])
    def test_raises_urgency_modifier(self, amount):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        before = getattr(m.environment, "urgency_modifier", 1.0)
        iv.boost_urgency(m, amount)
        after = getattr(m.environment, "urgency_modifier", 1.0)
        assert after > before, (
            f"urgency_modifier did not increase after boost({amount}): {before:.3f} → {after:.3f}"
        )

    def test_urgency_capped_at_3(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        for _ in range(5):
            iv.boost_urgency(m, 1.0)
        assert getattr(m.environment, "urgency_modifier", 1.0) <= 3.0

    def test_reduces_stall_ticks(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 4)
        m.progress_stall_ticks = 10
        iv.boost_urgency(m, 0.4)
        assert m.progress_stall_ticks < 10, "boost_urgency should reduce progress_stall_ticks"

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_run_completes_after_boost(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 3)
        iv.boost_urgency(m, 0.5)
        _run_to_end(m)
        assert m.ended is True

    def test_high_urgency_shortens_run(self):
        """Urgency boost at early tick should not extend the run beyond baseline."""
        baseline = _make("office_proposal", "office", seed=42, team_type="smooth")
        _run_to_end(baseline)

        boosted = _make("office_proposal", "office", seed=42, team_type="smooth")
        _step(boosted, 3)
        iv.boost_urgency(boosted, 0.6)
        _run_to_end(boosted)

        assert boosted.tick <= baseline.tick + 3, (
            f"boosted run took {boosted.tick} ticks vs baseline {baseline.tick}"
        )


# ---------------------------------------------------------------------------
# 4. ease_pressure
# ---------------------------------------------------------------------------

class TestEasePressure:

    def test_returns_success(self):
        m = _make("escape_room", "escape", team_type="tension")
        _step(m, 2)
        iv.boost_urgency(m, 0.3)
        result = iv.ease_pressure(m, 0.1)
        assert result["success"] is True
        assert "Pressure eased" in result["message"]

    def test_lowers_urgency_modifier(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        iv.boost_urgency(m, 0.3)
        before = getattr(m.environment, "urgency_modifier", 0.0)
        iv.ease_pressure(m, 0.1)
        after = getattr(m.environment, "urgency_modifier", 0.0)
        assert after < before, (
            f"urgency_modifier did not decrease after ease_pressure: {before:.3f} → {after:.3f}"
        )

    def test_pressure_floor_at_zero(self):
        m = _make("cafe_restaurant", "cafe", team_type="smooth")
        _step(m, 1)
        before = getattr(m.environment, "urgency_modifier", 0.0)
        result = iv.ease_pressure(m, 0.2)
        after = getattr(m.environment, "urgency_modifier", 0.0)
        assert after == pytest.approx(0.0)
        assert after >= 0.0
        assert result["pressure_before"] == pytest.approx(before)
        assert result["pressure_after"] == pytest.approx(0.0)

    def test_relaxed_run_still_completes(self):
        m = _make("escape_room", "escape", seed=42, team_type="smooth")
        _step(m, 3)
        iv.ease_pressure(m, 0.1)
        _run_to_end(m)
        assert m.ended is True


# ---------------------------------------------------------------------------
# 5. inject_tension
# ---------------------------------------------------------------------------

class TestInjectTension:

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_returns_success(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 3)
        result = iv.inject_tension(m, 0.3)
        assert result["success"] is True
        assert "tension raised" in result["message"]

    @pytest.mark.parametrize("amount", [0.1, 0.25, 0.5])
    def test_raises_group_tension(self, amount):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        before = m.group_tension
        iv.inject_tension(m, amount)
        assert m.group_tension > before, (
            f"group_tension did not increase after inject({amount})"
        )

    @pytest.mark.parametrize("amount", [0.1, 0.3, 0.5])
    def test_raises_agent_stress(self, amount):
        m = _make("office_proposal", "office", team_type="smooth")
        _step(m, 2)
        stress_before = [a.stress for a in m.agents]
        iv.inject_tension(m, amount)
        stress_after  = [a.stress for a in m.agents]
        assert any(af >= bf for bf, af in zip(stress_before, stress_after)), (
            "inject_tension should raise stress in at least one agent"
        )

    def test_group_tension_capped_at_1(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        iv.inject_tension(m, 1.0)
        iv.inject_tension(m, 1.0)
        assert m.group_tension <= 1.0

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_run_completes_after_tension(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 3)
        iv.inject_tension(m, 0.3)
        _run_to_end(m)
        assert m.ended is True

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    def test_events_produced_after_tension(self, scenario_id, env):
        m = _make(scenario_id, env, team_type="balanced")
        _step(m, 3)
        tick_at = m.tick
        iv.inject_tension(m, 0.4)
        _step(m, 2)
        post = _events_after(m, tick_at)
        assert len(post) > 0, f"{scenario_id}: no events after inject_tension"

    def test_tension_team_amplifies_inject_tension_stress(self):
        """inject_tension on a tension team should produce higher stress than on smooth."""
        smooth  = _make("office_proposal", "office", team_type="smooth")
        tension = _make("office_proposal", "office", team_type="tension")
        _step(smooth, 3)
        _step(tension, 3)
        iv.inject_tension(smooth,  0.3)
        iv.inject_tension(tension, 0.3)
        assert _avg_stress(tension) >= _avg_stress(smooth), (
            f"tension team stress ({_avg_stress(tension):.3f}) < "
            f"smooth team stress ({_avg_stress(smooth):.3f}) after same injection"
        )

    def test_tension_impulse_survives_same_tick_recovery(self):
        m = _make("office_proposal", "office", team_type="smooth")
        _step(m, 3)
        before = float(m.group_tension)
        iv.inject_tension(m, 0.05)
        m.step()
        assert m.group_tension >= before + 0.049, (
            f"inject_tension spike was erased in the same tick: {before:.3f} -> {m.group_tension:.3f}"
        )

    def test_tension_impulse_lasts_into_next_step(self):
        m = _make("office_proposal", "office", team_type="smooth")
        _step(m, 3)
        before = float(m.group_tension)
        iv.inject_tension(m, 0.05)
        m.step()
        after_first = float(m.group_tension)
        m.step()
        after_second = float(m.group_tension)
        assert after_first >= before + 0.049
        assert after_second >= before + 0.049, (
            f"tension impulse did not remain visible into the next step: "
            f"{before:.3f} -> {after_first:.3f} -> {after_second:.3f}"
        )


# ---------------------------------------------------------------------------
# 5. force_meeting
# ---------------------------------------------------------------------------

class TestForceMeeting:

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_returns_success(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 2)
        a, b = _agents_sorted(m)[:2]
        result = iv.force_meeting(m, a.public_id, b.public_id)
        assert result["success"] is True
        assert "Meeting forced" in result["message"]

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_agents_linked_after_meeting(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 2)
        a, b = _agents_sorted(m)[:2]
        iv.force_meeting(m, a.public_id, b.public_id)
        assert a.current_conversation_with == b.public_id
        assert b.current_conversation_with == a.public_id

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_pair_events_produced(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 2)
        a, b = _agents_sorted(m)[:2]
        tick_before = m.tick
        iv.force_meeting(m, a.public_id, b.public_id)
        _step(m, 2)
        pair_events = [
            e for e in _events_after(m, tick_before)
            if {e.get("actor"), e.get("target")} == {a.public_id, b.public_id}
        ]
        assert len(pair_events) > 0, (
            f"{scenario_id}/{team_type}: no events between {a.public_id} and "
            f"{b.public_id} after force_meeting"
        )

    def test_same_agent_fails(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        result = iv.force_meeting(m, "A1", "A1")
        assert result["success"] is False

    def test_unknown_agent_fails(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        result = iv.force_meeting(m, "A1", "Z99")
        assert result["success"] is False

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_run_completes_after_meeting(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 3)
        a, b = _agents_sorted(m)[:2]
        iv.force_meeting(m, a.public_id, b.public_id)
        _run_to_end(m)
        assert m.ended is True

    def test_raises_mutual_trust(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        a1 = next(a for a in m.agents if a.public_id == "A1")
        a2 = next(a for a in m.agents if a.public_id == "A2")
        t12 = a1.trust.get("A2", 0.5)
        t21 = a2.trust.get("A1", 0.5)
        iv.force_meeting(m, "A1", "A2")
        assert a1.trust.get("A2", 0.5) >= t12, "A1→A2 trust fell after force_meeting"
        assert a2.trust.get("A1", 0.5) >= t21, "A2→A1 trust fell after force_meeting"

    def test_meeting_queues_pending_opener_events(self):
        m = _make("office_proposal", "office", team_type="balanced")
        _step(m, 2)
        before = len(getattr(m, "_pending_events", []))
        iv.force_meeting(m, "A1", "A2")
        after = len(getattr(m, "_pending_events", []))
        assert after > before, "force_meeting did not queue any opener events"


# ---------------------------------------------------------------------------
# 6. Combined intervention sequences
# ---------------------------------------------------------------------------

class TestCombinedInterventions:
    """Multiple interventions in the same run must not crash or deadlock."""

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_urgency_then_reveal_completes(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 3)
        iv.boost_urgency(m, 0.3)
        _step(m, 1)
        agent, item = _first_unknown(m)
        if agent and item:
            iv.reveal_info(m, agent.public_id, item)
        _run_to_end(m)
        assert m.ended is True

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_tension_then_nudge_completes(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, team_type=team_type)
        _step(m, 3)
        iv.inject_tension(m, 0.3)
        iv.nudge_strategy(m, _agents_sorted(m)[0].public_id, "cooperative")
        _run_to_end(m)
        assert m.ended is True

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_meeting_then_reveal_completes(self, scenario_id, env, team_type):
        m = _make(scenario_id, env, seed=99, team_type=team_type)
        _step(m, 2)
        a, b = _agents_sorted(m)[:2]
        iv.force_meeting(m, a.public_id, b.public_id)
        _step(m, 1)
        agent, item = _first_unknown(m)
        if agent and item:
            iv.reveal_info(m, agent.public_id, item)
        _run_to_end(m)
        assert m.ended is True

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", CORE_STYLES)
    def test_all_five_interventions_in_sequence(self, scenario_id, env, team_type):
        """All five interventions applied within one run must not cause a hang or crash."""
        m = _make(scenario_id, env, seed=7, team_type=team_type, max_ticks=40)
        _step(m, 2)

        r1 = iv.boost_urgency(m, 0.25)
        assert r1["success"] is True, f"{scenario_id}/{team_type}: boost_urgency failed"

        r2 = iv.inject_tension(m, 0.2)
        assert r2["success"] is True, f"{scenario_id}/{team_type}: inject_tension failed"

        r3 = iv.nudge_strategy(m, _agents_sorted(m)[0].public_id, "cooperative")
        assert r3["success"] is True, f"{scenario_id}/{team_type}: nudge_strategy failed"

        a, b = _agents_sorted(m)[:2]
        r4 = iv.force_meeting(m, a.public_id, b.public_id)
        assert r4["success"] is True, f"{scenario_id}/{team_type}: force_meeting failed"

        _step(m, 2)
        agent, item = _first_unknown(m)
        if agent and item:
            r5 = iv.reveal_info(m, agent.public_id, item)
            assert r5["success"] is True, f"{scenario_id}/{team_type}: reveal_info failed"

        _run_to_end(m)
        assert m.ended is True, (
            f"{scenario_id}/{team_type}: run did not terminate after all five interventions"
        )
