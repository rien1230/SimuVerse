"""Short- and long-term memory helpers used by each agent.

This file is the memory layer behind how agents retain social experiences over
time, instead of only reacting to the current tick.
"""

from collections import deque
from typing import Dict, List, Any, Optional
from datetime import datetime
import math


class EmotionalMemory:
    """Combined short-term and long-term social memory for one agent."""

    EMOTION_IMPORTANCE_BOOST = {
        # Very high impact emotions (life-changing, traumatic)
        'grief': 0.45,
        'fear': 0.40,
        'anger': 0.35,

        # High impact emotions
        'disgust': 0.30,
        'remorse': 0.30,
        'love': 0.28,
        'joy': 0.25,

        # Medium impact
        'sadness': 0.22,
        'surprise': 0.20,
        'disappointment': 0.20,
        'pride': 0.18,

        # Low impact
        'admiration': 0.15,
        'amusement': 0.15,
        'gratitude': 0.15,
        'excitement': 0.15,

        # Very low impact (everyday emotions)
        'approval': 0.10,
        'annoyance': 0.10,
        'curiosity': 0.10,
        'optimism': 0.10,
        'relief': 0.08,
        'confusion': 0.05,
        'realization': 0.05,
        'desire': 0.05,
        'caring': 0.05,
        'nervousness': 0.05,
        'embarrassment': 0.05,

        # Neutral (baseline)
        'neutral': 0.00
    }

    def __init__(self, agent_id: str, max_stm_size: int = 50):
        """Set up empty memory stores for one agent.

        Parameters
        ----------
        agent_id : str
            The public_id of the agent this memory belongs to.
        max_stm_size : int
            How many events the short-term memory can hold before
            the oldest ones are automatically dropped (deque behaviour).
        """
        self.agent_id = agent_id
        # STM automatically evicts old entries once it's full — no manual pruning needed
        self.stm = deque(maxlen=max_stm_size)
        self.ltm: List[Dict[str, Any]] = []  # only high-importance memories survive here
        self.impressions: Dict[str, Dict[str, Any]] = {}  # per-speaker personality profiles
        self.stats = {
            'total_interactions': 0,
            'emotion_counts': {},
            'last_updated': 0
        }

    def add_memory(self, memory: Dict[str, Any]) -> None:
        """Store a new memory in STM and promote to LTM if it's important enough.

        Everything goes into STM. Only memories with importance >= 0.6
        get promoted to LTM, which is kept sorted so the most impactful
        memories are always at the front.
        """
        self.stm.append(memory)
        self.stats['total_interactions'] += 1

        # Track how often each emotion has been encountered (useful for stats)
        emotion = memory.get('primary_emotion', 'unknown')
        self.stats['emotion_counts'][emotion] = self.stats['emotion_counts'].get(emotion, 0) + 1

        importance = self._calculate_importance(memory)
        memory['importance'] = importance  # write score back into the memory dict

        # Only promote high-importance memories to LTM
        if importance >= 0.6:
            self.ltm.append(memory)
            # Keep LTM sorted by importance (most important first)
            self.ltm.sort(key=lambda x: x.get('importance', 0), reverse=True)
            # Cap LTM at 50 entries — drop the least important when it overflows
            if len(self.ltm) > 50:
                self.ltm = self.ltm[:50]


    def _calculate_importance(self, memory: Dict[str, Any]) -> float:
        """Score a memory on a 0–1 scale based on four factors:
          1. Base rate (0.3) — every memory starts with some importance
          2. Emotion intensity (confidence) — stronger emotions = stronger memory
          3. Emotion type — negative emotions have bigger boosts (negativity bias)
          4. First encounter — meeting someone for the first time is always memorable
          5. Recency — very recent events get a small extra bump

        Returns a float clamped to [0.0, 1.0].
        """
        importance = 0.3  # base importance — every memory matters a little
        confidence = memory.get('confidence', 0.5)
        importance += confidence * 0.3  # higher confidence = more memorable

        # Per-emotion boost: grief/fear/anger are the most memorable (research-backed)
        emotion = memory.get('primary_emotion', '')
        importance += self.EMOTION_IMPORTANCE_BOOST.get(emotion, 0.1)  # default 0.1 if unknown emotion

        # First interaction with this speaker is extra salient
        speaker = memory.get('speaker', '')
        speaker_memories = [m for m in self.stm if m.get('speaker') == speaker]
        if len(speaker_memories) == 1:  # only 1 means this IS the first one
            importance += 0.2

        # Recency boost: events in the last 10 ticks decay linearly toward 0
        current_tick = memory.get('tick', 0)
        if hasattr(self, 'last_tick'):
            tick_diff = current_tick - self.last_tick
            if tick_diff < 10:
                importance += 0.1 * (1 - tick_diff / 10)

        return max(0.0, min(1.0, importance))


    def get_recent_interactions(self, speaker: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recent memories involving a specific speaker, newest first.

        Note: memories are stored under the key "from" (not "speaker") because that's
        what agent.py uses when writing events into the buffer — keeping the key
        consistent fixed a bug where impressions never formed.
        """
        interactions = [m for m in self.stm if m.get('from') == speaker]
        interactions.sort(key=lambda x: x.get('tick', 0), reverse=True)
        return interactions[:limit]


    def get_emotional_trend(self, speaker: str, emotion: str, window: int = 20) -> float:
        """Measure whether a speaker is showing a given emotion more or less lately.

        Works by splitting the interaction window in half and comparing emotion
        rate in the older half vs the newer half. A positive value means the
        speaker has been showing this emotion *more* recently.

        Returns a float in [-1.0, 1.0]. Requires at least 3 interactions to be
        meaningful — fewer than that returns 0.0.
        """
        interactions = self.get_recent_interactions(speaker, window)
        if len(interactions) < 3:
            # Not enough data to say anything useful
            return 0.0

        # Split the window into two halves to compare older vs newer behaviour
        mid = len(interactions) // 2
        first_half = interactions[:mid]   # more recent (sorted newest-first)
        second_half = interactions[mid:]  # older interactions

        first_count = sum(1 for m in first_half if m.get('primary_emotion') == emotion)
        second_count = sum(1 for m in second_half if m.get('primary_emotion') == emotion)

        first_rate = first_count / len(first_half)
        second_rate = second_count / len(second_half)

        # Multiply by 2 so that a shift from 0% to 50% maps to trend = +1.0
        trend = second_rate - first_rate
        return max(-1.0, min(1.0, trend * 2))

    EVENT_SIGNAL: Dict[str, float] = {
        "share_info":  1.0,   # cooperative, positive signal
        "agree":       1.0,   # supportive, positive signal
        "compliment":  0.8,   # warm, positive signal
        "challenge":  -1.0,   # friction, negative signal
        "refuse":     -0.8,   # blocking, negative signal
        "complain":   -0.6,   # frustration, negative signal
    }

    def update_impressions(self, current_tick: int) -> Dict[str, Any]:

        new_impressions = {}
        # Collect every speaker found in STM (uses "from" not "speaker" — see fix note)
        speakers = set(m.get('from') for m in self.stm if m.get('from'))
        for speaker in speakers:
            interactions = self.get_recent_interactions(speaker, 30)
            if len(interactions) < 3:   # need at least 3 interactions to call it a pattern
                continue

            total = len(interactions)
            positive_score = 0.0
            negative_score = 0.0
            emotion_counts: Dict[str, int] = {}

            for m in interactions:
                # Score each memory by its event type (works even without NLP)
                kind = m.get('kind', '')
                sig = self.EVENT_SIGNAL.get(kind, 0.0)
                if sig > 0:
                    positive_score += sig
                elif sig < 0:
                    negative_score += abs(sig)

                # If we have NLP emotion data, layer it on top for a richer picture
                emotion = m.get('primary_emotion', '')
                if emotion and emotion != 'neutral':
                    emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
                    positive_nlu = ['joy', 'gratitude', 'admiration', 'love', 'approval']
                    negative_nlu = ['anger', 'disgust', 'annoyance', 'fear', 'disappointment']
                    if emotion in positive_nlu:
                        positive_score += 1.5   # NLP signal is weighted more heavily
                    elif emotion in negative_nlu:
                        negative_score += 1.5

            # Normalise by interaction count so short-history agents aren't penalised
            pos_rate = positive_score / total
            neg_rate = negative_score / total

            impressions: Dict[str, Any] = {}

            # Flag speakers whose interaction history is more negative than average
            if neg_rate > 0.25:
                impressions['conflict_prone'] = round(neg_rate, 3)

            # Flag consistently supportive/cooperative speakers
            if pos_rate > 0.30:
                impressions['positive'] = round(pos_rate, 3)

            # Anger-specific flag — this one only appears when NLP is active
            anger_count = emotion_counts.get('anger', 0)
            if anger_count / total > 0.25:
                impressions['anger_prone'] = round(anger_count / total, 3)

            # volatile: high on both sides — warm sometimes, hostile other times
            if pos_rate > 0.20 and neg_rate > 0.20:
                impressions['volatile'] = True

            if impressions:
                self.impressions[speaker] = {
                    'formed_at': current_tick,
                    'patterns': impressions,
                    'interaction_count': total,
                }
                new_impressions[speaker] = self.impressions[speaker]

        self.stats['last_updated'] = current_tick
        return new_impressions

    # Gets current impression of speaker
    def get_impression(self, speaker: str) -> Optional[Dict[str, Any]]:
        """Return the stored impression dict for a speaker, or None if we haven't formed one yet."""
        return self.impressions.get(speaker)

    def recall_similar(self, current_text: str, current_emotion: str, limit: int = 5) -> List[Dict[str, Any]]:

        # Split text into words to use as topic keywords
        keywords = set(current_text.lower().split())

        scored_memories = []
        for memory in self.ltm + list(self.stm):
            score = 0

            # Emotion match is a strong signal — same emotional context = more relevant
            if memory.get('primary_emotion') == current_emotion:
                score += 0.5

            # Keyword match: filter out short words (they're too generic to be useful)
            mem_text = memory.get('text', '').lower()
            for keyword in keywords:
                if keyword in mem_text and len(keyword) > 3:
                    score += 0.2

            if score > 0:
                scored_memories.append((score, memory))

        # Sort highest-scoring memories first and return the top `limit`
        scored_memories.sort(reverse=True)
        return [m for score, m in scored_memories[:limit]]

    def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics for logging."""
        return {
            'stm_size': len(self.stm),
            'ltm_size': len(self.ltm),
            'impressions_count': len(self.impressions),
            'total_interactions': self.stats['total_interactions'],
            'emotion_distribution': self.stats['emotion_counts']
        }

    def summarize(self) -> str:
        """Generate a human-readable summary of memory state."""
        lines = []
        lines.append(f" Memory for {self.agent_id}")
        lines.append(f"  Recent: {len(self.stm)} events")
        lines.append(f"  Important: {len(self.ltm)} memories")
        lines.append(f"  Impressions: {len(self.impressions)} agents")

        if self.impressions:
            lines.append("  Impressions:")
            for speaker, imp in list(self.impressions.items())[:3]:
                patterns = ', '.join(imp['patterns'].keys())
                lines.append(f"    - {speaker}: {patterns}")

        return '\n'.join(lines)
