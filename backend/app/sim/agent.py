from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional
import mesa
from .emotions_analyser import  EmotionAnalyser

# trust (0-1), valence (-1 to 1), and arousal (0-1) within valid ranges
def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# How events change TRUST (target trusts actor more/less)
TRUST_DELTA = {
    "say": +0.02,
    "help": +0.12,
    "compliment": +0.10,
    "ignore": -0.07,
    "insult": -0.15,
}
# Valence: Pleasantness vs Unpleasantness
# How events change MOOD VALENCE (target feels better/worse)
VALENCE_DELTA = {
    "say": +0.03,
    "help": +0.18,
    "compliment": +0.12,
    "ignore": -0.10,
    "insult": -0.22,
}


class SimAgent(mesa.Agent):
    """
    - traits = personality sliders (mostly stable)
    - mood = how they feel right now (changes)
    - trust = how much they trust each other person (changes)
    - memory = short-term + long-term
    - goal = what they are trying to achieve
    """

    def __init__(
        self,
        model: mesa.Model,
        public_id: str,
        traits: Dict[str, float],
        speech_style: str,
        long_goal: str,
    ) -> None:
        super().__init__(public_id, model)
        self.public_id = public_id

        # Personality sliders
        self.traits = traits
        self.speech_style = speech_style

        # Goals
        self.long_goal = long_goal
        self.active_short_goal = "socialise"
        self.goal_progress = 0.0

        # Mood: valence (-1..1) and arousal (0..1)
        self.valence = 0.0
        self.arousal = 0.3

        # Energy (simple “battery” so behaviour changes over time)
        self.energy = 100

        # Memory
        self.stm = deque(maxlen=25)              # short-term memory (recent)
        self.ltm: List[Dict[str, Any]] = []      # long-term memory (important)

        # Trust: other_id -> 0..1 (filled in by model after all agents exist)
        self.trust: Dict[str, float] = {}

        # Debugging/interpretability
        self.last_thought = ""

        #emotion analyser
        self.emotion_analyser = EmotionAnalyser()  # ← ADD THIS
        self.emotion_memory = deque(maxlen=50)

    #Where agents Processes emotional content of messages. It would skip if there is no text. It would do that by
    # getting the strongest emotion and if the emotion is negative trust would decrease. If the emotions is positive
    # trust will increase. Ensuring the emotion interaction is stored in their memory.

    def process_emotional_message(self, text: str, speaker: str, tick: int) -> Dict[str, float]:

        if not text:
            return {}

        # Analyse emotions in the message
        emotions = self.emotion_analyser.analyse(text)

        if emotions:
            # Get the strongest emotion
            primary = max(emotions.items(), key=lambda x: x[1])[0]
            confidence = emotions[primary]

            # React based on the emotion detected
            if primary in ['anger', 'disgust', 'annoyance']:
                # Negative emotions decrease trust
                self.trust[speaker] = clamp(self.trust.get(speaker, 0.5) - 0.03, 0.0, 1.0)
                self.valence = clamp(self.valence - 0.05, -1.0, 1.0)
                self.last_thought = f"They seem {primary} with me."

            elif primary in ['joy', 'gratitude', 'admiration']:
                # Positive emotions increase trust
                self.trust[speaker] = clamp(self.trust.get(speaker, 0.5) + 0.02, 0.0, 1.0)
                self.valence = clamp(self.valence + 0.03, -1.0, 1.0)
                self.last_thought = f"They're being {primary}!"

            elif primary in ['sadness', 'grief', 'remorse']:
                # Sadness triggers empathy (especially for agreeable agents)
                if self.traits.get("A", 0.5) > 0.6:
                    self.valence = clamp(self.valence - 0.02, -1.0, 1.0)
                    self.last_thought = f"They seem sad. I feel for them."
                else:
                    self.last_thought = f"They're sad. Awkward."

            # Remember this emotional interaction
            self.emotion_memory.append({
                'tick': tick,
                'speaker': speaker,
                'primary_emotion': primary,
                'confidence': confidence,
                'all_emotions': emotions,
                'text': text
            })

        return emotions
    # ----------------------------
    # Decision: choose 0 or 1 action per tick
    # ----------------------------
    def decide_event(self, others: List["SimAgent"]) -> Optional[Dict[str, Any]]:
        """
        Decide one social event (or None).
        Uses model.random => deterministic when seed is the same.
        """
        E = self.traits.get("E", 0.5)  # extraversion
        A = self.traits.get("A", 0.5)  # agreeableness
        generosity = self.traits.get("generosity", 0.5)

        # talkative people act more and tired people act less
        act_chance = clamp(0.20 + 0.60 * E - 0.003 * (100 - self.energy), 0.05, 0.90)

        # ----------------------------
        # reply rule:
        # ----------------------------
        reply_actor_id = getattr(self.model, "reply_inbox", {}).get(self.public_id)

        # If someone talked to me last tick, boost the chance I do something this tick
        if reply_actor_id:
            act_chance = clamp(act_chance + 0.25, 0.05, 0.95)

        # Decide if I act this tick (using boosted act_chance)
        if self.model.random.random() > act_chance:
            self.last_thought = "I’m staying quiet."
            return None

        # Prefer replying to the person who spoke to me last tick
        reply_target = None
        if reply_actor_id:
            reply_target = next((o for o in others if o.public_id == reply_actor_id), None)

        # Probability of replying (more extraverted = more likely to reply)
        reply_p = clamp(0.60 + 0.25 * E, 0.50, 0.90)

        if reply_target and self.model.random.random() < reply_p:
            target = reply_target
        else:
            target = self._pick_target(others)

        # mood affects kindness vs rudeness
        p_insult = clamp((1.0 - A) * max(0.0, -self.valence) * 0.7, 0.0, 0.6)
        p_ignore = clamp(max(0.0, -self.valence) * 0.4, 0.0, 0.5)
        p_help = clamp((A * generosity) * max(0.0, self.valence + 0.2) * 0.6, 0.0, 0.7)
        p_compliment = clamp(A * max(0.0, self.valence + 0.1) * 0.5, 0.0, 0.6)

        r = self.model.random.random()

        if r < p_insult:
            self.last_thought = f"I’m irritated with {target.public_id}."
            return self._event("insult", target.public_id, self._say("insult", target.public_id))
        r -= p_insult

        if r < p_ignore:
            self.last_thought = f"I’m going to ignore {target.public_id}."
            return self._event("ignore", target.public_id, "")
        r -= p_ignore

        if r < p_help:
            self.last_thought = f"I can help {target.public_id}."
            return self._event("help", target.public_id, self._say("help", target.public_id))
        r -= p_help

        if r < p_compliment:
            self.last_thought = f"I’ll be nice to {target.public_id}."
            return self._event("compliment", target.public_id, self._say("compliment", target.public_id))

        self.last_thought = f"I’ll talk to {target.public_id}."
        return self._event("say", target.public_id, self._say("say", target.public_id))

    def _pick_target(self, others: List["SimAgent"]) -> "SimAgent":
        """Choose someone; slightly prefer people you trust less (creates drama)."""
        weights: List[float] = []
        for o in others:
            t = self.trust.get(o.public_id, 0.5)
            weights.append(max(0.01, 1.0 - t))

        total = sum(weights)
        r = self.model.random.random() * total
        acc = 0.0
        for o, w in zip(others, weights):
            acc += w
            if r <= acc:
                return o
        return others[-1]

    def _event(self, etype: str, target: str, text: str) -> Dict[str, Any]:
        return {"type": etype, "actor": self.public_id, "target": target, "text": text}

    # ----------------------------
    # Apply: update trust/mood/memory from events
    # ----------------------------
    def apply_events(self, events: List[Dict[str, Any]], tick: int) -> None:
        # tick-by-tick drift so things don’t explode
        self.energy = max(0, self.energy - 1)
        self.valence *= 0.97
        self.arousal = clamp(self.arousal * 0.98 + 0.01, 0.0, 1.0)

        for e in events:
            if e.get("target") != self.public_id:
                continue

            actor = e.get("actor", "")
            etype = e.get("type", "")
            text= e.get("text", "")


            # trust update
            dt = TRUST_DELTA.get(etype, 0.0)
            self.trust[actor] = clamp(self.trust.get(actor, 0.5) + dt, 0.0, 1.0)

            # mood update
            dv = VALENCE_DELTA.get(etype, 0.0)
            self.valence = clamp(self.valence + dv, -1.0, 1.0)
            self.arousal = clamp(self.arousal + abs(dv) * 0.15, 0.0, 1.0)

            # NEW: Process emotion from the message text
            if text:
                self.process_emotional_message(text, actor, tick)

            # memory
            mem = {
                "tick": tick,
                "kind": etype,
                "from": actor,
                "text": text,
                "importance": clamp(abs(dv) + abs(dt), 0.0, 1.0),
            }
            self.stm.append(mem)
            if mem["importance"] >= 0.5:
                self.ltm.append(mem)

        # tiny goal progress (happy agents progress slightly faster)
        self.goal_progress = clamp(
            self.goal_progress + (0.01 + 0.01 * max(0.0, self.valence)),
            0.0,
            1.0,
        )

    # ----------------------------
    # “Speech”
    # ----------------------------
    def _say(self, kind: str, target_id: str) -> str:
        style = self.speech_style

        if kind == "help":
            return f"I can help you, {target_id}." if style == "formal" else f"I got you, {target_id}."
        if kind == "compliment":
            return f"Well done, {target_id}." if style == "formal" else f"Nice one, {target_id}!"
        if kind == "insult":
            return (
                f"That was unacceptable, {target_id}."
                if style == "formal"
                else f"{target_id}, that’s embarrassing."
            )

        # normal “say”
        if style == "bubbly":
            return f"Hey {target_id}!! 😊"
        if style == "dry":
            return f"{target_id}. Sup."
        if style == "formal":
            return f"Hello {target_id}."
        return f"Hi {target_id}."

    # ----------------------------
    # Export to JSON
    # ----------------------------
    def to_state(self) -> Dict[str, Any]:
        state = {
            "id": self.public_id,
            "traits": {k: round(float(v), 2) for k, v in self.traits.items()},
            "mood": {"valence": round(self.valence, 3), "arousal": round(self.arousal, 3)},
            "energy": self.energy,
            "goal": {
                "long": self.long_goal,
                "short": self.active_short_goal,
                "progress": round(self.goal_progress, 3),
            },
            "stm_tail": list(self.stm)[-3:],
            "last_thought": self.last_thought,
        }

        # NEW: Add recent emotion if available
        if self.emotion_memory:
            state["last_emotion"] = self.emotion_memory[-1]['primary_emotion']

        return state
