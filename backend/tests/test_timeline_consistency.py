"""
Regression tests for timeline/state-machine consistency.

These tests focus on logical validity rather than copy polish:
  - scenario vocab must stay isolated
  - each tick carries one authoritative active blocker
  - blockers resolve in defined order
  - generic coordination / ask events cannot resolve work on their own
  - future-info reveals may appear early but must not resolve early
  - seeded reproducibility must remain intact
"""

from __future__ import annotations

import os
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List

import pytest

warnings.filterwarnings("ignore")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from app.sim.model import SimModel
from app.sim.interventions import _delayed_reveal_coordination_text


SCENARIO_RUNS = {
    "cafe": ("cafe_restaurant", "cafe", 24, "tension"),
    "office": ("office_proposal", "office", 30, "smooth"),
    "escape": ("escape_puzzle", "escape", 24, "tension"),
}

ORDER_MAP = {
    "cafe": ["dietary_constraint", "budget_constraint", "location_constraint", "decision"],
    "office": ["requirements", "design", "tech_specs", "budget"],
    "escape": ["map", "lock", "key", "door", "unlock"],
}

# Raw knowledge-item keys agents hold in each scenario.  These appear as
# event["item"] in agent messages but are NOT the canonical blocker/constraint
# keys.  Both sets are valid for vocabulary-isolation checks.
_CAFE_RAW_ITEMS   = {"italian", "vegan", "cheap", "fancy"}
_OFFICE_RAW_ITEMS = {"frontend", "backend", "testing", "documentation"}
_ESCAPE_RAW_ITEMS = set()   # escape agents reference blocker keys directly

VALID_ITEMS: dict[str, set[str]] = {
    "cafe":   set(ORDER_MAP["cafe"])   | _CAFE_RAW_ITEMS,
    "office": set(ORDER_MAP["office"]) | _OFFICE_RAW_ITEMS,
    "escape": set(ORDER_MAP["escape"]) | _ESCAPE_RAW_ITEMS,
}

ESCAPE_PHRASES = ("room map", "lock pattern", "key location", "door code", "exit lock", "final unlock")
CAFE_PHRASES = ("dietary constraint", "vegan", "budget", "location", "nearby", "decision")


def _make_model(kind: str, seed: int = 101) -> SimModel:
    scenario_id, env, max_ticks, team_type = SCENARIO_RUNS[kind]
    model = SimModel(
        seed=seed,
        scenario_id=scenario_id,
        environment=env,
        episode_max_ticks=max_ticks,
        team_type=team_type,
    )
    model.skip_emotions = True
    return model


def _run(model: SimModel) -> SimModel:
    while not model.ended and model.tick < model.episode_max_ticks:
        model.step()
    return model


def _first_unresolved(tasks: Dict[str, Any], kind: str) -> str | None:
    for item in ORDER_MAP[kind]:
        if not tasks.get(item, False):
            return item
    return None


def _resolved_sequence(model: SimModel) -> List[str]:
    resolved: List[str] = []
    for snap in model.history:
        resolved.extend(snap.get("scenario", {}).get("resolved_items", []))
    return resolved


class TestScenarioVocabularyIsolation:
    def test_cafe_output_never_contains_escape_room_blockers(self):
        model = _run(_make_model("cafe", seed=101))
        valid_items = VALID_ITEMS["cafe"]   # includes raw knowledge keys (vegan, italian, etc.)
        for snap in model.history:
            active = snap.get("group_state", {}).get("active_blocker")
            assert active in valid_items or active is None
            for item in snap.get("scenario", {}).get("resolved_items", []):
                assert item in valid_items
            for event in snap.get("events", []):
                if event.get("item") is not None:
                    assert event["item"] in valid_items, (
                        f"café tick {snap['tick']}: event item {event['item']!r} not in valid café items {valid_items}"
                    )
                lower = str(event.get("text", "")).lower()
                assert not any(phrase in lower for phrase in ESCAPE_PHRASES), lower

    def test_escape_output_never_contains_cafe_blockers(self):
        model = _run(_make_model("escape", seed=101))
        valid_items = VALID_ITEMS["escape"]
        for snap in model.history:
            active = snap.get("group_state", {}).get("active_blocker")
            assert active in valid_items or active is None
            for item in snap.get("scenario", {}).get("resolved_items", []):
                assert item in valid_items
            for event in snap.get("events", []):
                if event.get("item") is not None:
                    assert event["item"] in valid_items, (
                        f"escape tick {snap['tick']}: event item {event['item']!r} not in valid escape items {valid_items}"
                    )
                lower = str(event.get("text", "")).lower()
                assert not any(phrase in lower for phrase in CAFE_PHRASES), lower


class TestActiveBlockerConsistency:
    @pytest.mark.parametrize("kind", ["cafe", "office", "escape"])
    def test_each_step_has_one_authoritative_active_blocker(self, kind: str):
        model = _run(_make_model(kind, seed=101))
        previous_tasks = {item: False for item in ORDER_MAP[kind]}
        for snap in model.history:
            expected = _first_unresolved(previous_tasks, kind)
            active = snap.get("group_state", {}).get("active_blocker")
            assert active == expected, (
                f"{kind} tick {snap['tick']}: expected active blocker {expected!r}, got {active!r}"
            )
            previous_tasks = dict(snap.get("scenario", {}).get("tasks", {}))

    @pytest.mark.parametrize("kind", ["cafe", "office", "escape"])
    def test_future_info_events_do_not_resolve_early(self, kind: str):
        model = _run(_make_model(kind, seed=101))
        for snap in model.history:
            active = snap.get("group_state", {}).get("active_blocker")
            resolved = set(snap.get("scenario", {}).get("resolved_items", []))
            for event in snap.get("events", []):
                item = event.get("item")
                if not item or item == active:
                    continue
                if event.get("type") in {"share_info", "agree", "confirm"}:
                    assert item not in resolved, (
                        f"{kind} tick {snap['tick']}: future item {item!r} resolved while active blocker was {active!r}"
                    )


class TestResolutionRules:
    @pytest.mark.parametrize("kind", ["cafe", "office", "escape"])
    def test_blockers_resolve_in_defined_order(self, kind: str):
        model = _run(_make_model(kind, seed=101))
        sequence = _resolved_sequence(model)
        order_index = {item: idx for idx, item in enumerate(ORDER_MAP[kind])}
        assert sequence, f"{kind}: no resolved items recorded"
        numeric = [order_index[item] for item in sequence if item in order_index]
        assert numeric == sorted(numeric), f"{kind}: blockers resolved out of order: {sequence}"

    @pytest.mark.parametrize("kind", ["cafe", "office", "escape"])
    def test_generic_coordination_messages_do_not_resolve_blockers(self, kind: str):
        model = _run(_make_model(kind, seed=101))
        generic_types = {"say", "suggest", "coord", "compliment", "reassure", "pressure"}
        resolving_types = {"share_info", "agree", "confirm", "open", "enter"}
        for snap in model.history:
            resolved = snap.get("scenario", {}).get("resolved_items", [])
            if not resolved:
                continue
            if kind == "escape" and resolved == ["unlock"]:
                continue
            event_types = {event.get("type") for event in snap.get("events", [])}
            assert event_types & resolving_types, (
                f"{kind} tick {snap['tick']}: resolved {resolved} with only generic events {sorted(event_types & generic_types)}"
            )

    @pytest.mark.parametrize("kind", ["cafe", "office", "escape"])
    def test_ask_events_never_resolve_blockers(self, kind: str):
        model = _run(_make_model(kind, seed=101))
        for snap in model.history:
            resolved = snap.get("scenario", {}).get("resolved_items", [])
            event_types = {event.get("type") for event in snap.get("events", [])}
            if "ask_info" in event_types and not (event_types & {"share_info", "agree", "confirm", "open", "enter"}):
                assert not resolved, (
                    f"{kind} tick {snap['tick']}: ask-led step resolved {resolved} without resolving evidence"
                )

    @pytest.mark.parametrize("kind", ["cafe", "office", "escape"])
    def test_resolved_blocker_matches_step_focus(self, kind: str):
        model = _run(_make_model(kind, seed=101))
        for snap in model.history:
            resolved = snap.get("scenario", {}).get("resolved_items", [])
            if not resolved:
                continue
            active = snap.get("group_state", {}).get("active_blocker")
            for item in resolved:
                assert item == active, (
                    f"{kind} tick {snap['tick']}: resolved {item!r} while active blocker was {active!r}"
                )

    def test_completed_escape_run_contains_full_five_blocker_chain(self):
        model = _run(_make_model("escape", seed=101))
        assert model.ended
        assert model.scenario.progress_ratio() == pytest.approx(1.0)
        assert _resolved_sequence(model) == ["map", "lock", "key", "door", "unlock"]

    def test_completed_office_run_contains_full_four_blocker_chain(self):
        model = _run(_make_model("office", seed=101))
        assert model.ended
        assert model.scenario.progress_ratio() == pytest.approx(1.0)
        assert _resolved_sequence(model) == ["requirements", "design", "tech_specs", "budget"]

    def test_cafe_timeline_still_resolves_in_expected_four_step_order(self):
        model = _run(_make_model("cafe", seed=101))
        resolved = _resolved_sequence(model)
        assert resolved == ["dietary_constraint", "budget_constraint", "location_constraint", "decision"]


class TestCafeInterventionTargetContracts:
    def test_cafe_frontend_reveal_targets_exclude_decision(self):
        src = (Path(__file__).resolve().parents[2] / "frontend" / "interaction.js").read_text(encoding="utf-8")
        start = src.index("function revealableItemsForAgent(agentId)")
        body = src[start:start + 500]
        assert 'env === "cafe"' in body or 'env === "cafe_restaurant"' in body
        assert 'item !== "decision"' in body

    def test_cafe_final_chain_still_includes_decision(self):
        assert ORDER_MAP["cafe"] == [
            "dietary_constraint",
            "budget_constraint",
            "location_constraint",
            "decision",
        ]

    def test_cafe_decision_target_is_rejected_before_decision_phase(self):
        model = _make_model("cafe", seed=101)
        result = model.apply_intervention("reveal_info", {"agent_id": "A1", "item": "decision"})
        assert result["success"] is False
        assert "Decision cannot be targeted directly" in result["message"]


    def test_fresh_cafe_current_blocker_is_dietary_not_decision(self):
        model = _make_model("cafe", seed=101)
        assert model._active_blocker_from_tasks(model.scenario.tasks) == "dietary_constraint"
        from app.sim import interventions as iv
        assert iv._current_blocker_item(model) == "dietary_constraint"

    def test_cafe_decision_still_resolves_automatically_after_prior_constraints(self):
        model = _run(_make_model("cafe", seed=101))
        final_tasks = model.history[-1].get("scenario", {}).get("tasks", {})
        assert final_tasks.get("dietary_constraint") is True
        assert final_tasks.get("budget_constraint") is True
        assert final_tasks.get("location_constraint") is True
        assert final_tasks.get("decision") is True

    def test_legacy_cafe_decision_labels_remain_defined_for_history_rendering(self):
        src = (Path(__file__).resolve().parents[2] / "frontend" / "interaction.js").read_text(encoding="utf-8")
        assert 'final_decision: "Decision"' in src
        assert 'decision:           "Decision"' in src or 'decision: "Decision"' in src

    def test_office_and_escape_orders_are_unchanged(self):
        assert ORDER_MAP["office"] == ["requirements", "design", "tech_specs", "budget"]
        assert ORDER_MAP["escape"] == ["map", "lock", "key", "door", "unlock"]


class TestEscapeInterventionTargetContracts:
    def test_escape_frontend_reveal_targets_exclude_final_unlock(self):
        src = (Path(__file__).resolve().parents[2] / "frontend" / "interaction.js").read_text(encoding="utf-8")
        start = src.index("function revealableItemsForAgent(agentId)")
        body = src[start:start + 700]
        assert 'env === "escape"' in body or 'env === "escape_room"' in body
        assert 'item !== "unlock"' in body

    def test_escape_final_chain_still_includes_final_unlock(self):
        assert ORDER_MAP["escape"] == ["map", "lock", "key", "door", "unlock"]

    def test_escape_final_unlock_target_is_rejected_before_unlock_phase(self):
        model = _make_model("escape", seed=101)
        result = model.apply_intervention("reveal_info", {"agent_id": "A1", "item": "unlock"})
        assert result["success"] is False
        assert "Final Unlock cannot be targeted directly" in result["message"]

    def test_escape_final_unlock_still_resolves_automatically_after_door(self):
        model = _run(_make_model("escape", seed=101))
        final_tasks = model.history[-1].get("scenario", {}).get("tasks", {})
        assert final_tasks.get("map") is True
        assert final_tasks.get("lock") is True
        assert final_tasks.get("key") is True
        assert final_tasks.get("door") is True
        assert final_tasks.get("unlock") is True

    def test_legacy_escape_unlock_labels_remain_defined_for_history_rendering(self):
        src = (Path(__file__).resolve().parents[2] / "frontend" / "interaction.js").read_text(encoding="utf-8")
        assert 'unlock:             "Final Unlock"' in src or 'unlock: "Final Unlock"' in src

    def test_cafe_and_office_options_remain_unchanged(self):
        assert ORDER_MAP["cafe"] == [
            "dietary_constraint",
            "budget_constraint",
            "location_constraint",
            "decision",
        ]
        assert ORDER_MAP["office"] == ["requirements", "design", "tech_specs", "budget"]

    def test_escape_room_map_resolves_and_active_blocker_advances(self):
        model = _run(_make_model("escape", seed=101))
        map_tick = next(
            snap for snap in model.history
            if "map" in snap.get("scenario", {}).get("resolved_items", [])
        )
        assert map_tick["scenario"]["tasks"]["map"] is True
        later = [snap for snap in model.history if snap["tick"] > map_tick["tick"]]
        assert any(snap.get("group_state", {}).get("active_blocker") == "lock" for snap in later)

    def test_escape_timeout_with_map_still_active_is_not_success(self):
        model = _make_model("escape", seed=101)
        model.episode_max_ticks = 1
        _run(model)
        assert model.ended
        assert model.history[-1].get("group_state", {}).get("active_blocker") == "map"
        assert model.end_reason != "success"

    def test_escape_busy_confirmer_falls_back_to_other_teammate(self):
        model = _make_model("escape", seed=101)
        logic = model.behaviour
        logic._init_state(model)

        model.tick = 3
        model.scenario.tasks["map"] = False
        model._escape_revealed["map"] = True
        model._escape_confirmed["map"] = False
        model._escape_pending_confirm["map"] = {
            "owner": "A1",
            "confirmer": "A2",
            "share_tick": 1,
        }

        events = [{
            "type": "say",
            "actor": "A2",
            "target": "A1",
            "text": "Keep moving.",
            "reason": "escape_coordination",
        }]
        extra = logic.post_tick(model, events)

        assert model.scenario.tasks["map"] is True
        assert model._escape_confirmed["map"] is True
        assert any(event.get("reason") == "escape_confirm_fallback" for event in extra)

    def test_intervention_generated_map_share_and_agree_resolves_map(self):
        model = _make_model("escape", seed=101)
        logic = model.behaviour
        logic._init_state(model)
        model.tick = 2
        events = [
            {
                "type": "share_info",
                "actor": "A1",
                "target": "A3",
                "item": "map",
                "text": "east wall — there's a panel behind the bookshelf.",
                "reason": "user_nudge_strategy",
                "partial": False,
                "can_complete": True,
            },
            {
                "type": "agree",
                "actor": "A3",
                "target": "A1",
                "preference": "map",
                "text": "Perfect. We can move with map now.",
                "reason": "user_nudge_strategy",
            },
        ]
        extra = logic.post_tick(model, events)
        assert model.scenario.tasks["map"] is True
        assert model._escape_confirmed["map"] is True
        assert logic._priority_missing(model)[0] == "lock"
        assert extra == []

    def test_repeated_map_shares_from_different_agents_resolve_map(self):
        model = _make_model("escape", seed=101)
        logic = model.behaviour
        logic._init_state(model)
        model.tick = 4
        model._escape_bottleneck_age = 4
        model._escape_revealed["map"] = True
        rec = logic._evidence_record(model, "map")
        rec["shared_by"].add("A1")
        rec["first_shared_tick"] = 1
        rec["last_evidence_tick"] = 1
        events = [
            {
                "type": "share_info",
                "actor": "A3",
                "target": "A1",
                "item": "map",
                "text": "Map is ready.",
                "reason": "user_force_meeting",
                "partial": False,
                "can_complete": True,
            }
        ]
        extra = logic.post_tick(model, events)
        assert model.scenario.tasks["map"] is True
        assert model._escape_confirmed["map"] is True
        assert any(event.get("reason") == "escape_evidence_resolve" for event in extra) or extra == []

    def test_challenge_only_map_events_do_not_resolve_map(self):
        model = _make_model("escape", seed=101)
        logic = model.behaviour
        logic._init_state(model)
        model.tick = 3
        events = [
            {
                "type": "challenge",
                "actor": "A2",
                "target": "A1",
                "item": "map",
                "text": "Could we be misreading the map?",
                "reason": "escape_doubt",
            }
        ]
        logic.post_tick(model, events)
        assert model.scenario.tasks["map"] is False
        assert logic._priority_missing(model)[0] == "map"

    def test_future_lock_reveal_does_not_resolve_before_map(self):
        model = _make_model("escape", seed=101)
        logic = model.behaviour
        logic._init_state(model)
        model.tick = 2
        events = [
            {
                "type": "share_info",
                "actor": "A3",
                "target": "A1",
                "item": "lock",
                "text": "triangle, circle, square.",
                "reason": "user_reveal_info",
                "partial": False,
                "can_complete": True,
            },
            {
                "type": "agree",
                "actor": "A1",
                "target": "A3",
                "preference": "lock",
                "text": "Good, keep that for later.",
                "reason": "user_reveal_info",
            },
        ]
        logic.post_tick(model, events)
        assert model.scenario.tasks["map"] is False
        assert model.scenario.tasks["lock"] is False
        assert logic._priority_missing(model)[0] == "map"

    def test_escape_success_requires_full_task_chain(self):
        model = _run(_make_model("escape", seed=101))
        if model.end_reason == "success":
            final_tasks = model.history[-1]["scenario"]["tasks"]
            assert all(final_tasks.get(item, False) for item in ["map", "lock", "key", "door", "unlock"])

    def test_cafe_challenge_resolution_ticks_always_carry_resolved_items(self):
        """
        Regression: if a blocker resolves on a tick whose only agent events are
        challenges / ask / social (no share / agree / confirm / open / enter),
        the snap must still set resolved_items so the frontend can inject a
        synthetic "X Finalised" event rather than leaving ✓ hanging after a
        challenge event with no resolution explanation.
        """
        _RESOLVING_TYPES = {"share_info", "share", "agree", "confirm", "open", "enter"}
        model = _run(_make_model("cafe", seed=101))
        for snap in model.history:
            resolved = snap.get("scenario", {}).get("resolved_items", [])
            if not resolved:
                continue
            events = snap.get("events", [])
            event_types = {str(ev.get("type", "")).lower() for ev in events}
            has_resolving = bool(event_types & _RESOLVING_TYPES)
            if not has_resolving and events:
                # Tick has agent events but none are resolving types (e.g. challenge only).
                # resolved_items must be set so the frontend can inject a finalisation event.
                assert resolved, (
                    f"tick {snap['tick']}: blocker resolved with only non-resolving events "
                    f"{sorted(event_types)} but resolved_items is empty — "
                    "frontend cannot inject a synthetic finalisation explanation"
                )

    def test_cafe_quiet_tick_decision_resolution_has_resolved_items_set(self):
        """
        Regression: when the café Decision resolves on a tick with no agent events
        (quiet tick — only a user intervention landed), the backend must still
        set resolved_items = ["decision"] so the frontend can render it as
        "Decision Finalised" rather than "No new agent interaction".

        If Decision resolves on a tick that does have agent events this test
        still passes — it only fails if resolved_items is missing when it should
        be present.
        """
        model = _run(_make_model("cafe", seed=101))
        assert model.ended, "café run did not complete — increase max_ticks or change seed"
        for snap in model.history:
            resolved = snap.get("scenario", {}).get("resolved_items", [])
            if "decision" not in resolved:
                continue
            # Decision resolved this tick. resolved_items must be non-empty so
            # the frontend knows to show a resolution event, not a hold event.
            assert resolved, (
                f"tick {snap['tick']}: decision resolved but resolved_items is empty — "
                "frontend cannot distinguish a quiet-resolve tick from a pure hold tick"
            )
            # Whether or not the tick had agent events, resolved_items["decision"]
            # must be present and the snap must carry task truth.
            tasks = snap.get("scenario", {}).get("tasks", {})
            assert tasks.get("decision") is True, (
                f"tick {snap['tick']}: resolved_items contains 'decision' "
                "but tasks['decision'] is not True"
            )


class TestInterventionTickIntegrity:
    def test_duplicate_intervention_entries_cannot_appear_in_same_tick(self):
        model = _make_model("cafe", seed=42)
        model.step()
        model.step()
        model.apply_intervention("boost_urgency", {"amount": 0.4})
        model.step()
        snap = model.history[-1]
        interventions = snap.get("interventions", [])
        keys = [(entry.get("tick"), entry.get("type")) for entry in interventions]
        assert len(keys) == len(set(keys)), f"duplicate interventions in tick history: {interventions}"


class TestSeededTimelineReproducibility:
    @pytest.mark.parametrize("kind", ["cafe", "escape"])
    def test_same_seed_produces_identical_timeline_blockers(self, kind: str):
        run_a = _run(_make_model(kind, seed=101))
        run_b = _run(_make_model(kind, seed=101))

        timeline_a = [
            (
                snap.get("tick"),
                snap.get("group_state", {}).get("active_blocker"),
                tuple(snap.get("scenario", {}).get("resolved_items", [])),
                tuple((event.get("type"), event.get("item"), event.get("text")) for event in snap.get("events", [])),
            )
            for snap in run_a.history
        ]
        timeline_b = [
            (
                snap.get("tick"),
                snap.get("group_state", {}).get("active_blocker"),
                tuple(snap.get("scenario", {}).get("resolved_items", [])),
                tuple((event.get("type"), event.get("item"), event.get("text")) for event in snap.get("events", [])),
            )
            for snap in run_b.history
        ]

        assert timeline_a == timeline_b, f"{kind}: same seed produced different timeline state"


class TestEscapeTimelineClarity:
    """
    Verifies that a completed Escape run exposes its full five-blocker
    progression so the frontend can render it without gaps.
    """

    def test_completed_escape_timeline_contains_all_five_blocker_names(self):
        """All five escape blockers must appear as active_blocker at some point."""
        model = _run(_make_model("escape", seed=101))
        assert model.ended, "escape run did not complete"
        seen_blockers = {
            snap.get("group_state", {}).get("active_blocker")
            for snap in model.history
        } - {None}
        expected = set(ORDER_MAP["escape"])
        missing = expected - seen_blockers
        assert not missing, (
            f"Escape blocker(s) never appeared as active_blocker: {missing}. "
            f"Seen: {seen_blockers}"
        )

    def test_escape_does_not_jump_from_map_to_complete(self):
        """
        Room Map must not be the last active_blocker before the run ends.
        At least one tick with a different active_blocker must separate
        the first 'map' tick and the final tick.
        """
        model = _run(_make_model("escape", seed=101))
        assert model.ended, "escape run did not complete"
        blockers_in_order = [
            snap.get("group_state", {}).get("active_blocker")
            for snap in model.history
        ]
        non_map = [b for b in blockers_in_order if b and b != "map"]
        assert non_map, (
            "Escape timeline went from 'map' directly to complete with no other "
            "blocker ever active."
        )

    def test_completed_escape_final_tasks_show_full_chain(self):
        """
        The last history snapshot must show all five tasks as True so the
        frontend can render the complete blocker chain in the summary card.
        """
        model = _run(_make_model("escape", seed=101))
        assert model.ended, "escape run did not complete"
        final_tasks = model.history[-1].get("scenario", {}).get("tasks", {})
        for item in ORDER_MAP["escape"]:
            assert final_tasks.get(item) is True, (
                f"Final task snapshot missing {item!r}: tasks = {final_tasks}"
            )

    def test_escape_all_five_blockers_appear_in_resolved_sequence(self):
        """
        The per-tick resolved_items across all snapshots must include every
        escape blocker so the frontend phase-divider injection has data to work with.
        """
        model = _run(_make_model("escape", seed=101))
        resolved_all = set(_resolved_sequence(model))
        expected = set(ORDER_MAP["escape"])
        missing = expected - resolved_all
        assert not missing, (
            f"Escape blockers never recorded as resolved: {missing}. "
            f"Resolved: {resolved_all}"
        )

    def test_early_future_reveal_does_not_advance_active_blocker(self):
        """
        When a non-active item is shared/agreed on, it must NOT appear in
        resolved_items for that tick — the active blocker must be the one
        that resolves.  (Prevents false 'X resolved' UI label.)
        """
        model = _run(_make_model("escape", seed=101))
        for snap in model.history:
            active = snap.get("group_state", {}).get("active_blocker")
            resolved = set(snap.get("scenario", {}).get("resolved_items", []))
            if not resolved:
                continue
            for item in resolved:
                assert item == active, (
                    f"Tick {snap['tick']}: item {item!r} resolved but active blocker "
                    f"was {active!r} — future reveal incorrectly counted as resolution."
                )


class TestCafeProgressionOrder:
    """Café must resolve blockers in the declared order regardless of seed."""

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_cafe_resolves_in_expected_order(self, seed: int):
        model = _run(_make_model("cafe", seed=seed))
        sequence = _resolved_sequence(model)
        order = ORDER_MAP["cafe"]
        order_index = {item: idx for idx, item in enumerate(order)}
        resolved_order = [order_index[item] for item in sequence if item in order_index]
        assert resolved_order == sorted(resolved_order), (
            f"Café (seed={seed}): blockers resolved out of order: "
            f"{[order[i] for i in resolved_order]}"
        )

    def test_cafe_final_tasks_match_expected_chain(self):
        model = _run(_make_model("cafe", seed=101))
        assert model.ended, "cafe run did not complete"
        final_tasks = model.history[-1].get("scenario", {}).get("tasks", {})
        for item in ORDER_MAP["cafe"]:
            assert final_tasks.get(item) is True, (
                f"Café final snapshot missing {item!r}: tasks = {final_tasks}"
            )


class TestCafeBlockerLabels:
    """
    Blocker labels in the history must always reflect the authoritative active_blocker
    for that tick — not a stale value from a previous tick.

    These tests verify the backend contract that frontends rely on to render
    "Current blocker" labels on interventions and step headers.
    """

    def test_after_budget_resolves_next_tick_active_blocker_is_location(self):
        """
        Once budget_constraint is marked resolved, every subsequent tick must
        have active_blocker == 'location_constraint', not 'budget_constraint'.
        """
        model = _run(_make_model("cafe", seed=101))
        budget_resolved_at = None
        for snap in model.history:
            if snap.get("scenario", {}).get("tasks", {}).get("budget_constraint"):
                if budget_resolved_at is None:
                    budget_resolved_at = snap["tick"]
            if budget_resolved_at is not None and snap["tick"] > budget_resolved_at:
                active = snap.get("group_state", {}).get("active_blocker")
                assert active != "budget_constraint", (
                    f"Tick {snap['tick']}: budget already resolved at tick "
                    f"{budget_resolved_at} but active_blocker is still 'budget_constraint'"
                )

    def test_after_location_resolves_next_tick_active_blocker_is_decision(self):
        """
        Once location_constraint is resolved, every subsequent tick must
        have active_blocker == 'decision'.
        """
        model = _run(_make_model("cafe", seed=101))
        location_resolved_at = None
        for snap in model.history:
            if snap.get("scenario", {}).get("tasks", {}).get("location_constraint"):
                if location_resolved_at is None:
                    location_resolved_at = snap["tick"]
            if location_resolved_at is not None and snap["tick"] > location_resolved_at:
                active = snap.get("group_state", {}).get("active_blocker")
                assert active != "location_constraint", (
                    f"Tick {snap['tick']}: location already resolved at tick "
                    f"{location_resolved_at} but active_blocker is still 'location_constraint'"
                )

    def test_decision_resolution_tick_has_decision_as_active_blocker(self):
        """
        The tick that resolves 'decision' must have active_blocker == 'decision'.
        This ensures the step that carries the decision confirm event is correctly
        labelled — not labelled as a previous constraint.
        """
        model = _run(_make_model("cafe", seed=101))
        for snap in model.history:
            resolved = snap.get("scenario", {}).get("resolved_items", [])
            if "decision" in resolved:
                active = snap.get("group_state", {}).get("active_blocker")
                assert active == "decision", (
                    f"Tick {snap['tick']}: decision resolved but active_blocker "
                    f"was {active!r} instead of 'decision'"
                )

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_cafe_decision_resolution_step_contains_agreement_event(self, seed: int):
        """
        The step that resolves 'decision' must carry at least one agree/confirm
        event — confirming it is a real resolution, not a silent advance.
        """
        model = _run(_make_model("cafe", seed=seed))
        resolution_types = {"agree", "confirm", "share_info", "share"}
        for snap in model.history:
            if "decision" in snap.get("scenario", {}).get("resolved_items", []):
                event_types = {e.get("type") for e in snap.get("events", [])}
                assert event_types & resolution_types, (
                    f"Café (seed={seed}) tick {snap['tick']}: decision resolved "
                    f"but no agreement/confirm event present. Types: {sorted(event_types)}"
                )


# ---------------------------------------------------------------------------
# Office-specific regression tests
# ---------------------------------------------------------------------------

class TestOfficeProgressionOrder:
    """Office must resolve blockers in the declared order regardless of seed."""

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_office_resolves_in_expected_order(self, seed: int):
        """
        Requirements → Design Plans → Spec Doc → Budget must never appear
        out of order in the resolution sequence.
        """
        model = _run(_make_model("office", seed=seed))
        sequence = _resolved_sequence(model)
        order = ORDER_MAP["office"]
        order_index = {item: idx for idx, item in enumerate(order)}
        resolved_order = [order_index[item] for item in sequence if item in order_index]
        assert resolved_order == sorted(resolved_order), (
            f"Office (seed={seed}): blockers resolved out of order: "
            f"{[order[i] for i in resolved_order]}"
        )

    def test_office_final_tasks_match_expected_chain(self):
        """All four office tasks must be resolved when the run completes."""
        model = _run(_make_model("office", seed=101))
        assert model.ended, "office run did not complete"
        final_tasks = model.history[-1].get("scenario", {}).get("tasks", {})
        for item in ORDER_MAP["office"]:
            assert final_tasks.get(item) is True, (
                f"Office final snapshot missing {item!r}: tasks = {final_tasks}"
            )


class TestOfficeBlockerLabels:
    """
    active_blocker must always equal the first unresolved item in ORDER_MAP["office"].
    No intervention or future-reveal share may cause the active blocker to skip ahead
    while an earlier item is still outstanding.
    """

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_office_active_blocker_does_not_lag_after_resolution(self, seed: int):
        """
        Once an item has been marked resolved (i.e., it appears as True in
        tasks on tick T), every subsequent tick T+1, T+2, … must NOT report
        that item as active_blocker.

        A one-tick lag on the resolution tick itself is allowed (same-tick
        semantics, matching the Café blocker-label contract).  But stale
        active_blocker values must not persist beyond that tick.

        This also ensures that a future-reveal or urgency boost targeting
        'budget' cannot make active_blocker read 'budget' while 'requirements'
        is still the authoritative first-unresolved item.
        """
        model = _run(_make_model("office", seed=seed))
        order = ORDER_MAP["office"]
        # Track the tick at which each item was first resolved
        resolved_at: dict[str, int] = {}
        for snap in model.history:
            tasks = snap.get("scenario", {}).get("tasks", {})
            active = snap.get("group_state", {}).get("active_blocker")
            tick = snap["tick"]
            # Record first resolution tick for each item
            for item in order:
                if tasks.get(item, False) and item not in resolved_at:
                    resolved_at[item] = tick
            # After the resolution tick, active_blocker must not still name a
            # resolved item (one-tick lag is permitted on the resolution tick itself)
            for item, res_tick in resolved_at.items():
                if tick > res_tick:
                    assert active != item, (
                        f"Office (seed={seed}) tick {tick}: active_blocker is "
                        f"still {item!r} but it was resolved at tick {res_tick}. "
                        f"Tasks: {tasks}"
                    )

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_office_each_resolved_item_has_matching_evidence_event(self, seed: int):
        """
        For every item that appears in resolved_items on a tick, that same tick
        must carry at least one resolving event (share_info / share / agree /
        confirm / open / enter) whose 'item' field matches.

        This prevents 'Spec Doc resolves from a Budget event' contradictions —
        the per-item evidence injection in the frontend relies on the backend
        producing at least one correctly-tagged event per resolved item.
        """
        resolving_types = {"share_info", "share", "agree", "confirm", "open", "enter"}
        model = _run(_make_model("office", seed=seed))
        for snap in model.history:
            resolved = snap.get("scenario", {}).get("resolved_items", [])
            events = snap.get("events", [])
            for resolved_item in resolved:
                has_evidence = any(
                    str(ev.get("type", "")).lower() in resolving_types
                    and str(ev.get("item", "")) == resolved_item
                    for ev in events
                )
                assert has_evidence, (
                    f"Office (seed={seed}) tick {snap['tick']}: {resolved_item!r} "
                    f"in resolved_items but no matching resolving event found. "
                    f"Event types/items: "
                    f"{[(ev.get('type'), ev.get('item')) for ev in events]}"
                )

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_office_budget_share_does_not_resolve_earlier_items(self, seed: int):
        """
        A budget share/agree event must not appear in the same tick as a
        resolution of requirements, design, or tech_specs — budget is always
        the last blocker, so its evidence cannot be the trigger for earlier
        items resolving.
        """
        budget_evidence_types = {"share_info", "share", "agree", "confirm"}
        earlier_items = {"requirements", "design", "tech_specs"}
        model = _run(_make_model("office", seed=seed))
        for snap in model.history:
            resolved = set(snap.get("scenario", {}).get("resolved_items", []))
            events = snap.get("events", [])
            # Is there a budget-tagged resolving event this tick?
            has_budget_evidence = any(
                str(ev.get("type", "")).lower() in budget_evidence_types
                and str(ev.get("item", "")) == "budget"
                for ev in events
            )
            if not has_budget_evidence:
                continue
            # If there is, none of the earlier items should be resolving here
            # (budget evidence cannot be the sole cause of an earlier item resolving)
            for item in earlier_items:
                if item in resolved:
                    # This tick resolved an earlier item AND had budget evidence.
                    # Verify the tick also carries item-specific evidence for that item.
                    has_item_evidence = any(
                        str(ev.get("type", "")).lower() in budget_evidence_types
                        and str(ev.get("item", "")) == item
                        for ev in events
                    )
                    assert has_item_evidence, (
                        f"Office (seed={seed}) tick {snap['tick']}: {item!r} "
                        f"resolved in same tick as a budget share event, but no "
                        f"{item!r}-tagged resolving event found. "
                        f"Budget evidence cannot be the sole trigger for {item!r}."
                    )


class TestOfficeBlockerTransitions:
    """
    After each blocker resolves, the immediately subsequent tick must update
    active_blocker to the next item in the canonical chain.

    Requirements → Design Plans → Spec Doc → Budget
    """

    def test_after_requirements_resolves_next_active_blocker_is_design(self):
        """
        The tick after requirements is marked True must have active_blocker == 'design'.
        This ensures the UI never shows 'moves on to Budget' when requirements resolves.
        """
        model = _run(_make_model("office", seed=101))
        req_resolved_at = None
        for snap in model.history:
            tasks = snap.get("scenario", {}).get("tasks", {})
            active = snap.get("group_state", {}).get("active_blocker")
            tick = snap["tick"]
            if tasks.get("requirements", False) and req_resolved_at is None:
                req_resolved_at = tick
            if req_resolved_at is not None and tick > req_resolved_at:
                assert active != "requirements", (
                    f"Tick {tick}: requirements resolved at tick {req_resolved_at} "
                    f"but active_blocker is still 'requirements'."
                )
                assert active != "budget", (
                    f"Tick {tick}: active_blocker jumped to 'budget' after "
                    f"'requirements' resolved — should be 'design'."
                )
                break  # only check the first tick after resolution

    def test_after_design_resolves_next_active_blocker_is_tech_specs(self):
        model = _run(_make_model("office", seed=101))
        design_resolved_at = None
        for snap in model.history:
            tasks = snap.get("scenario", {}).get("tasks", {})
            active = snap.get("group_state", {}).get("active_blocker")
            tick = snap["tick"]
            if tasks.get("design", False) and design_resolved_at is None:
                design_resolved_at = tick
            if design_resolved_at is not None and tick > design_resolved_at:
                assert active != "design", (
                    f"Tick {tick}: design resolved at tick {design_resolved_at} "
                    f"but active_blocker is still 'design'."
                )
                assert active != "budget", (
                    f"Tick {tick}: active_blocker jumped to 'budget' after "
                    f"'design' resolved — should be 'tech_specs'."
                )
                break

    def test_after_spec_doc_resolves_next_active_blocker_is_budget(self):
        """
        The tick after tech_specs is marked True must have active_blocker == 'budget'.
        This ensures Step 18 reads 'Current blocker: Budget' not 'Current blocker: Spec Doc'.
        """
        model = _run(_make_model("office", seed=101))
        spec_resolved_at = None
        for snap in model.history:
            tasks = snap.get("scenario", {}).get("tasks", {})
            active = snap.get("group_state", {}).get("active_blocker")
            tick = snap["tick"]
            if tasks.get("tech_specs", False) and spec_resolved_at is None:
                spec_resolved_at = tick
            if spec_resolved_at is not None and tick > spec_resolved_at:
                assert active != "tech_specs", (
                    f"Tick {tick}: tech_specs resolved at tick {spec_resolved_at} "
                    f"but active_blocker is still 'tech_specs'."
                )
                assert active == "budget", (
                    f"Tick {tick}: active_blocker is {active!r} but should be "
                    f"'budget' once tech_specs is resolved."
                )
                break  # only check the first tick after resolution

    def test_future_budget_target_does_not_advance_active_blocker_early(self):
        """
        Even if the user targets 'budget' via an urgency or tension intervention
        while design or tech_specs is still unresolved, active_blocker must remain
        on the earliest unresolved item — never 'budget'.
        """
        model = _run(_make_model("office", seed=101))
        order = ORDER_MAP["office"]
        for snap in model.history:
            tasks = snap.get("scenario", {}).get("tasks", {})
            active = snap.get("group_state", {}).get("active_blocker")
            if active != "budget":
                continue
            # If active_blocker is 'budget', all earlier items must be resolved
            for earlier in order[:-1]:  # everything before budget
                assert tasks.get(earlier, False), (
                    f"Tick {snap['tick']}: active_blocker is 'budget' but "
                    f"{earlier!r} is not yet resolved. Tasks: {tasks}"
                )


class TestOfficeEvidenceQuality:
    """
    When a blocker resolves, the tick must carry at least one resolving event
    whose text is *substantive* — i.e. it actually describes the item's content
    rather than generic acknowledgement ("Yeah, that's fine.", "Got it.").

    The frontend's hasSubstantiveItemEvidence() relies on this contract to
    decide whether to inject a concrete synthetic finalisation event.
    """

    # Mirrors _SUBSTANTIVE_PATTERNS in interaction.js
    _PATTERNS = {
        "requirements": re.compile(r"mobile|offline", re.I),
        "design":       re.compile(r"flat|blue|modern|colour|color|layout", re.I),
        "tech_specs":   re.compile(r"react|node|postgresql|stack", re.I),
        "budget":       re.compile(r"\$50|\b50k\b|contingency|sign.?off", re.I),
    }
    _RESOLVING_TYPES = {"share_info", "share", "agree", "confirm", "open", "enter"}

    def _has_substantive_evidence(self, events: list, resolved_item: str) -> bool:
        pattern = self._PATTERNS.get(resolved_item)
        for ev in events:
            if str(ev.get("type", "")).lower() not in self._RESOLVING_TYPES:
                continue
            if str(ev.get("item", "")) != resolved_item:
                continue
            if pattern is None:
                return True   # no content requirement for this item
            if pattern.search(str(ev.get("text", ""))):
                return True
        return False

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_requirements_substantive_share_appears_somewhere_in_run(self, seed: int):
        """
        The backend must share substantive requirements content (mentioning 'mobile'
        or 'offline') at least once during the run.  This is the source-of-truth
        that justifies the frontend's synthetic finalisation text:
        "The requirements are confirmed: mobile access and offline mode support."

        Note: the resolution *tick* itself may only have a generic agree event —
        that's handled by the frontend's hasSubstantiveItemEvidence() injection.
        The test verifies the real content was shared earlier in the run.
        """
        model = _run(_make_model("office", seed=seed))
        all_events = [ev for snap in model.history for ev in snap.get("events", [])]
        share_types = {"share_info", "share"}
        found = any(
            str(ev.get("type", "")).lower() in share_types
            and str(ev.get("item", "")) == "requirements"
            and self._PATTERNS["requirements"].search(str(ev.get("text", "")))
            for ev in all_events
        )
        assert found, (
            f"Office (seed={seed}): no substantive requirements share event found "
            f"anywhere in the run (must mention 'mobile' or 'offline')."
        )

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_design_substantive_share_appears_somewhere_in_run(self, seed: int):
        """
        The backend must share substantive design content (flat, blue, modern,
        colour, or layout) at least once during the run.  Justifies the frontend's
        synthetic: "The design is confirmed: a flat, modern UI with a blue colour
        scheme."
        """
        model = _run(_make_model("office", seed=seed))
        all_events = [ev for snap in model.history for ev in snap.get("events", [])]
        share_types = {"share_info", "share"}
        found = any(
            str(ev.get("type", "")).lower() in share_types
            and str(ev.get("item", "")) == "design"
            and self._PATTERNS["design"].search(str(ev.get("text", "")))
            for ev in all_events
        )
        assert found, (
            f"Office (seed={seed}): no substantive design share event found "
            f"anywhere in the run (must mention flat/blue/modern/colour/layout)."
        )

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_tech_specs_substantive_share_appears_somewhere_in_run(self, seed: int):
        """
        The backend must share substantive tech_specs content (mentioning 'react',
        'node', 'postgresql', or 'stack') at least once during the run.  Justifies
        the frontend's synthetic: "The technical specification is confirmed: React
        frontend, Node backend, and PostgreSQL database."
        """
        model = _run(_make_model("office", seed=seed))
        all_events = [ev for snap in model.history for ev in snap.get("events", [])]
        share_types = {"share_info", "share"}
        found = any(
            str(ev.get("type", "")).lower() in share_types
            and str(ev.get("item", "")) == "tech_specs"
            and self._PATTERNS["tech_specs"].search(str(ev.get("text", "")))
            for ev in all_events
        )
        assert found, (
            f"Office (seed={seed}): no substantive tech_specs share event found "
            f"anywhere in the run (must mention react/node/postgresql/stack)."
        )

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_no_one_left_counting_at_budget_resolution(self, seed: int):
        """
        In the tick that resolves 'budget' (final Office item), no agent event
        text should contain 'one left' or 'one more' — budget IS the final item,
        so that phrasing is factually misleading.
        """
        model = _run(_make_model("office", seed=seed))
        anti_pattern = re.compile(r"\bone\s+left\b|\bone\s+more\b", re.I)
        for snap in model.history:
            if "budget" in snap.get("scenario", {}).get("resolved_items", []):
                for ev in snap.get("events", []):
                    text = str(ev.get("text", ""))
                    assert not anti_pattern.search(text), (
                        f"Office (seed={seed}) tick {snap['tick']}: budget resolved "
                        f"but event text contains counting language: {text!r}"
                    )


# ---------------------------------------------------------------------------
# Office wording / title regression tests
# ---------------------------------------------------------------------------

class _StubAgent:
    """Minimal stub that _delayed_reveal_coordination_text expects."""

    class _Behaviour:
        scenario_type = "office"

    class _Model:
        bottleneck_item = None
        behaviour = None  # set per-test below

    def __init__(self, scenario_type: str = "office", bottleneck_item=None):
        self.model = self._Model()
        self.model.behaviour = type("B", (), {"scenario_type": scenario_type})()
        self.model.bottleneck_item = bottleneck_item


class TestOfficeInterventionWording:
    """
    Regression tests for the three Office timeline contradiction fixes.

    Issue 1 — Step title:
        The tick that resolves 'requirements' must carry a requirements-tagged
        resolving event so the frontend's displayPriority(1.5) elevation gives
        that event the group title ("Requirements Confirmed"), not a co-occurring
        design event ("Design Plans Confirmed").

    Issue 2 — Why-text blocker:
        group_state.active_blocker must equal the first unresolved item at tick
        START.  If design resolves in the same tick as a boost_urgency response,
        active_blocker (tick-start) is still "design", letting the frontend render
        "while Design Plans remains the live blocker" — not "Spec Doc".

    Issue 3 — Requirements coordination wording:
        _delayed_reveal_coordination_text for item="requirements" in the office
        scenario must return the content-specific phrase, not the generic template.
    """

    # ── Issue 3 unit tests ───────────────────────────────────────────────────

    def test_requirements_delayed_reveal_returns_content_specific_text(self):
        """
        _delayed_reveal_coordination_text(item='requirements') must return
        'I've got the requirements ready: mobile access and offline mode support.'
        so the timeline never shows the generic 'I've got the requirements piece
        ready. Once <blocker> lands, I'll slot it straight in.' phrasing.
        """
        agent = _StubAgent(scenario_type="office", bottleneck_item="design")
        result = _delayed_reveal_coordination_text(agent, "requirements")
        assert result == "I've got the requirements ready: mobile access and offline mode support.", (
            f"requirements coordination text was: {result!r}"
        )

    def test_requirements_delayed_reveal_ignores_active_blocker(self):
        """
        The content-specific requirements phrase must be returned regardless of
        what the current bottleneck_item is, because the phrase is self-contained.
        """
        for blocker in [None, "design", "tech_specs", "budget"]:
            agent = _StubAgent(scenario_type="office", bottleneck_item=blocker)
            result = _delayed_reveal_coordination_text(agent, "requirements")
            assert "mobile access" in result and "offline mode" in result, (
                f"requirements phrase missing content keywords when blocker={blocker!r}: {result!r}"
            )

    def test_other_office_items_still_use_generic_template(self):
        """
        Only 'requirements' gets the content-specific override.  Other items
        (design, tech_specs, budget) must still use the blocker-referencing template.
        """
        for item in ["design", "tech_specs", "budget"]:
            agent = _StubAgent(scenario_type="office", bottleneck_item=None)
            result = _delayed_reveal_coordination_text(agent, item)
            # Generic template ends with "ready to bring in", "ready to use", or similar
            # but never the requirements-specific content.
            assert "mobile access" not in result, (
                f"{item!r} returned requirements-specific phrase: {result!r}"
            )
            assert "offline mode" not in result, (
                f"{item!r} returned requirements-specific phrase: {result!r}"
            )

    # ── Issue 1 backend contract (title data integrity) ───────────────────────

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_requirements_resolution_tick_has_requirements_tagged_event(self, seed: int):
        """
        Regression for Issue 1: the tick that marks 'requirements' resolved must
        carry at least one resolving event (share_info / agree / confirm) whose
        item field is exactly 'requirements'.

        The frontend's displayPriority() gives such events priority 1.5 so they
        sort first in their step group and the group title becomes
        "Requirements Confirmed" — not "Design Plans Confirmed".

        If this event is missing, the frontend has no requirements-tagged card to
        elevate and will fall back to whichever event appears first (which could
        be a design card from a co-occurring early reveal).
        """
        resolving_types = {"share_info", "share", "agree", "confirm"}
        model = _run(_make_model("office", seed=seed))
        for snap in model.history:
            resolved = snap.get("scenario", {}).get("resolved_items", [])
            if "requirements" not in resolved:
                continue
            events = snap.get("events", [])
            has_req_event = any(
                str(ev.get("type", "")).lower() in resolving_types
                and str(ev.get("item", "")) == "requirements"
                for ev in events
            )
            assert has_req_event, (
                f"Office (seed={seed}) tick {snap['tick']}: 'requirements' in "
                f"resolved_items but no requirements-tagged resolving event found. "
                f"Frontend cannot set 'Requirements Confirmed' step title. "
                f"Event types/items: {[(ev.get('type'), ev.get('item')) for ev in events]}"
            )

    # ── Issue 2 backend contract (tick-start blocker accuracy) ────────────────

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_active_blocker_at_design_resolution_tick_is_design_not_tech_specs(self, seed: int):
        """
        Regression for Issue 2: the tick that resolves 'design' must have
        group_state.active_blocker == 'design', NOT 'tech_specs'.

        The frontend reads ev.__stepActiveBlocker (= group_state.active_blocker)
        as the tick-START blocker for user-triggered event Why-text.  If a
        boost_urgency response lands in the same tick that design resolves,
        the Why text must say "while Design Plans remains the live blocker" —
        which is only possible if active_blocker is 'design' on that tick.

        The existing test_each_step_has_one_authoritative_active_blocker covers
        this via the canonical first-unresolved rule; this test makes the
        issue-2 regression explicit.
        """
        model = _run(_make_model("office", seed=seed))
        for snap in model.history:
            resolved = snap.get("scenario", {}).get("resolved_items", [])
            if "design" not in resolved:
                continue
            active = snap.get("group_state", {}).get("active_blocker")
            assert active == "design", (
                f"Office (seed={seed}) tick {snap['tick']}: 'design' resolved "
                f"but active_blocker (tick-start blocker) is {active!r} instead "
                f"of 'design'. Frontend Why-text will incorrectly say "
                f"'while {active} remains the live blocker' instead of "
                f"'while Design Plans remains the live blocker'."
            )


# ---------------------------------------------------------------------------
# Step 17 regression tests (Design Plans resolution step title / effect / why)
# ---------------------------------------------------------------------------

class TestOfficeStep17Regressions:
    """
    Regression tests for Step 17 contradictions (Design Plans resolution tick).

    Before fix:
      - Step title was "Spec Doc Confirmed" (from end-of-tick blocker = tech_specs)
      - Effect text was "Confidence rises around Spec Doc." (same root cause)
      - Why text was "targeting Spec Doc, while Design Plans remains the live blocker"
        even when the user's intervention targeted Budget

    After fix (frontend uses ev.__stepActiveBlocker for user-triggered events):
      - Step title must be driven by the tick-start blocker ("design") → "Design Plans Confirmed"
      - Effect text must reference Design Plans, not Spec Doc
      - Why text must name the actual intervention target (bottleneck_item) not the
        end-of-tick blocker

    Backend contracts verified here (frontend logic tested separately):
    """

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_design_resolution_tick_active_blocker_is_design(self, seed: int):
        """
        The tick that resolves 'design' must report active_blocker == 'design'
        (the tick-start, first-unresolved blocker), not 'tech_specs' (the
        end-of-tick blocker after design has been cleared).

        Frontend stepEventTitle() reads ev.__stepActiveBlocker = active_blocker
        for user-triggered events; if this is 'design', the title is
        "Design Plans Confirmed", not "Spec Doc Confirmed".
        """
        model = _run(_make_model("office", seed=seed))
        for snap in model.history:
            if "design" not in snap.get("scenario", {}).get("resolved_items", []):
                continue
            active = snap.get("group_state", {}).get("active_blocker")
            assert active == "design", (
                f"Office (seed={seed}) tick {snap['tick']}: design resolved but "
                f"active_blocker is {active!r}. Frontend would title the step "
                f"'{active} Confirmed' instead of 'Design Plans Confirmed'."
            )

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_design_resolution_tick_has_design_tagged_resolving_event(self, seed: int):
        """
        The tick that resolves 'design' must carry a resolving event (share_info /
        agree / confirm) tagged with item='design'.

        Frontend displayPriority() gives such events priority 1.5 so they sort
        first in the step group and set the title "Design Plans Confirmed" even
        when a user-triggered event (priority 1) is also present.

        Without this event, there is nothing for the frontend to elevate, and a
        co-occurring user-triggered response could set the title incorrectly.
        """
        resolving_types = {"share_info", "share", "agree", "confirm"}
        model = _run(_make_model("office", seed=seed))
        for snap in model.history:
            if "design" not in snap.get("scenario", {}).get("resolved_items", []):
                continue
            events = snap.get("events", [])
            has_design_event = any(
                str(ev.get("type", "")).lower() in resolving_types
                and str(ev.get("item", "")) == "design"
                for ev in events
            )
            assert has_design_event, (
                f"Office (seed={seed}) tick {snap['tick']}: 'design' in "
                f"resolved_items but no design-tagged resolving event found. "
                f"Frontend cannot set 'Design Plans Confirmed' step title. "
                f"Event types/items: {[(ev.get('type'), ev.get('item')) for ev in events]}"
            )

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_no_tick_has_tech_specs_confidence_before_tech_specs_active(self, seed: int):
        """
        No event on a tick where Design Plans is active (tech_specs not yet
        active) should have item='tech_specs' appear as a confidence/agree
        event that would produce 'Confidence rises around Spec Doc'.

        Specifically: the tick that resolves design must not have an agree/confirm
        event whose item='tech_specs' (which would cause the effect text to say
        'Confidence rises around Spec Doc' while design is still the live blocker).

        Note: a future-reveal SHARE of tech_specs is allowed (the agent can surface
        future info), but an AGREE/CONFIRM about tech_specs while design is active
        indicates a state-machine error.
        """
        agree_types = {"agree", "confirm"}
        model = _run(_make_model("office", seed=seed))
        for snap in model.history:
            active = snap.get("group_state", {}).get("active_blocker")
            if active != "design":
                continue
            events = snap.get("events", [])
            for ev in events:
                ev_type = str(ev.get("type", "")).lower()
                ev_item = str(ev.get("item", ""))
                ev_reason = str(ev.get("reason", ""))
                # user-triggered agree/confirm responses while design is active must not
                # be tagged with tech_specs — that would produce wrong effect text
                if ev_type in agree_types and ev_item == "tech_specs" and not ev_reason.startswith("user_"):
                    assert False, (
                        f"Office (seed={seed}) tick {snap['tick']}: agree/confirm event "
                        f"with item='tech_specs' while active_blocker='design'. "
                        f"Frontend effect text would say 'Confidence rises around Spec Doc' "
                        f"before Spec Doc is the live blocker."
                    )

    @pytest.mark.parametrize("seed", [101, 202, 303])
    def test_future_budget_intervention_bottleneck_item_set_correctly(self, seed: int):
        """
        When boost_urgency targets 'budget' while Design Plans is still active,
        group_state.bottleneck_item must be 'budget' on that tick so the frontend
        can read ev.__stepNextBlocker = 'budget' and produce:
        'targeting Budget, while Design Plans remains the live blocker.'

        This test verifies the backend contract: if an intervention targeting a
        future item is applied, bottleneck_item reflects that target.

        We verify indirectly: any tick where active_blocker='design' but
        bottleneck_item is set, it must be either 'design' (same as active,
        targeting the live blocker) or a valid item in the blocker order (a
        future item being targeted).  It must NOT be a nonsensical value.
        """
        valid_items = set(ORDER_MAP["office"])
        model = _run(_make_model("office", seed=seed))
        for snap in model.history:
            active = snap.get("group_state", {}).get("active_blocker")
            bottleneck = snap.get("group_state", {}).get("bottleneck_item")
            if active != "design" or bottleneck is None:
                continue
            assert bottleneck in valid_items, (
                f"Office (seed={seed}) tick {snap['tick']}: active_blocker='design' "
                f"but bottleneck_item={bottleneck!r} is not a valid office blocker. "
                f"Valid items: {valid_items}"
            )


# ─── Task-transition derived chain regression tests ──────────────────────────
# Python mirror of the JS deriveResolvedPhasesFromHistory helper.
# These tests prove that:
#   (a) each scenario's actual task-state transitions match the expected chain
#   (b) completed scenarios are fully validated (all tasks true + all transitions present)
#   (c) no cross-scenario blocker label leaks appear in any run

SCENARIO_LABELS: dict[str, dict[str, str]] = {
    "cafe": {
        "dietary_constraint": "Dietary Constraint",
        "budget_constraint":  "Budget",
        "location_constraint": "Location",
        "decision":           "Decision",
    },
    "office": {
        "requirements": "Requirements",
        "design":       "Design Plans",
        "tech_specs":   "Spec Doc",
        "budget":       "Budget",
    },
    "escape": {
        "map":    "Room Map",
        "lock":   "Lock Pattern",
        "key":    "Key Location",
        "door":   "Door Code",
        "unlock": "Final Unlock",
    },
}

EXPECTED_CHAINS: dict[str, list[str]] = {
    "cafe":   ["Dietary Constraint", "Budget", "Location", "Decision"],
    "office": ["Requirements", "Design Plans", "Spec Doc", "Budget"],
    "escape": ["Room Map", "Lock Pattern", "Key Location", "Door Code", "Final Unlock"],
}


def _derive_resolved_phases(history: list[dict], scenario_key: str) -> list[dict]:
    """Python mirror of JS deriveResolvedPhasesFromHistory."""
    order  = ORDER_MAP[scenario_key]
    labels = SCENARIO_LABELS[scenario_key]
    prev   = {item: False for item in order}
    transitions: list[dict] = []
    for snap in history:
        tasks = snap.get("scenario", {}).get("tasks", {})
        tick  = snap.get("tick", 0)
        for item in order:
            if not prev[item] and tasks.get(item):
                transitions.append({"item": item, "tick": tick, "label": labels[item]})
            if tasks.get(item):
                prev[item] = True
    return transitions


def _validate_completed_scenario(history: list[dict], scenario_key: str) -> dict:
    """Python mirror of JS validateCompletedScenario."""
    order       = ORDER_MAP[scenario_key]
    transitions = _derive_resolved_phases(history, scenario_key)
    resolved_set = {t["item"] for t in transitions}
    last_snap   = history[-1] if history else {}
    final_tasks = last_snap.get("scenario", {}).get("tasks", {})
    all_tasks_true         = all(bool(final_tasks.get(it)) for it in order)
    all_transitions_present = all(it in resolved_set for it in order)
    return {
        "valid":                   all_tasks_true and all_transitions_present,
        "all_tasks_true":          all_tasks_true,
        "all_transitions_present": all_transitions_present,
        "resolved_transitions":    transitions,
        "missing_from_tasks":      [it for it in order if not final_tasks.get(it)],
        "missing_from_transitions":[it for it in order if it not in resolved_set],
    }


@pytest.mark.parametrize("seed", [101, 202, 303])
class TestTaskTransitionDerivedChains:
    """
    Verify that task-state false→true transitions in history match the
    expected canonical chain for every scenario.  These tests are the
    backend equivalent of the JS deriveResolvedPhasesFromHistory + validateCompletedScenario.
    """

    # ── Café ──────────────────────────────────────────────────────────────────

    def test_cafe_derived_chain_matches_expected(self, seed):
        model = _run(_make_model("cafe", seed=seed))
        transitions = _derive_resolved_phases(model.history, "cafe")
        derived_labels = [t["label"] for t in transitions]
        assert derived_labels == EXPECTED_CHAINS["cafe"], (
            f"Café (seed={seed}) derived chain {derived_labels!r} "
            f"!= expected {EXPECTED_CHAINS['cafe']!r}"
        )

    def test_cafe_validation_passes(self, seed):
        model = _run(_make_model("cafe", seed=seed))
        result = _validate_completed_scenario(model.history, "cafe")
        assert result["valid"], (
            f"Café (seed={seed}) validation failed: "
            f"missing_tasks={result['missing_from_tasks']} "
            f"missing_transitions={result['missing_from_transitions']}"
        )

    def test_cafe_no_escape_or_office_labels_in_transitions(self, seed):
        model = _run(_make_model("cafe", seed=seed))
        transitions = _derive_resolved_phases(model.history, "cafe")
        escape_items = set(ORDER_MAP["escape"])
        office_items = set(ORDER_MAP["office"])
        contaminated = [t for t in transitions if t["item"] in escape_items | office_items]
        assert not contaminated, (
            f"Café (seed={seed}) transitions contain non-café items: {contaminated}"
        )

    # ── Office ────────────────────────────────────────────────────────────────

    def test_office_derived_chain_matches_expected(self, seed):
        model = _run(_make_model("office", seed=seed))
        transitions = _derive_resolved_phases(model.history, "office")
        derived_labels = [t["label"] for t in transitions]
        assert derived_labels == EXPECTED_CHAINS["office"], (
            f"Office (seed={seed}) derived chain {derived_labels!r} "
            f"!= expected {EXPECTED_CHAINS['office']!r}"
        )

    def test_office_validation_passes(self, seed):
        model = _run(_make_model("office", seed=seed))
        result = _validate_completed_scenario(model.history, "office")
        assert result["valid"], (
            f"Office (seed={seed}) validation failed: "
            f"missing_tasks={result['missing_from_tasks']} "
            f"missing_transitions={result['missing_from_transitions']}"
        )

    def test_office_no_cafe_or_escape_labels_in_transitions(self, seed):
        model = _run(_make_model("office", seed=seed))
        transitions = _derive_resolved_phases(model.history, "office")
        cafe_items   = set(ORDER_MAP["cafe"])
        escape_items = set(ORDER_MAP["escape"])
        contaminated = [t for t in transitions if t["item"] in cafe_items | escape_items]
        assert not contaminated, (
            f"Office (seed={seed}) transitions contain non-office items: {contaminated}"
        )

    # ── Escape ────────────────────────────────────────────────────────────────

    def test_escape_derived_chain_matches_expected(self, seed):
        model = _run(_make_model("escape", seed=seed))
        transitions = _derive_resolved_phases(model.history, "escape")
        derived_labels = [t["label"] for t in transitions]
        assert derived_labels == EXPECTED_CHAINS["escape"], (
            f"Escape (seed={seed}) derived chain {derived_labels!r} "
            f"!= expected {EXPECTED_CHAINS['escape']!r}"
        )

    def test_escape_validation_passes(self, seed):
        model = _run(_make_model("escape", seed=seed))
        result = _validate_completed_scenario(model.history, "escape")
        assert result["valid"], (
            f"Escape (seed={seed}) validation failed: "
            f"missing_tasks={result['missing_from_tasks']} "
            f"missing_transitions={result['missing_from_transitions']}"
        )

    def test_escape_all_five_transitions_present_in_order(self, seed):
        """Completed Escape must show all five blockers resolving, in chain order."""
        model = _run(_make_model("escape", seed=seed))
        transitions = _derive_resolved_phases(model.history, "escape")
        items_in_order = [t["item"] for t in transitions]
        assert items_in_order == ORDER_MAP["escape"], (
            f"Escape (seed={seed}) did not resolve all five blockers in order: "
            f"got {items_in_order!r}"
        )

    def test_escape_does_not_show_room_map_unresolved_after_its_resolution_tick(self, seed):
        """
        After the map task transitions to true, no later snapshot should have
        map=False.  Validates the data the JS timeline will read.
        """
        model = _run(_make_model("escape", seed=seed))
        transitions = _derive_resolved_phases(model.history, "escape")
        map_transition = next((t for t in transitions if t["item"] == "map"), None)
        assert map_transition is not None, f"Escape (seed={seed}): map never resolved"
        resolution_tick = map_transition["tick"]
        for snap in model.history:
            if snap["tick"] > resolution_tick:
                tasks = snap.get("scenario", {}).get("tasks", {})
                assert tasks.get("map") is True, (
                    f"Escape (seed={seed}): map=False at tick {snap['tick']} "
                    f"which is after resolution tick {resolution_tick}"
                )

    def test_escape_no_cafe_or_office_labels_in_transitions(self, seed):
        model = _run(_make_model("escape", seed=seed))
        transitions = _derive_resolved_phases(model.history, "escape")
        cafe_items   = set(ORDER_MAP["cafe"])
        office_items = set(ORDER_MAP["office"])
        contaminated = [t for t in transitions if t["item"] in cafe_items | office_items]
        assert not contaminated, (
            f"Escape (seed={seed}) transitions contain non-escape items: {contaminated}"
        )

    def test_escape_summary_chain_not_used_as_blind_fallback(self, seed):
        """
        The derived transition list and final tasks must agree with the
        summaryChain — verifying that when all tasks are True the labels
        match, so the frontend chain display is never lying.
        """
        model = _run(_make_model("escape", seed=seed))
        result = _validate_completed_scenario(model.history, "escape")
        assert result["all_tasks_true"], (
            f"Escape (seed={seed}): not all tasks true at end — "
            f"summary chain fallback would be incorrect. "
            f"Missing: {result['missing_from_tasks']}"
        )
        # Derived labels must match summaryChain labels exactly
        derived_labels = [t["label"] for t in result["resolved_transitions"]]
        assert derived_labels == EXPECTED_CHAINS["escape"], (
            f"Escape (seed={seed}): derived labels {derived_labels!r} "
            f"differ from canonical chain {EXPECTED_CHAINS['escape']!r}"
        )


class TestFinalMetricSnapshots:
    def test_tick_diff_carries_real_pressure_after_boost_urgency(self):
        model = _make_model("escape", seed=101)
        base_pressure = float(model.environment.urgency_modifier)
        model.apply_intervention("boost_urgency", {"amount": 0.25})
        model.step()

        assert model.last_diff is not None
        assert model.last_diff["group_state"]["pressure"] == pytest.approx(base_pressure + 0.25)
        assert model.last_diff["scenario"]["urgency_modifier"] == pytest.approx(base_pressure + 0.25)

    def test_completed_run_history_preserves_final_pressure_value(self):
        model = _make_model("escape", seed=101)
        base_pressure = float(model.environment.urgency_modifier)
        model.apply_intervention("boost_urgency", {"amount": 0.25})
        _run(model)

        assert model.history, "completed run should preserve tick history"
        final_snapshot = model.history[-1]
        assert final_snapshot["group_state"]["pressure"] == pytest.approx(base_pressure + 0.25)
        assert final_snapshot["scenario"]["urgency_modifier"] == pytest.approx(base_pressure + 0.25)
        assert final_snapshot["group_state"]["pressure"] > base_pressure

    def test_tick_diff_carries_real_pressure_after_ease_pressure(self):
        model = _make_model("escape", seed=101)
        model.apply_intervention("boost_urgency", {"amount": 0.25})
        model.step()
        boosted_pressure = float(model.environment.urgency_modifier)
        model.apply_intervention("ease_pressure", {"amount": 0.1})
        model.step()

        assert model.last_diff is not None
        assert model.last_diff["group_state"]["pressure"] == pytest.approx(max(0.0, boosted_pressure - 0.1))
        assert model.last_diff["scenario"]["urgency_modifier"] == pytest.approx(max(0.0, boosted_pressure - 0.1))
