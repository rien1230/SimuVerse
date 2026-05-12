"""Relationship-tie helpers for trust links between agents.

This file only computes the pairwise trust snapshot used by the frontend and
history layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from app.sim.model import SimModel


def compute_ties(
    model: "SimModel",
    agents_sorted: list,
) -> List[Dict[str, Any]]:
    """Build one undirected trust edge per agent pair."""
    ties: List[Dict[str, Any]] = []
    id_to_agent = {agent.public_id: agent for agent in agents_sorted}
    ids = [agent.public_id for agent in agents_sorted]

    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a_id, b_id = ids[i], ids[j]
            trust = (
                id_to_agent[a_id].trust.get(b_id, 0.5)
                + id_to_agent[b_id].trust.get(a_id, 0.5)
            ) / 2.0
            ties.append({"a": a_id, "b": b_id, "trust": round(trust, 3)})

    return ties
