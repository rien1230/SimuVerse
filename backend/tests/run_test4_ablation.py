"""
Test 4: Ablation Study — Contribution of Trust, Memory, and Personality
========================================================================
Supports design claims — Removing individual components (trust dynamics,
memory, personality variation) should produce measurably different outcomes
compared to the full model.

Run with:
    PYTHONPATH=. python tests/run_test4_ablation.py
"""

import os, warnings
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore")

from app.sim.model import SimModel
from scipy import stats

# ── Config ────────────────────────────────────────────────────────────────────
SCENARIO  = "office_proposal"
PRESET    = "tension_team"   # Tension preset amplifies the effect of ablations
N_RUNS    = 15
MAX_TICKS = 120
# ─────────────────────────────────────────────────────────────────────────────

NEUTRAL_TRAITS = {"E": 0.5, "A": 0.5, "N": 0.5, "C": 0.5, "O": 0.5}


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


# ── Condition runners ─────────────────────────────────────────────────────────

def run_full(seed):
    """Full model — trust dynamics, memory, personality all active."""
    m = SimModel(seed=seed, scenario_id=SCENARIO,
                 team_preset=PRESET, episode_max_ticks=MAX_TICKS, use_nlp=False)
    while not m.ended:
        m.step()
    ec = count_events(m)
    return {
        "outcome":    m.end_reason,
        "steps":      m.tick,
        "trust":      avg_trust(m),
        "stress":     sum(a.stress for a in m.agents) / len(m.agents),
        "conflicts":  ec["refuse"] + ec["challenge"],
        "shares":     ec["share_info"],
    }


def run_no_trust(seed):
    """Trust fixed at 0.5 — no dynamic trust updates between agents."""
    m = SimModel(seed=seed, scenario_id=SCENARIO,
                 team_preset=PRESET, episode_max_ticks=MAX_TICKS, use_nlp=False)
    # Initialise all trust to 0.5
    for a in m.agents:
        a.trust = {peer: 0.5 for peer in a.trust}
    while not m.ended:
        m.step()
        # Reset trust after each tick (prevents dynamic updates having effect)
        for a in m.agents:
            a.trust = {peer: 0.5 for peer in a.trust}
    ec = count_events(m)
    return {
        "outcome":   m.end_reason,
        "steps":     m.tick,
        "trust":     avg_trust(m),
        "stress":    sum(a.stress for a in m.agents) / len(m.agents),
        "conflicts": ec["refuse"] + ec["challenge"],
        "shares":    ec["share_info"],
    }


def run_no_memory(seed):
    """Memory cleared after every tick — agents have no persistent impressions."""
    m = SimModel(seed=seed, scenario_id=SCENARIO,
                 team_preset=PRESET, episode_max_ticks=MAX_TICKS, use_nlp=False)
    while not m.ended:
        m.step()
        # Clear short-term memory each tick
        for a in m.agents:
            if hasattr(a, "memory") and hasattr(a.memory, "stm"):
                a.memory.stm.clear()
            if hasattr(a, "memory") and hasattr(a.memory, "impressions"):
                a.memory.impressions.clear()
    ec = count_events(m)
    return {
        "outcome":   m.end_reason,
        "steps":     m.tick,
        "trust":     avg_trust(m),
        "stress":    sum(a.stress for a in m.agents) / len(m.agents),
        "conflicts": ec["refuse"] + ec["challenge"],
        "shares":    ec["share_info"],
    }


def run_no_personality(seed):
    """All agents given neutral traits (0.5 across all OCEAN dimensions)."""
    m = SimModel(seed=seed, scenario_id=SCENARIO,
                 team_preset=PRESET, episode_max_ticks=MAX_TICKS, use_nlp=False)
    # Neutralise traits before simulation starts
    for a in m.agents:
        a.traits = dict(NEUTRAL_TRAITS)
    while not m.ended:
        m.step()
    ec = count_events(m)
    return {
        "outcome":   m.end_reason,
        "steps":     m.tick,
        "trust":     avg_trust(m),
        "stress":    sum(a.stress for a in m.agents) / len(m.agents),
        "conflicts": ec["refuse"] + ec["challenge"],
        "shares":    ec["share_info"],
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


# ── Run all conditions ────────────────────────────────────────────────────────
conditions = [
    ("Full model",         run_full),
    ("No trust dynamics",  run_no_trust),
    ("No memory",          run_no_memory),
    ("Neutral personality",run_no_personality),
]

print()
print("=" * 70)
print("  TEST 4: ABLATION STUDY — CONTRIBUTION OF EACH COMPONENT")
print(f"  Scenario: {SCENARIO}  |  Preset: {PRESET}  |  N={N_RUNS} per condition")
print("=" * 70)

all_results = {}
for name, runner in conditions:
    print(f"\n  Running {N_RUNS} runs — {name} ...", flush=True)
    runs = [runner(seed) for seed in range(N_RUNS)]
    all_results[name] = runs
    outcomes = [r["outcome"] for r in runs]
    print(f"  Done. Outcomes: {set(outcomes)}")

# ── Results table ─────────────────────────────────────────────────────────────
print()
print("  RESULTS TABLE (mean ± std)")
print()
print(f"  {'Condition':<22} {'Steps':<14} {'Conflicts':<14} {'Shares':<12} "
      f"{'Trust':<10} {'Stress'}")
print(f"  {'-'*22} {'-'*14} {'-'*14} {'-'*12} {'-'*10} {'-'*10}")

for name, _ in conditions:
    runs = all_results[name]
    st  = [r["steps"]     for r in runs]
    cf  = [r["conflicts"] for r in runs]
    sh  = [r["shares"]    for r in runs]
    tr  = [r["trust"]     for r in runs]
    sr  = [r["stress"]    for r in runs]
    print(f"  {name:<22} {mean(st):.1f}±{stdev(st):.1f}   "
          f"{mean(cf):.1f}±{stdev(cf):.1f}   "
          f"{mean(sh):.1f}±{stdev(sh):.1f}  "
          f"{mean(tr):.3f}    "
          f"{mean(sr):.3f}")

# ── Statistical tests vs full model ──────────────────────────────────────────
ALPHA = 0.05 / 3   # Bonferroni correction (3 ablation comparisons)
full_runs = all_results["Full model"]
full_steps     = [r["steps"]     for r in full_runs]
full_conflicts = [r["conflicts"] for r in full_runs]

print()
print(f"  STATISTICAL TESTS vs Full Model (Welch's t-test, Bonferroni α={ALPHA:.4f})")
print()
print(f"  {'Ablation':<22} {'Metric':<14} {'Full mean':<12} {'Ablated mean':<14} "
      f"{'p-value':<12} {'d':<8} {'Sig?'}")
print(f"  {'-'*22} {'-'*14} {'-'*12} {'-'*14} {'-'*12} {'-'*8} {'-'*6}")

for name, _ in conditions[1:]:   # skip Full model itself
    runs = all_results[name]
    abl_steps     = [r["steps"]     for r in runs]
    abl_conflicts = [r["conflicts"] for r in runs]

    # Test steps
    t_st, p_st = stats.ttest_ind(full_steps, abl_steps, equal_var=False)
    d_st = cohens_d(full_steps, abl_steps)
    sig_st = "Yes" if p_st < ALPHA else "No"

    # Test conflicts
    t_cf, p_cf = stats.ttest_ind(full_conflicts, abl_conflicts, equal_var=False)
    d_cf = cohens_d(full_conflicts, abl_conflicts)
    sig_cf = "Yes" if p_cf < ALPHA else "No"

    print(f"  {name:<22} {'Steps':<14} {mean(full_steps):<12.1f} {mean(abl_steps):<14.1f} "
          f"{p_st:<12.4f} {abs(d_st):<8.3f} {sig_st}")
    print(f"  {'':<22} {'Conflict events':<14} {mean(full_conflicts):<12.1f} {mean(abl_conflicts):<14.1f} "
          f"{p_cf:<12.4f} {abs(d_cf):<8.3f} {sig_cf}")
    print()

print(f"  Bonferroni-corrected significance threshold: α = {ALPHA:.4f}")
print()
print("  INTERPRETATION")
print("  " + "-" * 55)

for name, _ in conditions[1:]:
    runs    = all_results[name]
    abl_st  = [r["steps"]     for r in runs]
    abl_cf  = [r["conflicts"] for r in runs]
    _, p_st = stats.ttest_ind(full_steps, abl_st, equal_var=False)
    _, p_cf = stats.ttest_ind(full_conflicts, abl_cf, equal_var=False)

    step_diff = mean(full_steps) - mean(abl_st)
    cf_diff   = mean(full_conflicts) - mean(abl_cf)

    if p_st < ALPHA or p_cf < ALPHA:
        print(f"  ✅ {name}: significantly alters simulation behaviour")
        if p_st < ALPHA:
            direction = "longer" if step_diff < 0 else "shorter"
            print(f"     Steps {direction} by {abs(step_diff):.1f} (p={p_st:.4f})")
        if p_cf < ALPHA:
            direction = "more" if cf_diff < 0 else "fewer"
            print(f"     {direction.capitalize()} conflict events (p={p_cf:.4f})")
    else:
        print(f"  — {name}: difference not significant at corrected α")
        print(f"     (steps p={p_st:.4f}, conflicts p={p_cf:.4f})")

print()
print("  These results indicate which components contribute measurably to")
print("  simulation behaviour. Components whose removal produces no")
print("  significant change should be noted as design limitations.")
print()
print("=" * 70)
print()
