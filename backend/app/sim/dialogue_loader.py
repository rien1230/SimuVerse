"""Loads dialogue data from JSON files. Provides the same interface as the old dialogue_banks.py."""
import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "dialogue"


def _load(filename: str):
    with open(_DATA_DIR / filename) as f:
        return json.load(f)


# Expose the same names that used to be in dialogue_banks.py
BANKS = _load("banks.json")
