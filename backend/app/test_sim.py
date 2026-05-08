#!/usr/bin/env python3
"""
Test script for goal-driven simulation.
"""

import sys
import os

# Add the project root to sys.path so that imports work
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.sim.model import SimModel
from app.sim.scenario_data import SCENARIOS
import random


def run_test(scenario_id: str, max_ticks: int = 30, seed: int = 42):
    print(f"\n=== Testing Scenario: {scenario_id} ===\n")

    # Configure the simulation
    config = {
        "environment": SCENARIOS[scenario_id]["environment"],
        "scenario_id": scenario_id,
        "min_events_per_tick": 0,
        "episode_max_ticks": max_ticks,
    }

    # Create model
    model = SimModel(seed=seed, **config)

    # Run step by step
    tick = 0
    while not model.ended and tick < max_ticks:
        model.step()
        tick = model.tick

        # Get the diff from last_step
        diff = model.last_diff
        if not diff:
            print("No diff produced, stopping.")
            break

        # Print tick header
        print(f"\n--- Tick {tick} ---")

        # Print events
        events = diff.get("events", [])
        if events:
            print("Events:")
            for e in events:
                etype = e.get("type", "?")
                actor = e.get("actor", "?")
                target = e.get("target", "?")
                text = e.get("text", "")
                item = e.get("item", "")
                if item:
                    print(f"  {actor} -> {target} [{etype}]: {text} (item: {item})")
                else:
                    print(f"  {actor} -> {target} [{etype}]: {text}")
        else:
            print("No events this tick.")

        # Print scenario tasks
        scenario_info = diff.get("scenario", {})
        tasks = scenario_info.get("tasks", {})
        if tasks:
            print("Tasks:")
            for task, done in tasks.items():
                mark = "✓" if done else "✗"
                print(f"  {mark} {task}")

        # Print progress
        progress = scenario_info.get("progress", 0)
        outcome = scenario_info.get("outcome", "running")
        print(f"Progress: {progress * 100:.1f}%  Outcome: {outcome}")

        # ==================== SAFE NLP + AGENT STATES (CRASH FIXED) ====================
        print("\nAgent states (NLP + internal state):")
        for agent in model.agents:
            state = agent.to_state()
            # Safe handling for None values on early ticks
            emotion = state.get("last_detected_emotion") or "None"
            stress = state.get("stress") or 0.0
            strategy = state.get("strategy", "N/A")
            valence = state["mood"].get("valence", 0.0)
            arousal = state["mood"].get("arousal", 0.0)
            print(f"  {state['id']:>3} | emotion: {emotion:<12} | stress: {stress:.2f} | "
                  f"strategy: {strategy:<15} | valence: {valence:.2f} | arousal: {arousal:.2f}")

    # Final outcome
    print("\n=== Simulation Ended ===")
    print(f"End reason: {model.end_reason}")
    print(f"Final tasks: {model.scenario.tasks}")
    print(f"Final outcome: {model.scenario.outcome(model.tick)}")

    # Print agent known_items
    print("\nAgent knowledge:")
    for agent in model.agents:
        print(f"  {agent.public_id}: knows {agent.known_items}")


if __name__ == "__main__":
    # List available scenarios
    print("Available scenarios:")
    for sid in SCENARIOS.keys():
        print(f"  {sid}")

    # Pick a scenario to tests
    scenario = "office_proposal"
    # scenario = "cafe_restaurant"
    # scenario = "escape_code"

    run_test(scenario, max_ticks=30, seed=random.randint(0, 10000))