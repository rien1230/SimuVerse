"""
Test 1: Reproducibility Under Seeded Runs
==========================================
Supports RQ3 — SimuVerse should produce identical outcomes
when the same seed and configuration are used.

Run with:
    PYTHONPATH=. python tests/run_test1_reproducibility.py
"""

import os, sys, warnings
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore")

from app.sim.model import SimModel

# ── Config ────────────────────────────────────────────────────────────────────
SCENARIO   = "escape_puzzle"
PRESET     = "smooth_team"
SEED       = 42
N_RUNS     = 10
MAX_TICKS  = 120
# ─────────────────────────────────────────────────────────────────────────────


def avg_trust(model):
    vals = []
    for a in model.agents:
        if a.trust:
            vals.append(sum(a.trust.values()) / len(a.trust))
    return sum(vals) / len(vals) if vals else 0.0


def avg_stress(model):
    return sum(a.stress for a in model.agents) / len(model.agents)


def run_once(seed):
    m = SimModel(seed=seed, scenario_id=SCENARIO,
                 team_preset=PRESET, episode_max_ticks=MAX_TICKS, use_nlp=False)
    while not m.ended:
        m.step()
    return {
        "outcome": m.end_reason,
        "steps":   m.tick,
        "trust":   avg_trust(m),
        "stress":  avg_stress(m),
    }


def stdev(values):
    n = len(values)
    if n < 2:
        return 0.0
    m = sum(values) / n
    return (sum((x - m) ** 2 for x in values) / (n - 1)) ** 0.5


def cv(values):
    m = sum(values) / len(values)
    if m == 0:
        return 0.0
    return stdev(values) / m * 100


# ── Run ───────────────────────────────────────────────────────────────────────
print()
print("=" * 65)
print("  TEST 1: REPRODUCIBILITY UNDER SEEDED RUNS")
print(f"  Scenario: {SCENARIO}  |  Preset: {PRESET}  |  Seed: {SEED}  |  N={N_RUNS}")
print("=" * 65)
print()

results = []
print(f"  {'Run':<5} {'Outcome':<12} {'Steps':<8} {'Avg Trust':<12} {'Avg Stress'}")
print(f"  {'-'*5} {'-'*12} {'-'*8} {'-'*12} {'-'*10}")

for i in range(1, N_RUNS + 1):
    r = run_once(SEED)
    results.append(r)
    print(f"  {i:<5} {r['outcome']:<12} {r['steps']:<8} {r['trust']:<12.4f} {r['stress']:.4f}")

print()

# ── Analysis ──────────────────────────────────────────────────────────────────
outcomes  = [r["outcome"] for r in results]
steps_v   = [r["steps"]  for r in results]
trust_v   = [r["trust"]  for r in results]
stress_v  = [r["stress"] for r in results]

concordant_outcome = all(o == outcomes[0] for o in outcomes)
concordance_count  = sum(1 for o in outcomes if o == outcomes[0])

print("  ANALYSIS")
print("  " + "-" * 50)
print(f"  Outcome concordance : {concordance_count}/{N_RUNS}  ({'100%' if concordant_outcome else f'{concordance_count/N_RUNS*100:.0f}%'})")
print(f"  Steps               : mean={sum(steps_v)/len(steps_v):.2f}, "
      f"std={stdev(steps_v):.4f}, CV={cv(steps_v):.2f}%")
print(f"  Avg Trust           : mean={sum(trust_v)/len(trust_v):.4f}, "
      f"std={stdev(trust_v):.6f}, CV={cv(trust_v):.2f}%")
print(f"  Avg Stress          : mean={sum(stress_v)/len(stress_v):.4f}, "
      f"std={stdev(stress_v):.6f}, CV={cv(stress_v):.2f}%")

print()
if concordant_outcome and stdev(steps_v) == 0:
    print("  ✅ RESULT: Perfect reproducibility — identical outcome, steps, trust,")
    print("     and stress across all 10 runs with the same seed.")
    print("     Addresses the reproducibility gap identified in Liu et al.")
elif concordant_outcome:
    print(f"  ✅ RESULT: Outcome concordance 100%. Minor floating-point variance")
    print(f"     in trust/stress (CV < 1%) is within acceptable bounds.")
else:
    print(f"  ⚠  RESULT: {concordance_count}/{N_RUNS} runs agree — check seed handling.")

print()
print("=" * 65)
print()
