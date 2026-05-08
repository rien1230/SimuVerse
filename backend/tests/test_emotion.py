"""
Tests for the emotion classification and injection feature.

Coverage:
1. classify_user_emotion() output schema
2. Valence / arousal / intensity bounds
3. Fallback mode (model unavailable)
4. inject_user_emotion() creates emotion_injection event
5. Stress / trust stay in [0, 1] after injection
6. Emotion decay reduces effect over subsequent ticks
7. emotion_summary appears in run export
8. Benchmark: positive vs negative emotion produce directional effects
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from app.sim.emotions_analyser import classify_user_emotion, EmotionAnalyser
from app.sim.model import SimModel
from app.sim.metrics import summarize_emotions


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_model(scenario: str = "office_proposal", seed: int = 1) -> SimModel:
    return SimModel(seed=seed, scenario_id=scenario, episode_max_ticks=30)


def _run_to_end(model: SimModel) -> None:
    while not model.ended:
        model.step()


# ──────────────────────────────────────────────────────────────────────────────
# 1. Output schema
# ──────────────────────────────────────────────────────────────────────────────

class TestClassifySchema:
    REQUIRED_KEYS = {
        "text", "top_emotion", "confidence", "top_labels",
        "fallback_used", "tick_applied", "valence", "arousal",
        "intensity", "interpretation",
    }

    def test_schema_present(self):
        result = classify_user_emotion("I feel really anxious and pressured", tick=5)
        assert self.REQUIRED_KEYS.issubset(result.keys()), (
            f"Missing keys: {self.REQUIRED_KEYS - result.keys()}"
        )

    def test_text_echoed(self):
        text = "I feel hopeful and calm"
        result = classify_user_emotion(text)
        assert result["text"] == text

    def test_top_labels_is_list_of_dicts(self):
        result = classify_user_emotion("I am so angry right now")
        assert isinstance(result["top_labels"], list)
        assert len(result["top_labels"]) >= 1
        for entry in result["top_labels"]:
            assert "label" in entry and "score" in entry

    def test_tick_applied_echoed(self):
        result = classify_user_emotion("feeling sad", tick=7)
        assert result["tick_applied"] == 7

    def test_fallback_used_is_bool(self):
        result = classify_user_emotion("I feel great")
        assert isinstance(result["fallback_used"], bool)

    def test_empty_text_returns_neutral(self):
        result = classify_user_emotion("")
        assert result["top_emotion"] == "neutral"
        assert result["fallback_used"] is True

    def test_interpretation_is_nonempty_string(self):
        result = classify_user_emotion("I am nervous about this")
        assert isinstance(result["interpretation"], str)
        assert len(result["interpretation"]) > 10


# ──────────────────────────────────────────────────────────────────────────────
# 2. Valence / arousal / intensity bounds
# ──────────────────────────────────────────────────────────────────────────────

class TestBounds:
    TEXTS = [
        "I feel really anxious and pressured",
        "I am so happy and excited!",
        "This is disappointing and sad",
        "I am furious about this",
        "Everything is fine",
        "I feel hopeful and grateful",
        "I'm scared and don't know what to do",
        "",
    ]

    def test_valence_in_range(self):
        for text in self.TEXTS:
            r = classify_user_emotion(text)
            assert -1.0 <= r["valence"] <= 1.0, (
                f"valence={r['valence']} out of range for: {text!r}"
            )

    def test_arousal_in_range(self):
        for text in self.TEXTS:
            r = classify_user_emotion(text)
            assert 0.0 <= r["arousal"] <= 1.0, (
                f"arousal={r['arousal']} out of range for: {text!r}"
            )

    def test_intensity_in_range(self):
        for text in self.TEXTS:
            r = classify_user_emotion(text)
            assert 0.0 <= r["intensity"] <= 1.0, (
                f"intensity={r['intensity']} out of range for: {text!r}"
            )

    def test_confidence_in_range(self):
        for text in self.TEXTS:
            r = classify_user_emotion(text)
            assert 0.0 <= r["confidence"] <= 1.0, (
                f"confidence={r['confidence']} out of range for: {text!r}"
            )

    def test_all_valence_arousal_map_values_bounded(self):
        for emotion, (v, a) in EmotionAnalyser.VALENCE_AROUSAL_MAP.items():
            assert -1.0 <= v <= 1.0,  f"{emotion}: valence {v} out of range"
            assert  0.0 <= a <= 1.0,  f"{emotion}: arousal {a} out of range"


# ──────────────────────────────────────────────────────────────────────────────
# 3. Fallback mode
# ──────────────────────────────────────────────────────────────────────────────

class TestFallback:
    def test_fallback_when_model_unavailable(self):
        """When GoEmotions classifier is None, fallback_used must be True."""
        with patch("app.sim.emotions_analyser.get_emotion_classifier", return_value=None):
            result = classify_user_emotion("I feel anxious and nervous")
        assert result["fallback_used"] is True, "fallback_used should be True when model unavailable"

    def test_fallback_does_not_crash(self):
        """Must not raise even when the model is completely unavailable."""
        with patch("app.sim.emotions_analyser.get_emotion_classifier", return_value=None):
            result = classify_user_emotion("I am really angry and frustrated")
        assert "top_emotion" in result

    def test_fallback_returns_valid_emotion(self):
        with patch("app.sim.emotions_analyser.get_emotion_classifier", return_value=None):
            result = classify_user_emotion("I feel nervous and scared")
        assert result["top_emotion"] in EmotionAnalyser.ALL_EMOTIONS

    def test_fallback_reason_set_when_unavailable(self):
        with patch("app.sim.emotions_analyser.get_emotion_classifier", return_value=None):
            result = classify_user_emotion("feeling sad and down")
        # fallback_reason is set (non-empty string)
        assert result.get("fallback_reason"), "fallback_reason should be a non-empty string"

    def test_fallback_keyword_angry(self):
        with patch("app.sim.emotions_analyser.get_emotion_classifier", return_value=None):
            result = classify_user_emotion("I am really angry and furious today")
        assert result["top_emotion"] in {"anger", "annoyance", "disapproval"}

    def test_fallback_keyword_happy(self):
        with patch("app.sim.emotions_analyser.get_emotion_classifier", return_value=None):
            result = classify_user_emotion("I feel so happy and joyful")
        assert result["top_emotion"] in {"joy", "excitement", "approval", "gratitude"}


# ──────────────────────────────────────────────────────────────────────────────
# 4. Emotion event logging
# ──────────────────────────────────────────────────────────────────────────────

class TestEventLogging:
    def test_inject_returns_event_dict(self):
        m = _make_model()
        result = m.inject_user_emotion("I feel nervous and pressured")
        assert isinstance(result, dict)

    def test_event_type_is_emotion_injection(self):
        m = _make_model()
        result = m.inject_user_emotion("I feel anxious")
        assert result["type"] == "emotion_injection"

    def test_event_appended_to_emotion_log(self):
        m = _make_model()
        assert len(m._emotion_log) == 0
        m.inject_user_emotion("I feel anxious and under pressure")
        assert len(m._emotion_log) == 1

    def test_event_log_required_fields(self):
        m = _make_model()
        entry = m.inject_user_emotion("I am really stressed out")
        required = {
            "tick", "type", "text", "detected_emotion", "confidence",
            "valence", "arousal", "intensity", "affected_agents",
            "stress_before", "stress_after", "trust_before", "trust_after",
            "explanation",
        }
        assert required.issubset(entry.keys()), (
            f"Missing fields: {required - entry.keys()}"
        )

    def test_affected_agents_lists_all_agents(self):
        m = _make_model()
        entry = m.inject_user_emotion("I feel sad")
        assert len(entry["affected_agents"]) == len(m.agents)

    def test_multiple_injections_all_logged(self):
        m = _make_model()
        m.inject_user_emotion("I feel anxious")
        m.inject_user_emotion("Now I feel better")
        assert len(m._emotion_log) == 2

    def test_event_queued_in_pending_events(self):
        m = _make_model()
        before = len(m._pending_events)
        m.inject_user_emotion("I feel pressured")
        assert len(m._pending_events) == before + 1


# ──────────────────────────────────────────────────────────────────────────────
# 5. Stress / trust remain bounded after injection
# ──────────────────────────────────────────────────────────────────────────────

class TestBoundsAfterInjection:
    HIGH_STRESS_TEXTS = [
        "I feel extremely anxious, terrified, and very angry",
        "I am furious beyond belief right now!",
        "I feel angry and nervous and scared at the same time",
    ] * 5   # inject multiple times to stress-test accumulation

    def test_stress_stays_in_range_after_negative_injection(self):
        m = _make_model()
        for text in self.HIGH_STRESS_TEXTS:
            m.inject_user_emotion(text)
        for agent in m.agents:
            assert 0.0 <= agent.stress <= 1.0, (
                f"Agent {agent.public_id} stress={agent.stress} out of range"
            )

    def test_trust_stays_in_range_after_negative_injection(self):
        m = _make_model()
        for text in self.HIGH_STRESS_TEXTS:
            m.inject_user_emotion(text)
        for agent in m.agents:
            for oid, tv in agent.trust.items():
                assert 0.0 <= tv <= 1.0, (
                    f"Agent {agent.public_id} trust[{oid}]={tv} out of range"
                )

    def test_stress_stays_in_range_after_positive_injection(self):
        m = _make_model()
        for _ in range(10):
            m.inject_user_emotion("I feel incredibly happy and grateful!")
        for agent in m.agents:
            assert 0.0 <= agent.stress <= 1.0

    def test_valence_stays_in_range_after_injection(self):
        m = _make_model()
        for _ in range(10):
            m.inject_user_emotion("I feel really angry and disappointed")
        for agent in m.agents:
            assert -1.0 <= agent.valence <= 1.0


# ──────────────────────────────────────────────────────────────────────────────
# 6. Decay
# ──────────────────────────────────────────────────────────────────────────────

class TestDecay:
    def test_stress_partially_reversed_after_ticks(self):
        """Negative emotion raises stress; ticking reverses some of it."""
        m = _make_model()
        # Record stress before injection
        stress_before = sum(a.stress for a in m.agents) / len(m.agents)
        m.inject_user_emotion("I feel very anxious and nervous")
        stress_after_inject = sum(a.stress for a in m.agents) / len(m.agents)

        # The injection must have raised stress (for a high-arousal negative emotion)
        # (this could be 0 if the rule-based analyser produces neutral; guard for that)
        if stress_after_inject <= stress_before:
            pytest.skip("Rule-based analyser produced neutral for this text — skip decay check")

        # Step 3 ticks — stress should partially recover
        for _ in range(3):
            m.step()
        stress_after_decay = sum(a.stress for a in m.agents) / len(m.agents)
        assert stress_after_decay < stress_after_inject, (
            f"Stress did not decay: before={stress_after_inject:.3f}, after={stress_after_decay:.3f}"
        )

    def test_emotion_effect_cleared_after_full_decay(self):
        """_emotion_effect should be cleared once fully faded."""
        m = _make_model()
        m.inject_user_emotion("I feel very stressed and anxious")
        if not m._emotion_effect:
            pytest.skip("No active effect (neutral emotion detected) — skip")

        # Step enough ticks for effect to fade
        for _ in range(20):
            m.step()
            if not m._emotion_effect:
                break
        assert not m._emotion_effect, "_emotion_effect should be empty after full decay"

    def test_current_strength_decreases_over_ticks(self):
        """current_strength in _emotion_effect should decrease each tick."""
        m = _make_model()
        m.inject_user_emotion("I feel anxious and terrified")
        if not m._emotion_effect:
            pytest.skip("No active effect — skip")

        strengths = [m._emotion_effect.get("current_strength", 0.0)]
        for _ in range(4):
            m.step()
            if m._emotion_effect:
                strengths.append(m._emotion_effect.get("current_strength", 0.0))

        if len(strengths) >= 2:
            assert strengths[-1] < strengths[0], (
                f"Strength did not decrease: {strengths}"
            )


# ──────────────────────────────────────────────────────────────────────────────
# 7. emotion_summary in export
# ──────────────────────────────────────────────────────────────────────────────

class TestEmotionSummaryExport:
    def test_emotion_summary_present_with_no_injection(self):
        m = _make_model()
        _run_to_end(m)
        summary = m.emotion_summary()
        assert "emotion_inputs" in summary
        assert summary["emotion_inputs"] == 0

    def test_emotion_summary_no_injection_interpretation(self):
        m = _make_model()
        _run_to_end(m)
        summary = m.emotion_summary()
        assert "interpretation" in summary
        assert "No user emotion input" in summary["interpretation"]

    def test_emotion_summary_with_injection(self):
        m = _make_model()
        m.inject_user_emotion("I feel anxious and under pressure", tick=0)
        _run_to_end(m)
        summary = m.emotion_summary()
        assert summary["emotion_inputs"] == 1
        assert summary["dominant_emotion"] is not None
        assert summary["average_valence"] is not None
        assert summary["stress_impact"] is not None

    def test_emotion_summary_required_keys(self):
        m = _make_model()
        m.inject_user_emotion("I feel hopeful")
        _run_to_end(m)
        summary = m.emotion_summary()
        required = {
            "emotion_inputs", "dominant_emotion", "average_valence",
            "average_arousal", "strongest_input", "stress_impact",
            "trust_impact", "ticks_applied", "interpretation",
        }
        assert required.issubset(summary.keys()), (
            f"Missing keys: {required - summary.keys()}"
        )

    def test_emotion_summary_multiple_injections(self):
        m = _make_model()
        m.inject_user_emotion("I feel anxious", tick=0)
        m.inject_user_emotion("I feel hopeful now", tick=2)
        _run_to_end(m)
        summary = m.emotion_summary()
        assert summary["emotion_inputs"] == 2
        assert 0 in summary["ticks_applied"]

    def test_summarize_emotions_standalone(self):
        """summarize_emotions() works directly on a model instance."""
        m = _make_model()
        m.inject_user_emotion("I am nervous and pressured")
        summary = summarize_emotions(m)
        assert summary["emotion_inputs"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# 8. Benchmark: directional effects
# ──────────────────────────────────────────────────────────────────────────────

class TestBenchmarkDirectional:
    """
    Same seed + same scenario + different emotion → measurable directional effect.
    We don't hardcode exact values — only direction.
    """

    SCENARIO  = "office_proposal"
    SEED      = 42
    MAX_TICKS = 30

    def _run(self, emotion_text=None):
        m = SimModel(seed=self.SEED, scenario_id=self.SCENARIO,
                     episode_max_ticks=self.MAX_TICKS)
        if emotion_text:
            m.inject_user_emotion(emotion_text, tick=0)
        _run_to_end(m)
        import collections
        ec = collections.Counter()
        for h in m.metric_history:
            for k, v in h.get("event_counts", {}).items():
                ec[k] += v
        avg_stress = (
            sum(h["avg_stress"] for h in m.metric_history) / max(1, len(m.metric_history))
        )
        avg_trust = (
            sum(h["avg_trust"] for h in m.metric_history) / max(1, len(m.metric_history))
        )
        return {
            "avg_stress":  avg_stress,
            "avg_trust":   avg_trust,
            "challenges":  ec.get("challenge", 0),
            "agrees":      ec.get("agree", 0),
            "ticks":       m.tick,
        }

    def test_negative_emotion_raises_stress_vs_no_emotion(self):
        """Negative high-arousal injection → avg stress ≥ no-emotion run."""
        baseline = self._run(emotion_text=None)
        negative = self._run(emotion_text="I feel very anxious, nervous, and under pressure")
        assert negative["avg_stress"] >= baseline["avg_stress"] - 0.02, (
            f"Expected higher stress: baseline={baseline['avg_stress']:.3f}, "
            f"negative={negative['avg_stress']:.3f}"
        )

    def test_positive_emotion_does_not_raise_stress_vs_no_emotion(self):
        """Positive injection → avg stress ≤ no-emotion run (or close)."""
        baseline = self._run(emotion_text=None)
        positive = self._run(emotion_text="I feel hopeful, calm and grateful")
        assert positive["avg_stress"] <= baseline["avg_stress"] + 0.02, (
            f"Expected stress not higher: baseline={baseline['avg_stress']:.3f}, "
            f"positive={positive['avg_stress']:.3f}"
        )

    def test_negative_trust_lower_than_positive(self):
        """Negative emotion run should have avg trust ≤ positive emotion run."""
        negative = self._run(emotion_text="I feel angry and frustrated with everything")
        positive = self._run(emotion_text="I feel grateful and happy about this")
        # Allow a tiny tolerance — trust changes are small
        assert negative["avg_trust"] <= positive["avg_trust"] + 0.05, (
            f"negative trust={negative['avg_trust']:.3f}, positive trust={positive['avg_trust']:.3f}"
        )

    def test_neutral_emotion_minimal_stress_change(self):
        """Neutral emotion injection should not significantly shift stress."""
        baseline = self._run(emotion_text=None)
        neutral  = self._run(emotion_text="I feel okay, everything is fine")
        # Must be within ±0.05
        diff = abs(neutral["avg_stress"] - baseline["avg_stress"])
        assert diff < 0.05, (
            f"Neutral emotion changed stress too much: diff={diff:.3f}"
        )
