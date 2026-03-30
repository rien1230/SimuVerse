from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RUNS_DIR = Path(__file__).resolve().parents[2] / "data" / "runs"


def _ensure_dir() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _run_path(run_id: str) -> Path:
    return RUNS_DIR / f"run_{run_id}.json"


def build_run_summary(model, run_id: str) -> Dict[str, Any]:
    metrics       = model.last_diff.get("metrics", {})      if model.last_diff else {}
    interventions = model.last_diff.get("interventions", []) if model.last_diff else []

    # Compute whole-run peak tension and time_to_first_share from metric_history
    history = getattr(model, "metric_history", [])
    peak_tension = round(max((h["group_tension"] for h in history), default=0.0), 3)
    first_share_tick = next(
        (h["tick"] for h in history if h.get("share_count", 0) > 0), None
    )

    agents_summary = [
        {
            "id":            a.public_id,
            "strategy":      a.strategy,
            "final_stress":  round(a.stress, 3),
            "final_valence": round(a.valence, 3),
            "known_items":   list(a.known_items),
            "trust":         {k: round(v, 3) for k, v in a.trust.items()},
        }
        for a in model.agents
    ]

    return {
        "run_id":         run_id,
        "scenario_id":    model.scenario.id,
        "scenario_name":  model.scenario.name,
        "seed":           getattr(model, "seed_value", None),
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "outcome":        model.end_reason,
        "ticks":          model.tick,
        "final_progress": round(model.scenario.progress_ratio(), 3),
        "metrics": {
            "avg_trust":      metrics.get("avg_trust", 0.0),
            "avg_stress":     metrics.get("avg_stress", 0.0),
            "conflict_rate":  metrics.get("conflict_rate", 0.0),
            "total_refusals": model.total_refusals,
            "total_shares":   model.total_shares,
            "stalled_ticks":  model.total_stalled_ticks,
            "group_tension":  round(model.group_tension, 3),
            "group_cohesion": round(model.group_cohesion, 3),
        },
        "group_state": {
            "tension":           round(model.group_tension, 3),
            "cohesion":          round(model.group_cohesion, 3),
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
    }


def save_run(model, run_id: Optional[str] = None) -> str:
    _ensure_dir()
    if run_id is None:
        run_id = str(uuid.uuid4())[:8]
    summary = build_run_summary(model, run_id)
    with open(_run_path(run_id), "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Run saved: id={run_id}, outcome={model.end_reason}, ticks={model.tick}")
    return run_id


def load_run(run_id: str) -> Optional[Dict[str, Any]]:
    path = _run_path(run_id)
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def list_runs(scenario_id: Optional[str] = None) -> List[Dict[str, Any]]:
    _ensure_dir()
    runs = []
    for fpath in RUNS_DIR.glob("run_*.json"):
        try:
            with open(fpath) as f:
                data = json.load(f)
            if scenario_id and data.get("scenario_id") != scenario_id:
                continue
            runs.append({
                "run_id":             data["run_id"],
                "scenario_id":        data["scenario_id"],
                "scenario_name":      data.get("scenario_name", ""),
                "seed":               data.get("seed"),
                "timestamp":          data.get("timestamp"),
                "outcome":            data.get("outcome"),
                "ticks":              data.get("ticks"),
                "final_progress":     data.get("final_progress"),
                "metrics":            data.get("metrics", {}),
                "intervention_count": data.get("intervention_count", 0),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    runs.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return runs


def delete_run(run_id: str) -> bool:
    path = _run_path(run_id)
    if path.exists():
        path.unlink()
        logger.info(f"Run deleted: id={run_id}")
        return True
    logger.warning(f"Delete requested for non-existent run: id={run_id}")
    return False


def replay_run(run_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Return the full tick-by-tick history for a saved run.
    Returns None if the run is not found.
    """
    run = load_run(run_id)
    if run is None:
        logger.warning(f"Replay requested for non-existent run: id={run_id}")
        return None
    history = run.get("history", [])
    logger.debug(f"Replay loaded: id={run_id}, ticks={len(history)}")
    return history


def compare_runs(run_id_a: str, run_id_b: str) -> Optional[Dict[str, Any]]:
    run_a = load_run(run_id_a)
    run_b = load_run(run_id_b)
    if run_a is None or run_b is None:
        return None

    def _delta(key: str, source: str = "metrics") -> Dict[str, Any]:
        src_a = run_a.get(source, {}) if source else run_a
        src_b = run_b.get(source, {}) if source else run_b
        a_val = src_a.get(key, 0) if isinstance(src_a, dict) else run_a.get(key, 0)
        b_val = src_b.get(key, 0) if isinstance(src_b, dict) else run_b.get(key, 0)
        return {"run_a": a_val, "run_b": b_val, "delta": round(b_val - a_val, 4)}

    m_a, m_b = run_a.get("metrics", {}), run_b.get("metrics", {})

    return {
        "run_a_id":      run_id_a,
        "run_b_id":      run_id_b,
        "same_scenario": run_a.get("scenario_id") == run_b.get("scenario_id"),
        "same_seed":     run_a.get("seed") == run_b.get("seed"),
        "scenario":      {"run_a": run_a.get("scenario_id"), "run_b": run_b.get("scenario_id")},
        "outcome":       {"run_a": run_a.get("outcome"),     "run_b": run_b.get("outcome")},

        "ticks":          _delta("ticks",          source=None),
        "final_progress": _delta("final_progress", source=None),

        "avg_trust":      {**_delta("avg_trust"),      "better": "run_a" if m_a.get("avg_trust", 0)      > m_b.get("avg_trust", 0)      else "run_b"},
        "avg_stress":     {**_delta("avg_stress"),     "better": "run_a" if m_a.get("avg_stress", 0)     < m_b.get("avg_stress", 0)     else "run_b"},
        "conflict_rate":  {**_delta("conflict_rate"),  "better": "run_a" if m_a.get("conflict_rate", 0)  < m_b.get("conflict_rate", 0)  else "run_b"},
        "total_shares":   {**_delta("total_shares"),   "better": "run_a" if m_a.get("total_shares", 0)   > m_b.get("total_shares", 0)   else "run_b"},
        "total_refusals": {**_delta("total_refusals"), "better": "run_a" if m_a.get("total_refusals", 0) < m_b.get("total_refusals", 0) else "run_b"},
        "group_tension":  _delta("group_tension"),
        "group_cohesion": _delta("group_cohesion"),

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