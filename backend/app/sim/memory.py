"""Short- and long-term memory helpers used by each agent."""

from collections import deque
from typing import Dict, List, Any, Optional
from datetime import datetime
import math


class EmotionalMemory:
    # Stores emotional experiences and detects patterns in interactions. Each agent has one EmotionalMemory instance.
    # Negativity Bias (Baumeister et al., 2001)
    # Negative emotions are more memorable (negativity bias), extreme emotions are highly memorable
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

    # With specific speaker returning list of memory dict with newest first.
    def get_recent_interactions(self, speaker: str, limit: int = 10) -> List[Dict[str, Any]]:
        interactions = [m for m in self.stm if m.get('speaker') == speaker]
        interactions.sort(key=lambda x: x.get('tick', 0), reverse=True)
        return interactions[:limit]

    # Is this person becoming more or less [emotion] over time? If there is less than 3 interactions then we can't
    # calculate as it's not enough. We calculate by splitting the emotion interactions list in half. Where the first
    # half is the older interactions and the second half is the newer interaction. We calculate how many of a specific
    # emotion shows up in the two split list. Then compare the values.
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

    def update_impressions(self, current_tick: int) -> Dict[str, Any]:
        new_impressions = {}
        speakers = set(m.get('speaker') for m in self.stm if m.get('speaker'))
        for speaker in speakers:
            interactions = self.get_recent_interactions(speaker, 30)
            if len(interactions) < 5:
                continue

            emotion_counts = {}
            for m in interactions:
                emotion = m.get('primary_emotion', 'unknown')
                emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

            total = len(interactions)
            impressions = {}

            # Anger pattern
            anger_rate = emotion_counts.get('anger', 0) / total
            if anger_rate > 0.3:
                impressions['anger_prone'] = anger_rate

            # Positivity pattern
            positive_emotions = ['joy', 'gratitude', 'admiration', 'love']
            positive_rate = sum(emotion_counts.get(e, 0) for e in positive_emotions) / total
            if positive_rate > 0.4:
                impressions['positive'] = positive_rate

            # Conflict pattern
            negative_emotions = ['anger', 'disgust', 'annoyance', 'fear']
            negative_rate = sum(emotion_counts.get(e, 0) for e in negative_emotions) / total
            if negative_rate > 0.3:
                impressions['conflict_prone'] = negative_rate

            # Emotional volatility (mix of positive and negative)
            if positive_rate > 0.2 and negative_rate > 0.2:
                impressions['volatile'] = True

            if impressions:
                self.impressions[speaker] = {
                    'formed_at': current_tick,
                    'patterns': impressions,
                    'interaction_count': total
                }
                new_impressions[speaker] = self.impressions[speaker]

        self.stats['last_updated'] = current_tick
        return new_impressions

    # Gets current impression of speaker
    def get_impression(self, speaker: str) -> Optional[Dict[str, Any]]:
        return self.impressions.get(speaker)

    # When someone says something, this function searches through the agent's memory for similar past conversations
    # - ones with the same emotion or that mentioned the same topics. It then brings back the most relevant memories so
    # the agent can learn from past experiences.
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
