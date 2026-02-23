# holds ticks(number) and it increases by 1 we 'step' and must output a simple message .
from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional
import mesa
from app.sim.agent import SimAgent


class SimModel(mesa.Model):
    """
    - 4 agents
    - remembers last tick events so agents can reply (reply_inbox)
    - keeps pacing fast (min_events_per_tick)
    - ends automatically (max_ticks)
    - adds metrics to every diff
    - stores diff in self.last_diff (because Mesa step() return is swallowed)
    """

    def __init__(
        self,
        seed: int,
        min_events_per_tick: int = 2,
        episode_max_ticks: int = 120,
    ) -> None:
        # Mesa seeded randomness (self.random)
        super().__init__(seed=seed)

        # Tick counter
        self.tick = 0

        # Story pacing: ensure at least N events per tick
        self.min_events_per_tick = min_events_per_tick

        # Episode length cap
        self.episode_max_ticks = episode_max_ticks

        # Mesa step() return is swallowed, so I put the "diff" here
        self.last_diff: Optional[Dict[str, Any]] = None
        self.prev_events: List[Dict[str, Any]] = []

        # ✅ Milestone 2: target_id -> actor_id (who last spoke to me)
        self.reply_inbox: Dict[str, str] = {}

        # ending state
        self.ended = False
        self.end_reason = ""


        self.avg_trust_hist = deque(maxlen=10)

        # ----------------------------
        # Create 4 agents (Mesa )
        # ----------------------------
        SimAgent(self, public_id="A1", traits={"E": 0.55, "A": 0.35, "generosity": 0.30}, speech_style="formal",  long_goal="Gain influence")
        SimAgent(self, public_id="A2", traits={"E": 0.85, "A": 0.75, "generosity": 0.85}, speech_style="bubbly",  long_goal="Keep harmony")
        SimAgent(self, public_id="A3", traits={"E": 0.35, "A": 0.30, "generosity": 0.25}, speech_style="dry",     long_goal="Avoid disrespect")
        SimAgent(self, public_id="A4", traits={"E": 0.60, "A": 0.55, "generosity": 0.55}, speech_style="neutral", long_goal="Understand motives")

        # Initialise trust AFTER all agents exist
        agents_sorted = sorted(list(self.agents), key=lambda a: a.public_id)
        ids = [a.public_id for a in agents_sorted]
        for a in agents_sorted:
            a.trust = {other: 0.5 for other in ids if other != a.public_id}

    # ----------------------------
    # built a reply_inbox from last tick’s events
    # ----------------------------
    def _build_reply_inbox(self) -> None:
        """
        Make a little “who spoke to me last tick?” map. To increase chances of them interacting.
        """
        inbox: Dict[str, str] = {}
        for e in self.prev_events:
            actor = e.get("actor")
            target = e.get("target")
            if actor and target:
                inbox[target] = actor
        self.reply_inbox = inbox

    # ----------------------------
    # Mesa tick
    # ----------------------------
    def step(self) -> None:
        """
        Run one tick.

        Mesa wraps step() so the return value is lost.
        That’s why i stored the diff in self.last_diff.
        """
        # If episode ended, do nothing
        if self.ended:
            return

        # Tick advances
        self.tick += 1

        # Build reply inbox based on previous tick
        self._build_reply_inbox()

        agents_sorted = sorted(list(self.agents), key=lambda a: a.public_id)

        # 1) Decide events (agents can read self.reply_inbox for reply behaviour)
        events: List[Dict[str, Any]] = []
        for a in agents_sorted:
            others = [o for o in agents_sorted if o is not a]
            e = a.decide_event(others)
            if e is not None:
                events.append(e)

        # 2) Ensure pacing (not slow): force at least N events
        while len(events) < self.min_events_per_tick:
            speaker = agents_sorted[self.random.randrange(len(agents_sorted))]
            target = [x for x in agents_sorted if x is not speaker][self.random.randrange(len(agents_sorted) - 1)]
            events.append({"type": "say", "actor": speaker.public_id, "target": target.public_id, "text": "Hi."})

        # 3) Apply events (trust/mood/memory)
        for a in agents_sorted:
            a.apply_events(events, tick=self.tick)

        # 4) Build ties (average trust both ways)
        ties: List[Dict[str, Any]] = []
        id_to_agent = {a.public_id: a for a in agents_sorted}
        ids = [a.public_id for a in agents_sorted]

        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a_id, b_id = ids[i], ids[j]
                aa = id_to_agent[a_id]
                bb = id_to_agent[b_id]
                trust = (aa.trust.get(b_id, 0.5) + bb.trust.get(a_id, 0.5)) / 2.0
                ties.append({"a": a_id, "b": b_id, "trust": round(trust, 3)})

        # ----------------------------
        #  metrics
        # ----------------------------
        avg_trust = (sum(t["trust"] for t in ties) / len(ties)) if ties else 0.5
        mean_valence = sum(a.valence for a in agents_sorted) / len(agents_sorted)
        mean_arousal = sum(a.arousal for a in agents_sorted) / len(agents_sorted)

        negative_events = sum(1 for e in events if e.get("type") in ("ignore", "insult"))
        conflict_rate = negative_events / max(1, len(events))

        event_counts: Dict[str, int] = {}
        for e in events:
            et = str(e.get("type", ""))
            event_counts[et] = event_counts.get(et, 0) + 1

        metrics = {
            "avg_trust": round(avg_trust, 3),
            "mean_valence": round(mean_valence, 3),
            "mean_arousal": round(mean_arousal, 3),
            "conflict_rate": round(conflict_rate, 3),
            "event_counts": event_counts,
        }

        self.avg_trust_hist.append(avg_trust)

        # 1) Hard stop at max ticks
        if self.tick >= self.episode_max_ticks:
            self.ended = True
            self.end_reason = "max_ticks"

        # 2) Early stop if trust stays low/high for 10 ticks
        if len(self.avg_trust_hist) == self.avg_trust_hist.maxlen:
            if all(x < 0.30 for x in self.avg_trust_hist):
                self.ended = True
                self.end_reason = "meltdown"
            elif all(x > 0.75 for x in self.avg_trust_hist):
                self.ended = True
                self.end_reason = "harmony"

        # Save this tick’s events so next tick can reply
        self.prev_events = events

        # Save the diff for RunManager (since Mesa step return is swallowed)
        self.last_diff = {
            "tick": self.tick,
            "agents": [a.to_state() for a in agents_sorted],
            "ties": ties,
            "events": events,
            "metrics": metrics,
            "ended": self.ended,
            "end_reason": self.end_reason,
        }
