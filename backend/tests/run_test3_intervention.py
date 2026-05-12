"""
Test 3: Intervention Counterfactual — Force Meeting Causal Effect
=================================================================
Supports RQ4 — Force Meeting intervention should produce measurably
higher average trust compared to a no-intervention control condition,
when applied to a tension-preset team at an early simulation tick.

Design: paired counterfactual (same seed sequence, two conditions).
Each seed generates one control run and one intervention run.
Comparison is trust and completion time at run end.

Run with:
    PYTHONPATH=. python tests/run_test3_intervention.py
"""

import os, warnings
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore")

from app.sim.model import SimModel
from scipy import stats

# ── Config ────────────────────────────────────────────────────────────────────
SCENARIO        = "office_proposal"
PRESET          = "tension_team"
N_RUNS          = 15
MAX_TICKS       = 120
INTERVENE_TICK  = 5       # Apply Force Meeting at tick 5
AGENT_A         = "A1"
AGENT_B         = "A3"
# ─────────────────────────────────────────────────────────────────────────────


def avg_trust(model):
    vals = []
    for a in model.agents:
        if a.trust:
            vals.append(sum(a.trust.values()) / len(a.trust))
    return sum(vals) / len(vals) if vals else 0.0


def run_control(seed):
    m = SimModel(seed=seed, scenario_id=SCENARIO,
                 team_preset=PRESET, episode_max_ticks=MAX_TICKS, use_nlp=False)
    while not m.ended:
        m.step()
    return {
        "outcome": m.end_reason,
        "steps":   m.tick,
        "trust":   avg_trust(m),
        "stress":  sum(a.stress for a in m.agents) / len(m.agents),
    }


def run_intervention(seed):
    m = SimModel(seed=seed, scenario_id=SCENARIO,
                 team_preset=PRESET, episode_max_ticks=MAX_TICKS, use_nlp=False)
    applied = False
    while not m.ended:
        if m.tick == INTERVENE_TICK and not applied:
            m.apply_intervention("force_meeting",
                                 {"agent_a_id": AGENT_A, "agent_b_id": AGENT_B})
            applied = True
        m.step()
    return {
        "outcome":   m.end_reason,
        "steps":     m.tick,
        "trust":     avg_trust(m),
        "stress":    sum(a.stress for a in m.agents) / len(m.agents),
        "intervened": applied,
    }


def mean(v):   return sum(v) / len(v) if v else 0.0
def stdev(v):
    n = len(v)
    if n < 2: return 0.0
    mu = mean(v)
    return (sum((x-mu)**2 for x in v) / (n-1))**0.5


def cohens_d(a, b):
    na, nb = len(a), len(b)
    pooled = (((na-1)*stdev(a)**2 + (nb-1)*stdev(b)**2) / (na+nb-2))**0.5
    if pooled == 0: return 0.0
    return (mean(a) - mean(b)) / pooled


# ── Run ───────────────────────────────────────────────────────────────────────
print()
print("=" * 65)
print("  TEST 3: INTERVENTION COUNTERFACTUAL — FORCE MEETING")
print(f"  Scenario: {SCENARIO}  |  Preset: {PRESET}  |  N={N_RUNS} per condition")
print(f"  Intervention: Force Meeting ({AGENT_A}↔{AGENT_B}) at tick {INTERVENE_TICK}")
print(f"  Design: paired (same seed, two conditions per seed)")
print("=" * 65)

print(f"\n  Running {N_RUNS} paired runs ...", flush=True)
control_results = []
interv_results  = []
for seed in range(N_RUNS):
    control_results.append(run_control(seed))
    interv_results.append(run_intervention(seed))
print(f"  Done.")

# ── Per-run detail ────────────────────────────────────────────────────────────
print()
print(f"  {'Seed':<6} {'Ctrl steps':<12} {'Ctrl trust':<12} "
      f"{'Intv steps':<12} {'Intv trust':<12} {'Δ trust'}")
print(f"  {'-'*6} {'-'*12} {'-'*12} {'-'*12} {'-'*12} {'-'*8}")

trust_deltas = []
for i in range(N_RUNS):
    c = control_results[i]
    v = interv_results[i]
    delta = v["trust"] - c["trust"]
    trust_deltas.append(delta)
    sign = "+" if delta >= 0 else ""
    print(f"  {i:<6} {c['steps']:<12} {c['trust']:<12.4f} "
          f"{v['steps']:<12} {v['trust']:<12.4f} {sign}{delta:.4f}")

# ── Summary stats ─────────────────────────────────────────────────────────────
ctrl_trust  = [r["trust"]  for r in control_results]
interv_trust= [r["trust"]  for r in interv_results]
ctrl_steps  = [r["steps"]  for r in control_results]
interv_steps= [r["steps"]  for r in interv_results]

# Paired t-test on trust (same seeds)
t_trust, p_trust = stats.ttest_rel(ctrl_trust, interv_trust)
d_trust = cohens_d(ctrl_trust, interv_trust)

# Independent t-test on steps
t_steps, p_steps = stats.ttest_ind(ctrl_steps, interv_steps, equal_var=False)
d_steps = cohens_d(ctrl_steps, interv_steps)

positive_deltas = sum(1 for d in trust_deltas if d > 0)

print()
print(f"  SUMMARY")
print(f"  {'Condition':<24} {'Mean steps':<14} {'Mean trust':<14} {'Std trust'}")
print(f"  {'-'*24} {'-'*14} {'-'*14} {'-'*12}")
print(f"  {'Control (no interv.)':<24} {mean(ctrl_steps):<14.1f} {mean(ctrl_trust):<14.4f} {stdev(ctrl_trust):.4f}")
print(f"  {'Force Meeting (interv.)':<24} {mean(interv_steps):<14.1f} {mean(interv_trust):<14.4f} {stdev(interv_trust):.4f}")

print()
cohens_header = "Cohen's d"
print(f"  STATISTICAL TESTS")
print(f"  {'Test':<30} {'t-stat':<10} {'p-value':<12} {cohens_header:<12} {'Sig?'}")
print(f"  {'-'*30} {'-'*10} {'-'*12} {'-'*12} {'-'*8}")
print(f"  {'Trust (paired t-test)':<30} {t_trust:<10.3f} {p_trust:<12.4f} "
      f"{abs(d_trust):<12.3f} {'Yes **' if p_trust < 0.01 else ('Yes *' if p_trust < 0.05 else 'No (ns)')}")
print(f"  {'Steps (Welch t-test)':<30} {t_steps:<10.3f} {p_steps:<12.4f} "
      f"{abs(d_steps):<12.3f} {'Yes **' if p_steps < 0.01 else ('Yes *' if p_steps < 0.05 else 'No (ns)')}")

print()
print(f"  Directional consistency: {positive_deltas}/{N_RUNS} seeds show positive trust delta")
print(f"  Mean trust delta: {mean(trust_deltas):+.4f} (std={stdev(trust_deltas):.4f})")

print()
print("  INTERPRETATION")
print("  " + "-" * 55)

if p_trust < 0.05:
    print(f"  ✅ Force Meeting intervention produced significantly higher")
    print(f"     final trust (p={p_trust:.4f}, d={abs(d_trust):.3f}, paired t-test).")
    print(f"     This supports RQ4: user interventions produce measurable")
    print(f"     changes beyond natural simulation variance.")
else:
    print(f"  Trust difference: p={p_trust:.4f} (not significant at α=0.05).")

if positive_deltas >= N_RUNS - 2:
    print(f"  ✅ Directional consistency: {positive_deltas}/{N_RUNS} seeds show positive trust")
    print(f"     delta after Force Meeting, indicating a consistent effect")
    print(f"     even if the magnitude is modest.")
elif positive_deltas > N_RUNS // 2:
    print(f"  The effect is directionally consistent ({positive_deltas}/{N_RUNS} positive deltas)")
    print(f"  but not significant. A larger sample (n≥30) is recommended.")
else:
    print(f"  The effect is inconsistent ({positive_deltas}/{N_RUNS} positive deltas).")

print()
print("=" * 65)
print()
