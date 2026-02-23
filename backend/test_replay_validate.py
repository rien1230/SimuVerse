# backend/test_replay_validate.py
from __future__ import annotations

import json
from pathlib import Path


REQUIRED_KEYS = {"tick", "agents", "ties", "events"}


def main() -> None:
    # change this to an actual replay file you generated
    path = Path("../data/replays").glob("*.jsonl")
    file_path = next(path, None)
    if file_path is None:
        raise RuntimeError("No replay files found in data/replays")

    with file_path.open("r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    # line 0 must be meta
    meta = json.loads(lines[0])
    if meta.get("type") != "run_meta":
        raise AssertionError("First line must be run_meta header")

    expected_tick = 1
    for i, raw in enumerate(lines[1:], start=1):
        obj = json.loads(raw)

        # required keys
        missing = REQUIRED_KEYS - set(obj.keys())
        if missing:
            raise AssertionError(f"Line {i} missing keys: {missing}")

        # ticks must count up
        if obj["tick"] != expected_tick:
            raise AssertionError(f"Line {i} tick wrong: got {obj['tick']} expected {expected_tick}")
        expected_tick += 1

    print(" Replay valid:", file_path)


if __name__ == "__main__":
    main()
