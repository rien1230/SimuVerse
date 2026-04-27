"""Service helpers for building and running experiment batches."""

from __future__ import annotations

import logging
import statistics
from typing import Any, Dict, List, Optional

from app.services.run_history_service import save_run
from app.sim.model import SimModel
from app.sim.scenario_data import SCENARIOS, resolve_scenario_id
from app.core.config import DEFAULT_N_RUNS, DEFAULT_EXPERIMENT_MAX_TICKS

logger = logging.getLogger(__name__)

DEFAULT_TEAM_STYLE_SET = ["smooth", "tension", "creative"]
DEFAULT_SCENARIO_SET = ["office_proposal", "cafe_restaurant", "escape_puzzle"]


def _normalize_scenario_ids(scenario_ids: List[str]) -> List[str]:
    initialised: List[str] = []
    seen = set()
    for scenario_id in scenario_ids:
        resolved = resolve_scenario_id(scenario_id)
        if resolved not in seen:
            initialised.append(resolved)
            seen.add(resolved)
    return initialised


def _display_team_type(team_type: Optional[str]) -> str:
    labels = {
        "smooth": "Smooth Team",
        "tension": "Tension Team",
        "creative": "Creative Team",
        "pressure": "Pressure Team",
        "balanced": "Balanced Team",
        "cooperative": "Cooperative Team",
        "tense": "Tense Team",
        "random": "Random Team",
    }
    key = str(team_type or "not_recorded").lower()
    return labels.get(key, str(team_type or "Not recorded").replace("_", " ").title())


def _run_single_simulation(
    scenario_id: str,
    seed: int,
    episode_max_ticks: int,
    skip_emotions: bool = False,
    team_type: Optional[str] = None,
    persist_run: bool = False,
    experiment_type: Optional[str] = None,
) -> Dict[str, Any]:
    scenario_id = resolve_scenario_id(scenario_id)
    if scenario_id not in SCENARIOS:
        return {"error": f"Unknown scenario '{scenario_id}'"}

    model = SimModel(
        seed=seed,
        scenario_id=scenario_id,
        environment=SCENARIOS[scenario_id]["environment"],
        episode_max_ticks=episode_max_ticks,
        team_type=team_type,
    )
    model.seed_value = seed
    if skip_emotions:
        model.skip_emotions = True

    while not model.ended and model.tick < episode_max_ticks:
        model.step()

    history = model.metric_history
    if history:
        run_avg_trust = round(statistics.mean(h["avg_trust"] for h in history), 4)
        run_avg_stress = round(statistics.mean(h["avg_stress"] for h in history), 4)
        run_conflict_rate = round(statistics.mean(h["conflict_rate"] for h in history), 4)
        run_group_tension = round(statistics.mean(h["group_tension"] for h in history), 4)
        run_group_cohesion = round(statistics.mean(h["group_cohesion"] for h in history), 4)
        run_peak_stress = round(max(h["avg_stress"] for h in history), 4)
        run_peak_tension = round(max(h["group_tension"] for h in history), 4)
    else:
        # No metric history: fall back to last_diff metrics, then live model state.
        # Avoids reporting 0.00 for peak_stress on runs that ended before recording any tick.
        metrics = model.last_diff.get("metrics", {}) if model.last_diff else {}
        run_avg_trust = metrics.get("avg_trust", model.group_cohesion)
        run_avg_stress = metrics.get("avg_stress", 0.0)
        run_conflict_rate = metrics.get("conflict_rate", 0.0)
        run_group_tension = model.group_tension
        run_group_cohesion = model.group_cohesion
        # Derive peak_stress from live agent state if metric history is absent
        if model.agents:
            agent_stresses = [getattr(a, "stress", 0.0) for a in model.agents]
            run_peak_stress = round(max(run_avg_stress, max(agent_stresses, default=0.0)), 4)
        else:
            run_peak_stress = run_avg_stress
        run_peak_tension = model.group_tension

    first_share_tick = next(
        (h["tick"] for h in history if h.get("share_count", 0) > 0),
        None,
    )

    run_id = None
    if persist_run:
        run_id = save_run(
            model,
            config={
                "scenario_id": scenario_id,
                "environment": SCENARIOS[scenario_id]["environment"],
                "episode_max_ticks": episode_max_ticks,
                "team_type": team_type,
                "use_nlp": not skip_emotions,
                "experiment_type": experiment_type,
            },
        )

    return {
        "run_id": run_id,
        "seed": seed,
        "scenario_id": scenario_id,
        "scenario_name": SCENARIOS[scenario_id]["name"],
        "environment": SCENARIOS[scenario_id]["environment"],
        "team_type": team_type,
        "team_label": _display_team_type(team_type),
        "outcome": model.end_reason,
        "ticks": model.tick,
        "final_progress": round(model.scenario.progress_ratio(), 3),
        "avg_trust": run_avg_trust,
        "avg_stress": run_avg_stress,
        "peak_stress": run_peak_stress,
        "conflict_rate": run_conflict_rate,
        "group_tension": run_group_tension,
        "peak_tension": run_peak_tension,
        "group_cohesion": run_group_cohesion,
        "total_refusals": model.total_refusals,
        "total_shares": model.total_shares,
        "stalled_ticks": model.total_stalled_ticks,
        "first_share_tick": first_share_tick,
        "completion_order": getattr(model, "completion_order", []),
    }


def run_experiment(
    scenario_id: str,
    n_runs: int = 20,
    episode_max_ticks: int = 120,
    skip_emotions: bool = False,
    team_type: Optional[str] = None,
    persist_runs: bool = False,
) -> Dict[str, Any]:
    """
    Run the same scenario n_runs times with seeds 0..n_runs-1.
    Uses whole-run metric averages (not just final tick) for accurate results.

    Parameters
    ----------
    scenario_id       : which scenario to run
    n_runs            : number of independent runs (recommend 20-50)
    episode_max_ticks : hard tick limit per run
    skip_emotions     : disable NLP pipeline for baseline comparison
    """
    scenario_id = resolve_scenario_id(scenario_id)
    if scenario_id not in SCENARIOS:
        return {"error": f"Unknown scenario '{scenario_id}'. Valid: {list(SCENARIOS.keys())}"}

    logger.info(
        "Starting experiment: scenario=%s, n_runs=%s, max_ticks=%s, nlp=%s, team=%s",
        scenario_id,
        n_runs,
        episode_max_ticks,
        "off" if skip_emotions else "on",
        team_type or "default",
    )

    results = []

    for seed in range(n_runs):
        logger.debug("  Run %s/%s (seed=%s)", seed + 1, n_runs, seed)
        results.append(
            _run_single_simulation(
                scenario_id=scenario_id,
                seed=seed,
                episode_max_ticks=episode_max_ticks,
                skip_emotions=skip_emotions,
                team_type=team_type,
                persist_run=persist_runs,
                experiment_type="batch",
            )
        )

    result = _aggregate(scenario_id, n_runs, skip_emotions, results)
    result["team_type"] = team_type
    logger.info(
        "Experiment complete: success_rate=%s, deadlock_rate=%s",
        f"{result['success_rate']:.0%}",
        f"{result['outcome_rates'].get('deadlock', 0):.0%}",
    )
    return result


def run_multi_scenario_experiment(
    scenario_ids: List[str],
    n_runs: int = 20,
    episode_max_ticks: int = 120,
    team_type: Optional[str] = None,
    persist_runs: bool = False,
) -> Dict[str, Any]:
    """
    Run multiple scenarios and return results for all of them.
    Useful for cross-scenario comparison in the dissertation.
    """
    results = {}
    for sid in _normalize_scenario_ids(scenario_ids):
        if sid not in SCENARIOS:
            results[sid] = {"error": f"Unknown scenario '{sid}'"}
            continue
        results[sid] = run_experiment(
            scenario_id=sid,
            n_runs=n_runs,
            episode_max_ticks=episode_max_ticks,
            skip_emotions=False,
            team_type=team_type,
            persist_runs=persist_runs,
        )
    return results


def _aggregate(
    scenario_id: str,
    n_runs: int,
    skip_emotions: bool,
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    outcomes = [r["outcome"] for r in results]
    outcome_counts = {
        "success":   outcomes.count("success"),
        "partial":   outcomes.count("partial"),
        "failure":   outcomes.count("failure"),
        "meltdown":  outcomes.count("meltdown"),
        "deadlock":  outcomes.count("deadlock"),
        "harmony":   outcomes.count("harmony"),
        "max_ticks": outcomes.count("max_ticks"),
    }
    outcome_rates = {k: round(v / n_runs, 3) for k, v in outcome_counts.items()}

    def _stats(key: str) -> Dict[str, float]:
        vals = [r[key] for r in results if r.get(key) is not None]
        if not vals:
            return {"mean": 0.0, "median": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0}
        return {
            "mean":   round(statistics.mean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "stdev":  round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
            "min":    round(min(vals), 4),
            "max":    round(max(vals), 4),
        }

    total_ref   = sum(r["total_refusals"] for r in results)
    total_share = sum(r["total_shares"]   for r in results)
    ref_share_ratio = round(total_ref / total_share, 3) if total_share > 0 else None

    success_ticks = [r["ticks"] for r in results if r["outcome"] == "success"]
    avg_ticks_to_success = round(statistics.mean(success_ticks), 2) if success_ticks else None

    first_share_ticks = [r["first_share_tick"] for r in results if r.get("first_share_tick")]
    avg_first_share_tick = round(statistics.mean(first_share_ticks), 2) if first_share_ticks else None

    return {
        "scenario_id":            scenario_id,
        "n_runs":                 n_runs,
        "mode":                   "nlp_off" if skip_emotions else "nlp_on",
        "nlp_enabled":            not skip_emotions,
        "outcome_counts":         outcome_counts,
        "outcome_rates":          outcome_rates,
        "success_rate":           outcome_rates.get("success", 0.0),
        "avg_ticks_to_success":   avg_ticks_to_success,
        "avg_first_share_tick":   avg_first_share_tick,
        "refusal_to_share_ratio": ref_share_ratio,
        # Whole-run average metrics
        "ticks":           _stats("ticks"),
        "final_progress":  _stats("final_progress"),
        "avg_trust":       _stats("avg_trust"),
        "avg_stress":      _stats("avg_stress"),
        "peak_stress":     _stats("peak_stress"),
        "conflict_rate":   _stats("conflict_rate"),
        "group_tension":   _stats("group_tension"),
        "peak_tension":    _stats("peak_tension"),
        "group_cohesion":  _stats("group_cohesion"),
        "total_refusals":  _stats("total_refusals"),
        "total_shares":    _stats("total_shares"),
        "stalled_ticks":   _stats("stalled_ticks"),
        "per_run":         results,
    }


def compare_team_styles(
    scenario_id: str,
    seed: int = 5902,
    episode_max_ticks: int = 120,
    team_types: Optional[List[str]] = None,
    persist_runs: bool = True,
) -> Dict[str, Any]:
    scenario_id = resolve_scenario_id(scenario_id)
    if scenario_id not in SCENARIOS:
        return {"error": f"Unknown scenario '{scenario_id}'"}

    selected_team_types = list(team_types or DEFAULT_TEAM_STYLE_SET)
    rows = [
        _run_single_simulation(
            scenario_id=scenario_id,
            seed=seed,
            episode_max_ticks=episode_max_ticks,
            team_type=team_type,
            persist_run=persist_runs,
            experiment_type="team_styles",
        )
        for team_type in selected_team_types
    ]

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row.get("final_progress", 0),
            row.get("avg_trust", 0),
            -row.get("peak_stress", 0),
            -row.get("conflict_rate", 0),
        ),
        reverse=True,
    )
    best = sorted_rows[0]
    worst = sorted_rows[-1]
    key_difference = (
        f"Only team style changed. Scenario and seed stayed fixed at "
        f"{SCENARIOS[scenario_id]['name']} and {seed}. "
        f"{best['team_label']} finished at {round(best['final_progress'] * 100)}% progress "
        f"with trust {best['avg_trust']:.2f} and peak stress {best['peak_stress']:.2f}, "
        f"while {worst['team_label']} ended at {round(worst['final_progress'] * 100)}% "
        f"with conflict {worst['conflict_rate']:.2f}."
    )

    return {
        "experiment": "team_styles",
        "scenario_id": scenario_id,
        "scenario_name": SCENARIOS[scenario_id]["name"],
        "seed": seed,
        "rows": rows,
        "controlled_variable": "team_style",
        "fixed_factors": {
            "scenario_id": scenario_id,
            "seed": seed,
            "episode_max_ticks": episode_max_ticks,
            "nlp_enabled": False,
        },
        "method_note": "Only team style changes here. Scenario, seed, and tick limit stay fixed for every row.",
        "key_difference": key_difference,
    }


def compare_scenarios(
    team_type: str,
    seed: int = 5902,
    episode_max_ticks: int = 120,
    scenario_ids: Optional[List[str]] = None,
    persist_runs: bool = True,
) -> Dict[str, Any]:
    selected_scenarios = _normalize_scenario_ids(list(scenario_ids or DEFAULT_SCENARIO_SET))
    rows = [
        _run_single_simulation(
            scenario_id=scenario_id,
            seed=seed,
            episode_max_ticks=episode_max_ticks,
            team_type=team_type,
            persist_run=persist_runs,
            experiment_type="scenario_pressure",
        )
        for scenario_id in selected_scenarios
        if scenario_id in SCENARIOS
    ]

    highest_stress = max(rows, key=lambda row: row.get("peak_stress", 0))
    calmest = min(rows, key=lambda row: row.get("peak_stress", 0))
    key_difference = (
        f"Only scenario changed. Team style stayed fixed as {rows[0]['team_label']} and seed stayed fixed at {seed}. "
        f"{highest_stress['scenario_name']} produced the highest peak stress ({highest_stress['peak_stress']:.2f}), "
        f"while {calmest['scenario_name']} stayed calmest at {calmest['peak_stress']:.2f}. "
        f"This isolates environment pressure rather than personality changes."
    )

    return {
        "experiment": "scenarios",
        "team_type": team_type,
        "team_label": _display_team_type(team_type),
        "seed": seed,
        "rows": rows,
        "controlled_variable": "scenario",
        "fixed_factors": {
            "team_type": team_type,
            "seed": seed,
            "episode_max_ticks": episode_max_ticks,
            "nlp_enabled": False,
        },
        "method_note": "Only the scenario changes here. Team style, seed, and tick limit stay fixed for every row.",
        "key_difference": key_difference,
    }


def robustness_experiment(
    scenario_id: str,
    team_type: str,
    seed_start: int = 5902,
    n_runs: int = 5,
    episode_max_ticks: int = 120,
    persist_runs: bool = True,
) -> Dict[str, Any]:
    scenario_id = resolve_scenario_id(scenario_id)
    if scenario_id not in SCENARIOS:
        return {"error": f"Unknown scenario '{scenario_id}'"}

    rows = [
        _run_single_simulation(
            scenario_id=scenario_id,
            seed=seed_start + offset,
            episode_max_ticks=episode_max_ticks,
            team_type=team_type,
            persist_run=persist_runs,
            experiment_type="robustness",
        )
        for offset in range(n_runs)
    ]

    aggregate = _aggregate(scenario_id, n_runs, skip_emotions=False, results=rows)
    aggregate["team_type"] = team_type
    aggregate["seed_start"] = seed_start

    progress_spread = aggregate["final_progress"]["max"] - aggregate["final_progress"]["min"]
    key_difference = (
        f"Only seed changed. Scenario stayed fixed as {SCENARIOS[scenario_id]['name']} and team style stayed fixed as "
        f"{_display_team_type(team_type)}. Across {n_runs} seeds starting at {seed_start}, "
        f"average progress was {round(aggregate['final_progress']['mean'] * 100)}% and success rate was "
        f"{round(aggregate['success_rate'] * 100)}%. Progress spread across seeds was {round(progress_spread * 100)} points."
    )

    return {
        "experiment": "robustness",
        "scenario_id": scenario_id,
        "scenario_name": SCENARIOS[scenario_id]["name"],
        "team_type": team_type,
        "team_label": _display_team_type(team_type),
        "seed_start": seed_start,
        "n_runs": n_runs,
        "rows": rows,
        "aggregate": aggregate,
        "controlled_variable": "seed",
        "fixed_factors": {
            "scenario_id": scenario_id,
            "team_type": team_type,
            "episode_max_ticks": episode_max_ticks,
            "nlp_enabled": False,
        },
        "method_note": "Only the seed changes here. Scenario, team style, and tick limit stay fixed for every run.",
        "key_difference": key_difference,
    }


def compare_experiments(
    scenario_id: str,
    n_runs: int = 20,
    episode_max_ticks: int = 120,
) -> Dict[str, Any]:
    """
    Key academic experiment: same scenario, NLP on vs NLP off.
    Directly answers: does the emotion pipeline affect coordination outcomes?
    """
    scenario_id = resolve_scenario_id(scenario_id)
    with_nlp    = run_experiment(scenario_id, n_runs, episode_max_ticks, skip_emotions=False)
    without_nlp = run_experiment(scenario_id, n_runs, episode_max_ticks, skip_emotions=True)

    def _safe_get(data: Dict, key: str, subkey: str = "mean") -> float:
        val = data.get(key)
        if isinstance(val, dict):
            return val.get(subkey, 0.0)
        return float(val) if val is not None else 0.0

    def _diff(key: str) -> Dict[str, Any]:
        a = _safe_get(with_nlp, key)
        b = _safe_get(without_nlp, key)
        return {"with_nlp": a, "without_nlp": b, "delta": round(a - b, 4)}

    def _outcome_diff(key: str) -> Dict[str, Any]:
        a = with_nlp["outcome_rates"].get(key, 0)
        b = without_nlp["outcome_rates"].get(key, 0)
        return {"with_nlp": a, "without_nlp": b, "delta": round(a - b, 4)}

    return {
        "scenario_id":  scenario_id,
        "n_runs_each":  n_runs,
        "experiment":   "NLP on vs NLP off",

        "success_rate":  _outcome_diff("success"),
        "failure_rate":  _outcome_diff("failure"),
        "deadlock_rate": _outcome_diff("deadlock"),
        "partial_rate":  _outcome_diff("partial"),

        "avg_trust":      {**_diff("avg_trust"),      "nlp_better": _safe_get(with_nlp, "avg_trust")      > _safe_get(without_nlp, "avg_trust")},
        "avg_stress":     {**_diff("avg_stress"),     "nlp_better": _safe_get(with_nlp, "avg_stress")     < _safe_get(without_nlp, "avg_stress")},
        "peak_stress":    {**_diff("peak_stress"),    "nlp_better": _safe_get(with_nlp, "peak_stress")    < _safe_get(without_nlp, "peak_stress")},
        "conflict_rate":  {**_diff("conflict_rate"),  "nlp_better": _safe_get(with_nlp, "conflict_rate")  < _safe_get(without_nlp, "conflict_rate")},
        "total_shares":   {**_diff("total_shares"),   "nlp_better": _safe_get(with_nlp, "total_shares")   > _safe_get(without_nlp, "total_shares")},
        "total_refusals": {**_diff("total_refusals"), "nlp_better": _safe_get(with_nlp, "total_refusals") < _safe_get(without_nlp, "total_refusals")},
        "stalled_ticks":  {**_diff("stalled_ticks"),  "nlp_better": _safe_get(with_nlp, "stalled_ticks")  < _safe_get(without_nlp, "stalled_ticks")},
        "group_tension":  {**_diff("group_tension"),  "nlp_better": _safe_get(with_nlp, "group_tension")  < _safe_get(without_nlp, "group_tension")},

        "ticks_to_success": {
            "with_nlp":    with_nlp.get("avg_ticks_to_success"),
            "without_nlp": without_nlp.get("avg_ticks_to_success"),
        },
        "first_share_tick": {
            "with_nlp":    with_nlp.get("avg_first_share_tick"),
            "without_nlp": without_nlp.get("avg_first_share_tick"),
        },
        "refusal_to_share_ratio": {
            "with_nlp":    with_nlp.get("refusal_to_share_ratio"),
            "without_nlp": without_nlp.get("refusal_to_share_ratio"),
        },

        "summary": _generate_summary(with_nlp, without_nlp),

        "full_with_nlp":    with_nlp,
        "full_without_nlp": without_nlp,
    }


def compare_intervention_experiment(
    scenario_id: str,
    intervention_type: str,
    intervention_params: Dict[str, Any],
    intervention_tick: int = 5,
    n_runs: int = 20,
    episode_max_ticks: int = 120,
) -> Dict[str, Any]:
    """
    Compare runs with and without a specific intervention applied at a fixed tick.
    Directly answers: does this intervention improve coordination outcomes?

    Example usage:
        compare_intervention_experiment(
            scenario_id="office_proposal",
            intervention_type="nudge_strategy",
            intervention_params={"agent_id": "A3", "strategy": "cooperative"},
            intervention_tick=5,
            n_runs=20,
        )
    """
    scenario_id = resolve_scenario_id(scenario_id)
    baseline     = run_experiment(scenario_id, n_runs, episode_max_ticks, skip_emotions=False)
    with_intervention = _run_with_intervention(
        scenario_id, n_runs, episode_max_ticks,
        intervention_type, intervention_params, intervention_tick,
    )

    def _safe_get(data: Dict, key: str, subkey: str = "mean") -> float:
        val = data.get(key)
        if isinstance(val, dict):
            return val.get(subkey, 0.0)
        return float(val) if val is not None else 0.0

    def _diff(key: str) -> Dict[str, Any]:
        a = _safe_get(baseline, key)
        b = _safe_get(with_intervention, key)
        return {"baseline": a, "with_intervention": b, "delta": round(b - a, 4)}

    def _outcome_diff(key: str) -> Dict[str, Any]:
        a = baseline["outcome_rates"].get(key, 0)
        b = with_intervention["outcome_rates"].get(key, 0)
        return {"baseline": a, "with_intervention": b, "delta": round(b - a, 4)}

    return {
        "scenario_id":        scenario_id,
        "n_runs_each":        n_runs,
        "experiment":         "baseline vs intervention",
        "intervention_type":  intervention_type,
        "intervention_params": intervention_params,
        "intervention_tick":  intervention_tick,

        "success_rate":  _outcome_diff("success"),
        "failure_rate":  _outcome_diff("failure"),
        "deadlock_rate": _outcome_diff("deadlock"),

        "avg_trust":      {**_diff("avg_trust"),      "intervention_better": _safe_get(with_intervention, "avg_trust")      > _safe_get(baseline, "avg_trust")},
        "avg_stress":     {**_diff("avg_stress"),     "intervention_better": _safe_get(with_intervention, "avg_stress")     < _safe_get(baseline, "avg_stress")},
        "conflict_rate":  {**_diff("conflict_rate"),  "intervention_better": _safe_get(with_intervention, "conflict_rate")  < _safe_get(baseline, "conflict_rate")},
        "total_shares":   {**_diff("total_shares"),   "intervention_better": _safe_get(with_intervention, "total_shares")   > _safe_get(baseline, "total_shares")},
        "total_refusals": {**_diff("total_refusals"), "intervention_better": _safe_get(with_intervention, "total_refusals") < _safe_get(baseline, "total_refusals")},

        "ticks_to_success": {
            "baseline":          baseline.get("avg_ticks_to_success"),
            "with_intervention": with_intervention.get("avg_ticks_to_success"),
        },

        "summary": _generate_intervention_summary(
            baseline, with_intervention, intervention_type, intervention_params
        ),

        "full_baseline":          baseline,
        "full_with_intervention": with_intervention,
    }


def _run_with_intervention(
    scenario_id: str,
    n_runs: int,
    episode_max_ticks: int,
    intervention_type: str,
    intervention_params: Dict[str, Any],
    intervention_tick: int,
) -> Dict[str, Any]:
    """Run n_runs simulations applying an intervention at a specific tick."""
    scenario_id = resolve_scenario_id(scenario_id)
    if scenario_id not in SCENARIOS:
        return {"error": f"Unknown scenario '{scenario_id}'"}

    results = []
    for seed in range(n_runs):
        model = SimModel(
            seed=seed,
            scenario_id=scenario_id,
            environment=SCENARIOS[scenario_id]["environment"],
            episode_max_ticks=episode_max_ticks,
        )
        model.seed_value = seed

        while not model.ended and model.tick < episode_max_ticks:
            model.step()
            # Apply intervention at the specified tick
            if model.tick == intervention_tick:
                model.apply_intervention(intervention_type, intervention_params)

        history = model.metric_history
        if history:
            run_avg_trust      = round(statistics.mean(h["avg_trust"]      for h in history), 4)
            run_avg_stress     = round(statistics.mean(h["avg_stress"]     for h in history), 4)
            run_conflict_rate  = round(statistics.mean(h["conflict_rate"]  for h in history), 4)
            run_group_tension  = round(statistics.mean(h["group_tension"]  for h in history), 4)
            run_group_cohesion = round(statistics.mean(h["group_cohesion"] for h in history), 4)
            run_peak_stress    = round(max(h["avg_stress"]    for h in history), 4)
            run_peak_tension   = round(max(h["group_tension"] for h in history), 4)
        else:
            m = model.last_diff.get("metrics", {}) if model.last_diff else {}
            run_avg_trust = m.get("avg_trust", 0.0); run_avg_stress = m.get("avg_stress", 0.0)
            run_conflict_rate = m.get("conflict_rate", 0.0)
            run_group_tension = model.group_tension; run_group_cohesion = model.group_cohesion
            run_peak_stress = run_avg_stress; run_peak_tension = run_group_tension

        first_share_tick = next(
            (h["tick"] for h in history if h.get("share_count", 0) > 0), None
        )

        results.append({
            "seed":             seed,
            "outcome":          model.end_reason,
            "ticks":            model.tick,
            "final_progress":   round(model.scenario.progress_ratio(), 3),
            "avg_trust":        run_avg_trust,
            "avg_stress":       run_avg_stress,
            "peak_stress":      run_peak_stress,
            "conflict_rate":    run_conflict_rate,
            "group_tension":    run_group_tension,
            "peak_tension":     run_peak_tension,
            "group_cohesion":   run_group_cohesion,
            "total_refusals":   model.total_refusals,
            "total_shares":     model.total_shares,
            "stalled_ticks":    model.total_stalled_ticks,
            "first_share_tick": first_share_tick,
            "completion_order": getattr(model, "completion_order", []),
        })

    return _aggregate(scenario_id, n_runs, skip_emotions=False, results=results)


def _generate_intervention_summary(
    baseline: Dict,
    with_intervention: Dict,
    intervention_type: str,
    intervention_params: Dict,
) -> str:
    sr_base = baseline["outcome_rates"].get("success", 0)
    sr_int  = with_intervention["outcome_rates"].get("success", 0)
    dl_base = baseline["outcome_rates"].get("deadlock", 0)
    dl_int  = with_intervention["outcome_rates"].get("deadlock", 0)

    param_str = ", ".join(f"{k}={v}" for k, v in intervention_params.items())
    lines = [f"Intervention: {intervention_type} ({param_str})."]

    if sr_int > sr_base:
        lines.append(
            f"The intervention improved success rate from {sr_base:.0%} to {sr_int:.0%}, "
            f"suggesting it had a positive effect on coordination."
        )
    elif sr_int < sr_base:
        lines.append(
            f"The intervention did not improve success rate ({sr_int:.0%} vs baseline {sr_base:.0%}), "
            f"suggesting limited or no benefit in this configuration."
        )
    else:
        lines.append("Success rate was unchanged by the intervention.")

    if dl_int < dl_base:
        lines.append(
            f"Deadlock frequency decreased from {dl_base:.0%} to {dl_int:.0%}, "
            f"indicating the intervention helped prevent coordination failures."
        )

    sh_base = baseline.get("total_shares", {}).get("mean", 0)
    sh_int  = with_intervention.get("total_shares", {}).get("mean", 0)
    if sh_int > sh_base:
        lines.append(
            f"Average shares increased ({sh_int:.1f} vs {sh_base:.1f}), "
            f"consistent with the intervention promoting information flow."
        )

    return " ".join(lines)


def _generate_summary(with_nlp: Dict, without_nlp: Dict) -> str:
    """
    Generate a balanced, academically honest summary of NLP on vs off results.
    Reports trade-offs where they exist rather than claiming NLP improves everything.
    """
    lines = []

    sr_nlp  = with_nlp["outcome_rates"].get("success", 0)
    sr_base = without_nlp["outcome_rates"].get("success", 0)
    dl_nlp  = with_nlp["outcome_rates"].get("deadlock", 0)
    dl_base = without_nlp["outcome_rates"].get("deadlock", 0)

    # Success rate
    if sr_nlp > sr_base:
        lines.append(
            f"NLP-enabled runs showed a higher success rate ({sr_nlp:.0%} vs {sr_base:.0%})."
        )
    elif sr_nlp < sr_base:
        lines.append(
            f"NLP-disabled runs showed a higher success rate ({sr_base:.0%} vs {sr_nlp:.0%}), "
            f"suggesting that emotional modelling may increase hesitancy in some configurations."
        )
    else:
        lines.append("Success rates were equal across both conditions.")

    # Deadlock
    if dl_nlp < dl_base:
        lines.append(
            f"Deadlock was less frequent with NLP ({dl_nlp:.0%} vs {dl_base:.0%})."
        )
    elif dl_nlp > dl_base:
        lines.append(
            f"Deadlock was more frequent with NLP ({dl_nlp:.0%} vs {dl_base:.0%}), "
            f"which may reflect increased emotional sensitivity causing agents to disengage."
        )

    # Trust and stress — report trade-offs honestly
    t_nlp  = with_nlp.get("avg_trust", {}).get("mean", 0)
    t_base = without_nlp.get("avg_trust", {}).get("mean", 0)
    s_nlp  = with_nlp.get("avg_stress", {}).get("mean", 0)
    s_base = without_nlp.get("avg_stress", {}).get("mean", 0)

    trust_higher  = t_nlp > t_base
    stress_higher = s_nlp > s_base

    if trust_higher and not stress_higher:
        lines.append(
            f"NLP-enabled runs also showed higher average trust ({t_nlp:.3f} vs {t_base:.3f}) "
            f"and lower stress, suggesting that emotion-aware behaviour improved relationship quality."
        )
    elif trust_higher and stress_higher:
        lines.append(
            f"NLP-enabled runs showed higher trust ({t_nlp:.3f} vs {t_base:.3f}) "
            f"but also higher stress ({s_nlp:.3f} vs {s_base:.3f}), suggesting that "
            f"emotion-aware behaviour may improve coordination while increasing emotional intensity."
        )
    elif not trust_higher and stress_higher:
        lines.append(
            f"NLP-enabled runs showed higher stress ({s_nlp:.3f} vs {s_base:.3f}) "
            f"without a corresponding trust improvement, suggesting that emotional processing "
            f"may amplify negative reactions in this scenario."
        )

    # Shares and refusals
    sh_nlp  = with_nlp.get("total_shares", {}).get("mean", 0)
    sh_base = without_nlp.get("total_shares", {}).get("mean", 0)
    rf_nlp  = with_nlp.get("total_refusals", {}).get("mean", 0)
    rf_base = without_nlp.get("total_refusals", {}).get("mean", 0)

    if sh_nlp > sh_base and rf_nlp < rf_base:
        lines.append(
            f"Information sharing was more frequent ({sh_nlp:.1f} vs {sh_base:.1f} per run) "
            f"and refusals less frequent ({rf_nlp:.1f} vs {rf_base:.1f}), "
            f"indicating that emotional context promoted cooperative behaviour."
        )
    elif sh_nlp > sh_base:
        lines.append(
            f"Agents shared more frequently with NLP ({sh_nlp:.1f} vs {sh_base:.1f} per run)."
        )
    elif rf_nlp > rf_base:
        lines.append(
            f"Refusals were more frequent with NLP ({rf_nlp:.1f} vs {rf_base:.1f} per run), "
            f"suggesting emotional state increased reluctance to share in some cases."
        )

    return " ".join(lines) if lines else "No significant differences observed between conditions."
