"""Short- and long-term memory helpers used by each agent."""

from collections import deque
from typing import Dict, List, Any, Optional
from datetime import datetime
import math


class EmotionalMemory:
    # Each agent has one EmotionalMemory instance. It acts as a combined short-term and
    # long-term memory store, tracking who the agent has interacted with, how those
    # interactions felt, and — crucially — what kind of person each partner seems to be.
    # The memory system has two tiers:
    #   - STM (short-term memory): a rolling deque of recent interactions, max 50 entries
    #   - LTM (long-term memory): only the highest-importance memories survive here,
    #     sorted by importance score, capped at 50 entries
    # Importance is calculated separately for each memory (see _calculate_importance below).
    # The emotional importance boosts below are grounded in psychological research:
    #   - Negativity bias (Baumeister et al., 2001): negative events are processed more
    #     thoroughly and remembered more strongly than equivalent positive ones
    #   - Emotional arousal enhances memory consolidation (McGaugh, 2003): the amygdala
    #     modulates hippocampal storage in proportion to emotional intensity
    #   - Negative emotions are recalled with greater vividness and accuracy (Kensinger, 2007)
    # This is why grief, fear, and anger have the highest boosts — they're the emotions
    # most likely to produce durable behavioural change in a social agent.
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
        self.agent_id = agent_id
        self.stm = deque(maxlen=max_stm_size)
        self.ltm: List[Dict[str, Any]] = []
        self.impressions: Dict[str, Dict[str, Any]] = {}
        self.stats = {
            'total_interactions': 0,
            'emotion_counts': {},
            'last_updated': 0
        }

    def add_memory(self, memory: Dict[str, Any]) -> None:
        self.stm.append(memory)
        self.stats['total_interactions'] += 1
        emotion = memory.get('primary_emotion', 'unknown')
        self.stats['emotion_counts'][emotion] = self.stats['emotion_counts'].get(emotion, 0) + 1
        importance = self._calculate_importance(memory)
        memory['importance'] = importance
        if importance >= 0.6:
            self.ltm.append(memory)
            # Keep LTM sorted by importance (most important first)
            self.ltm.sort(key=lambda x: x.get('importance', 0), reverse=True)
            # Keep only top 50 most important memories
            if len(self.ltm) > 50:
                self.ltm = self.ltm[:50]

    # To calculate the importance of a memory. I'll be considering 4 factors that increases importance :
    #         - High emotional intensity (confidence)
    #         - Emotion type (using per-emotion importance boosts)
    #         - First interaction with someone
    #         - Very recent events (recency bias)
    # How I came up with emotion importance boost is that I found that negative emotions has high intensity memory
    # effect than everyday emotions. Based on psychological research on emotional memory:
    #         - Negativity bias (Baumeister et al., 2001)
    #         - Emotional arousal enhances memory (McGaugh, 2003)
    #         - Negative emotions remembered more vividly (Kensinger, 2007)
    def _calculate_importance(self, memory: Dict[str, Any]) -> float:
        importance = 0.3  # Base importance
        confidence = memory.get('confidence', 0.5)
        importance += confidence * 0.3
        # PER-EMOTION IMPORTANCE BOOST - different emotions have different memorability
        emotion = memory.get('primary_emotion', '')
        importance += self.EMOTION_IMPORTANCE_BOOST.get(emotion, 0.1)  # Default 0.1 if unknown

        # First interaction with this speaker?
        speaker = memory.get('speaker', '')
        speaker_memories = [m for m in self.stm if m.get('speaker') == speaker]
        if len(speaker_memories) == 1:  # First time
            importance += 0.2

        # events in last 10 ticks are more important.
        current_tick = memory.get('tick', 0)
        if hasattr(self, 'last_tick'):
            tick_diff = current_tick - self.last_tick
            if tick_diff < 10:
                importance += 0.1 * (1 - tick_diff / 10)

        return max(0.0, min(1.0, importance))

    # Returns recent interactions with a specific speaker, newest first.
    # I store memories under the key "from" (not "speaker") because that's the field
    # name used when agent.py writes events into the memory buffer via apply_events().
    # Keeping these consistent was a bug fix — the original code searched for "speaker"
    # and therefore always returned an empty list, which is why impressions never formed.
    def get_recent_interactions(self, speaker: str, limit: int = 10) -> List[Dict[str, Any]]:
        interactions = [m for m in self.stm if m.get('from') == speaker]
        interactions.sort(key=lambda x: x.get('tick', 0), reverse=True)
        return interactions[:limit]

    # Is this person becoming more or less [emotion] over time?
    # I calculate emotional trend by splitting the interaction window in half and comparing
    # the emotion rate in the older half vs the newer half. A positive trend means the
    # target is showing that emotion *more* recently; negative means they've calmed down.
    # The minimum of 3 interactions is a practical floor — two data points isn't enough
    # to call a trend. The result is clamped to [-1, 1] and scaled by 2 so that a shift
    # from 0% → 50% in one half maps to a trend of +1.0 (maximum detectable change).
    def get_emotional_trend(self, speaker: str, emotion: str, window: int = 20) -> float:
        interactions = self.get_recent_interactions(speaker, window)
        if len(interactions) < 3:
            return 0.0
        mid = len(interactions) // 2
        first_half = interactions[:mid]
        second_half = interactions[mid:]
        first_count = sum(1 for m in first_half if m.get('primary_emotion') == emotion)
        second_count = sum(1 for m in second_half if m.get('primary_emotion') == emotion)
        first_rate = first_count / len(first_half)
        second_rate = second_count / len(second_half)
        trend = second_rate - first_rate
        return max(-1.0, min(1.0, trend * 2))

    # What kind of person is this agent based on their emotional patterns?
    # Every 10 ticks, this function reviews the last 30 conversations with each person and asks: 'Is this person angry?
    # Positive? Conflict-causing? Unpredictable?' It then stores these impressions so the agent knows who to trust,
    # who to avoid, and how to act around different people.

    # Event-type signals used when NLP emotion data is absent (use_nlp=False).
    # Each event kind contributes a positive or negative signal toward impression formation.
    EVENT_SIGNAL: Dict[str, float] = {
        "share_info":  1.0,   # cooperative, positive signal
        "agree":       1.0,   # supportive, positive signal
        "compliment":  0.8,   # warm, positive signal
        "challenge":  -1.0,   # friction, negative signal
        "refuse":     -0.8,   # blocking, negative signal
        "complain":   -0.6,   # frustration, negative signal
    }

    def update_impressions(self, current_tick: int) -> Dict[str, Any]:
        """Build per-speaker impressions from STM using both event-type signals
        (works without NLP) and emotion-analysis records (enriches when NLP is on).

        Key fix: memories are stored under key ``"from"``, not ``"speaker"``.
        The threshold has been lowered to 3 to support short café/office runs.
        """
        new_impressions = {}
        # FIX: memories use "from" not "speaker"
        speakers = set(m.get('from') for m in self.stm if m.get('from'))
        for speaker in speakers:
            interactions = self.get_recent_interactions(speaker, 30)
            if len(interactions) < 3:   # lowered from 5 — short runs need this
                continue

            total = len(interactions)
            positive_score = 0.0
            negative_score = 0.0
            emotion_counts: Dict[str, int] = {}

            for m in interactions:
                # ── Event-type signals (NLP-independent) ──────────────────
                kind = m.get('kind', '')
                sig = self.EVENT_SIGNAL.get(kind, 0.0)
                if sig > 0:
                    positive_score += sig
                elif sig < 0:
                    negative_score += abs(sig)

                # ── Emotion signals (enriches when NLP is active) ──────────
                emotion = m.get('primary_emotion', '')
                if emotion and emotion != 'neutral':
                    emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
                    positive_nlu = ['joy', 'gratitude', 'admiration', 'love', 'approval']
                    negative_nlu = ['anger', 'disgust', 'annoyance', 'fear', 'disappointment']
                    if emotion in positive_nlu:
                        positive_score += 1.5
                    elif emotion in negative_nlu:
                        negative_score += 1.5

            pos_rate = positive_score / total
            neg_rate = negative_score / total

            impressions: Dict[str, Any] = {}

            # Conflict / negativity pattern
            if neg_rate > 0.25:
                impressions['conflict_prone'] = round(neg_rate, 3)

            # Positivity / cooperative pattern
            if pos_rate > 0.30:
                impressions['positive'] = round(pos_rate, 3)

            # Anger-specific (NLP enriched)
            anger_count = emotion_counts.get('anger', 0)
            if anger_count / total > 0.25:
                impressions['anger_prone'] = round(anger_count / total, 3)

            # Emotional volatility (mix of strong positive and negative)
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
        return self.impressions.get(speaker)

    # When an agent encounters new dialogue, this function searches their memory for similar
    # past conversations — matching on the same emotion label or overlapping topic keywords.
    # The idea is loosely based on cue-dependent retrieval (Tulving & Thomson, 1973): the
    # emotion present in a new situation acts as a retrieval cue that surfaces memories
    # formed in similar emotional contexts. In practice this means an agent who previously
    # had a tense exchange about the "budget" item will surface that memory when a new
    # budget conversation starts — which can subtly influence how cautiously they respond.
    def recall_similar(self, current_text: str, current_emotion: str, limit: int = 5) -> List[Dict[str, Any]]:

        # Simple keyword extraction from current text
        keywords = set(current_text.lower().split())

        scored_memories = []
        for memory in self.ltm + list(self.stm):
            score = 0

            # Match by emotion
            if memory.get('primary_emotion') == current_emotion:
                score += 0.5

            # Match by keywords in text
            mem_text = memory.get('text', '').lower()
            for keyword in keywords:
                if keyword in mem_text and len(keyword) > 3:
                    score += 0.2

            if score > 0:
                scored_memories.append((score, memory))

        # Sort by score and return top
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
