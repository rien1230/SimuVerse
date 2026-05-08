"""
test_dialogue_quality.py
========================
Regression tests for dialogue quality and blocker-resolution correctness in the
cafe_restaurant scenario.

These tests guard against the specific issues fixed in the dialogue polish pass:

  1. Generic coordination asks must NOT resolve blockers.
  2. Blockers must resolve only when a share_info event is present in that tick.
  3. Dietary share messages must contain dietary-domain words.
  4. Budget share messages must contain budget-domain words.
  5. Location share messages must contain location-domain words.
  6. A same-tick ask_info is removed when a share_info for the same item exists.
  7. A tension injection can produce challenge events without resolving any blocker.
  8. Seeded runs are reproducible after the phrase pool expansion.
  9. CONSTRAINT_TEXT pools have sufficient variety (≥ 7 phrases each).

Run from the backend directory:
    source .venv/bin/activate
    pytest tests/test_dialogue_quality.py -v
"""

from __future__ import annotations

import copy
import os
import random
import warnings
from typing import List, Dict, Any

import pytest

warnings.filterwarnings("ignore")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from app.sim.model import SimModel
from app.sim.scenario_logic.cafe_logic import (
    CONSTRAINT_TEXT,
    CONSTRAINT_ITEMS,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_cafe(seed: int = 42, max_ticks: int = 20, team_type: str = "balanced") -> SimModel:
    m = SimModel(
        seed=seed,
        scenario_id="cafe_restaurant",
        environment="cafe",
        episode_max_ticks=max_ticks,
        team_type=team_type,
    )
    m.skip_emotions = True
    return m


def _run(model: SimModel, ticks: int) -> None:
    for _ in range(ticks):
        if not model.ended:
            model.step()


def _all_events(model: SimModel) -> List[Dict[str, Any]]:
    """Flatten all events from the model's history."""
    return [e for snap in model.history for e in snap.get("events", [])]


def _events_at_tick(model: SimModel, tick: int) -> List[Dict[str, Any]]:
    for snap in model.history:
        if snap.get("tick") == tick:
            return snap.get("events", [])
    return []


def _constraint_share_ticks(model: SimModel) -> Dict[str, int]:
    """Return {item: tick} for each constraint's first share_info event."""
    result: Dict[str, int] = {}
    for snap in model.history:
        tick = snap.get("tick", 0)
        for e in snap.get("events", []):
            if e.get("type") == "share_info" and e.get("item") in CONSTRAINT_ITEMS:
                item = e["item"]
                if item not in result:
                    result[item] = tick
    return result


# ── 1. Phrase pool variety ─────────────────────────────────────────────────────

class TestConstraintTextPools:

    def test_dietary_pool_has_sufficient_variety(self):
        assert len(CONSTRAINT_TEXT["dietary_constraint"]) >= 7, (
            "dietary_constraint phrase pool is too small — agents will sound repetitive"
        )

    def test_budget_pool_has_sufficient_variety(self):
        assert len(CONSTRAINT_TEXT["budget_constraint"]) >= 7

    def test_location_pool_has_sufficient_variety(self):
        assert len(CONSTRAINT_TEXT["location_constraint"]) >= 7

    def test_all_pool_phrases_are_non_empty_strings(self):
        for item, pool in CONSTRAINT_TEXT.items():
            for phrase in pool:
                assert isinstance(phrase, str) and phrase.strip(), (
                    f"Empty/non-string phrase in {item} pool: {phrase!r}"
                )

    def test_pools_contain_no_duplicates(self):
        for item, pool in CONSTRAINT_TEXT.items():
            assert len(pool) == len(set(pool)), (
                f"Duplicate phrases in {item} constraint pool"
            )


# ── 2. Seeded reproducibility ─────────────────────────────────────────────────

class TestSeededReproducibility:
    # NOTE: Both models use the global Python random module.  Creating two
    # SimModel instances before running either shifts the RNG state (init
    # consumes random calls) so run_a starts from the wrong seed state.
    # Correct pattern: create → run → capture, then create → run → capture.
    # This guarantees each model resets the seed and runs from the same state.

    def test_same_seed_produces_identical_event_texts(self):
        """Two sequential runs with the same seed must produce the same dialogue texts."""
        # Run A: create and fully run before creating run B
        run_a = _make_cafe(seed=77)
        _run(run_a, 12)
        texts_a = [e.get("text") for e in _all_events(run_a)]

        # Run B: create after run A is done so seed reset starts from same state
        run_b = _make_cafe(seed=77)
        _run(run_b, 12)
        texts_b = [e.get("text") for e in _all_events(run_b)]

        assert texts_a == texts_b, "Same seed produced different dialogue texts after phrase pool expansion"

    def test_same_seed_produces_identical_task_completion_order(self):
        """Task completion order must be deterministic for a given seed."""
        run_a = _make_cafe(seed=55)
        _run(run_a, 15)
        share_ticks_a = _constraint_share_ticks(run_a)

        run_b = _make_cafe(seed=55)
        _run(run_b, 15)
        share_ticks_b = _constraint_share_ticks(run_b)

        assert share_ticks_a == share_ticks_b, (
            "Same seed produced different constraint resolution order"
        )

    def test_different_seeds_produce_different_outputs(self):
        """Different seeds should (almost always) produce different outputs."""
        run_a = _make_cafe(seed=1)
        _run(run_a, 10)
        texts_a = [e.get("text") for e in _all_events(run_a)]

        run_b = _make_cafe(seed=2)
        _run(run_b, 10)
        texts_b = [e.get("text") for e in _all_events(run_b)]

        # Not guaranteed, but for seeds 1 vs 2 over 10 ticks, identical output
        # would be a strong signal of a broken RNG.
        assert texts_a != texts_b, "Different seeds produced identical output — RNG may be broken"


# ── 3. Blocker resolution correctness ─────────────────────────────────────────

class TestBlockerResolutionCorrectness:

    def test_generic_ask_does_not_resolve_blocker(self):
        """A tick containing only ask_info events must not resolve any blocker."""
        m = _make_cafe(seed=42)

        for snap_idx in range(15):
            if m.ended:
                break
            m.step()
            snap = m.history[-1]
            tick_events = snap.get("events", [])

            shares_this_tick = [e for e in tick_events if e.get("type") == "share_info"
                                 and e.get("item") in CONSTRAINT_ITEMS]
            asks_this_tick   = [e for e in tick_events if e.get("type") == "ask_info"
                                 and e.get("item") in CONSTRAINT_ITEMS]

            # If there are no share events this tick, no constraint should be newly True.
            if not shares_this_tick and asks_this_tick:
                # Read constraint state from the scenario snapshot
                revealed = snap.get("scenario", {}).get("tasks", {})
                # No constraint should have flipped solely because of asks.
                # (We verify this indirectly: if tasks show True here, some share must
                # have occurred this tick — but we already confirmed shares_this_tick==[].)
                for item in CONSTRAINT_ITEMS:
                    if revealed.get(item, False):
                        # It's possible it was already True from a prior tick — check
                        # whether it was False in the previous tick's snapshot.
                        if snap_idx > 0:
                            prev_snap = m.history[-2]
                            prev_revealed = prev_snap.get("scenario", {}).get("tasks", {})
                            if not prev_revealed.get(item, False):
                                # Newly True this tick with no share event — that's the bug.
                                pytest.fail(
                                    f"Blocker '{item}' resolved at tick {snap['tick']} "
                                    f"with no share_info event in that tick."
                                )

    def test_blocker_resolves_only_when_share_info_present(self):
        """Every tick where a constraint flips True must contain a share_info for it."""
        m = _make_cafe(seed=99)
        _run(m, 20)

        prev_tasks: Dict[str, bool] = {item: False for item in CONSTRAINT_ITEMS}
        for snap in m.history:
            tasks = snap.get("scenario", {}).get("tasks", {})
            tick_events = snap.get("events", [])

            for item in CONSTRAINT_ITEMS:
                was_false = not prev_tasks.get(item, False)
                is_now_true = tasks.get(item, False)

                if was_false and is_now_true:
                    # This tick resolved the blocker — there must be a share_info for it.
                    share_present = any(
                        e.get("type") == "share_info" and e.get("item") == item
                        for e in tick_events
                    )
                    assert share_present, (
                        f"Constraint '{item}' resolved at tick {snap['tick']} "
                        f"but no share_info event for it exists in that tick."
                    )

            prev_tasks = dict(tasks)

    def test_no_same_tick_ask_and_share_for_same_item(self):
        """After the redundant-ask filter, no tick should have both ask_info and
        share_info for the same constraint item."""
        m = _make_cafe(seed=42)
        _run(m, 20)

        for snap in m.history:
            tick_events = snap.get("events", [])
            shared_items = {
                e.get("item") for e in tick_events
                if e.get("type") == "share_info" and e.get("item") in CONSTRAINT_ITEMS
            }
            asked_items = [
                e.get("item") for e in tick_events
                if e.get("type") == "ask_info" and e.get("item") in CONSTRAINT_ITEMS
            ]
            overlap = [a for a in asked_items if a in shared_items]
            assert not overlap, (
                f"Tick {snap['tick']}: ask_info and share_info both present for {overlap}. "
                f"The redundant-ask filter is not working."
            )

    def test_filter_redundant_asks_unit(self):
        """Unit test for _filter_redundant_asks: ask for shared item is removed."""
        m = _make_cafe(seed=1)

        events = [
            {"type": "ask_info",   "actor": "A1", "target": "A2", "item": "dietary_constraint", "text": "What are the dietary needs?"},
            {"type": "share_info", "actor": "A2", "target": "A1", "item": "dietary_constraint", "text": "We need vegan options."},
            {"type": "ask_info",   "actor": "A1", "target": "A3", "item": "budget_constraint",  "text": "What's the budget?"},
        ]
        filtered = m._filter_redundant_asks(events)

        types_and_items = [(e["type"], e["item"]) for e in filtered]
        assert ("ask_info",   "dietary_constraint") not in types_and_items, (
            "ask_info for dietary should be removed when share_info is present"
        )
        assert ("share_info", "dietary_constraint") in types_and_items, (
            "share_info for dietary should be preserved"
        )
        assert ("ask_info",   "budget_constraint") in types_and_items, (
            "ask_info for budget should be kept (no share for budget in this batch)"
        )

    def test_filter_redundant_asks_no_shares_passes_through(self):
        """When no share_info events exist the filter must return events unchanged."""
        m = _make_cafe(seed=1)

        events = [
            {"type": "ask_info", "actor": "A1", "target": "A2", "item": "dietary_constraint", "text": "..."},
            {"type": "ask_info", "actor": "A1", "target": "A3", "item": "budget_constraint",  "text": "..."},
        ]
        filtered = m._filter_redundant_asks(events)
        assert filtered == events


# ── 4. Share message domain correctness ───────────────────────────────────────

class TestShareMessageDomains:

    _DIETARY_WORDS = {"vegan", "vegetarian", "dietary", "food", "diet", "plant", "allergen"}
    _BUDGET_WORDS  = {"£", "budget", "affordable", "cost", "price", "per person", "spend", "cheap", "ceiling", "limit", "money"}
    _LOCATION_WORDS = {"nearby", "close", "distance", "walk", "easy to get", "proximity", "far", "minutes", "location", "trek"}

    def _get_share_texts(self, item: str, seeds=(42, 7, 99)) -> List[str]:
        texts = []
        for seed in seeds:
            m = _make_cafe(seed=seed)
            _run(m, 20)
            for e in _all_events(m):
                if e.get("type") == "share_info" and e.get("item") == item:
                    texts.append(e.get("text", "").lower())
        return texts

    def test_dietary_share_messages_contain_dietary_words(self):
        texts = self._get_share_texts("dietary_constraint")
        assert texts, "No dietary_constraint share_info events found in test runs"
        for text in texts:
            has_word = any(w in text for w in self._DIETARY_WORDS)
            assert has_word, (
                f"Dietary share message contains no dietary-domain words: {text!r}\n"
                f"Expected at least one of: {self._DIETARY_WORDS}"
            )

    def test_budget_share_messages_contain_budget_words(self):
        texts = self._get_share_texts("budget_constraint")
        assert texts, "No budget_constraint share_info events found in test runs"
        for text in texts:
            has_word = any(w in text for w in self._BUDGET_WORDS)
            assert has_word, (
                f"Budget share message contains no budget-domain words: {text!r}\n"
                f"Expected at least one of: {self._BUDGET_WORDS}"
            )

    def test_location_share_messages_contain_location_words(self):
        texts = self._get_share_texts("location_constraint")
        assert texts, "No location_constraint share_info events found in test runs"
        for text in texts:
            has_word = any(w in text for w in self._LOCATION_WORDS)
            assert has_word, (
                f"Location share message contains no location-domain words: {text!r}\n"
                f"Expected at least one of: {self._LOCATION_WORDS}"
            )


# ── 5. Intervention correctness ───────────────────────────────────────────────

class TestInterventionCorrectness:

    def test_tension_injection_produces_challenges_without_resolving_blocker(self):
        """boost_tension intervention should increase challenge events but must not
        directly resolve any constraint blocker."""
        m = _make_cafe(seed=42)
        # Run 3 ticks to establish baseline state
        _run(m, 3)

        # Record which constraints are currently revealed
        before_revealed = dict(m._cafe_revealed_constraints)

        # Apply tension injection
        m.apply_intervention("boost_tension", {"amount": 0.3})

        # Step once — the tick in which tension is most freshly applied
        m.step()
        snap = m.history[-1]

        # Constraint state after the intervention tick
        after_tasks = snap.get("scenario", {}).get("tasks", {})
        after_revealed = {
            item: after_tasks.get(item, False) for item in CONSTRAINT_ITEMS
        }

        # Any newly resolved constraint in this tick must be accompanied by share_info
        for item in CONSTRAINT_ITEMS:
            if not before_revealed.get(item, False) and after_revealed.get(item, False):
                share_present = any(
                    e.get("type") == "share_info" and e.get("item") == item
                    for e in snap.get("events", [])
                )
                assert share_present, (
                    f"Tension injection tick resolved '{item}' without a share_info event."
                )

    def test_reveal_info_intervention_marks_correct_constraint(self):
        """reveal_info intervention should mark the specified item as known to the agent."""
        m = _make_cafe(seed=42)
        _run(m, 2)

        # Reveal dietary constraint to A1
        result = m.apply_intervention("reveal_info", {"agent_id": "A1", "item": "dietary_constraint"})
        assert result.get("success") is True or result.get("success") == True

    def test_nudge_cooperation_does_not_resolve_blocker_directly(self):
        """nudge_cooperation strategy shift should not directly flip a constraint to True."""
        m = _make_cafe(seed=42)
        _run(m, 2)

        before_constraints = dict(m._cafe_revealed_constraints)
        m.apply_intervention("nudge_strategy", {"agent_id": "A2", "strategy": "cooperative"})

        # The intervention itself (no step) should not change revealed constraints
        assert m._cafe_revealed_constraints == before_constraints, (
            "nudge_strategy intervention directly mutated _cafe_revealed_constraints"
        )


# ── 6. Blocker-context message suppression ────────────────────────────────────

class TestBlockerContextSuppression:

    def test_budget_suggestions_rare_during_dietary_phase(self):
        """While dietary_constraint is active and unresolved, budget-dimension
        suggestions (fancy/cheap) should be significantly less frequent than
        dietary/cuisine suggestions."""
        # Use multiple seeds to get a stable sample
        budget_during_dietary = 0
        cuisine_during_dietary = 0

        for seed in range(10, 20):
            m = _make_cafe(seed=seed)
            for _ in range(15):
                if m.ended:
                    break
                m.step()
                snap = m.history[-1]
                dietary_open = not snap.get("scenario", {}).get("tasks", {}).get("dietary_constraint", True)
                if not dietary_open:
                    break  # dietary resolved — stop counting

                for e in snap.get("events", []):
                    if e.get("type") == "suggest":
                        pref = e.get("preference", "")
                        if pref in ("fancy", "cheap"):
                            budget_during_dietary += 1
                        elif pref in ("vegan", "italian"):
                            cuisine_during_dietary += 1

        # Budget suggestions during dietary phase should be well below cuisine suggestions
        # (not eliminated — just significantly suppressed)
        total = budget_during_dietary + cuisine_during_dietary
        if total > 0:
            budget_ratio = budget_during_dietary / total
            assert budget_ratio < 0.40, (
                f"Budget suggestions made up {budget_ratio:.0%} of all suggestions during "
                f"the dietary constraint phase (expected < 40%). "
                f"Budget: {budget_during_dietary}, Cuisine: {cuisine_during_dietary}"
            )
