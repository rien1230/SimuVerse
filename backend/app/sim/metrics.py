"""Group-level metric helpers for trust, stress, cohesion, and conflict."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from app.sim.model import SimModel


def compute_tick_metrics(
    model: "SimModel",
    agents_sorted: list,
    events: list,
) -> Dict[str, Any]:
    ties = model._compute_ties(agents_sorted)
    avg_trust = sum(tie["trust"] for tie in ties) / len(ties) if ties else 0.5

    stresses = [getattr(agent, "stress", 0.5) for agent in agents_sorted]
    avg_stress = sum(stresses) / len(stresses)
    stress_variance = sum((stress - avg_stress) ** 2 for stress in stresses) / len(
        stresses
    )

    negative_events = sum(
        1
        for event in events
        if event.get("type") in ("ignore", "insult", "refuse", "challenge")
    )
    conflict_rate = negative_events / max(1, len(events))
    refusal_count = sum(1 for event in events if event.get("type") == "refuse")
    share_count = sum(1 for event in events if model._counts_as_share(event))

    event_counts: Dict[str, int] = {}
    for event in events:
        event_type = str(event.get("type", ""))
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

    pressure_count = sum(
        1
        for event in events
        if event.get("type") == "pressure"
        or event.get("pressure", False) is True
    )

    strategy_distribution: Dict[str, int] = {}
    for agent in agents_sorted:
        strategy = getattr(agent, "strategy", "unknown")
        strategy_distribution[strategy] = strategy_distribution.get(strategy, 0) + 1

    return {
        "avg_trust": round(avg_trust, 3),
        "mean_valence": round(
            sum(agent.valence for agent in agents_sorted) / len(agents_sorted),
            3,
        ),
        "mean_arousal": round(
            sum(agent.arousal for agent in agents_sorted) / len(agents_sorted),
            3,
        ),
        "conflict_rate": round(conflict_rate, 3),
        "cumulative_conflict_rate": round(
            model.total_conflict_events / max(1, model.total_events), 3
        ),
        "avg_stress": round(avg_stress, 3),
        "stress_variance": round(stress_variance, 4),
        "refusal_count": refusal_count,
        "share_count": share_count,
        "pressure_count": pressure_count,
        "event_counts": event_counts,
        "stalled_ticks": model.progress_stall_ticks,
        "bottleneck_item": model.bottleneck_item,
        "bottleneck_holder": model.bottleneck_holder,
        "bottleneck_age": model.bottleneck_age,
        "strategy_distribution": strategy_distribution,
        "cumulative_refusals": model.total_refusals,
        "cumulative_shares": model.total_shares,
        "cumulative_stalled": model.total_stalled_ticks,
        "group_tension": model.group_tension,
        "group_cohesion": model.group_cohesion,
    }
