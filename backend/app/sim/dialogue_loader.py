"""
Loads dialogue data from JSON files on disk into Python dicts.

This module replaced the old approach of hardcoding all dialogue directly in
dialogue_banks.py. Moving the data to JSON makes it much easier to edit phrases
without touching any Python code.

The public API (BANKS) is kept the same so existing imports don't need to change.

This file is intentionally simple: load the JSON once and expose it.
"""
import json
from pathlib import Path

# Navigate up two levels from this file to reach the backend root, then into data/dialogue
_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "dialogue"


def _load(filename: str):
    """Read and parse a JSON file from the dialogue data directory."""
    with open(_DATA_DIR / filename) as f:
        return json.load(f)


# Load the main dialogue bank at import time — it's a nested dict structured as:
# environment -> personality -> tone -> action -> [list of phrase strings]
# Expose the same names that used to be in dialogue_banks.py
BANKS = _load("banks.json")
