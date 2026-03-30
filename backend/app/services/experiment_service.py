from __future__ import annotations

import logging
import statistics
from typing import Any, Dict, List, Optional

from app.sim.model import SimModel
from app.sim.scenario_data import SCENARIOS
from app.core.config import DEFAULT_N_RUNS, DEFAULT_EXPERIMENT_MAX_TICKS

logger = logging.getLogger(__name__)


def run_experiment(
    scenario_id: str,
    n_runs: int = 20,
    episode_max_ticks: int = 120,
    skip_emotions: bool = False,
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
    if scenario_id not in SCENARIOS:
        return {"error": f"Unknown scenario '{scenario_id}'. Valid: {list(SCENARIOS.keys())}"}

    logger.info(f"Starting experiment: scenario={scenario_id}, n_runs={n_runs}, "
                f"max_ticks={episode_max_ticks}, nlp={'off' if skip_emotions else 'on'}")

    results = []

    for seed in range(n_runs):
        logger.debug(f"  Run {seed + 1}/{n_runs} (seed={seed})")
        model = SimModel(
            seed=seed,
            scenario_id=scenario_id,
            environment=SCENARIOS[scenario_id]["environment"],
            episode_max_ticks=episode_max_ticks,
        )
        model.seed_value = seed
        if skip_emotions:
            model.skip_emotions = True

        # Hard outer guard — prevents infinite loop if model logic has a bug
        while not model.ended and model.tick < episode_max_ticks:
            model.step()

        # ----------------------------------------------------------------
        # Use whole-run averages from metric_history, not last-tick only.
        # This fixes the conflict_rate=0.0 problem and gives accurate
        # trust/stress figures that reflect the full simulation arc.
        # ----------------------------------------------------------------
        history = model.metric_history
        if history:
            run_avg_trust      = round(statistics.mean(h["avg_trust"]     for h in history), 4)
            run_avg_stress     = round(statistics.mean(h["avg_stress"]    for h in history), 4)
            run_conflict_rate  = round(statistics.mean(h["conflict_rate"] for h in history), 4)
            run_group_tension  = round(statistics.mean(h["group_tension"] for h in history), 4)
            run_group_cohesion = round(statistics.mean(h["group_cohesion"] for h in history), 4)
            run_peak_stress    = round(max(h["avg_stress"]    for h in history), 4)
            run_peak_tension   = round(max(h["group_tension"] for h in history), 4)
        else:
            # Fallback to last-tick metrics if history is empty
            m = model.last_diff.get("metrics", {}) if model.last_diff else {}
            run_avg_trust      = m.get("avg_trust", 0.0)
            run_avg_stress     = m.get("avg_stress", 0.0)
            run_conflict_rate  = m.get("conflict_rate", 0.0)
            run_group_tension  = model.group_tension
            run_group_cohesion = model.group_cohesion
            run_peak_stress    = run_avg_stress
            run_peak_tension   = run_group_tension

        # Time to first share (tick number)
        first_share_tick = next(
            (h["tick"] for h in history if h["share_count"] > 0), None
        )

        results.append({
            "seed":              seed,
            "outcome":           model.end_reason,
            "ticks":             model.tick,
            "final_progress":    round(model.scenario.progress_ratio(), 3),
            "avg_trust":         run_avg_trust,
            "avg_stress":        run_avg_stress,
            "peak_stress":       run_peak_stress,
            "conflict_rate":     run_conflict_rate,
            "group_tension":     run_group_tension,
            "peak_tension":      run_peak_tension,
            "group_cohesion":    run_group_cohesion,
            "total_refusals":    model.total_refusals,
            "total_shares":      model.total_shares,
            "stalled_ticks":     model.total_stalled_ticks,
            "first_share_tick":  first_share_tick,
            "completion_order":  getattr(model, "completion_order", []),
        })

    result = _aggregate(scenario_id, n_runs, skip_emotions, results)
    logger.info(f"Experiment complete: success_rate={result['success_rate']:.0%}, "
                f"deadlock_rate={result['outcome_rates'].get('deadlock', 0):.0%}")
    return result


def run_multi_scenario_experiment(
    scenario_ids: List[str],
    n_runs: int = 20,
    episode_max_ticks: int = 120,
) -> Dict[str, Any]:
    """
    Run multiple scenarios and return results for all of them.
    Useful for cross-scenario comparison in the dissertation.
    """
    results = {}
    for sid in scenario_ids:
        if sid not in SCENARIOS:
            results[sid] = {"error": f"Unknown scenario '{sid}'"}
            continue
        results[sid] = run_experiment(
            scenario_id=sid,
            n_runs=n_runs,
            episode_max_ticks=episode_max_ticks,
            skip_emotions=False,
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


def compare_experiments(
    scenario_id: str,
    n_runs: int = 20,
    episode_max_ticks: int = 120,
) -> Dict[str, Any]:
    """
    Key academic experiment: same scenario, NLP on vs NLP off.
    Directly answers: does the emotion pipeline affect coordination outcomes?
    """
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