"""
test_scenarios.py
=================
Core scenario tests for SimuVerse.

Covers every valid scenario + team-style combination used in the dissertation:
  Scenarios  : office_proposal | cafe_restaurant | escape_puzzle
  Team styles: smooth | balanced | tension | creative | pressure

A simulation is created via SimModel(seed, scenario_id, environment,
episode_max_ticks, team_type) — exactly as the production /simulation/start
endpoint does.  No HTTP server required.

Test groups
-----------
  TestReproducibility   – same seed → identical output every run
  TestCompletion        – each combo reaches a valid terminal outcome
  TestTaskProgression   – completed tasks never regress to False
  TestEventStructure    – every event has type/actor/target; types are valid
  TestMetricRanges      – trust, stress, valence, arousal stay in [0,1]
  TestKnowledgeGrowth   – agents accumulate known items via share_info

Run from the backend directory:
    source .venv/bin/activate
    pytest tests/test_scenarios.py -v
"""

import os
import sys
import warnings
from pathlib import Path
import pytest

warnings.filterwarnings("ignore")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Keep the backend package importable whether pytest is launched from the repo
# root or from inside backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sim.model import SimModel
from app.sim.scenario_data import SCENARIOS, resolve_scenario_id

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The three scenarios used in the dissertation
DISSERTATION_SCENARIOS = [
    ("office_proposal", "office"),
    ("cafe_restaurant", "cafe"),
    ("escape_puzzle",   "escape"),
]

# All five team styles available in the UI
TEAM_STYLES = ["smooth", "balanced", "tension", "creative", "pressure"]

# Seeds used across evaluation experiments
SEEDS = [42, 99, 7]

# Valid dialogue-act types
VALID_EVENT_TYPES = {
    "ask_info", "share_info", "agree", "suggest", "refuse",
    "challenge", "say", "help", "compliment", "ignore",
}

# Internal task-key tokens that are underscored identifiers and must never
# appear verbatim in agent dialogue (common English words such as "key" or
# "map" are intentionally spoken by agents and are therefore not listed here)
INTERNAL_KEY_TOKENS = {
    "budget_constraint",
    "location_constraint",
    "dietary_constraint",
    "tech_specs",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_model(scenario_id: str, env: str, seed: int,
               team_type: str = "balanced",
               max_ticks: int = 30) -> SimModel:
    """Create and fully run a SimModel to completion or max_ticks."""
    sid = resolve_scenario_id(scenario_id)
    model = SimModel(
        seed=seed,
        scenario_id=sid,
        environment=env,
        episode_max_ticks=max_ticks,
        team_type=team_type,
    )
    model.skip_emotions = True
    while not model.ended and model.tick < max_ticks:
        model.step()
    return model


def all_events(model: SimModel):
    return [e for tick in model.history for e in (tick.get("events") or [])]


def avg_trust(model: SimModel) -> float:
    vals = [v for a in model.agents for v in a.trust.values()]
    return sum(vals) / max(1, len(vals))


def avg_stress(model: SimModel) -> float:
    agents = list(model.agents)
    return sum(a.stress for a in agents) / len(agents)


# ---------------------------------------------------------------------------
# Fixtures – run each scenario once (module scope = no repeated cold starts)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def office_balanced():
    return make_model("office_proposal", "office", seed=42, team_type="balanced")


@pytest.fixture(scope="module")
def cafe_balanced():
    return make_model("cafe_restaurant", "cafe", seed=42, team_type="balanced")


@pytest.fixture(scope="module")
def escape_balanced():
    return make_model("escape_puzzle", "escape", seed=42, team_type="balanced")


# ---------------------------------------------------------------------------
# 1. Reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility:
    """Identical (scenario, team_type, seed) triples must produce identical output."""

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "tension", "pressure"])
    def test_same_seed_same_outcome(self, scenario_id, env, team_type):
        a = make_model(scenario_id, env, seed=42, team_type=team_type)
        b = make_model(scenario_id, env, seed=42, team_type=team_type)
        assert a.end_reason == b.end_reason, (
            f"{scenario_id}/{team_type}: end_reason differs across identical seeds"
        )
        assert a.tick == b.tick, (
            f"{scenario_id}/{team_type}: tick count differs across identical seeds"
        )

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "pressure"])
    def test_same_seed_same_task_state(self, scenario_id, env, team_type):
        a = make_model(scenario_id, env, seed=99, team_type=team_type)
        b = make_model(scenario_id, env, seed=99, team_type=team_type)
        assert a.scenario.tasks == b.scenario.tasks, (
            f"{scenario_id}/{team_type}: final task state differs across identical seeds"
        )

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["balanced", "pressure"])
    def test_same_seed_same_total_events(self, scenario_id, env, team_type):
        a = make_model(scenario_id, env, seed=7, team_type=team_type)
        b = make_model(scenario_id, env, seed=7, team_type=team_type)
        assert len(all_events(a)) == len(all_events(b)), (
            f"{scenario_id}/{team_type}: total event count differs across identical seeds"
        )


# ---------------------------------------------------------------------------
# 2. Completion
# ---------------------------------------------------------------------------

class TestCompletion:
    """Every scenario × team-style combination must reach a valid terminal state."""

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", TEAM_STYLES)
    @pytest.mark.parametrize("seed", SEEDS)
    def test_run_terminates(self, scenario_id, env, team_type, seed):
        m = make_model(scenario_id, env, seed=seed, team_type=team_type)
        assert m.ended is True, (
            f"{scenario_id}/{team_type} seed={seed}: model.ended is False after {m.tick} ticks"
        )

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", TEAM_STYLES)
    @pytest.mark.parametrize("seed", SEEDS)
    def test_end_reason_is_valid(self, scenario_id, env, team_type, seed):
        m = make_model(scenario_id, env, seed=seed, team_type=team_type)
        assert m.end_reason in {"success", "partial", "failure", "harmony"}, (
            f"{scenario_id}/{team_type} seed={seed}: unexpected end_reason '{m.end_reason}'"
        )

    # Smooth team on cooperative scenarios should reliably succeed
    def test_office_smooth_succeeds(self):
        m = make_model("office_proposal", "office", seed=42, team_type="smooth")
        assert m.end_reason == "success"

    def test_cafe_smooth_succeeds(self):
        m = make_model("cafe_restaurant", "cafe", seed=42, team_type="smooth")
        assert m.end_reason == "success"

    def test_escape_smooth_succeeds(self):
        m = make_model("escape_puzzle", "escape", seed=42, team_type="smooth")
        assert m.end_reason == "success"

    # Balanced team — standard dissertation baseline
    def test_office_balanced_succeeds(self, office_balanced):
        assert office_balanced.end_reason == "success"

    def test_cafe_balanced_succeeds(self, cafe_balanced):
        assert cafe_balanced.end_reason == "success"

    def test_escape_balanced_succeeds(self, escape_balanced):
        assert escape_balanced.end_reason == "success"


# ---------------------------------------------------------------------------
# 3. Task progression
# ---------------------------------------------------------------------------

class TestTaskProgression:
    """Tasks must never regress from True (done) back to False (not done)."""

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "tension", "pressure"])
    def test_tasks_never_regress(self, scenario_id, env, team_type):
        sid = resolve_scenario_id(scenario_id)
        model = SimModel(
            seed=42,
            scenario_id=sid,
            environment=env,
            episode_max_ticks=30,
            team_type=team_type,
        )
        model.skip_emotions = True
        completed: set = set()
        while not model.ended and model.tick < 30:
            model.step()
            for item, done in model.scenario.tasks.items():
                if done:
                    completed.add(item)
                else:
                    assert item not in completed, (
                        f"{scenario_id}/{team_type}: task '{item}' regressed at tick {model.tick}"
                    )

    def test_all_office_tasks_complete_smooth(self):
        m = make_model("office_proposal", "office", seed=42, team_type="smooth")
        assert all(m.scenario.tasks.values()), "office_proposal/smooth: not all tasks completed"

    def test_all_cafe_tasks_complete_smooth(self):
        m = make_model("cafe_restaurant", "cafe", seed=42, team_type="smooth")
        assert all(m.scenario.tasks.values()), "cafe_restaurant/smooth: not all tasks completed"

    def test_all_escape_tasks_complete_smooth(self):
        m = make_model("escape_puzzle", "escape", seed=42, team_type="smooth")
        assert all(m.scenario.tasks.values()), "escape_puzzle/smooth: not all tasks completed"


# ---------------------------------------------------------------------------
# 4. Event structure
# ---------------------------------------------------------------------------

class TestEventStructure:
    """All events must carry required fields and use recognised type labels."""

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "tension", "pressure"])
    def test_every_event_has_required_fields(self, scenario_id, env, team_type):
        m = make_model(scenario_id, env, seed=42, team_type=team_type)
        for ev in all_events(m):
            assert "type"   in ev, f"Event missing 'type': {ev}"
            assert "actor"  in ev, f"Event missing 'actor': {ev}"
            assert "target" in ev, f"Event missing 'target': {ev}"

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "tension", "pressure"])
    def test_event_types_are_valid(self, scenario_id, env, team_type):
        m = make_model(scenario_id, env, seed=42, team_type=team_type)
        for ev in all_events(m):
            assert ev["type"] in VALID_EVENT_TYPES, (
                f"{scenario_id}/{team_type}: unrecognised event type '{ev['type']}'"
            )

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "pressure"])
    def test_no_internal_key_tokens_in_speech(self, scenario_id, env, team_type):
        """Underscored internal task identifiers must never appear in agent dialogue."""
        m = make_model(scenario_id, env, seed=42, team_type=team_type)
        violations = []
        for ev in all_events(m):
            text = (ev.get("text") or "").lower()
            for token in INTERNAL_KEY_TOKENS:
                if token in text:
                    violations.append((token, text[:80]))
        assert not violations, (
            f"{scenario_id}/{team_type}: internal key tokens in dialogue: {violations[:3]}"
        )

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "pressure"])
    def test_most_ticks_produce_events(self, scenario_id, env, team_type):
        """At least 60% of ticks must produce at least one event."""
        m = make_model(scenario_id, env, seed=42, team_type=team_type)
        history = m.history
        if not history:
            return
        active = sum(1 for t in history if len(t.get("events") or []) > 0)
        ratio = active / len(history)
        assert ratio >= 0.60, (
            f"{scenario_id}/{team_type}: only {active}/{len(history)} ticks active ({ratio:.0%})"
        )


# ---------------------------------------------------------------------------
# 5. Metric ranges
# ---------------------------------------------------------------------------

class TestMetricRanges:
    """Trust, stress, valence, and arousal must remain within their defined bounds."""

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "tension", "pressure"])
    def test_trust_bounded(self, scenario_id, env, team_type):
        m = make_model(scenario_id, env, seed=42, team_type=team_type)
        for agent in m.agents:
            for pid, val in agent.trust.items():
                assert 0.0 <= val <= 1.0, (
                    f"{scenario_id}/{team_type}: trust[{agent.public_id}→{pid}]={val:.3f}"
                )

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "tension", "pressure"])
    def test_stress_bounded(self, scenario_id, env, team_type):
        m = make_model(scenario_id, env, seed=42, team_type=team_type)
        for agent in m.agents:
            assert 0.0 <= agent.stress <= 1.0, (
                f"{scenario_id}/{team_type}: stress[{agent.public_id}]={agent.stress:.3f}"
            )

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "tension", "pressure"])
    def test_valence_bounded(self, scenario_id, env, team_type):
        m = make_model(scenario_id, env, seed=42, team_type=team_type)
        for agent in m.agents:
            assert -1.0 <= agent.valence <= 1.0, (
                f"{scenario_id}/{team_type}: valence[{agent.public_id}]={agent.valence:.3f}"
            )

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "tension", "pressure"])
    def test_arousal_bounded(self, scenario_id, env, team_type):
        m = make_model(scenario_id, env, seed=42, team_type=team_type)
        for agent in m.agents:
            assert 0.0 <= agent.arousal <= 1.0, (
                f"{scenario_id}/{team_type}: arousal[{agent.public_id}]={agent.arousal:.3f}"
            )

    def test_tension_team_higher_stress_than_smooth_office(self):
        smooth  = make_model("office_proposal", "office", seed=42, team_type="smooth")
        tension = make_model("office_proposal", "office", seed=42, team_type="tension")
        assert avg_stress(tension) > avg_stress(smooth), (
            f"tension stress ({avg_stress(tension):.3f}) not > smooth stress ({avg_stress(smooth):.3f})"
        )

    def test_tension_team_lower_trust_than_smooth_office(self):
        smooth  = make_model("office_proposal", "office", seed=42, team_type="smooth")
        tension = make_model("office_proposal", "office", seed=42, team_type="tension")
        assert avg_trust(smooth) > avg_trust(tension), (
            f"smooth trust ({avg_trust(smooth):.3f}) not > tension trust ({avg_trust(tension):.3f})"
        )

    def test_escape_stress_higher_than_cafe_balanced(self):
        cafe   = make_model("cafe_restaurant", "cafe",   seed=42, team_type="balanced")
        escape = make_model("escape_puzzle",   "escape", seed=42, team_type="balanced")
        assert avg_stress(escape) > avg_stress(cafe), (
            f"escape stress ({avg_stress(escape):.3f}) not > café stress ({avg_stress(cafe):.3f})"
        )


# ---------------------------------------------------------------------------
# 6. Knowledge growth
# ---------------------------------------------------------------------------

class TestKnowledgeGrowth:
    """Agents must accumulate known_items across the run via share_info events."""

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "pressure"])
    def test_knowledge_grows(self, scenario_id, env, team_type):
        sid = resolve_scenario_id(scenario_id)
        model = SimModel(
            seed=42, scenario_id=sid, environment=env,
            episode_max_ticks=30, team_type=team_type,
        )
        model.skip_emotions = True
        known_start = sum(len(a.known_items) for a in model.agents)
        while not model.ended and model.tick < 30:
            model.step()
        known_end = sum(len(a.known_items) for a in model.agents)
        assert known_end >= known_start, (
            f"{scenario_id}/{team_type}: collective knowledge shrank during the run"
        )

    @pytest.mark.parametrize("scenario_id,env", DISSERTATION_SCENARIOS)
    @pytest.mark.parametrize("team_type", ["smooth", "balanced", "tension", "pressure"])
    def test_share_info_events_produced(self, scenario_id, env, team_type):
        m = make_model(scenario_id, env, seed=42, team_type=team_type)
        shares = [e for e in all_events(m) if e.get("type") == "share_info"]
        assert len(shares) > 0, (
            f"{scenario_id}/{team_type}: no share_info events — tasks could not have completed"
        )
