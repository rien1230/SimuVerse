"""
test_evaluation_core.py
=======================
Evaluation-focused test suite for the SimuVerse backend — Chapter 5 evidence.

Covers 12 key functional areas in 16 tests:

  1.  Scenario loading            — Office, Cafe, Escape all construct without error
  2.  Simulation step             — a single step advances the tick counter
  3.  Metric validity             — stress, trust, tension stay within [0, 1]
  4.  Metric history structure    — all required keys present per tick
  5.  reveal_info intervention    — target agent gains the specified knowledge item
  6.  force_meeting intervention  — returns valid trust-change fields
  7.  boost_urgency intervention  — urgency modifier is non-decreasing after the call
  8.  inject_emotion intervention — call succeeds and agent states stay bounded
  9.  Memory system (STM)         — short-term memory is populated after interaction
 10.  Preset config differences   — smooth vs tension/pressure differ in key config values
 11.  Preset structural effect    — smooth produces lower initial stress than tension preset
 12.  Save a completed run        — file is written, valid JSON, contains required fields
 13.  Load a saved run            — load_run returns the correct run dict
 14.  Replay a saved run          — replay_run returns a tick-by-tick list
 15.  Experiment runner           — run_experiment returns a valid result dict
 16.  Experiment success rate     — success_rate is a bounded float within [0, 1]

Run this suite alone with:
    pytest backend/tests/test_evaluation_core.py -v

Does NOT test exact dialogue wording (classifier output is stochastic).
Uses temporary directories for all persistence tests — real saved runs are untouched.
"""

from __future__ import annotations

import json
import os
import warnings

import pytest

warnings.filterwarnings("ignore")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from app.sim.model import SimModel
from app.sim.game_config import PRESET_INITIAL_STATE, PRESET_STRESS_SEED, PRESET_AGREE_BIAS
from app.services import run_history_service
from app.services.experiment_service import run_experiment

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make(scenario_id: str = "office_proposal", preset: str = "balanced_team",
          seed: int = 42, max_ticks: int = 25) -> SimModel:
    return SimModel(seed=seed, scenario_id=scenario_id,
                    team_preset=preset, episode_max_ticks=max_ticks, use_nlp=False)


def _run_to_end(model: SimModel) -> SimModel:
    while not model.ended:
        model.step()
    return model


@pytest.fixture()
def tmp_runs(tmp_path, monkeypatch):
    """Redirect RUNS_DIR to a pytest-managed temp directory."""
    monkeypatch.setattr(run_history_service, "RUNS_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# 1–2  Scenario loading and step advancement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario_id", [
    "office_proposal",
    "cafe_restaurant",
    "escape_puzzle",
])
def test_scenario_loads_and_has_agents(scenario_id):
    """All three scenarios construct a model with agents and a valid scenario object."""
    model = _make(scenario_id)
    assert len(model.agents) > 0, f"{scenario_id}: no agents created"
    assert model.scenario is not None
    assert model.scenario.id == scenario_id


def test_simulation_step_advances_tick():
    """A single call to model.step() increments the tick counter from 0 to 1."""
    model = _make()
    assert model.tick == 0
    model.step()
    assert model.tick == 1


# ---------------------------------------------------------------------------
# 3–4  Metric validity
# ---------------------------------------------------------------------------


def test_agent_metrics_bounded_after_steps():
    """Stress and trust stay within [0, 1] across all agents after 10 steps."""
    model = _make(max_ticks=30)
    for _ in range(10):
        if not model.ended:
            model.step()
    for agent in model.agents:
        assert 0.0 <= agent.stress <= 1.0, f"stress out of range: {agent.stress}"
        for peer_id, trust_val in agent.trust.items():
            assert 0.0 <= trust_val <= 1.0, f"trust out of range: {trust_val}"
    assert 0.0 <= model.group_tension <= 1.0


def test_metric_history_has_required_keys():
    """Every tick in metric_history contains the core analytical fields."""
    required = {"tick", "avg_trust", "avg_stress", "group_tension",
                "group_cohesion", "share_count", "refusal_count", "progress"}
    model = _make(max_ticks=30)
    for _ in range(8):
        if not model.ended:
            model.step()
    for entry in model.metric_history:
        missing = required - entry.keys()
        assert not missing, f"Metric history entry missing keys: {missing}"


# ---------------------------------------------------------------------------
# 5–8  Interventions
# ---------------------------------------------------------------------------


def test_reveal_info_adds_knowledge_item():
    """reveal_info adds the specified item to the target agent's known_items set."""
    model = _make()
    model.step()
    agent = next(a for a in model.agents if a.public_id == "A2")
    item = "requirements"
    result = model.apply_intervention("reveal_info", {"agent_id": "A2", "item": item})
    assert result["success"] is True
    assert item in agent.known_items


def test_force_meeting_returns_trust_data():
    """force_meeting returns success and the three expected trust-change fields."""
    model = _make()
    model.step()
    result = model.apply_intervention("force_meeting", {"agent_a_id": "A1", "agent_b_id": "A3"})
    assert result["success"] is True
    assert "trust_before" in result
    assert "trust_after" in result
    assert "trust_delta" in result


def test_boost_urgency_raises_pressure():
    """boost_urgency increases the environment urgency modifier."""
    model = _make()
    model.step()
    before = model.environment.urgency_modifier
    result = model.apply_intervention("boost_urgency", {"amount": 0.25})
    assert result["success"] is True
    assert model.environment.urgency_modifier >= before


def test_inject_emotion_succeeds_and_stays_bounded():
    """inject_emotion returns success and all agent states remain in valid ranges."""
    model = _make()
    model.step()
    result = model.apply_intervention("inject_emotion",
                                      {"text": "This is overwhelming and stressful"})
    assert result["success"] is True
    for agent in model.agents:
        assert 0.0 <= agent.stress <= 1.0
        assert -1.0 <= agent.valence <= 1.0


# ---------------------------------------------------------------------------
# 9  Memory system
# ---------------------------------------------------------------------------


def test_memory_stm_populated_after_interaction():
    """At least one agent's short-term memory contains entries after 15 steps."""
    model = _make(max_ticks=30)
    for _ in range(15):
        if not model.ended:
            model.step()
    populated = [a for a in model.agents if len(a.memory.stm) > 0]
    assert len(populated) > 0, "No agent has STM entries after 15 steps"


# ---------------------------------------------------------------------------
# 10–11  Team preset differences
# ---------------------------------------------------------------------------


def test_preset_configurations_differ():
    """Smooth and tension/pressure presets have different stress seeds and agree biases."""
    assert PRESET_STRESS_SEED["smooth_team"] < PRESET_STRESS_SEED["tension_team"]
    assert PRESET_STRESS_SEED["smooth_team"] < PRESET_STRESS_SEED["pressure_team"]
    assert PRESET_AGREE_BIAS["smooth_team"] > PRESET_AGREE_BIAS["tension_team"]


def test_smooth_preset_produces_lower_initial_stress():
    """Smooth team starts with lower average agent stress than the tension preset."""
    m_smooth = _make(preset="smooth_team", seed=99)
    m_tension = _make(preset="tension_team", seed=99)
    avg_smooth = sum(a.stress for a in m_smooth.agents) / len(m_smooth.agents)
    avg_tension = sum(a.stress for a in m_tension.agents) / len(m_tension.agents)
    assert avg_smooth <= avg_tension, (
        f"Expected smooth avg_stress ({avg_smooth:.3f}) <= tension ({avg_tension:.3f})"
    )


# ---------------------------------------------------------------------------
# 12–14  Run persistence
# ---------------------------------------------------------------------------


def test_completed_run_saves_valid_json(tmp_runs):
    """A finished run produces a valid JSON file with the required top-level fields."""
    model = _run_to_end(_make(max_ticks=20))
    run_id = run_history_service.save_run(model, run_id="eval_save", config={}, owner=None)
    saved_file = tmp_runs / "run_eval_save.json"
    assert saved_file.exists()
    data = json.loads(saved_file.read_text())
    for field in ("run_id", "history", "metric_trajectory", "event_counts", "outcome"):
        assert field in data, f"Saved run missing field: {field}"
    assert data["run_id"] == run_id


def test_saved_run_loads_correctly(tmp_runs):
    """load_run returns the correct run dict for a previously saved run."""
    model = _run_to_end(_make(max_ticks=20))
    run_history_service.save_run(model, run_id="eval_load", config={}, owner=None)
    loaded = run_history_service.load_run("eval_load", owner=None)
    assert loaded is not None
    assert loaded["run_id"] == "eval_load"
    assert isinstance(loaded["history"], list)


def test_saved_run_replays_tick_by_tick(tmp_runs):
    """replay_run returns a list with one entry per simulation tick."""
    model = _run_to_end(_make(max_ticks=20))
    ticks = model.tick
    run_history_service.save_run(model, run_id="eval_replay", config={}, owner=None)
    history = run_history_service.replay_run("eval_replay", owner=None)
    assert isinstance(history, list)
    assert len(history) == ticks
    for entry in history:
        assert "tick" in entry


# ---------------------------------------------------------------------------
# 15–16  Experiment runner
# ---------------------------------------------------------------------------


def test_experiment_runner_returns_result_dict():
    """run_experiment on a small batch returns a dict with core result keys."""
    result = run_experiment("office_proposal", n_runs=3,
                            episode_max_ticks=20, skip_emotions=True)
    assert isinstance(result, dict)
    for key in ("scenario_id", "n_runs", "success_rate", "outcome_rates",
                "avg_trust", "avg_stress"):
        assert key in result, f"Experiment result missing key: {key}"


def test_experiment_success_rate_is_bounded():
    """run_experiment success_rate is a float in [0, 1]."""
    result = run_experiment("cafe_restaurant", n_runs=3,
                            episode_max_ticks=20, skip_emotions=True)
    sr = result["success_rate"]
    assert isinstance(sr, float)
    assert 0.0 <= sr <= 1.0, f"success_rate out of range: {sr}"
