"""Loads saved runs and reshapes them for the history and replay views.

Run files are stored as JSON in backend/data/runs/. Each file holds everything
the frontend needs: agent states, tick-by-tick history, metrics, interventions.

Key functions:
  save_run()     — serialise a finished SimModel to disk
  load_run()     — load one run by ID (with optional ownership check)
  list_runs()    — list all runs (sorted newest first)
  replay_run()   — return just the tick history for the replay panel
  compare_runs() — side-by-side metric diff between two runs
  prune_runs()   — clean up old/excess run files automatically

This is the storage / replay layer for finished runs.
If the live run system is "what is happening right now?",
this module is "what do we keep after the run ends?"
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

# Lock prevents two concurrent requests from pruning at the same time
_prune_lock = threading.Lock()

# All run files live in backend/data/runs/
RUNS_DIR = Path(__file__).resolve().parents[2] / "data" / "runs"
# Hard limits to stop the disk filling up over time
MAX_SAVED_RUNS = 50
MAX_RUN_AGE_DAYS = 14


def _ensure_dir() -> None:
    """Create the runs directory if it doesn't exist yet."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _run_path(run_id: str) -> Path:
    """Return the full path for a run file given its ID."""
    return RUNS_DIR / f"run_{run_id}.json"


def _iter_run_files() -> List[Path]:
    """Return all run JSON files, sorted alphabetically by name."""
    _ensure_dir()
    return sorted(RUNS_DIR.glob("run_*.json"))


def prune_runs(max_saved_runs: int = MAX_SAVED_RUNS, max_age_days: int = MAX_RUN_AGE_DAYS) -> int:
    """Delete old saved run files by age and retention count.

    Two pruning passes:
      1. Remove any file older than max_age_days (by filesystem mtime)
      2. If more than max_saved_runs files remain, delete the oldest ones

    Negative values for either param disables that pass.
    Returns the total number of files deleted.
    """
    with _prune_lock:
        removed = 0
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=max(0, max_age_days))

        files_with_time: List[tuple[Path, datetime]] = []
        for fpath in _iter_run_files():
            try:
                mtime = datetime.fromtimestamp(fpath.stat().st_mtime, tz=timezone.utc)
                # First pass: delete anything older than the cutoff date
                if max_age_days >= 0 and mtime < cutoff:
                    fpath.unlink(missing_ok=True)
                    removed += 1
                    continue
                files_with_time.append((fpath, mtime))
            except OSError:
                continue

        # Second pass: if we still have too many files, drop the oldest ones
        if max_saved_runs >= 0 and len(files_with_time) > max_saved_runs:
            # Sort newest-first so we can slice off the oldest at the end
            files_with_time.sort(key=lambda item: item[1], reverse=True)
            for fpath, _ in files_with_time[max_saved_runs:]:
                try:
                    fpath.unlink(missing_ok=True)
                    removed += 1
                except OSError:
                    continue

        if removed:
            logger.info("Pruned %s saved run file(s) from history", removed)
        return removed


# ──────────────────────────────────────────────────────────────────────────
# Run serialisation
# This section turns a finished SimModel into the JSON shape used by history,
# replay, dashboard results, and PDF export.
# ──────────────────────────────────────────────────────────────────────────

def build_run_summary(model, run_id: str, config: Optional[Dict[str, Any]] = None, owner: Optional[str] = None) -> Dict[str, Any]:
    """Build the full JSON structure that gets written to disk for a completed run.

    This is the most data-rich function in this module. It pulls together:
      - agent states (stress, trust, known items, strategy)
      - event counts (messages, clues, agreements, challenges)
      - metric trajectory (trust/stress start → peak → end)
      - blocker timeline (which constraints were active and for how long)
      - full tick-by-tick history for replay
      - interventions applied during the run

    Parameters
    ----------
    model  : the finished SimModel instance
    run_id : ID string that will be used as the filename
    config : the launch config to embed (scenario, ticks, team_type, etc.)
    owner  : email of the user who created this run, or None for anonymous
    """
    # The summary object is intentionally rich so frontend pages do not each
    # have to recalculate counts, peaks, chains, and replay metadata themselves.
    metrics = model.last_diff.get("metrics", {}) if model.last_diff else {}

    # Collect ALL interventions from the full run-level log (not just the last tick's diff).
    # model._applied_interventions_log is appended to by model.apply_intervention() for
    # every intervention across the whole run; model.last_diff["interventions"] only holds
    # the interventions that happened in the final tick, so it would always be [] for runs
    # where the last action was not an intervention.
    full_history_for_iv = getattr(model, "history", [])
    interventions = [
        iv
        for tick_data in full_history_for_iv
        for iv in tick_data.get("interventions", [])
    ]
    # Fallback: if history interventions are empty but the log has entries, synthesise
    # minimal records from _applied_interventions_log so the count is never lost.
    if not interventions:
        interventions = [
            {"type": t, "tick": None}
            for t in getattr(model, "_applied_interventions_log", [])
        ]
    # Strip None values from config before saving — keeps the JSON clean
    persisted_config = {k: v for k, v in (config or {}).items() if v is not None}

    # Compute whole-run peak tension and time_to_first_share from metric_history
    history = getattr(model, "metric_history", [])
    peak_tension = round(max((h["group_tension"] for h in history), default=0.0), 3)
    first_share_tick = next(
        (h["tick"] for h in history if h.get("share_count", 0) > 0), None
    )

    # Snapshot of each agent's final state at the end of the run
    agents_summary = [
        {
            "id":            a.public_id,
            "name":          a.public_id,
            "role":          getattr(a, "to_state", lambda: {})().get("role", a.public_id),
            "personality":   getattr(a, "personality_type", ""),
            "strategy":      a.strategy,
            "final_stress":  round(a.stress, 3),
            "final_valence": round(a.valence, 3),
            "known_items":   list(a.known_items),
            # Round trust values to 3dp to keep the JSON readable
            "trust":         {k: round(v, 3) for k, v in a.trust.items()},
        }
        for a in model.agents
    ]

    # ── Event counts ──────────────────────────────────────────────────────────
    # Tallied across every tick in model.history so the frontend can display
    # a behaviour summary (messages exchanged, clues shared, etc.) without
    # having to scan the full history array itself.
    full_history = getattr(model, "history", [])
    _ec_messages    = 0
    _ec_clues       = 0
    _ec_questions   = 0
    _ec_agreements  = 0
    _ec_challenges  = 0
    for tick_data in full_history:
        for ev in tick_data.get("events", []):
            t = ev.get("type", "")
            if ev.get("text"):
                _ec_messages += 1
            if t == "share_info":
                _ec_clues += 1
            elif t in ("ask_info", "request_info"):
                _ec_questions += 1
            elif t == "agree":
                _ec_agreements += 1
            elif t in ("refuse", "challenge", "push_back"):
                _ec_challenges += 1

    # Blockers resolved — tasks dict values are plain booleans (True = done)
    # in escape/office scenarios, or status-dicts in generic scenarios.
    tasks_dict = getattr(model.scenario, "tasks", {})
    _blockers_total    = len(tasks_dict)
    _blockers_resolved = sum(
        1 for v in tasks_dict.values()
        if (v.get("status") == "done" if isinstance(v, dict) else v is True)
    )
    _interventions_used = len(
        [iv for tick_data in full_history
         for iv in tick_data.get("interventions", [])]
    )

    event_counts = {
        "messages_exchanged": _ec_messages,
        "clues_shared":       _ec_clues,
        "questions_asked":    _ec_questions,
        "agreements":         _ec_agreements,
        "challenges":         _ec_challenges,
        "blockers_resolved":  _blockers_resolved,
        "blockers_total":     _blockers_total,
        "interventions_used": _interventions_used,
    }

    # ── Metric trajectory ─────────────────────────────────────────────────────
    # Precomputed from metric_history so the frontend doesn't have to scan the
    # full history array.  Captures where trust and stress started, peaked, and
    # ended so the completion modal can show directional change.
    mh = getattr(model, "metric_history", [])
    _mt_trust_start = round(mh[0]["avg_trust"],  3) if mh else 0.0
    _mt_trust_end   = round(mh[-1]["avg_trust"], 3) if mh else 0.0
    _stress_pairs   = [(h["tick"], round(h["avg_stress"], 3)) for h in mh]
    _mt_stress_start = _stress_pairs[0][1]  if _stress_pairs else 0.0
    _mt_stress_end   = _stress_pairs[-1][1] if _stress_pairs else 0.0
    _peak_entry      = max(_stress_pairs, key=lambda x: x[1]) if _stress_pairs else (0, 0.0)
    _mt_stress_peak_tick, _mt_stress_peak = _peak_entry

    metric_trajectory = {
        "trust_start":      _mt_trust_start,
        "trust_end":        _mt_trust_end,
        "trust_delta":      round(_mt_trust_end - _mt_trust_start, 3),
        "stress_start":     _mt_stress_start,
        "stress_peak":      _mt_stress_peak,
        "stress_peak_tick": _mt_stress_peak_tick,
        "stress_end":       _mt_stress_end,
    }

    # ── Progress timeline ─────────────────────────────────────────────────────
    # Scans metric_history for constraint/task transitions to build one timeline
    # entry per active blocker.
    #
    # Field priority:
    #   active_blocker — the constraint at the START of the tick (pre-resolution).
    #     This is the semantically correct field: it shows what was being actively
    #     worked on during a tick, including constraints that resolved in their very
    #     first tick (e.g. Café dietary_constraint resolved at tick 1 never becomes
    #     bottleneck_item because that field is updated after resolution).
    #   bottleneck_item — legacy fallback for runs saved before active_blocker was
    #     added to metric_history.
    blocker_timeline: list = []
    _prev_blocker  = None
    _blocker_start = 1
    for _h in mh:
        _item = _h.get("active_blocker") or _h.get("bottleneck_item")
        # When the active focus changes, close the previous segment and start a new one
        if _item != _prev_blocker:
            if _prev_blocker is not None:
                _end = _h["tick"] - 1
                blocker_timeline.append({
                    "item":       _prev_blocker,
                    "start_tick": _blocker_start,
                    "end_tick":   _end,
                    "duration":   max(1, _end - _blocker_start + 1),
                })
            if _item is not None:
                _blocker_start = _h["tick"]
            _prev_blocker = _item
    # Close the final open segment — the last blocker runs to the end of the simulation
    if _prev_blocker is not None and mh:
        _last = mh[-1]["tick"]
        blocker_timeline.append({
            "item":       _prev_blocker,
            "start_tick": _blocker_start,
            "end_tick":   _last,
            "duration":   max(1, _last - _blocker_start + 1),
        })

    # For escape rooms: "unlock" is the final door-open phase.
    # It is marked complete via mark_task_complete("unlock") but is never set
    # as bottleneck_item (it's not in ESCAPE_PRIORITY), so it never appears
    # in the timeline above.  Synthesise it from the final ticks so the
    # timeline is complete and blockers_total stays consistent.
    # Note: use model.scenario_type ("escape"), NOT model.scenario.id
    # ("escape_puzzle") — the id check silently failed and caused the unlock
    # entry to be skipped, making the timeline show only 4 of 5 blockers.
    if getattr(model, "scenario_type", "") == "escape":
        _unlock_done = getattr(model.scenario, "tasks", {}).get("unlock", False)
        if _unlock_done is True and not any(b["item"] == "unlock" for b in blocker_timeline):
            _last_run_tick = mh[-1]["tick"] if mh else model.tick
            # Unlock phase starts right after the last tracked blocker ends
            _ul_start = (blocker_timeline[-1]["end_tick"] + 1) if blocker_timeline else 1
            _ul_end   = _last_run_tick
            if _ul_start <= _ul_end:
                blocker_timeline.append({
                    "item":       "unlock",
                    "start_tick": _ul_start,
                    "end_tick":   _ul_end,
                    "duration":   max(1, _ul_end - _ul_start + 1),
                })

    # Reconcile blocker counts so event_counts and blocker_timeline always agree.
    # The timeline is more reliable here — it reflects what the user actually saw,
    # whereas the raw tasks dict can include tasks that were never tracked as
    # bottlenecks (e.g. a cafe "decision" task that resolved silently).
    if blocker_timeline:
        event_counts["blockers_total"] = len(blocker_timeline)
        _resolved_count = 0
        for _b in blocker_timeline:
            _v = tasks_dict.get(_b["item"], False)
            if isinstance(_v, dict):
                if _v.get("status") == "done":
                    _resolved_count += 1
            elif _v is True:
                _resolved_count += 1
        event_counts["blockers_resolved"] = _resolved_count

    from app.sim.metrics import classify_run_outcome, describe_run
    _outcome_label  = classify_run_outcome(model)
    _outcome_detail = describe_run(model)

    return {
        "run_id":         run_id,
        "owner":          owner,        # email of creating user; None means legacy/shared
        "scenario_id":    model.scenario.id,
        "scenario_name":  model.scenario.name,
        "team_preset":    getattr(model, "team_preset", None),
        "seed":           getattr(model, "seed_value", None),
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "config":         persisted_config,
        "outcome":        model.end_reason,
        "outcome_label":  _outcome_label,
        "outcome_detail": _outcome_detail,
        "ticks":          model.tick,
        "final_progress": round(model.scenario.progress_ratio(), 3),
        "metrics": {
            "avg_trust":      metrics.get("avg_trust", 0.0),
            "avg_stress":     metrics.get("avg_stress", 0.0),
            "conflict_rate":  metrics.get("cumulative_conflict_rate",
                               metrics.get("conflict_rate", 0.0)),
            "pressure":       round(getattr(model.environment, "urgency_modifier", 0.0), 3),
            "total_refusals": model.total_refusals,
            "total_shares":   model.total_shares,
            "stalled_ticks":  model.total_stalled_ticks,
            "group_tension":  round(model.group_tension, 3),
            "group_cohesion": round(model.group_cohesion, 3),
        },
        "group_state": {
            "tension":           round(model.group_tension, 3),
            "cohesion":          round(model.group_cohesion, 3),
            "pressure":          round(getattr(model.environment, "urgency_modifier", 0.0), 3),
            "stall_ticks":       model.progress_stall_ticks,
            "bottleneck_item":   model.bottleneck_item,
            "bottleneck_holder": model.bottleneck_holder,
        },
        "tasks":              dict(model.scenario.tasks),
        "completion_order":   getattr(model, "completion_order", []),
        "peak_tension":       peak_tension,
        "time_to_first_share": first_share_tick,
        "intervention_count": len(interventions),
        "interventions":      interventions,
        "agents":             agents_summary,
        # Full tick-by-tick history for replay
        # Stored as a list of tick diffs — each contains agents, events, metrics
        "history":            getattr(model, "history", []),
        # Memory impressions formed during the run
        "memory_summary":     model.memory_summary(),
        # User emotion injections applied during the run
        "emotion_summary":    model.emotion_summary(),
        # Behaviour event tallies for the run summary panel
        "event_counts":       event_counts,
        # Trust / stress movement across the run (start → peak → end)
        "metric_trajectory":  metric_trajectory,
        # Per-blocker step ranges for the timeline panel
        "blocker_timeline":   blocker_timeline,
    }


def save_run(
    model,
    run_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    owner: Optional[str] = None,
) -> str:
    """Serialise a completed SimModel to a JSON file and return the run ID.

    Generates a random 8-character ID if one isn't provided.
    Prunes old runs before saving to keep disk usage under control.
    """
    _ensure_dir()
    prune_runs()
    if run_id is None:
        # Use first 8 chars of UUID for short but unique IDs
        run_id = str(uuid.uuid4())[:8]
    summary = build_run_summary(model, run_id, config=config, owner=owner)
    run_path = _run_path(run_id)
    with open(run_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Run saved: id={run_id}, outcome={model.end_reason}, ticks={model.tick}")
    return run_id


# ──────────────────────────────────────────────────────────────────────────
# Run lookup / listing
# Read saved runs back from disk for history, replay, and dashboard views.
# ──────────────────────────────────────────────────────────────────────────
def load_run(run_id: str, owner: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load a saved run by ID.

    Ownership filtering is applied **only when** *owner* is a non-None value.
    When *owner* is ``None`` (no authentication / anonymous), all runs are
    accessible — this keeps the app functional when login is not in use.
    When *owner* is a specific email string, only runs saved by that user are
    returned; a mismatched run is treated as not found.
    """
    path = _run_path(run_id)
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    # Apply ownership filter only when a specific owner is supplied
    if owner is not None and data.get("owner") != owner:
        return None
    return data


def list_runs(scenario_id: Optional[str] = None, owner: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return a list of saved run summaries, sorted newest first.

    Optionally filter by scenario_id or owner email. When owner is None,
    all runs are returned regardless of who created them (for anonymous use).
    """
    _ensure_dir()
    prune_runs()
    runs = []
    for fpath in RUNS_DIR.glob("run_*.json"):
        try:
            with open(fpath) as f:
                data = json.load(f)
            config = data.get("config", {}) or {}
            # Skip this run if it doesn't match the requested scenario
            if scenario_id and data.get("scenario_id") != scenario_id:
                continue
            timestamp = data.get("timestamp")
            if not timestamp:
                # Fall back to filesystem mtime for legacy run files that lack a timestamp
                timestamp = datetime.fromtimestamp(
                    fpath.stat().st_mtime,
                    tz=timezone.utc,
                ).isoformat()
            # Apply ownership filter only when a specific owner is supplied.
            # owner=None (no auth) returns all runs so History works without login.
            if owner is not None and data.get("owner") != owner:
                continue
            runs.append({
                "run_id":             data["run_id"],
                "scenario_id":        data["scenario_id"],
                "scenario_name":      data.get("scenario_name", ""),
                "seed":               data.get("seed"),
                "timestamp":          timestamp,
                "outcome":            data.get("outcome"),
                "outcome_label":      data.get("outcome_label"),
                "ticks":              data.get("ticks"),
                "final_progress":     data.get("final_progress"),
                "metrics":            data.get("metrics", {}),
                "metric_trajectory":  data.get("metric_trajectory"),
                "peak_tension":       data.get("peak_tension"),
                "group_state":        data.get("group_state", {}),
                "team_preset":        data.get("team_preset"),
                "intervention_count": data.get("intervention_count", 0),
                "environment":        config.get("environment"),
                "team_type":          config.get("team_type"),
                "goal":               config.get("goal"),
                "config":             config,
                "tasks":              data.get("tasks", {}),
            })
        except (json.JSONDecodeError, KeyError):
            logger.warning("Skipping malformed run file: %s", fpath.name)
            continue
    runs.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return runs


def delete_run(run_id: str, owner: Optional[str] = None) -> bool:
    """Delete a saved run."""
    path = _run_path(run_id)
    if not path.exists():
        logger.warning(f"Delete requested for non-existent run: id={run_id}")
        return False
    path.unlink()
    logger.info(f"Run deleted: id={run_id}")
    return True


def clear_runs(owner: Optional[str] = None) -> int:
    """Delete all saved run files and return the number removed."""
    removed = 0
    for fpath in _iter_run_files():
        try:
            fpath.unlink()
            removed += 1
        except OSError:
            continue
        except Exception:
            continue
    logger.info("Cleared %s saved run file(s) from history", removed)
    return removed


# ──────────────────────────────────────────────────────────────────────────
# Replay + comparison
# These helpers reshape saved runs for replay mode and side-by-side review.
# ──────────────────────────────────────────────────────────────────────────
def replay_run(run_id: str, owner: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """Return the full tick-by-tick history for a saved run.

    Passes *owner* to load_run() so ownership is enforced consistently.
    Returns None if the run is not found or the caller does not own it.
    """
    run = load_run(run_id, owner=owner)
    if run is None:
        logger.warning(f"Replay requested for non-existent/unauthorized run: id={run_id}")
        return None
    history = run.get("history", [])
    logger.debug(f"Replay loaded: id={run_id}, ticks={len(history)}")
    return history


def compare_runs(run_id_a: str, run_id_b: str, owner: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Compare two saved runs side-by-side and return per-metric deltas.

    Returns None if either run can't be found or isn't owned by the caller.
    The "better" field on each metric indicates which run performed better
    on that metric (higher trust = better, lower stress = better, etc.).
    """
    run_a = load_run(run_id_a, owner=owner)
    run_b = load_run(run_id_b, owner=owner)
    if run_a is None or run_b is None:
        return None

    def _delta(key: str, source: str = "metrics") -> Dict[str, Any]:
        """Extract a value from a specific sub-dict of each run and compute the diff."""
        src_a = run_a.get(source, {}) if source else run_a
        src_b = run_b.get(source, {}) if source else run_b
        a_val = src_a.get(key, 0) if isinstance(src_a, dict) else run_a.get(key, 0)
        b_val = src_b.get(key, 0) if isinstance(src_b, dict) else run_b.get(key, 0)
        # delta is always b - a, so positive means run_b is higher
        return {"run_a": a_val, "run_b": b_val, "delta": round(b_val - a_val, 4)}

    m_a, m_b = run_a.get("metrics", {}), run_b.get("metrics", {})

    return {
        "run_a_id":      run_id_a,
        "run_b_id":      run_id_b,
        # These flags help the UI show contextual labels like "same scenario"
        "same_scenario": run_a.get("scenario_id") == run_b.get("scenario_id"),
        "same_seed":     run_a.get("seed") == run_b.get("seed"),
        "scenario":      {"run_a": run_a.get("scenario_id"), "run_b": run_b.get("scenario_id")},
        "outcome":       {"run_a": run_a.get("outcome"),     "run_b": run_b.get("outcome")},

        # source=None means look at the top-level run dict, not the "metrics" sub-dict
        "ticks":          _delta("ticks",          source=None),
        "final_progress": _delta("final_progress", source=None),

        # "better" tells the UI which run won on each metric
        "avg_trust":      {**_delta("avg_trust"),      "better": "run_a" if m_a.get("avg_trust", 0)      > m_b.get("avg_trust", 0)      else "run_b"},
        "avg_stress":     {**_delta("avg_stress"),     "better": "run_a" if m_a.get("avg_stress", 0)     < m_b.get("avg_stress", 0)     else "run_b"},
        "conflict_rate":  {**_delta("conflict_rate"),  "better": "run_a" if m_a.get("conflict_rate", 0)  < m_b.get("conflict_rate", 0)  else "run_b"},
        "total_shares":   {**_delta("total_shares"),   "better": "run_a" if m_a.get("total_shares", 0)   > m_b.get("total_shares", 0)   else "run_b"},
        "total_refusals": {**_delta("total_refusals"), "better": "run_a" if m_a.get("total_refusals", 0) < m_b.get("total_refusals", 0) else "run_b"},
        "group_tension":  _delta("group_tension"),
        "group_cohesion": _delta("group_cohesion"),

        # Fewer ticks to finish = faster; use 999 as a fallback for unfinished runs
        "faster_completion": "run_a" if (run_a.get("ticks") or 999) < (run_b.get("ticks") or 999) else "run_b",

        "interventions": {
            "run_a_count": run_a.get("intervention_count", 0),
            "run_b_count": run_b.get("intervention_count", 0),
            "run_a_types": [i["type"] for i in run_a.get("interventions", [])],
            "run_b_types": [i["type"] for i in run_b.get("interventions", [])],
        },
        "tasks":       {"run_a": run_a.get("tasks", {}), "run_b": run_b.get("tasks", {})},
        "group_state": {"run_a": run_a.get("group_state", {}), "run_b": run_b.get("group_state", {})},
    }
