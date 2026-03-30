"""
Typed contracts for the experiment layer.
Using Pydantic ensures validation at the API boundary and clean
interfaces between services — no more raw dict passing.
"""
from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Input / config models
# ---------------------------------------------------------------------------

class ExperimentConfig(BaseModel):
    scenario_id:       str   = Field(default="office_proposal")
    n_runs:            int   = Field(default=20,  ge=1,  le=100)
    max_ticks:         int   = Field(default=120, ge=10, le=500)
    use_nlp:           bool  = Field(default=True)
    seed:              int   = Field(default=0,   ge=0)


class InterventionExperimentConfig(BaseModel):
    scenario_id:           str              = Field(default="office_proposal")
    intervention_type:     str
    intervention_params:   Dict[str, Any]   = Field(default_factory=dict)
    intervention_tick:     int              = Field(default=5, ge=1)
    n_runs:                int              = Field(default=20, ge=1, le=100)
    max_ticks:             int              = Field(default=120, ge=10, le=500)


# ---------------------------------------------------------------------------
# Per-run result
# ---------------------------------------------------------------------------

class RunResult(BaseModel):
    seed:             int
    outcome:          str
    ticks:            int
    final_progress:   float
    avg_trust:        float
    avg_stress:       float
    peak_stress:      float
    conflict_rate:    float
    group_tension:    float
    peak_tension:     float
    group_cohesion:   float
    total_refusals:   int
    total_shares:     int
    stalled_ticks:    int
    first_share_tick: Optional[int]
    completion_order: List[str]


# ---------------------------------------------------------------------------
# Aggregate stats block (reused across multiple response models)
# ---------------------------------------------------------------------------

class MetricStats(BaseModel):
    mean:   float
    median: float
    stdev:  float
    min:    float
    max:    float


class OutcomeCounts(BaseModel):
    success:   int = 0
    partial:   int = 0
    failure:   int = 0
    meltdown:  int = 0
    deadlock:  int = 0
    harmony:   int = 0
    max_ticks: int = 0


class OutcomeRates(BaseModel):
    success:   float = 0.0
    partial:   float = 0.0
    failure:   float = 0.0
    meltdown:  float = 0.0
    deadlock:  float = 0.0
    harmony:   float = 0.0
    max_ticks: float = 0.0


# ---------------------------------------------------------------------------
# Full experiment result
# ---------------------------------------------------------------------------

class ExperimentResult(BaseModel):
    scenario_id:              str
    n_runs:                   int
    mode:                     str          # "nlp_on" | "nlp_off"
    nlp_enabled:              bool
    outcome_counts:           OutcomeCounts
    outcome_rates:            OutcomeRates
    success_rate:             float
    avg_ticks_to_success:     Optional[float]
    avg_first_share_tick:     Optional[float]
    refusal_to_share_ratio:   Optional[float]
    ticks:                    MetricStats
    final_progress:           MetricStats
    avg_trust:                MetricStats
    avg_stress:               MetricStats
    peak_stress:              MetricStats
    conflict_rate:            MetricStats
    group_tension:            MetricStats
    peak_tension:             MetricStats
    group_cohesion:           MetricStats
    total_refusals:           MetricStats
    total_shares:             MetricStats
    stalled_ticks:            MetricStats
    per_run:                  List[RunResult]


# ---------------------------------------------------------------------------
# NLP comparison result
# ---------------------------------------------------------------------------

class MetricComparison(BaseModel):
    with_nlp:    float
    without_nlp: float
    delta:       float
    nlp_better:  bool


class OutcomeComparison(BaseModel):
    with_nlp:    float
    without_nlp: float
    delta:       float


class NLPCompareResult(BaseModel):
    scenario_id:              str
    n_runs_each:              int
    experiment:               str
    success_rate:             OutcomeComparison
    failure_rate:             OutcomeComparison
    deadlock_rate:            OutcomeComparison
    partial_rate:             OutcomeComparison
    avg_trust:                MetricComparison
    avg_stress:               MetricComparison
    peak_stress:              MetricComparison
    conflict_rate:            MetricComparison
    total_shares:             MetricComparison
    total_refusals:           MetricComparison
    stalled_ticks:            MetricComparison
    group_tension:            MetricComparison
    ticks_to_success:         Dict[str, Optional[float]]
    first_share_tick:         Dict[str, Optional[float]]
    refusal_to_share_ratio:   Dict[str, Optional[float]]
    summary:                  str
    full_with_nlp:            Dict[str, Any]
    full_without_nlp:         Dict[str, Any]