"""Group-level metric helpers for trust, stress, cohesion, and conflict."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

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

    # ── Emotional memory pressure ─────────────────────────────────────────────
    # Per-agent ratio of negative emotions in recent STM (last 15 entries).
    # This is a richer signal than counting conflict events because it reflects
    # the accumulated emotional texture of what each agent has experienced —
    # sustained low-grade hostility shows up here even when event counts are low.
    _neg_emotions = frozenset({
        "anger", "annoyance", "disapproval", "disgust", "fear",
        "sadness", "disappointment", "nervousness", "grief",
        "remorse", "embarrassment",
    })
    _pos_emotions = frozenset({
        "joy", "gratitude", "approval", "admiration",
        "optimism", "relief", "excitement", "love", "pride",
    })
    _em_pressures: List[float] = []
    _em_positives: List[float] = []
    for _a in agents_sorted:
        _stm = list(getattr(_a, "stm", []))[-15:]
        if not _stm:
            continue
        _total = len(_stm)
        _neg = sum(1 for m in _stm if m.get("primary_emotion") in _neg_emotions)
        _pos = sum(1 for m in _stm if m.get("primary_emotion") in _pos_emotions)
        _em_pressures.append(_neg / _total)
        _em_positives.append(_pos / _total)

    emotional_memory_pressure = (
        round(sum(_em_pressures) / len(_em_pressures), 3) if _em_pressures else 0.0
    )
    emotional_memory_positivity = (
        round(sum(_em_positives) / len(_em_positives), 3) if _em_positives else 0.0
    )

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
        "emotional_memory_pressure": emotional_memory_pressure,
        "emotional_memory_positivity": emotional_memory_positivity,
    }


def classify_run_outcome(model: "SimModel") -> str:
    """Return a human-readable outcome label for a finished (or in-progress) run.

    The label is derived from the actual simulation state — conflict rate,
    average stress, average trust, whether interventions were used, and whether
    the run completed — rather than hardcoded thresholds.  Callers should treat
    it as an explanatory summary, not a score.

    Critical design rule: stress and conflict are independent axes.
    A high-stress run (e.g. escape room, pressure_team) is NOT the same as a
    high-conflict run. Only label a run "high conflict" when conflict events
    actually dominated over cooperative ones. If cooperation clearly outweighed
    conflict, downgrade to a tension/pressure label even if conflict_rate is
    technically above threshold.
    """
    progress = model.scenario.progress_ratio()
    end_reason = getattr(model, "end_reason", "running")

    if end_reason == "running" and progress < 1.0:
        return "In progress"

    team_preset = getattr(model, "team_preset", "") or ""
    total_events = max(1, model.total_events)
    conflict_rate = model.total_conflict_events / total_events

    # Recent avg_stress — sample last 3 ticks of metric_history
    recent_mh = model.metric_history[-3:] if model.metric_history else []
    avg_stress = (
        sum(e.get("avg_stress", 0.5) for e in recent_mh) / len(recent_mh)
        if recent_mh else 0.5
    )

    # Peak stress over the full run — used for pressure labelling so a run
    # where stress spiked mid-run and recovered is still called "high pressure".
    # Recent avg_stress alone understates pressure for runs like escape rooms
    # where peak stress hits 0.55+ early then partially recovers.
    all_stresses = [e.get("avg_stress", 0.0) for e in (model.metric_history or [])]
    peak_stress = max(all_stresses) if all_stresses else avg_stress

    # Recent avg_trust — sample last 3 ticks of history
    trust_snaps = [
        tick.get("metrics", {}).get("avg_trust", 0.5)
        for tick in model.history[-3:]
    ]
    avg_trust = sum(trust_snaps) / max(1, len(trust_snaps)) if trust_snaps else 0.5

    # Did any intervention fire during this run?
    had_intervention = bool(getattr(model, "_applied_interventions_log", []))

    # ── Cooperation dominance check ─────────────────────────────────────────
    # Count cooperative events (shares + agreements) across full history.
    # This is the critical signal that separates "high pressure" from "high
    # conflict" — a run where coop_events >> conflict_events is not high conflict
    # regardless of the raw conflict_rate value.
    total_shares = getattr(model, "total_shares", 0)
    agree_count = sum(
        1 for snap in getattr(model, "history", [])
        for ev in snap.get("events", [])
        if ev.get("type") == "agree"
    )
    coop_events     = total_shares + agree_count
    conflict_events = getattr(model, "total_conflict_events", 0)
    # Cooperation dominates when coop events are at least 1.8× conflict events
    coop_dominates = coop_events >= max(1, conflict_events) * 1.8

    # High-stress thresholds match the JS stressBand() function:
    #   0.00–0.30 → low, 0.31–0.49 → moderate (is_high_stress), 0.50+ → high (is_very_high_stress)
    is_high_stress      = avg_stress > 0.30 or peak_stress > 0.30
    is_very_high_stress = avg_stress > 0.50 or peak_stress >= 0.50
    # Team-preset flags — each reflects how the team was *configured*, not
    # necessarily how the run *played out*.  Labels should match the expected
    # behaviour for that preset, not impose a single generic escape-room framing.
    is_tension_preset  = "tension"  in team_preset
    is_smooth_preset   = "smooth"   in team_preset
    is_pressure_preset = "pressure" in team_preset
    is_creative_preset = "creative" in team_preset
    pressure_word = (
        "high" if peak_stress >= 0.50
        else "moderate" if peak_stress > 0.30
        else "low"
    )

    # ── Incomplete / partial ────────────────────────────────────────────────
    if progress < 0.30:
        if conflict_rate > 0.35 and not coop_dominates:
            return "Incomplete — high conflict"
        return "Incomplete — unresolved blocker"

    if progress < 1.0:
        if had_intervention:
            return "Partial completion after intervention"
        if conflict_rate > 0.30 and not coop_dominates:
            return "Partial completion — high friction"
        return "Partial completion"

    # ── Completed ──────────────────────────────────────────────────────────
    if end_reason == "harmony":
        return "Completed smoothly — high-trust cooperative run"

    if avg_stress < 0.20 and avg_trust > 0.65 and conflict_rate < 0.10:
        if is_tension_preset:
            return "Completed under low pressure — tension contained"
        if is_creative_preset:
            return "Completed under low pressure — creative cooperation"
        if is_pressure_preset:
            return "Completed under controlled urgency — pressure team stayed effective"
        return "Completed smoothly — low-stress cooperative run"

    # High conflict: conflict events genuinely dominated AND conflict_rate is high
    is_high_conflict = conflict_rate > 0.30 and not coop_dominates

    if is_high_conflict or (is_tension_preset and not coop_dominates and conflict_rate > 0.15):
        if had_intervention:
            return "Completed with tension — intervention helped"
        # Tension preset: friction is expected, but label it as tension contained
        # rather than "high conflict" — cooperation still resolved all blockers.
        if is_tension_preset:
            return "Completed under high pressure — tension contained"
        return "Completed with tension — high conflict run"

    # High pressure but cooperation held (stress-driven, not conflict-driven)
    if is_very_high_stress and coop_dominates:
        if had_intervention:
            return "Completed under high pressure — intervention helped"
        if is_pressure_preset:
            return "Completed under high pressure — pressure team stayed effective"
        if is_tension_preset:
            return "Completed under high pressure — tension contained"
        return "Completed under high pressure — cooperation held"

    if is_high_stress and coop_dominates:
        if had_intervention:
            return "Completed under moderate pressure — intervention helped"
        if is_pressure_preset:
            return "Completed under moderate pressure — efficient recovery"
        if is_creative_preset:
            return "Completed through creative coordination"
        return "Completed under moderate pressure — cooperation held"

    # Mild tension / tension-preset: some conflict but cooperation still led
    if (conflict_rate > 0.12 or is_tension_preset) and coop_dominates:
        if had_intervention:
            return "Completed with mild tension — intervention helped"
        if is_tension_preset:
            return "Completed with mild tension — cooperation held"
        if is_pressure_preset:
            return "Completed under controlled urgency — cooperation dominated"
        return "Completed with mild tension — cooperation dominated"

    if had_intervention:
        return "Completed after intervention"

    # ── Cooperative completion — team-style aware ──────────────────────────────
    # Smooth and creative teams cooperate without much conflict; do not penalise
    # them with "moderate friction" just because they failed the trust > 0.60
    # threshold (trust caps differ per scenario/preset).
    if avg_trust > 0.60 and conflict_rate < 0.15:
        if is_creative_preset:
            return "Completed through creative coordination"
        if is_smooth_preset:
            return "Completed smoothly — smooth-team cooperation"
        return "Completed cooperatively"

    if coop_dominates and conflict_rate < 0.12:
        if is_smooth_preset:
            return f"Completed under {pressure_word} pressure — smooth team held together"
        if is_creative_preset:
            return "Completed under low pressure — creative cooperation" if pressure_word == "low" else "Completed through creative coordination"
        if is_pressure_preset:
            return "Completed under controlled urgency — pressure team stayed effective" if pressure_word == "low" else f"Completed under {pressure_word} pressure — pressure team stayed effective"

    if avg_stress > 0.35:
        if is_pressure_preset:
            return f"Completed under {pressure_word} pressure — pressure team stayed effective"
        return f"Completed under {pressure_word} pressure"

    # Catch-all — preserve team style at the bottom of the decision tree
    if is_smooth_preset:
        return f"Completed under {pressure_word} pressure — smooth team held together"
    if is_creative_preset:
        return "Completed through creative coordination"
    if is_pressure_preset:
        return f"Completed under {pressure_word} pressure — pressure team stayed effective"
    return "Completed with moderate friction"


def describe_run(model: "SimModel") -> str:
    """Return a plain-English paragraph explaining why the run played out as it did.

    Suitable for the dashboard footer or export notes.  Pulls from real state
    (scenario type, team preset, conflict rate, intervention list, blocker data)
    so the explanation is grounded in actual simulation events.
    """
    scenario_type = getattr(model, "scenario_type", "office")
    team_preset = (getattr(model, "team_preset", "") or "").replace("_", " ")
    label = classify_run_outcome(model)
    progress = round(model.scenario.progress_ratio() * 100)
    ticks = model.tick

    total_events = max(1, model.total_events)
    conflict_rate = model.total_conflict_events / total_events
    share_count = getattr(model, "total_shares", 0)

    recent_mh = model.metric_history[-3:] if model.metric_history else []
    avg_stress = (
        sum(e.get("avg_stress", 0.5) for e in recent_mh) / len(recent_mh)
        if recent_mh else 0.5
    )

    interventions_used = getattr(model, "_applied_interventions_log", [])
    intervention_str = (
        f" Interventions used: {', '.join(interventions_used)}."
        if interventions_used else ""
    )

    scenario_feel = {
        "cafe":   "low-stakes social setting",
        "office": "structured task-focused environment",
        "escape": "high-pressure time-limited environment",
    }.get(scenario_type, scenario_type)

    # Cooperation balance — used to separate stress from conflict in the narrative
    total_shares_d = getattr(model, "total_shares", 0)
    agree_count_d = sum(
        1 for snap in getattr(model, "history", [])
        for ev in snap.get("events", []) if ev.get("type") == "agree"
    )
    coop_total_d     = total_shares_d + agree_count_d
    conflict_total_d = getattr(model, "total_conflict_events", 0)
    coop_dominated   = coop_total_d >= max(1, conflict_total_d) * 1.8

    stress_feel = (
        "Stress stayed low" if avg_stress < 0.20
        else "Stress reached moderate levels" if avg_stress < 0.40
        else "Stress ran high"
    )
    if conflict_rate < 0.10 or coop_dominated:
        conflict_feel = "with little to no conflict"
    elif conflict_rate < 0.25:
        conflict_feel = "with some friction"
    else:
        conflict_feel = "with significant conflict and challenge events"

    # For high-stress but low-conflict runs, explicitly note the distinction
    stress_source = ""
    if avg_stress > 0.45 and coop_dominated:
        stress_source = (
            " The elevated stress came from scenario pressure and blocker ageing "
            "rather than interpersonal conflict — cooperation remained dominant throughout."
        )

    # Team-preset context — explains what each preset is configured for so a
    # reader does not interpret, say, low conflict on a Smooth Team as a bug.
    _tp_raw = (getattr(model, "team_preset", "") or "").lower()
    preset_context_map = {
        "smooth_team": (
            "This matches the Smooth Team preset: agents shared information, "
            "confirmed decisions, and resolved blockers without resistance."
        ),
        "tension_team": (
            "This matches the Tension Team preset. Stress rose while the active "
            "blocker remained unresolved, and challenge "
            "events showed friction under pressure, but "
            "cooperation still outweighed conflict."
        ),
        "pressure_team": (
            "For a Pressure Team, this run shows controlled urgency rather than "
            "conflict. Agents moved through blockers efficiently, with stress rising "
            "under pressure while cooperation remained intact."
        ),
        "creative_team": (
            "This matches the Creative Team preset: agents used flexible idea-sharing, "
            "confirmation, and collaborative problem-solving rather than conflict."
        ),
    }
    preset_context = preset_context_map.get(_tp_raw, "")
    preset_str = f" {preset_context}" if preset_context else ""

    return (
        f"This {scenario_feel} run ({team_preset or 'default team'}) reached "
        f"{progress}% completion in {ticks} steps. "
        f"{stress_feel} {conflict_feel}. "
        f"Agents exchanged {share_count} pieces of information. "
        f"Outcome: {label}.{stress_source}{preset_str}{intervention_str}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Memory summary
# ──────────────────────────────────────────────────────────────────────────────
# I chose to generate narrative text for the memory summary rather than just
# returning raw numbers because the simulation is part of a study on social
# agent cognition — readers of the export need to understand *why* an impression
# formed, not just that conflict_prone = 0.4. Each narrative is grounded in the
# actual STM data: which events the observer recorded, how many, and what
# behavioural effect the impression had in that specific scenario type.
# Café, office, and escape each get different wording because the same
# pattern (e.g. "conflict_prone") has different consequences depending on
# the coordination structure — refusing a request blocks a café preference
# negotiation differently from how it blocks an escape-room clue chain.

def _impression_evidence(
    target_id: str,
    observer_stm: list,
    pattern_key: str,
    max_items: int = 3,
) -> List[Dict[str, Any]]:
    """Extract the real STM events that drove an impression.

    For positive impressions I pull agree/share_info/confirm events from the
    target.  For conflict-prone impressions I pull refuse/challenge/push_back.
    Each entry gets the tick number and a short text label so the frontend can
    render step-level bullet points like "Step 3: A2 agreed with A1's clue."
    """
    if pattern_key == "positive":
        # Only unambiguously cooperative events count as positive evidence.
        # "say" is excluded because urgency phrases like "Fine. Move." or
        # "Door's open. Go." are coordination signals, not expressions of warmth.
        good_kinds = {"agree", "share_info", "confirm"}
        events = [
            m for m in observer_stm
            if m.get("from") == target_id and m.get("kind") in good_kinds
        ]
    else:  # conflict_prone
        bad_kinds = {"refuse", "challenge", "push_back", "deflect", "stall"}
        events = [
            m for m in observer_stm
            if m.get("from") == target_id and m.get("kind") in bad_kinds
        ]

    # Deduplicate by tick (keep first per tick), then take up to max_items
    seen_ticks: set = set()
    evidence = []
    for m in events:
        t = m.get("tick", 0)
        if t in seen_ticks:
            continue
        seen_ticks.add(t)
        evidence.append({
            "tick": t,
            "kind": m.get("kind", ""),
            "text": (
                ((m.get("text") or "")[:117] + "...")
                if len(m.get("text") or "") > 120
                else (m.get("text") or "")
            ),
            "item": m.get("item", ""),
        })
        if len(evidence) >= max_items:
            break
    return evidence


def _impression_narrative(
    observer_id: str,
    target_id: str,
    impression: Dict[str, Any],
    observer_stm: list,
    scenario_type: str,
    agent_personality: str,
    evidence_count: int = 0,
) -> str:
    """Build a one-to-two sentence human-readable explanation of:
    (a) what led to this impression, and
    (b) what behavioural effect it had.

    Uses real STM data for (a) and the actual coded decision rules for (b).
    """
    patterns = impression.get("patterns", {})

    # ── What events from the target drove the impression? ─────────────────
    target_events = [m for m in observer_stm if m.get("from") == target_id]
    shares    = [m for m in target_events if m.get("kind") == "share_info"]
    challenges= [m for m in target_events if m.get("kind") in ("challenge", "refuse")]
    agrees    = [m for m in target_events if m.get("kind") == "agree"]
    total_ev  = len(target_events)

    def _item_label(item: Optional[str]) -> str:
        if not item:
            return "information"
        # Convert snake_case to readable label
        return item.replace("_", " ")

    # ── Impression strength guard ─────────────────────────────────────────
    # An impression can only form after 3+ memories with the same speaker, but
    # the interaction_count stored in imp_data is the raw STM count which can be
    # exactly 3 — the minimum.  If it is that low, use weaker language rather
    # than asserting a "strong" or definitive impression.
    _shown_events = evidence_count or min(3, total_ev)
    if _shown_events <= 1:
        _signal_stage = "early"
    elif _shown_events == 2:
        _signal_stage = "emerging"
    else:
        _signal_stage = "strong"

    # ── Positive impression narrative ─────────────────────────────────────
    if "positive" in patterns and "conflict_prone" not in patterns:
        if _signal_stage == "early":
            impression_label = (
                "an early coordination signal"
                if scenario_type == "escape"
                else "an early positive signal"
            )
        elif _signal_stage == "emerging":
            impression_label = (
                "an emerging coordination pattern"
                if scenario_type == "escape"
                else "an emerging positive pattern"
            )
        else:
            impression_label = (
                "a strong coordination memory impression"
                if scenario_type == "escape"
                else "a strong positive memory impression"
            )
        if shares:
            # Describe the cause using the evidence content rather than the raw
            # item key so it doesn't render as "after A4 shared door" (missing article).
            if scenario_type == "escape":
                # Check whether the evidence suggests confirmation, code-sharing, or general clues
                share_items = [_item_label(s.get("item")) for s in shares if s.get("item")]
                if share_items:
                    stage = share_items[-1]
                    cause = (
                        f"after {target_id} confirmed clues and contributed to "
                        f"the {stage}-solving stage"
                    )
                else:
                    cause = f"after {target_id} contributed useful clue information"
            else:
                recent_item = _item_label(shares[-1].get("item"))
                cause = f"after {target_id} shared information on {recent_item}"
        elif agrees:
            count_a = len(agrees)
            cause = (
                f"after {count_a} agreement{'s' if count_a != 1 else ''} from {target_id}"
            )
        else:
            cause = f"through {total_ev} cooperative interactions"

        impact_by_scenario = {
            "cafe":   (
                f"This slightly increased {observer_id}'s willingness to share "
                f"their own constraints and reduced their chance of refusing "
                f"{target_id}'s requests."
            ),
            "office": (
                f"This slightly reduced {observer_id}'s reluctance to hand over "
                f"information when {target_id} asked, and nudged their trust upward."
            ),
            "escape": (
                f"This suggests {observer_id} became more confident in {target_id}'s "
                f"clue contributions and may be less likely to double-check "
                f"{target_id}'s suggestions later in the run."
            ),
        }
        impact = impact_by_scenario.get(
            scenario_type,
            f"This slightly increased {observer_id}'s cooperation with {target_id}.",
        )
        if _signal_stage == "early":
            if scenario_type == "escape" and len(agrees) == 1:
                return (
                    f"{observer_id} detected an early coordination signal from {target_id} after one agreement. "
                    f"This suggests {observer_id} became slightly more confident in {target_id}'s clue contributions, "
                    f"although there was not enough repeated evidence to form a strong memory impression."
                )
            return (
                f"An early coordination signal was detected from {target_id}. "
                f"This suggests slightly increased confidence, but there was not enough repeated evidence "
                f"to form a strong memory impression."
            )
        verb = "formed" if _signal_stage == "strong" else "detected"
        return f"{observer_id} {verb} {impression_label} from {target_id} {cause}. {impact}"

    # ── Conflict-prone impression narrative ───────────────────────────────
    if "conflict_prone" in patterns and "positive" not in patterns:
        if challenges:
            if _signal_stage == "early":
                cause = (
                    f"after {len(challenges)} early challenge or refusal signal(s) from {target_id} "
                    f"— too few interactions to confirm a strong conflict pattern"
                )
            else:
                cause = (
                    f"after {len(challenges)} challenge or refusal event(s) from {target_id}"
                )
        else:
            cause = f"through friction across {total_ev} interactions with {target_id}"

        impact_by_scenario = {
            "cafe":   (
                f"This made {observer_id} more resistant to {target_id}'s suggestions "
                f"and slightly more likely to refuse their requests."
            ),
            "office": (
                f"This increased {observer_id}'s reluctance to respond to "
                f"{target_id}'s asks, and pushed their trust slightly lower."
            ),
            "escape": (
                f"This raised {observer_id}'s doubt threshold for {target_id}'s "
                f"clue suggestions and made {observer_id} hold back sharing with them."
            ),
        }
        impact = impact_by_scenario.get(
            scenario_type,
            f"This made {observer_id} more cautious around {target_id}.",
        )
        if _signal_stage == "early":
            lead = f"{observer_id} detected an early conflict signal from {target_id} {cause}."
        elif _signal_stage == "emerging":
            lead = f"{observer_id} detected an emerging conflict pattern from {target_id} {cause}."
        else:
            lead = f"{observer_id} formed a strong conflict-prone memory impression of {target_id} {cause}."
        return f"{lead} {impact}"

    # ── Volatile (both positive and conflict-prone) ────────────────────────
    if "volatile" in patterns:
        return (
            f"{observer_id} formed a mixed impression of {target_id} — "
            f"both cooperative and challenging at different points across "
            f"{total_ev} interactions. The opposing signals cancelled out, "
            f"so this had little net effect on trust or sharing behaviour."
        )

    # Fallback for rare pattern combinations
    pat_names = ", ".join(patterns.keys())
    return (
        f"{observer_id} formed an impression of {target_id} ({pat_names}) "
        f"from {total_ev} interactions."
    )


def _no_impression_reason(model: "SimModel") -> str:
    """Return an honest explanation of why no impression formed in this run.

    I deliberately wrote this to be honest rather than optimistic — it's easy
    to write "impressions are still forming" as a placeholder, but that would
    mislead someone reading the export about what actually happened. Instead,
    this function checks the real reasons: run ended too quickly, agents had
    too few interactions with any single partner, or the scenario structure
    (e.g. escape room clues spread across different pairs) prevented enough
    repeat interactions. The threshold of 3 interactions per pair comes from
    the update_impressions() logic in EmotionalMemory — no impression can form
    unless at least 3 memories with the same 'from' speaker exist in STM.
    """
    scenario_type = getattr(model, "scenario_type", "office")
    ticks = model.tick

    # Check STM sizes to understand whether data was simply too sparse
    stm_sizes = [
        len(list(a.stm))
        for a in getattr(model, "agents", [])
        if hasattr(a, "stm")
    ]
    avg_stm = sum(stm_sizes) / max(1, len(stm_sizes))

    scenario_labels = {
        "cafe":   "café run",
        "office": "office run",
        "escape": "escape run",
    }
    label = scenario_labels.get(scenario_type, "run")

    if ticks < 6:
        return (
            f"No impression formed — this {label} ended in only {ticks} ticks, "
            f"too quickly for repeated interactions to build a pattern."
        )
    if avg_stm < 4:
        return (
            f"No strong impression formed in this {label}. Agents had too few "
            f"repeated interactions with any single partner "
            f"(average {avg_stm:.0f} memories per agent) to establish a pattern."
        )

    scenario_reasons = {
        "cafe": (
            f"No strong impression formed in this {label}. Agents resolved their "
            f"preferences through mostly neutral or distributed exchanges, "
            f"so no consistent positive or conflict pattern built up."
        ),
        "office": (
            f"No strong impression formed in this {label}. Tasks were completed "
            f"before agents accumulated enough repeat interactions with any one "
            f"partner to trigger a pattern."
        ),
        "escape": (
            f"No strong impression formed in this {label}. Each agent tended to "
            f"interact with different partners across clues, preventing the "
            f"three-plus interactions per pair needed to register a pattern."
        ),
    }
    return scenario_reasons.get(
        scenario_type,
        f"No strong impression formed in this {label} ({ticks} ticks).",
    )


def summarize_memory(model: "SimModel") -> Dict[str, Any]:
    """Build the memory_summary section for a finished run's export.

    Returns structured data (counts, strongest impressions) plus human-readable
    narratives derived entirely from real impression data.  When no impressions
    formed, returns an honest explanation rather than empty fields.

    I structured this to surface the two most interesting impressions —
    strongest_positive and strongest_conflict — rather than listing all of them,
    because those are the cases most likely to have actually changed agent
    behaviour during the run. A weak positive impression (pos_rate just above 0.30)
    has a small nudge effect; the strongest one had the largest trust and sharing
    influence. The all_impressions list is still included for full export / replay.
    """
    agents = getattr(model, "agents", [])
    scenario_type = getattr(model, "scenario_type", "office")

    # ── Collect every impression across all agents ────────────────────────
    all_impressions: List[Dict[str, Any]] = []
    for agent in agents:
        if not (hasattr(agent, "memory") and agent.memory):
            continue
        personality = getattr(agent, "personality_type", "")
        for target_id, imp_data in (agent.memory.impressions or {}).items():
            patterns = imp_data.get("patterns", {})
            stm_list = list(agent.stm)
            # Determine primary pattern for evidence selection
            primary_pattern = (
                "positive" if "positive" in patterns else
                "conflict_prone" if "conflict_prone" in patterns else
                "positive"
            )
            # Build per-scenario effect sentence
            _obs = agent.public_id
            _eff_maps: Dict[str, Dict[str, str]] = {
                "positive": {
                    "escape": f"{_obs} became more willing to accept {target_id}'s clue suggestions without second-guessing them.",
                    "office": f"{_obs} became more likely to respond quickly to {target_id}'s information requests.",
                    "cafe":   f"{_obs} became more open to {target_id}'s preferences during negotiation.",
                },
                "conflict_prone": {
                    "escape": f"{_obs} became more hesitant to share clues with {target_id} and more likely to double-check their suggestions.",
                    "office": f"{_obs} became slower to respond to {target_id}'s asks and less likely to volunteer information.",
                    "cafe":   f"{_obs} became more resistant to {target_id}'s choices and more likely to push back.",
                },
            }
            effect_sentence = (
                _eff_maps.get(primary_pattern, {})
                .get(scenario_type, f"{_obs}'s behaviour toward {target_id} shifted based on this impression.")
            )
            evidence = _impression_evidence(
                target_id=target_id,
                observer_stm=stm_list,
                pattern_key=primary_pattern,
            )
            entry: Dict[str, Any] = {
                "observer":          agent.public_id,
                "observer_personality": personality,
                "target":            target_id,
                "patterns":          dict(patterns),
                "formed_at_tick":    imp_data.get("formed_at", 0),
                "interaction_count": imp_data.get("interaction_count", 0),
                "evidence": evidence,
                "effect": effect_sentence,
                "narrative": _impression_narrative(
                    observer_id=agent.public_id,
                    target_id=target_id,
                    impression=imp_data,
                    observer_stm=stm_list,
                    scenario_type=scenario_type,
                    agent_personality=personality,
                    evidence_count=len(evidence),
                ),
            }
            all_impressions.append(entry)

    # ── Aggregate counts ──────────────────────────────────────────────────
    total_impressions  = len(all_impressions)
    positive_count     = sum(1 for e in all_impressions if "positive"      in e["patterns"])
    conflict_count     = sum(1 for e in all_impressions if "conflict_prone" in e["patterns"])

    # ── Pick strongest of each type ───────────────────────────────────────
    def _strength(entry: Dict[str, Any], key: str) -> float:
        return float(entry["patterns"].get(key, 0.0))

    positive_entries = [e for e in all_impressions if "positive" in e["patterns"]
                        and "conflict_prone" not in e["patterns"]]
    conflict_entries = [e for e in all_impressions if "conflict_prone" in e["patterns"]
                        and "positive" not in e["patterns"]]

    strongest_positive = (
        max(positive_entries, key=lambda e: _strength(e, "positive"))
        if positive_entries else None
    )
    strongest_conflict = (
        max(conflict_entries, key=lambda e: _strength(e, "conflict_prone"))
        if conflict_entries else None
    )

    # ── Build result ──────────────────────────────────────────────────────
    result: Dict[str, Any] = {
        "total_impressions":   total_impressions,
        "positive_count":      positive_count,
        "conflict_prone_count": conflict_count,
        "strongest_positive":  strongest_positive,
        "strongest_conflict":  strongest_conflict,
        "all_impressions":     all_impressions,
    }

    if total_impressions == 0:
        result["no_impression_reason"] = _no_impression_reason(model)
    else:
        result["no_impression_reason"] = None

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Emotion summary
# ──────────────────────────────────────────────────────────────────────────────
# I designed the emotion_summary to be self-contained and dissertation-ready.
# The key question I wanted it to answer is: "did injecting this emotion actually
# move the needle?" — so I included stress_impact and trust_impact as signed
# running totals, dominant_emotion for the label, and average_valence/arousal
# for the dimensional representation. The plain-English interpretation is written
# to be readable without understanding the simulation internals: a supervisor
# looking at the export should be able to tell at a glance whether the user's
# emotion injection had a meaningful effect on group dynamics.
# When no injection occurred I return a full placeholder (not None/empty) so
# the export schema is consistent regardless of whether the feature was used.

def _agent_emotional_pressure_summary(model: "SimModel") -> Dict[str, Any]:
    """Summarise the NLP-derived emotional pressure built up across all agents.

    Reads the per-agent STMs (short-term memories) at end-of-run and the
    emotional_memory_pressure snapshots in metric_history to give a
    sentence-level explanation of what the agents experienced emotionally.
    """
    mh: List[Dict[str, Any]] = getattr(model, "metric_history", [])
    pressures   = [e["emotional_memory_pressure"]   for e in mh if "emotional_memory_pressure"   in e]
    positivities = [e["emotional_memory_positivity"] for e in mh if "emotional_memory_positivity" in e]

    if not pressures:
        return {
            "avg_pressure":     0.0,
            "avg_positivity":   0.0,
            "peak_pressure":    0.0,
            "peak_pressure_tick": 0,
            "interpretation":   "No emotional memory data — run was too short or agents had no dialogue.",
        }

    avg_pressure   = round(sum(pressures)    / len(pressures),    3)
    avg_positivity = round(sum(positivities) / len(positivities),  3) if positivities else 0.0
    peak_pressure  = round(max(pressures),  3)
    peak_tick      = mh[pressures.index(peak_pressure)]["tick"] if peak_pressure in pressures else 0

    # Build dominant per-agent emotion counts
    _neg = frozenset({"anger","annoyance","disapproval","disgust","fear","sadness",
                       "disappointment","nervousness","grief","remorse","embarrassment"})
    _pos = frozenset({"joy","gratitude","approval","admiration","optimism",
                       "relief","excitement","love","pride"})
    all_emotions: Dict[str, int] = {}
    for agent in getattr(model, "agents", []):
        for mem in list(getattr(agent, "stm", [])):
            em = mem.get("primary_emotion", "")
            if em and em != "neutral":
                all_emotions[em] = all_emotions.get(em, 0) + 1

    dominant_neg = max((e for e in all_emotions if e in _neg), key=lambda k: all_emotions[k], default=None)
    dominant_pos = max((e for e in all_emotions if e in _pos), key=lambda k: all_emotions[k], default=None)

    if avg_pressure > 0.40:
        pressure_feel = "heavy"
    elif avg_pressure > 0.22:
        pressure_feel = "moderate"
    elif avg_pressure > 0.10:
        pressure_feel = "mild"
    else:
        pressure_feel = "low"

    parts = [f"Agents carried {pressure_feel} emotional pressure throughout the run "
             f"(avg {avg_pressure:.0%} of recent memories negative)."]
    if dominant_neg:
        parts.append(f"Most frequent negative emotion detected: {dominant_neg}.")
    if dominant_pos:
        parts.append(f"Most frequent positive emotion: {dominant_pos}.")
    if avg_positivity > avg_pressure:
        parts.append("Positive memories outweighed negative ones overall — the team's emotional tone was broadly constructive.")
    elif avg_pressure > 0.30:
        parts.append("Sustained negative emotional memory likely contributed to elevated stress and reduced share willingness over time.")

    # When scenario stress was high but emotional memory pressure was low,
    # make the distinction explicit so it doesn't look like a contradiction.
    if avg_pressure < 0.15:
        _recent_mh = getattr(model, "metric_history", [])[-5:]
        _run_avg_stress = (
            sum(e.get("avg_stress", 0.0) for e in _recent_mh) / max(1, len(_recent_mh))
            if _recent_mh else 0.0
        )
        if _run_avg_stress > 0.35:
            parts.append(
                "Agent emotional memory remained neutral, so the elevated stress came "
                "from scenario pressure and blocker ageing rather than accumulated "
                "negative memories."
            )

    return {
        "avg_pressure":       avg_pressure,
        "avg_positivity":     avg_positivity,
        "peak_pressure":      peak_pressure,
        "peak_pressure_tick": peak_tick,
        "dominant_negative":  dominant_neg,
        "dominant_positive":  dominant_pos,
        "interpretation":     " ".join(parts),
    }


def summarize_emotions(model: "SimModel") -> Dict[str, Any]:
    """Build the emotion_summary section for a finished run's export.

    Reads from model._emotion_log (list of emotion_injection events appended
    by inject_user_emotion()).  Returns a zero-inputs placeholder when no
    emotion injection occurred.
    """
    log: List[Dict[str, Any]] = getattr(model, "_emotion_log", [])

    if not log:
        return {
            "emotion_inputs":         0,
            "dominant_emotion":       None,
            "average_valence":        None,
            "average_arousal":        None,
            "strongest_input":        None,
            "stress_impact":          "+0.00",
            "trust_impact":           "+0.00",
            "ticks_applied":          [],
            "interpretation":         "No user emotion input was applied during this run.",
            "agent_emotional_memory": _agent_emotional_pressure_summary(model),
        }

    n = len(log)

    # Dominant emotion = most frequent top-label
    from collections import Counter
    emotion_counts: Counter = Counter(e["detected_emotion"] for e in log)
    dominant = emotion_counts.most_common(1)[0][0]

    avg_valence = round(sum(e["valence"] for e in log) / n, 3)
    avg_arousal = round(sum(e["arousal"] for e in log) / n, 3)

    # Strongest input = highest |stress_delta|
    strongest = max(log, key=lambda e: abs(e.get("stress_delta", 0.0)))

    total_stress_delta = sum(e.get("stress_delta", 0.0) for e in log)
    total_trust_delta  = sum(e.get("trust_delta",  0.0) for e in log)
    ticks_applied      = sorted({e["tick"] for e in log})

    # Plain-English valence / arousal labels
    if avg_valence > 0.4:
        valence_label = "strongly positive"
    elif avg_valence > 0.1:
        valence_label = "mildly positive"
    elif avg_valence < -0.4:
        valence_label = "strongly negative"
    elif avg_valence < -0.1:
        valence_label = "mildly negative"
    else:
        valence_label = "neutral"

    if avg_arousal > 0.65:
        arousal_label = "high"
    elif avg_arousal > 0.35:
        arousal_label = "moderate"
    else:
        arousal_label = "low"

    stress_sign = "increased" if total_stress_delta > 0 else "decreased"
    stress_abs  = abs(round(total_stress_delta, 3))
    trust_sign  = "increased" if total_trust_delta > 0 else "decreased" if total_trust_delta < 0 else "unchanged"

    # Effect strength label + zero-impact reason
    effect_abs = abs(total_stress_delta) + abs(total_trust_delta)
    if effect_abs >= 0.15:
        effect_label = "strong"
        zero_reason  = None
    elif effect_abs >= 0.04:
        effect_label = "moderate"
        zero_reason  = None
    else:
        effect_label = "minimal"
        # Explain specifically why
        if dominant == "neutral":
            zero_reason = (
                f"The detected emotion '{dominant}' maps to near-zero valence and "
                f"arousal in the Russell circumplex model, so no stress or trust "
                f"deltas were applied to agents."
            )
        elif avg_arousal < 0.2:
            zero_reason = (
                f"'{dominant}' has very low arousal ({avg_arousal:.2f}), "
                f"which keeps stress and trust deltas below the simulation's "
                f"action threshold — the signal was detected but not strong "
                f"enough to change agent behaviour."
            )
        else:
            zero_reason = (
                f"The combined stress and trust delta from '{dominant}' was "
                f"{effect_abs:.3f} — below the visible-effect threshold. "
                f"The emotion was classified but its intensity was too low to "
                f"move the simulation metrics."
            )

    if dominant == "neutral" or effect_label == "minimal":
        interp = (
            f"{n} emotion input{'s' if n > 1 else ''} detected (dominant: {dominant}). "
            f"Mapped valence: {valence_label} · arousal: {arousal_label}. "
            f"Simulation effect: minimal."
        )
    else:
        interp = (
            f"{n} emotion input{'s' if n > 1 else ''} detected. "
            f"Dominant emotion: {dominant} — {valence_label}, {arousal_label} arousal. "
            f"Group stress {stress_sign} by {stress_abs:.3f} and trust was {trust_sign}. "
            f"Effects decayed over the following ticks."
        )

    return {
        "emotion_inputs":   n,
        "dominant_emotion": dominant,
        "average_valence":  avg_valence,
        "average_arousal":  avg_arousal,
        "valence_label":    valence_label,
        "arousal_label":    arousal_label,
        "effect_label":     effect_label,
        "zero_reason":      zero_reason,
        "strongest_input":  strongest.get("text", ""),
        "stress_impact":    f"{total_stress_delta:+.3f}",
        "trust_impact":     f"{total_trust_delta:+.3f}",
        "ticks_applied":    ticks_applied,
        "interpretation":   interp,
        "injections":       log,
        # NLP-derived emotional texture from agent memory
        "agent_emotional_memory": _agent_emotional_pressure_summary(model),
    }


def generate_run_interpretation(model: "SimModel") -> Dict[str, Any]:
    """Generate experiment-framed interpretation of a completed simulation run.

    Aggregates per-agent and group-level metrics from model.history and returns
    two structured experiment findings (personality effect, environment effect)
    plus a plain-English summary.  Kept in metrics.py so route files stay thin.
    """
    agents = list(model.agents)
    history = model.history

    # ── Aggregate metrics across the run ──────────────────────────────────────
    all_stress = [tick["metrics"]["avg_stress"] for tick in history if "metrics" in tick]
    peak_stress = max(all_stress) if all_stress else 0.0
    final_stress = all_stress[-1] if all_stress else 0.0

    all_trust = [tick["metrics"]["avg_trust"] for tick in history if "metrics" in tick]
    final_trust = all_trust[-1] if all_trust else 0.5

    refusal_total = sum(
        tick["metrics"].get("refusal_count", 0)
        for tick in history if "metrics" in tick
    )
    share_total = sum(
        tick["metrics"].get("share_count", 0)
        for tick in history if "metrics" in tick
    )

    # ── Per-agent stats ────────────────────────────────────────────────────────
    per_agent_refusals: Dict[str, int] = {}
    per_agent_shares: Dict[str, int] = {}
    for tick in history:
        for ev in tick.get("events", []):
            actor = ev.get("actor", "")
            if ev.get("type") == "refuse":
                per_agent_refusals[actor] = per_agent_refusals.get(actor, 0) + 1
            elif ev.get("type") == "share_info":
                per_agent_shares[actor] = per_agent_shares.get(actor, 0) + 1

    # Agent personalities
    personalities = {a.public_id: getattr(a, "personality_type", "Easygoing") for a in agents}

    # Most reluctant agent (most refusals)
    reluctant_id = max(per_agent_refusals, key=per_agent_refusals.get) if per_agent_refusals else None
    reluctant_personality = personalities.get(reluctant_id, "") if reluctant_id else ""
    reluctant_refusals = per_agent_refusals.get(reluctant_id, 0) if reluctant_id else 0

    # Most cooperative agent (most shares)
    cooperative_id = max(per_agent_shares, key=per_agent_shares.get) if per_agent_shares else None
    cooperative_personality = personalities.get(cooperative_id, "") if cooperative_id else ""

    # ── Scenario-level framing ─────────────────────────────────────────────────
    scenario_id = model.scenario.id
    env_type = "office" if "office" in scenario_id else "cafe" if "cafe" in scenario_id else "escape"

    env_labels = {
        "office": "professional task-coordination",
        "cafe":   "low-stakes social decision-making",
        "escape": "high-pressure collaborative problem-solving",
    }
    env_label = env_labels.get(env_type, env_type)

    completion_ticks = model.tick
    outcome = model.end_reason or "unknown"
    progress = model.scenario.progress_ratio()

    # ── Experiment 1: Personality effect ─────────────────────────────────────
    personality_counts: Dict[str, int] = {}
    for p in personalities.values():
        personality_counts[p] = personality_counts.get(p, 0) + 1
    dominant_p = max(personality_counts, key=personality_counts.get) if personality_counts else "mixed"

    p1_lines = []
    if reluctant_id and reluctant_refusals > 0:
        p1_lines.append(
            f"{reluctant_personality} agents delayed sharing "
            f"({reluctant_refusals} refusal{'s' if reluctant_refusals > 1 else ''} recorded)."
        )
    if cooperative_id and per_agent_shares.get(cooperative_id, 0) > 1:
        coop_shares = per_agent_shares[cooperative_id]
        p1_lines.append(
            f"{cooperative_personality} agents drove information flow "
            f"({coop_shares} shares)."
        )
    if peak_stress > 0.35:
        p1_lines.append(
            f"Peak group stress reached {peak_stress:.2f} — "
            f"high-N personality traits amplified tension under pressure."
        )
    elif peak_stress < 0.15:
        p1_lines.append(
            f"Peak stress stayed low at {peak_stress:.2f} — "
            f"agreeable personality mix kept dynamics stable."
        )

    experiment_1 = {
        "label": "Experiment 1 — Personality Effect",
        "finding": " ".join(p1_lines) if p1_lines else
                   f"Personality mix ({dominant_p}-dominant) produced {outcome} in {completion_ticks} ticks.",
        "metrics": {
            "peak_stress":      round(peak_stress, 3),
            "final_trust":      round(final_trust, 3),
            "total_refusals":   refusal_total,
            "total_shares":     share_total,
        },
    }

    # ── Experiment 2: Environment effect ─────────────────────────────────────
    stress_trajectory = "rising" if len(all_stress) >= 4 and all_stress[-1] > all_stress[0] else "stable"
    coord_label = {
        "office": "structured and sequential — agents queued information by role.",
        "cafe":   "negotiation-driven — preferences expressed before constraints resolved.",
        "escape": "pressure-sequential — clues unlocked in strict dependency order.",
    }.get(env_type, "unstructured.")

    e2_lines = [
        f"Environment: {env_label}.",
        f"Coordination pattern: {coord_label}",
        f"Stress trajectory was {stress_trajectory} "
        f"(start {all_stress[0]:.2f} → end {final_stress:.2f})." if all_stress else "",
    ]
    if outcome == "success":
        e2_lines.append(
            f"Task completed in {completion_ticks} ticks "
            f"({round(progress * 100)}% of tasks resolved)."
        )
    else:
        e2_lines.append(
            f"Run ended as {outcome} at tick {completion_ticks} "
            f"with {round(progress * 100)}% task completion."
        )

    experiment_2 = {
        "label": "Experiment 2 — Environment Effect",
        "finding": " ".join(l for l in e2_lines if l),
        "metrics": {
            "completion_ticks":   completion_ticks,
            "progress_pct":       round(progress * 100, 1),
            "stress_start":       round(all_stress[0], 3) if all_stress else 0,
            "stress_end":         round(final_stress, 3),
            "stress_trajectory":  stress_trajectory,
        },
    }

    # ── Overall summary — scenario-aware thresholds ───────────────────────────
    # Escape is inherently high-pressure; adjust what counts as "smooth"
    stress_hi = 0.30 if env_type == "escape" else 0.35
    stress_lo = 0.12 if env_type == "escape" else 0.20

    if outcome == "success" and peak_stress <= stress_lo:
        if env_type == "escape":
            summary = (
                f"Clean escape — group solved all clues in {completion_ticks} ticks "
                f"with peak stress at {peak_stress:.2f}. Strong coordination under time pressure."
            )
        else:
            summary = (
                f"Smooth run — high cooperation, low conflict. "
                f"{env_label.capitalize()} scenario completed in {completion_ticks} ticks."
            )
    elif outcome == "success" and peak_stress >= stress_hi:
        summary = (
            f"Successful but tense — stress peaked at {peak_stress:.2f}. "
            f"Agents pushed through pressure to complete the {env_type} scenario in {completion_ticks} ticks."
        )
    elif outcome == "success":
        summary = (
            f"{env_label.capitalize()} scenario completed in {completion_ticks} ticks. "
            f"Stress peaked at {peak_stress:.2f} — moderate tension, resolved through trust ({final_trust:.2f})."
        )
    elif outcome in ("partial", "failure"):
        summary = (
            f"Incomplete run ({round(progress * 100)}% done). "
            f"Group dynamics broke down under {env_type} conditions — refusals blocked progress."
        )
    else:
        summary = f"Outcome: {outcome}. {env_label.capitalize()} scenario, {completion_ticks} ticks."

    return {
        "summary":      summary,
        "experiment_1": experiment_1,
        "experiment_2": experiment_2,
    }
