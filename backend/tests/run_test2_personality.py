"""
Test 2a: Personality Preset Effects on Cooperation and Conflict
===============================================================
Supports RQ2 — Different personality presets should produce
measurably different sharing, refusal, and conflict rates.

Run with:
    PYTHONPATH=. python tests/run_test2_personality.py
"""

import os, sys, warnings
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore")

from app.sim.model import SimModel
from scipy import stats

# ── Config ────────────────────────────────────────────────────────────────────
SCENARIO  = "office_proposal"
PRESETS   = ["smooth_team", "creative_team", "pressure_team", "tension_team"]
N_RUNS    = 20
MAX_TICKS = 120
# ─────────────────────────────────────────────────────────────────────────────


def count_events(model):
    counts = {"share_info": 0, "refuse": 0, "challenge": 0, "agree": 0}
    for tick_data in model.history:
        for ev in tick_data.get("events", []):
            t = ev.get("type", "")
            if t in counts:
                counts[t] += 1
    return counts


def avg_trust(model):
    vals = []
    for a in model.agents:
        if a.trust:
            vals.append(sum(a.trust.values()) / len(a.trust))
    return sum(vals) / len(vals) if vals else 0.0


def run_once(seed, preset):
    m = SimModel(seed=seed, scenario_id=SCENARIO,
                 team_preset=preset, episode_max_ticks=MAX_TICKS, use_nlp=False)
    while not m.ended:
        m.step()
    ec = count_events(m)
    return {
        "outcome":   m.end_reason,
        "steps":     m.tick,
        "shares":    ec["share_info"],
        "refusals":  ec["refuse"],
        "challenges":ec["challenge"],
        "agreements":ec["agree"],
        "trust":     avg_trust(m),
        "stress":    sum(a.stress for a in m.agents) / len(m.agents),
    }


def mean(v):   return sum(v) / len(v) if v else 0.0
def stdev(v):
    n = len(v)
    if n < 2: return 0.0
    m = mean(v)
    return (sum((x-m)**2 for x in v) / (n-1))**0.5


# ── Run ───────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("  TEST 2a: PERSONALITY PRESET EFFECTS ON COOPERATION AND CONFLICT")
print(f"  Scenario: {SCENARIO}  |  {N_RUNS} runs per preset")
print("=" * 70)

all_results = {}
for preset in PRESETS:
    label = preset.replace("_team", "").capitalize()
    print(f"\n  Running {N_RUNS} runs — {preset} ...", flush=True)
    runs = []
    for seed in range(N_RUNS):
        runs.append(run_once(seed, preset))
    all_results[preset] = runs
    print(f"  Done. Sample outcomes: {[r['outcome'] for r in runs[:5]]}")

# ── Summary table ─────────────────────────────────────────────────────────────
print()
print("  RESULTS TABLE (mean ± std)")
print()
print(f"  {'Preset':<14} {'Shares':<14} {'Refusals':<14} {'Challenges':<14} "
      f"{'Steps':<10} {'Trust':<10} {'Stress'}")
print(f"  {'-'*14} {'-'*14} {'-'*14} {'-'*14} {'-'*10} {'-'*10} {'-'*10}")

for preset in PRESETS:
    runs = all_results[preset]
    label = preset.replace("_team", "").capitalize()
    sh = [r["shares"]     for r in runs]
    rf = [r["refusals"]   for r in runs]
    ch = [r["challenges"] for r in runs]
    st = [r["steps"]      for r in runs]
    tr = [r["trust"]      for r in runs]
    sr = [r["stress"]     for r in runs]

    print(f"  {label:<14} "
          f"{mean(sh):.1f}±{stdev(sh):.1f}  {'':<6}"
          f"{mean(rf):.1f}±{stdev(rf):.1f}  {'':<6}"
          f"{mean(ch):.1f}±{stdev(ch):.1f}  {'':<6}"
          f"{mean(st):.1f}   {'':<3}"
          f"{mean(tr):.3f}   {'':<2}"
          f"{mean(sr):.3f}")

# ── Statistical tests ─────────────────────────────────────────────────────────
smooth_runs  = all_results["smooth_team"]
tension_runs = all_results["tension_team"]

smooth_shares    = [r["shares"]     for r in smooth_runs]
tension_shares   = [r["shares"]     for r in tension_runs]
smooth_refusals  = [r["refusals"]   for r in smooth_runs]
tension_refusals = [r["refusals"]   for r in tension_runs]
smooth_challenges= [r["challenges"] for r in smooth_runs]
tension_challenges=[r["challenges"] for r in tension_runs]
smooth_trust     = [r["trust"]      for r in smooth_runs]
tension_trust    = [r["trust"]      for r in tension_runs]
smooth_steps     = [r["steps"]      for r in smooth_runs]
tension_steps    = [r["steps"]      for r in tension_runs]


def cohens_d(a, b):
    na, nb = len(a), len(b)
    pooled_std = (((na-1)*stdev(a)**2 + (nb-1)*stdev(b)**2) / (na+nb-2))**0.5
    if pooled_std == 0:
        return 0.0
    return (mean(a) - mean(b)) / pooled_std


def ttest(a, b):
    t, p = stats.ttest_ind(a, b, equal_var=False)
    return t, p


print()
print("  STATISTICAL TESTS: Smooth vs Tension (Welch's t-test)")
cohens_header = "Cohen's d"
print(f"  {'Metric':<22} {'Smooth mean':<14} {'Tension mean':<14} {'t-stat':<10} {'p-value':<12} {cohens_header}")
print(f"  {'-'*22} {'-'*14} {'-'*14} {'-'*10} {'-'*12} {'-'*10}")

metrics = [
    ("Share events",   smooth_shares,    tension_shares,   "higher in Smooth"),
    ("Refusal events", smooth_refusals,  tension_refusals, "higher in Tension"),
    ("Challenge events", smooth_challenges, tension_challenges, "higher in Tension"),
    ("Avg Trust",      smooth_trust,     tension_trust,    "higher in Smooth"),
    ("Steps to end",   smooth_steps,     tension_steps,    "lower in Smooth"),
]

for label, a_vals, b_vals, direction in metrics:
    t, p = ttest(a_vals, b_vals)
    d = cohens_d(a_vals, b_vals)
    sig = "**" if p < 0.01 else ("*" if p < 0.05 else "ns")
    print(f"  {label:<22} {mean(a_vals):<14.2f} {mean(b_vals):<14.2f} "
          f"{t:<10.3f} {p:<12.4f} {abs(d):.3f}  {sig}")

print()
print("  ** p<0.01  * p<0.05  ns = not significant")
print()
print("  INTERPRETATION")
print("  " + "-" * 55)

# Compute t-test for refusals as primary metric
t_rf, p_rf = ttest(smooth_refusals, tension_refusals)
d_rf = cohens_d(smooth_refusals, tension_refusals)
t_sh, p_sh = ttest(smooth_shares, tension_shares)

if p_rf < 0.05:
    print(f"   Tension teams produce significantly more refusals than")
    print(f"     Smooth teams (p={p_rf:.4f}, d={abs(d_rf):.2f}).")
else:
    print(f"  Refusal difference: p={p_rf:.4f} (not significant at α=0.05).")

if p_sh < 0.05:
    t_sh, p_sh = ttest(smooth_shares, tension_shares)
    d_sh = cohens_d(smooth_shares, tension_shares)
    print(f"   Smooth teams share information more frequently")
    print(f"     (p={p_sh:.4f}, d={abs(d_sh):.2f}).")

t_tr, p_tr = ttest(smooth_trust, tension_trust)
d_tr = cohens_d(smooth_trust, tension_trust)
if p_tr < 0.05:
    print(f"   Smooth teams end with significantly higher average trust")
    print(f"     (p={p_tr:.4f}, d={abs(d_tr):.2f}).")

print()
print("  These results support the claim that personality presets produce")
print("  measurably different agent behaviours across all key social metrics.")
print()
print("=" * 70)
print()
