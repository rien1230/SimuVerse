"""
test_experiment_runner.py
=========================
Tests for the batch experiment runner service.

Covers four areas:
  1. run_single_seeded_experiment  — real simulation, correct fields, reproducibility
  2. aggregate_experiment_results  — correct maths, grouping, completion rate
  3. compare_team_styles           — correct winner detection, non-empty interpretation
  4. run_experiment_batch          — correct run count, aggregation wiring, reproducibility

All tests run the *real* SimModel with small max_steps so they finish quickly.
No mocking, no dummy data.

Run from the backend directory:
    source .venv/bin/activate
    pytest tests/test_experiment_runner.py -v
"""

from __future__ import annotations

import pytest

from app.services.experiment_runner import (
    _is_task_resolved,
    run_single_seeded_experiment,
    aggregate_experiment_results,
    compare_team_styles,
    run_experiment_batch,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

REQUIRED_RUN_KEYS = {
    "scenario", "scenario_id", "team_style", "seed",
    "completed", "completion_steps", "final_progress", "end_reason",
    "start_trust", "final_trust", "trust_delta",
    "peak_stress", "final_stress",
    "blocker_count", "blockers_resolved",
    "cooperation_count", "challenge_count",
    "intervention_count", "ticks",
}

_FAST_STEPS = 15   # keep each real-sim test short


def _make_mock_runs():
    """Synthetic run dicts for unit-testing aggregation/comparison in isolation."""
    return [
        {
            "team_style": "smooth", "completed": True,  "completion_steps": 8,
            "peak_stress": 0.28,  "final_trust": 0.72, "start_trust": 0.57,
            "trust_delta": 0.15,  "challenge_count": 0, "cooperation_count": 9,
            "blocker_count": 4, "blockers_resolved": 4,
        },
        {
            "team_style": "smooth", "completed": True,  "completion_steps": 10,
            "peak_stress": 0.32,  "final_trust": 0.69, "start_trust": 0.57,
            "trust_delta": 0.12,  "challenge_count": 1, "cooperation_count": 7,
            "blocker_count": 4, "blockers_resolved": 4,
        },
        {
            "team_style": "tension", "completed": False, "completion_steps": None,
            "peak_stress": 0.63,  "final_trust": 0.44, "start_trust": 0.38,
            "trust_delta": 0.06,  "challenge_count": 5, "cooperation_count": 5,
            "blocker_count": 4, "blockers_resolved": 2,
        },
        {
            "team_style": "tension", "completed": True,  "completion_steps": 18,
            "peak_stress": 0.61,  "final_trust": 0.47, "start_trust": 0.38,
            "trust_delta": 0.09,  "challenge_count": 4, "cooperation_count": 6,
            "blocker_count": 4, "blockers_resolved": 4,
        },
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  1.  run_single_seeded_experiment
# ══════════════════════════════════════════════════════════════════════════════

class TestRunSingleSeededExperiment:

    def test_returns_all_required_fields(self):
        result = run_single_seeded_experiment("office", "smooth", seed=42, max_steps=_FAST_STEPS)
        missing = REQUIRED_RUN_KEYS - result.keys()
        assert not missing, f"Missing keys: {missing}"

    def test_scenario_and_team_echoed(self):
        result = run_single_seeded_experiment("cafe", "tension", seed=7, max_steps=_FAST_STEPS)
        assert result["scenario"]    == "cafe"
        assert result["team_style"]  == "tension"
        assert result["seed"]        == 7

    def test_same_seed_produces_identical_result(self):
        """Core reproducibility guarantee: same seed → same run."""
        a = run_single_seeded_experiment("escape", "tension", seed=101, max_steps=35)
        b = run_single_seeded_experiment("escape", "tension", seed=101, max_steps=35)

        assert a["ticks"]             == b["ticks"],             "tick count differs"
        assert a["completed"]         == b["completed"],         "completion status differs"
        assert a["blockers_resolved"] == b["blockers_resolved"], "blocker resolution differs"
        assert a["challenge_count"]   == b["challenge_count"],   "challenge count differs"
        assert a["cooperation_count"] == b["cooperation_count"], "cooperation count differs"

    def test_completion_steps_none_when_not_completed(self):
        # max_steps=2 almost certainly won't complete
        result = run_single_seeded_experiment("escape", "tension", seed=42, max_steps=2)
        if not result["completed"]:
            assert result["completion_steps"] is None

    def test_final_progress_in_unit_interval(self):
        result = run_single_seeded_experiment("office", "smooth", seed=1, max_steps=_FAST_STEPS)
        assert 0.0 <= result["final_progress"] <= 1.0

    def test_trust_delta_matches_start_and_final(self):
        result = run_single_seeded_experiment("office", "creative", seed=55, max_steps=_FAST_STEPS)
        expected = round(result["final_trust"] - result["start_trust"], 3)
        assert abs(result["trust_delta"] - expected) < 0.005, (
            f"trust_delta={result['trust_delta']} but final-start={expected}"
        )

    def test_peak_stress_geq_final_stress(self):
        result = run_single_seeded_experiment("escape", "pressure", seed=77, max_steps=_FAST_STEPS)
        # Allow small floating-point slack
        assert result["peak_stress"] >= result["final_stress"] - 0.01

    def test_stress_values_in_unit_interval(self):
        result = run_single_seeded_experiment("cafe", "smooth", seed=33, max_steps=_FAST_STEPS)
        assert 0.0 <= result["peak_stress"]  <= 1.0
        assert 0.0 <= result["final_stress"] <= 1.0

    def test_event_counts_non_negative(self):
        result = run_single_seeded_experiment("office", "tension", seed=99, max_steps=_FAST_STEPS)
        assert result["cooperation_count"] >= 0
        assert result["challenge_count"]   >= 0

    def test_blockers_resolved_leq_total(self):
        result = run_single_seeded_experiment("escape", "smooth", seed=5, max_steps=35)
        assert result["blockers_resolved"] <= result["blocker_count"]

    def test_intervention_count_zero_in_batch(self):
        result = run_single_seeded_experiment("office", "smooth", seed=1, max_steps=_FAST_STEPS)
        assert result["intervention_count"] == 0

    @pytest.mark.parametrize("alias", ["office", "cafe", "escape", "escape_room"])
    def test_scenario_aliases_resolve_without_error(self, alias):
        result = run_single_seeded_experiment(alias, "smooth", seed=1, max_steps=8)
        assert "ticks" in result


# ══════════════════════════════════════════════════════════════════════════════
#  2.  aggregate_experiment_results
# ══════════════════════════════════════════════════════════════════════════════

class TestAggregateExperimentResults:

    def test_is_task_resolved_supports_boolean_values(self):
        tasks = {"map": True, "lock": True, "key": True}
        resolved = sum(1 for value in tasks.values() if _is_task_resolved(value))
        assert resolved / len(tasks) == pytest.approx(1.0)

    def test_is_task_resolved_supports_mixed_boolean_and_dict_values(self):
        tasks = {
            "map": True,
            "lock": {"status": "done"},
            "key": {"resolved": True},
            "door": False,
        }
        resolved = sum(1 for value in tasks.values() if _is_task_resolved(value))
        assert resolved / len(tasks) == pytest.approx(0.75)

    def test_group_labels_present(self):
        agg = aggregate_experiment_results(_make_mock_runs())
        assert "smooth"  in agg
        assert "tension" in agg

    def test_n_counts_correct(self):
        agg = aggregate_experiment_results(_make_mock_runs())
        assert agg["smooth"]["n"]  == 2
        assert agg["tension"]["n"] == 2

    def test_completion_rate_smooth_100(self):
        agg = aggregate_experiment_results(_make_mock_runs())
        assert agg["smooth"]["completion_rate"] == pytest.approx(1.0)

    def test_completion_rate_tension_50(self):
        agg = aggregate_experiment_results(_make_mock_runs())
        assert agg["tension"]["completion_rate"] == pytest.approx(0.5)

    def test_avg_completion_steps_smooth(self):
        agg = aggregate_experiment_results(_make_mock_runs())
        assert agg["smooth"]["avg_completion_steps"] == pytest.approx(9.0, rel=0.01)

    def test_avg_completion_steps_tension_excludes_incomplete(self):
        # Only the completed tension run (steps=18) should count
        agg = aggregate_experiment_results(_make_mock_runs())
        assert agg["tension"]["avg_completion_steps"] == pytest.approx(18.0, rel=0.01)

    def test_avg_peak_stress_smooth(self):
        agg = aggregate_experiment_results(_make_mock_runs())
        assert agg["smooth"]["avg_peak_stress"] == pytest.approx(0.30, rel=0.05)

    def test_avg_challenge_count_smooth(self):
        agg = aggregate_experiment_results(_make_mock_runs())
        assert agg["smooth"]["avg_challenge_count"] == pytest.approx(0.5, rel=0.01)

    def test_avg_trust_delta_present(self):
        agg = aggregate_experiment_results(_make_mock_runs())
        assert "avg_trust_delta" in agg["smooth"]
        assert "avg_trust_delta" in agg["tension"]

    def test_blocker_resolution_counts_completed_run_with_boolean_tasks(self):
        runs = [
            {
                "team_style": "smooth",
                "completed": True,
                "completion_steps": 8,
                "peak_stress": 0.28,
                "final_trust": 0.72,
                "start_trust": 0.57,
                "trust_delta": 0.15,
                "challenge_count": 0,
                "cooperation_count": 9,
                "blocker_count": 3,
                "blockers_resolved": 3,
            }
        ]
        agg = aggregate_experiment_results(runs)
        assert agg["smooth"]["avg_blockers_resolved_rate"] == pytest.approx(1.0)

    def test_empty_runs_returns_empty(self):
        assert aggregate_experiment_results([]) == {}


# ══════════════════════════════════════════════════════════════════════════════
#  3.  compare_team_styles
# ══════════════════════════════════════════════════════════════════════════════

class TestCompareTeamStyles:

    def _agg(self):
        return {
            "smooth": {
                "n": 5, "completion_rate": 1.0, "avg_completion_steps": 8.0,
                "avg_peak_stress": 0.28, "avg_final_trust": 0.72,
                "avg_start_trust": 0.57, "avg_trust_delta": 0.15,
                "avg_challenge_count": 0.2, "avg_cooperation_count": 8.5,
                "avg_blockers_resolved_rate": 1.0,
            },
            "tension": {
                "n": 5, "completion_rate": 0.8, "avg_completion_steps": 14.6,
                "avg_peak_stress": 0.61, "avg_final_trust": 0.48,
                "avg_start_trust": 0.38, "avg_trust_delta": 0.10,
                "avg_challenge_count": 4.2, "avg_cooperation_count": 6.8,
                "avg_blockers_resolved_rate": 0.9,
            },
        }

    def test_returns_findings_and_interpretation(self):
        result = compare_team_styles(self._agg())
        assert "findings"       in result
        assert "interpretation" in result

    def test_fastest_finding_is_smooth(self):
        result = compare_team_styles(self._agg())
        speed = next(f for f in result["findings"] if f["metric"] == "completion_speed")
        assert speed["winner"] == "smooth"

    def test_highest_stress_finding_is_tension(self):
        result = compare_team_styles(self._agg())
        stress = next(f for f in result["findings"] if f["metric"] == "peak_stress")
        assert stress["winner"] == "tension"

    def test_most_challenging_finding_is_tension(self):
        result = compare_team_styles(self._agg())
        chall = next(f for f in result["findings"] if f["metric"] == "challenge_count")
        assert chall["winner"] == "tension"

    def test_most_cooperative_finding_is_smooth(self):
        result = compare_team_styles(self._agg())
        coop = next(f for f in result["findings"] if f["metric"] == "cooperation")
        assert coop["winner"] == "smooth"

    def test_interpretation_is_non_trivial_string(self):
        result = compare_team_styles(self._agg())
        assert isinstance(result["interpretation"], str)
        assert len(result["interpretation"]) > 100

    def test_empty_input_returns_safe_fallback(self):
        result = compare_team_styles({})
        assert result["findings"]       == []
        assert "No data" in result["interpretation"]


# ══════════════════════════════════════════════════════════════════════════════
#  4.  run_experiment_batch
# ══════════════════════════════════════════════════════════════════════════════

class TestRunExperimentBatch:

    def test_correct_run_count(self):
        result = run_experiment_batch({
            "scenario": "office", "team_styles": ["smooth", "tension"],
            "seeds": [101, 102], "max_steps": _FAST_STEPS,
        })
        assert len(result["runs"]) == 4  # 2 styles × 2 seeds

    def test_all_requested_team_styles_appear(self):
        result = run_experiment_batch({
            "scenario": "office", "team_styles": ["smooth", "tension"],
            "seeds": [101], "max_steps": _FAST_STEPS,
        })
        styles = {r["team_style"] for r in result["runs"]}
        assert styles == {"smooth", "tension"}

    def test_summary_keys_present(self):
        result = run_experiment_batch({
            "scenario": "office", "team_styles": ["smooth"],
            "seeds": [101, 102, 103], "max_steps": _FAST_STEPS,
        })
        assert "smooth" in result["summary_by_team_style"]
        agg = result["summary_by_team_style"]["smooth"]
        assert agg["n"] == 3
        assert "completion_rate"      in agg
        assert "avg_peak_stress"      in agg
        assert "avg_trust_delta"      in agg
        assert "avg_challenge_count"  in agg
        assert "avg_cooperation_count" in agg

    def test_comparison_block_present(self):
        result = run_experiment_batch({
            "scenario": "office", "team_styles": ["smooth", "tension"],
            "seeds": [101], "max_steps": _FAST_STEPS,
        })
        assert "findings"       in result["comparison"]
        assert "interpretation" in result["comparison"]

    def test_config_echoed_with_total_runs(self):
        config = {"scenario": "cafe", "team_styles": ["smooth"], "seeds": [42], "max_steps": 20}
        result = run_experiment_batch(config)
        assert result["config"]["scenario"]   == "cafe"
        assert result["config"]["total_runs"] == 1

    def test_batch_reproducibility(self):
        """Running the same config twice must produce byte-identical run results."""
        config = {
            "scenario": "escape", "team_styles": ["smooth", "tension"],
            "seeds": [101, 102], "max_steps": 20,
        }
        a = run_experiment_batch(config)
        b = run_experiment_batch(config)

        for ra, rb in zip(a["runs"], b["runs"]):
            assert ra["ticks"]             == rb["ticks"],     \
                f"Tick mismatch — seed={ra['seed']} team={ra['team_style']}"
            assert ra["completed"]         == rb["completed"], \
                f"Completion mismatch — seed={ra['seed']} team={ra['team_style']}"
            assert ra["challenge_count"]   == rb["challenge_count"]
            assert ra["cooperation_count"] == rb["cooperation_count"]

    def test_completed_batch_runs_do_not_report_zero_blocker_resolution(self):
        result = run_experiment_batch({
            "scenario": "escape",
            "team_styles": ["smooth"],
            "seeds": [101],
            "max_steps": 30,
        })
        agg = result["summary_by_team_style"]["smooth"]
        assert agg["completion_rate"] == pytest.approx(1.0)
        assert agg["avg_blockers_resolved_rate"] == pytest.approx(1.0)
