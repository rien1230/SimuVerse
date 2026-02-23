# backend/test_determinism.py
from __future__ import annotations

from pathlib import Path
import hashlib

from app.services.run_manager import RunManager


def hash_tick_lines(path: Path) -> str:
    """
    Hash ONLY the tick lines (ignore line 0 run_meta),
    so different run_id does not break determinism.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        first = True
        for line in f:
            if first:
                first = False
                continue  # skip meta header
            h.update(line)
    return h.hexdigest()


def run_and_hash(*, seed: int, config: dict, run_id: str, n_ticks: int) -> str:
    rm = RunManager(seed=seed, config=config, run_id=run_id)
    rm.start()
    for _ in range(n_ticks):
        rm.step()
    return hash_tick_lines(rm.logger.path)


def main() -> None:
    N = 20
    config = {"min_events_per_tick": 2, "episode_max_ticks": 120}

    # ---- Test A: SAME seed should match (deterministic) ----
    seed = 123
    h1 = run_and_hash(seed=seed, config=config, run_id="det_run_1", n_ticks=N)
    h2 = run_and_hash(seed=seed, config=config, run_id="det_run_2", n_ticks=N)

    print("same-seed hash1:", h1)
    print("same-seed hash2:", h2)

    if h1 != h2:
        raise AssertionError(" Not deterministic: same-seed tick logs differ")
    print(" Deterministic: same-seed tick logs match")

    # ---- Test B: DIFFERENT seed should NOT match (sanity check) ----
    h3 = run_and_hash(seed=124, config=config, run_id="det_run_3", n_ticks=N)

    print("diff-seed hash3:", h3)

    if h1 == h3:
        raise AssertionError(" Suspicious: different seed produced identical tick logs")
    print(" Sanity check: different seed produced different tick logs")


if __name__ == "__main__":
    main()
