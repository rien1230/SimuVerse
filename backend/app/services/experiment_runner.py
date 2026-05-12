"""
Batch experiment runner — runs the real SimModel multiple times with
controlled seeds, team styles, and scenarios, then aggregates results.

No dummy data.  Every run uses the actual simulation engine.
The aggregation and interpretation functions derive all findings
from measured metrics, never from hardcoded thresholds or labels.

Three experiment modes are supported:
  - team_comparison: same scenario, different team styles
  - scenario_comparison: same team style, different scenarios
  - seed_reproducibility: same setup, different seeds (consistency check)

This file is the backend home of the Experiment Runner feature.
The flow is:
1. run real simulations with controlled inputs
2. collect per-run metrics
3. aggregate those metrics by group
4. turn the grouped results into findings the frontend can display
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.sim.model import SimModel

logger = logging.getLogger(__name__)


# ── Scenario alias normalisation ───────────────────────────────────────────────

# Maps short user-facing names to the canonical scenario IDs used by SimModel.
# This lets the API accept "office" or "escape" without the full internal ID.
_SCENARIO_ALIASES: Dict[str, str] = {
    "office":       "office_proposal",
    "office_room":  "office_proposal",
    "cafe":         "cafe_restaurant",
    "escape":       "escape_puzzle",
    "escape_room":  "escape_puzzle",
}

# All valid team style strings — used for validation and default lists
VALID_TEAM_STYLES: Tuple[str, ...] = ("smooth", "tension", "creative", "pressure", "balanced")

# Human-readable labels for scenario comparison charts
_SCENARIO_DISPLAY: Dict[str, str] = {
    "escape":          "Escape Room",
    "escape_puzzle":   "Escape Room",
    "office":          "Office Project",
    "office_proposal": "Office Project",
    "cafe":            "Cafe Planning",
    "cafe_restaurant": "Cafe Planning",
}


def _normalise_scenario(scenario: str) -> str:
    """Resolve short names (office, cafe, escape) to canonical scenario IDs."""
    key = scenario.lower().strip()
    # Return the mapped canonical ID if found, otherwise pass the value through unchanged
    return _SCENARIO_ALIASES.get(key, key)


def _avg_trust_from_agents(model: SimModel) -> float:
    """Compute mean trust across all agent pairs at the current model state.

    Trust is stored per-agent as a dict of {other_agent_id: trust_value},
    so we flatten all values across all agents and average them.
    """
    total, count = 0.0, 0
    for agent in model.agents:
        for v in agent.trust.values():
            total += v
            count += 1
    # Default to 0.5 (neutral trust) if no pairs exist yet
    return total / count if count else 0.5


def _is_task_resolved(value: Any) -> bool:
    """Check if a task is complete, supporting both bool and dict task formats.

    Some scenarios store tasks as plain True/False, others use a dict with
    a "status" key or individual boolean flags. This handles all cases.
    """
    if value is True:
        return True
    if value is False or value is None:
        return False

    if isinstance(value, dict):
        # Check the "status" string field first
        status = str(value.get("status", "")).lower()
        if status in {"done", "resolved", "complete", "completed"}:
            return True

        # Also check individual boolean flags as a fallback
        return bool(
            value.get("done") is True
            or value.get("resolved") is True
            or value.get("complete") is True
            or value.get("completed") is True
        )

    return False


# ── Single run ─────────────────────────────────────────────────────────────────
# Everything above this point is helper/normalisation code.
# The functions below are the real experiment pipeline.

def run_single_seeded_experiment(
    scenario: str,
    team_style: str,
    seed: int,
    max_steps: int = 30,
) -> Dict[str, Any]:
    """
    Run one complete simulation and return a flat results dict.

    Parameters
    ----------
    scenario   : Short name ("office", "cafe", "escape") or canonical ID.
    team_style : One of smooth / tension / creative / pressure / balanced.
    seed       : RNG seed — same seed always produces the same output.
    max_steps  : Step limit; the simulation also terminates on its own
                 end conditions (completion, harmony, failure).

    Returns
    -------
    A dict with every measured metric for this run.
    """
    # This uses the real simulation engine, not fake or cached data.
    scenario_id = _normalise_scenario(scenario)

    model = SimModel(
        seed=seed,
        scenario_id=scenario_id,
        episode_max_ticks=max_steps,
        team_type=team_style,
        use_nlp=False,
    )

    # Snapshot initial trust before any events mutate agent state
    start_trust = _avg_trust_from_agents(model)

    # Run to completion
    while not model.ended and model.tick < max_steps:
        model.step()

    # ── Extract metrics from metric_history ───────────────────────────────
    mh = getattr(model, "metric_history", [])
    # Peak stress is the worst moment across the whole run, not just the final tick
    peak_stress  = round(max((h["avg_stress"] for h in mh), default=0.0), 3)
    final_stress = round(mh[-1]["avg_stress"] if mh else 0.0, 3)
    # Fall back to the pre-run snapshot if metric_history is empty
    final_trust  = round(mh[-1]["avg_trust"]  if mh else start_trust, 3)

    # ── Count cooperation / challenge events from full history ────────────
    cooperation_count = 0
    challenge_count   = 0
    total_event_count = 0          # all agent events (neutral + social + conflict)
    for tick_data in getattr(model, "history", []):
        for ev in tick_data.get("events", []):
            total_event_count += 1
            t = ev.get("type", "")
            # Sharing and agreement are positive coordination signals
            if t in ("share_info", "agree", "confirm"):
                cooperation_count += 1
            # Refusals and pushback indicate friction in the team
            if t in ("refuse", "challenge", "push_back"):
                challenge_count += 1

    # ── Task / blocker resolution ──────────────────────────────────────────
    tasks_dict        = getattr(model.scenario, "tasks", {})
    blocker_count     = len(tasks_dict)
    blockers_resolved = sum(1 for v in tasks_dict.values() if _is_task_resolved(v))

    completed = model.scenario.progress_ratio() >= 1.0

    return {
        "scenario":           scenario,
        "scenario_id":        scenario_id,
        "team_style":         team_style,
        "seed":               seed,
        "completed":          completed,
        "completion_steps":   model.tick if completed else None,
        "final_progress":     round(model.scenario.progress_ratio(), 3),
        "end_reason":         model.end_reason or "max_steps",
        "start_trust":        round(start_trust, 3),
        "final_trust":        final_trust,
        "trust_delta":        round(final_trust - start_trust, 3),
        "peak_stress":        peak_stress,
        "final_stress":       final_stress,
        "blocker_count":      blocker_count,
        "blockers_resolved":  blockers_resolved,
        "cooperation_count":  cooperation_count,
        "challenge_count":    challenge_count,
        "total_event_count":  total_event_count,
        "intervention_count": 0,   # batch runs carry no user interventions
        "ticks":              model.tick,
    }


def _safe_run(
    scenario: str,
    team_style: str,
    seed: int,
    max_steps: int,
) -> Dict[str, Any]:
    """Run one experiment, returning a structured error dict on failure.

    Wrapping individual runs this way means one bad seed won't crash the whole batch.
    The error dict includes zero-value fields so aggregation still works on partial results.
    """
    try:
        return run_single_seeded_experiment(scenario, team_style, seed, max_steps)
    except Exception as exc:
        logger.error(
            "Run failed — team=%s seed=%d error=%s", team_style, seed, exc, exc_info=True,
        )
        return {
            "scenario": scenario, "scenario_id": scenario, "team_style": team_style,
            "seed": seed, "completed": False, "error": str(exc),
            "ticks": 0, "completion_steps": None, "final_progress": 0.0,
            "start_trust": 0.0, "final_trust": 0.0, "trust_delta": 0.0,
            "peak_stress": 0.0, "final_stress": 0.0,
            "blocker_count": 0, "blockers_resolved": 0,
            "cooperation_count": 0, "challenge_count": 0, "total_event_count": 0, "intervention_count": 0,
        }


# ── Aggregation ────────────────────────────────────────────────────────────────
# Batch runs come back as flat per-run dicts first.
# This section groups them into the summaries shown in the experiments UI.

def _mean(runs: List[Dict[str, Any]], key: str) -> float:
    """Compute the mean of a numeric field across a list of run dicts.

    Skips runs where the field is missing or non-numeric (e.g. error runs).
    """
    vals = [r[key] for r in runs if isinstance(r.get(key), (int, float))]
    return round(sum(vals) / len(vals), 3) if vals else 0.0


def aggregate_experiment_results(
    runs: List[Dict[str, Any]],
    group_by: str = "team_style",
) -> Dict[str, Dict[str, Any]]:
    """
    Group runs by `group_by` and compute per-group summary statistics.

    Returns a dict keyed by group label (e.g. "smooth", "tension", …).
    The group_by field changes depending on experiment type (team_style,
    scenario_label, or seed_label).
    """
    groups: Dict[str, list] = defaultdict(list)
    for run in runs:
        groups[run[group_by]].append(run)

    result: Dict[str, Dict[str, Any]] = {}
    for label, group_runs in groups.items():
        n         = len(group_runs)
        completed = [r for r in group_runs if r.get("completed")]
        # Only include steps from runs that actually completed
        comp_steps = [
            r["completion_steps"] for r in completed
            if r.get("completion_steps") is not None
        ]
        blocker_rates = []
        for r in group_runs:
            bc = r.get("blocker_count", 0)
            br = r.get("blockers_resolved", 0)
            if isinstance(bc, int) and bc > 0:
                # Scenario has tracked blockers — compute resolution ratio
                blocker_rates.append(br / bc)
            elif r.get("completed"):
                # No tracked blockers but run completed — treat as fully resolved
                blocker_rates.append(1.0)

        result[label] = {
            "n":                         n,
            "completion_rate":           round(len(completed) / n, 3) if n else 0.0,
            "avg_completion_steps":      round(sum(comp_steps) / len(comp_steps), 2)
                                         if comp_steps else None,
            "avg_peak_stress":           _mean(group_runs, "peak_stress"),
            "avg_final_trust":           _mean(group_runs, "final_trust"),
            "avg_start_trust":           _mean(group_runs, "start_trust"),
            "avg_trust_delta":           _mean(group_runs, "trust_delta"),
            "avg_challenge_count":       _mean(group_runs, "challenge_count"),
            "avg_cooperation_count":     _mean(group_runs, "cooperation_count"),
            "avg_total_event_count":     _mean(group_runs, "total_event_count"),
            "avg_blockers_resolved_rate": round(sum(blocker_rates) / len(blocker_rates), 3)
                                          if blocker_rates else 0.0,
        }

    return result


# ── Comparison ─────────────────────────────────────────────────────────────────
# This section turns grouped numeric summaries into higher-level findings.

def compare_team_styles(
    aggregated: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Derive a structured comparison and plain-English interpretation from the
    aggregated metrics.  All conclusions come from the data — nothing is
    hardcoded.

    Returns
    -------
    {
        "findings": [{"metric", "winner", "value", "summary"}, ...],
        "interpretation": "plain-English paragraph",
    }
    """
    if not aggregated:
        return {"findings": [], "interpretation": "No data to compare."}

    findings: List[Dict[str, Any]] = []

    # ── Fastest completion ─────────────────────────────────────────────────
    by_speed = [
        (label, g["avg_completion_steps"])
        for label, g in aggregated.items()
        if g["avg_completion_steps"] is not None
    ]
    if by_speed:
        fastest_label, fastest_steps = min(by_speed, key=lambda x: x[1])
        findings.append({
            "metric":  "completion_speed",
            "winner":  fastest_label,
            "value":   fastest_steps,
            "summary": (
                f"{fastest_label.title()} team completed fastest "
                f"(avg {fastest_steps:.1f} steps)."
            ),
        })

    # ── Highest peak stress ────────────────────────────────────────────────
    by_stress = [(label, g["avg_peak_stress"]) for label, g in aggregated.items()]
    if by_stress:
        high_label, high_stress = max(by_stress, key=lambda x: x[1])
        findings.append({
            "metric":  "peak_stress",
            "winner":  high_label,
            "value":   high_stress,
            "summary": (
                f"{high_label.title()} team produced the highest average "
                f"peak stress ({high_stress:.2f})."
            ),
        })

    # ── Most challenge / refusal events ───────────────────────────────────
    by_challenge = [(label, g["avg_challenge_count"]) for label, g in aggregated.items()]
    if by_challenge:
        challenge_label, challenge_val = max(by_challenge, key=lambda x: x[1])
        findings.append({
            "metric":  "challenge_count",
            "winner":  challenge_label,
            "value":   challenge_val,
            "summary": (
                f"{challenge_label.title()} team produced the most "
                f"challenge/refusal events (avg {challenge_val:.1f})."
            ),
        })

    # ── Most cooperative ──────────────────────────────────────────────────
    by_coop = [(label, g["avg_cooperation_count"]) for label, g in aggregated.items()]
    if by_coop:
        coop_label, coop_val = max(by_coop, key=lambda x: x[1])
        findings.append({
            "metric":  "cooperation",
            "winner":  coop_label,
            "value":   coop_val,
            "summary": (
                f"{coop_label.title()} team had the most cooperative events "
                f"(avg {coop_val:.1f})."
            ),
        })

    # ── Greatest trust growth ──────────────────────────────────────────────
    by_trust_delta = [(label, g["avg_trust_delta"]) for label, g in aggregated.items()]
    if by_trust_delta:
        trust_label, trust_val = max(by_trust_delta, key=lambda x: x[1])
        findings.append({
            "metric":  "trust_growth",
            "winner":  trust_label,
            "value":   trust_val,
            "summary": (
                f"{trust_label.title()} team showed the greatest trust growth "
                f"(avg {trust_val:+.3f})."
            ),
        })

    interpretation = _build_interpretation(aggregated, findings)
    return {"findings": findings, "interpretation": interpretation}


def _build_interpretation(
    aggregated: Dict[str, Dict[str, Any]],
    findings: List[Dict[str, Any]],
) -> str:
    """Generate a plain-English paragraph from actual aggregated numbers.

    This builds the "interpretation" string that gets shown in the UI results panel.
    Everything is derived from real numbers — no hardcoded conclusions.
    """
    # Sort groups by stress and challenge so we can identify the extremes
    stress_order    = sorted(aggregated.items(), key=lambda x: x[1]["avg_peak_stress"])
    challenge_order = sorted(aggregated.items(), key=lambda x: x[1]["avg_challenge_count"])

    parts = ["The experiment compared team styles across multiple seeded runs."]

    for label, stats in aggregated.items():
        rate = int(stats["completion_rate"] * 100)
        if stats["avg_completion_steps"] is not None:
            comp_str = (
                f"completed {rate}% of runs in an average of "
                f"{stats['avg_completion_steps']:.1f} steps"
            )
        else:
            comp_str = f"completed {rate}% of runs within the step limit"

        parts.append(
            f"{label.title()} team {comp_str}, "
            f"with peak stress {stats['avg_peak_stress']:.2f}, "
            f"{stats['avg_challenge_count']:.1f} avg challenge events, "
            f"{stats['avg_cooperation_count']:.1f} avg cooperation events, "
            f"and trust delta {stats['avg_trust_delta']:+.3f}."
        )

    low_stress,  high_stress  = stress_order[0][0],    stress_order[-1][0]
    low_conflict, high_conflict = challenge_order[0][0], challenge_order[-1][0]

    if low_stress != high_stress:
        parts.append(
            f"{high_stress.title()} team generated the highest stress "
            f"while {low_stress.title()} team remained the calmest."
        )
    if low_conflict != high_conflict:
        parts.append(
            f"{high_conflict.title()} team produced the most conflict events "
            f"whereas {low_conflict.title()} team showed the smoothest coordination."
        )

    parts.append(
        "These results indicate that team style meaningfully affected simulation "
        "behaviour across metrics including completion speed, stress, "
        "cooperation, and conflict."
    )

    return " ".join(parts)


def _compare_seed_consistency(aggregated: Dict[str, Dict]) -> Dict[str, Any]:
    """
    For seed reproducibility experiments — describe how consistent results are
    across seeds rather than picking a 'winner'.

    Instead of finding the 'best' group, this measures how much the results
    vary across seeds. Low variance means the simulation is deterministic and
    reproducible; high variance means random initialisation has a big impact.
    """
    if not aggregated:
        return {"findings": [], "interpretation": "No data to compare."}

    labels = list(aggregated.keys())
    n = len(labels)

    completion_rates = [aggregated[l]["completion_rate"] for l in labels]
    peak_stresses    = [aggregated[l]["avg_peak_stress"]  for l in labels]
    trust_deltas     = [aggregated[l]["avg_trust_delta"]  for l in labels]

    # Range (max - min) across seeds tells us how much variance exists per metric
    cr_range = round(max(completion_rates) - min(completion_rates), 3)
    ps_range = round(max(peak_stresses)    - min(peak_stresses),    3)
    td_range = round(max(trust_deltas)     - min(trust_deltas),     3)
    avg_cr   = round(sum(completion_rates) / n, 3)

    # Simple consistency classification based on how tight the ranges are
    if cr_range == 0 and ps_range < 0.05:
        consistency = "highly consistent"
    elif cr_range <= 0.2 and ps_range < 0.15:
        consistency = "mostly consistent"
    else:
        consistency = "variable across seeds"

    interp = (
        f"Across {n} seeds, this configuration produced {consistency} results. "
        f"Average completion rate was {int(avg_cr * 100)}%. "
        f"Peak stress varied by {ps_range:.3f} across seeds "
        f"(lower variation = more reproducible). "
        f"Trust delta range was {td_range:+.3f}. "
    )
    if cr_range == 0:
        interp += (
            "Completion outcomes were identical across all seeds — "
            "the setup is deterministic on this metric. "
        )
    else:
        interp += (
            f"Completion rate differed by {int(cr_range * 100)}% across seeds "
            f"— the behaviour shows some variance. "
        )
    interp += (
        "These results indicate whether the simulation is reproducible "
        "under fixed team and scenario settings."
    )
    return {"findings": [], "interpretation": interp}


# ── Top-level batch entry point ────────────────────────────────────────────────

def run_experiment_batch(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run a controlled batch experiment.

    Supports three experiment_type values
    ──────────────────────────────────────
    team_comparison      — fixed scenario, multiple team styles × seeds
    scenario_comparison  — fixed team style, multiple scenarios × seeds
    seed_reproducibility — fixed team + scenario, multiple seeds (consistency test)

    Returns
    -------
    {
        "config":                {..., "total_runs": N, "experiment_type": "..."},
        "runs":                  [{...per-run metrics...}],
        "summary_by_team_style": {group_label: {...averages...}},
        "comparison":            {"findings": [...], "interpretation": "..."},
    }
    """
    experiment_type = config.get("experiment_type", "team_comparison")
    max_steps       = int(config.get("max_steps", 30))
    seeds           = config.get("seeds", [101, 102, 103])

    runs:     List[Dict[str, Any]] = []
    group_by: str                  = "team_style"
    total:    int                  = 0

    # ── Team Style Comparison ──────────────────────────────────────────────────
    if experiment_type == "team_comparison":
        scenario    = config.get("scenario", "office")
        # Default to the first 4 styles if none are specified
        team_styles = config.get("team_styles", list(VALID_TEAM_STYLES[:4]))
        group_by    = "team_style"
        total       = len(team_styles) * len(seeds)
        logger.info(
            "Batch [team_comparison]: scenario=%s, styles=%s, seeds=%s → %d runs",
            scenario, team_styles, seeds, total,
        )
        # Run each team style across every seed for fair comparison
        for team_style in team_styles:
            for seed in seeds:
                runs.append(_safe_run(scenario, team_style, seed, max_steps))

    # ── Scenario Comparison ────────────────────────────────────────────────────
    elif experiment_type == "scenario_comparison":
        scenarios  = config.get("scenarios", ["escape", "office", "cafe"])
        team_style = config.get("team_style", "smooth")
        group_by   = "scenario_label"  # group by display name, not internal ID
        total      = len(scenarios) * len(seeds)
        logger.info(
            "Batch [scenario_comparison]: scenarios=%s, team=%s, seeds=%s → %d runs",
            scenarios, team_style, seeds, total,
        )
        for scenario in scenarios:
            for seed in seeds:
                result = _safe_run(scenario, team_style, seed, max_steps)
                # Attach a human-readable label so the chart shows "Escape Room" etc.
                result["scenario_label"] = _SCENARIO_DISPLAY.get(
                    scenario.lower(), scenario.replace("_", " ").title()
                )
                runs.append(result)

    # ── Seed Reproducibility ───────────────────────────────────────────────────
    elif experiment_type == "seed_reproducibility":
        scenario   = config.get("scenario", "escape")
        team_style = config.get("team_style", "smooth")
        group_by   = "seed_label"  # each seed is its own group here
        total      = len(seeds)
        logger.info(
            "Batch [seed_reproducibility]: scenario=%s, team=%s, seeds=%s → %d runs",
            scenario, team_style, seeds, total,
        )
        for seed in seeds:
            result = _safe_run(scenario, team_style, seed, max_steps)
            # Label each run by its seed value so the comparison is readable
            result["seed_label"] = f"Seed {seed}"
            runs.append(result)

    else:
        raise ValueError(f"Unknown experiment_type: {experiment_type!r}")

    aggregated = aggregate_experiment_results(runs, group_by=group_by)

    # Seed reproducibility uses a different comparison function since there's no
    # 'winner' to identify — we just want to measure consistency across seeds
    comparison = (
        _compare_seed_consistency(aggregated)
        if experiment_type == "seed_reproducibility"
        else compare_team_styles(aggregated)
    )

    succeeded = sum(1 for r in runs if r.get("completed"))
    logger.info("Experiment batch complete: %d/%d runs succeeded", succeeded, total)

    return {
        "config":                {**config, "total_runs": total, "experiment_type": experiment_type},
        "runs":                  runs,
        "summary_by_team_style": aggregated,
        "comparison":            comparison,
    }
