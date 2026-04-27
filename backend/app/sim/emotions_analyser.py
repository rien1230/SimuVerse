"""Turns raw emotion signals into the smaller scores the sim works with."""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple, Optional, Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.core.emotion_model import get_emotion_classifier

logger = logging.getLogger(__name__)


class EmotionAnalyser:
    """
    Hybrid emotion analyser for SimuVerse.

    Modes:
    - rule_based: deterministic, recommended default for simulation runs
    - ml: uses shared transformer classifier for richer emotion detection
    - hybrid: rule_based primary, ml fallback if available

    For reproducible seeded simulations, use mode="rule_based".
    """

    ALL_EMOTIONS = [
        "admiration", "amusement", "anger", "annoyance", "approval",
        "caring", "confusion", "curiosity", "desire", "disappointment",
        "disapproval", "disgust", "embarrassment", "excitement", "fear",
        "gratitude", "grief", "joy", "love", "nervousness",
        "optimism", "pride", "realization", "relief", "remorse",
        "sadness", "surprise", "neutral",
    ]

    LABEL_TO_NAME = {
        "LABEL_0": "admiration",
        "LABEL_1": "amusement",
        "LABEL_2": "anger",
        "LABEL_3": "annoyance",
        "LABEL_4": "approval",
        "LABEL_5": "caring",
        "LABEL_6": "confusion",
        "LABEL_7": "curiosity",
        "LABEL_8": "desire",
        "LABEL_9": "disappointment",
        "LABEL_10": "disapproval",
        "LABEL_11": "disgust",
        "LABEL_12": "embarrassment",
        "LABEL_13": "excitement",
        "LABEL_14": "fear",
        "LABEL_15": "gratitude",
        "LABEL_16": "grief",
        "LABEL_17": "joy",
        "LABEL_18": "love",
        "LABEL_19": "nervousness",
        "LABEL_20": "optimism",
        "LABEL_21": "pride",
        "LABEL_22": "realization",
        "LABEL_23": "relief",
        "LABEL_24": "remorse",
        "LABEL_25": "sadness",
        "LABEL_26": "surprise",
        "LABEL_27": "neutral",
    }

    HIGH_CONFIDENCE_EMOTIONS = {
        "neutral", "admiration", "approval", "annoyance", "gratitude",
        "disapproval", "amusement", "joy", "anger", "sadness",
        "curiosity", "confusion", "nervousness", "fear",
        "disappointment", "remorse", "surprise",
    }

    EMOTION_MAPPING = {
        "grief": "sadness",
        "remorse": "sadness",
        "disappointment": "sadness",
        "fear": "nervousness",
        "embarrassment": "nervousness",
        "love": "joy",
        "excitement": "joy",
        "pride": "admiration",
        "optimism": "approval",
        "caring": "approval",
        "desire": "curiosity",
        "confusion": "curiosity",
        "realization": "surprise",
        "relief": "joy",
    }

    EMOTION_THRESHOLDS = {
        "admiration": 0.20,
        "amusement": 0.20,
        "anger": 0.12,
        "annoyance": 0.12,
        "approval": 0.12,
        "caring": 0.15,
        "confusion": 0.10,
        "curiosity": 0.10,
        "desire": 0.12,
        "disappointment": 0.08,
        "disapproval": 0.10,
        "disgust": 0.15,
        "embarrassment": 0.15,
        "excitement": 0.20,
        "fear": 0.15,
        "gratitude": 0.18,
        "grief": 0.25,
        "joy": 0.15,
        "love": 0.20,
        "nervousness": 0.15,
        "optimism": 0.15,
        "pride": 0.20,
        "realization": 0.08,
        "relief": 0.15,
        "remorse": 0.12,
        "sadness": 0.15,
        "surprise": 0.10,
        "neutral": 0.35,
    }

    VALENCE_AROUSAL_MAP = {
        "admiration": (0.7, 0.4),
        "amusement": (0.8, 0.5),
        "anger": (-0.7, 0.8),
        "annoyance": (-0.5, 0.5),
        "approval": (0.6, 0.3),
        "caring": (0.6, 0.3),
        "confusion": (-0.2, 0.5),
        "curiosity": (0.3, 0.6),
        "desire": (0.5, 0.6),
        "disappointment": (-0.6, 0.3),
        "disapproval": (-0.6, 0.4),
        "disgust": (-0.7, 0.5),
        "embarrassment": (-0.5, 0.4),
        "excitement": (0.8, 0.9),
        "fear": (-0.7, 0.8),
        "gratitude": (0.8, 0.3),
        "grief": (-0.8, 0.2),
        "joy": (0.9, 0.7),
        "love": (0.9, 0.5),
        "nervousness": (-0.4, 0.7),
        "optimism": (0.7, 0.5),
        "pride": (0.7, 0.5),
        "realization": (0.1, 0.4),
        "relief": (0.6, 0.2),
        "remorse": (-0.6, 0.3),
        "sadness": (-0.7, 0.2),
        "surprise": (0.1, 0.7),
        "neutral": (0.0, 0.0),
    }

    def __init__(
        self,
        use_gpu: bool = False,
        use_reliable_only: bool = False,
        mode: str = "rule_based",
    ):
        self.use_reliable_only = use_reliable_only
        self.mode = mode
        self.rule_analyzer = SentimentIntensityAnalyzer()

        self.classifier: Optional[Any] = None
        if mode in {"ml", "hybrid"}:
            self.classifier = get_emotion_classifier(use_gpu=use_gpu)

        self.model_available = self.classifier is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, text: str) -> Dict[str, float]:
        if not text or not text.strip():
            return {"neutral": 1.0}

        if self.mode == "rule_based":
            emotions = self._rule_based_analysis(text)
        elif self.mode == "ml":
            emotions = self._ml_analysis(text)
        elif self.mode == "hybrid":
            emotions = self._rule_based_analysis(text)
            if emotions == {"neutral": 1.0} and self.model_available:
                emotions = self._ml_analysis(text)
        else:
            logger.warning("Unknown emotion analyser mode '%s'; using rule_based.", self.mode)
            emotions = self._rule_based_analysis(text)

        if self.use_reliable_only:
            emotions = self._filter_reliable_only(emotions)

        if not emotions:
            return {"neutral": 1.0}

        return emotions

    def get_primary_emotion(self, text: str) -> Tuple[str, float]:
        emotions = self.analyse(text)
        if emotions:
            return max(emotions.items(), key=lambda x: x[1])
        return ("neutral", 1.0)

    def get_top_emotions(self, text: str, n: int = 3) -> List[Tuple[str, float]]:
        emotions = self.analyse(text)
        return sorted(emotions.items(), key=lambda x: x[1], reverse=True)[:n]

    def get_valence_arousal(self, text: str) -> Dict[str, float]:
        emotions = self.analyse(text)

        total_weight = 0.0
        valence = 0.0
        arousal = 0.0

        for emotion, score in emotions.items():
            if emotion in self.VALENCE_AROUSAL_MAP:
                v, a = self.VALENCE_AROUSAL_MAP[emotion]
                valence += v * score
                arousal += a * score
                total_weight += score

        if total_weight > 0:
            valence /= total_weight
            arousal /= total_weight
        else:
            valence = 0.0
            arousal = 0.0

        primary = max(emotions.items(), key=lambda x: x[1])[0] if emotions else "neutral"

        return {
            "valence": max(-1.0, min(1.0, valence)),
            "arousal": max(0.0, min(1.0, arousal)),
            "primary_emotion": primary,
        }

    def explain(self, text: str) -> Dict[str, Any]:
        emotions = self.analyse(text)
        primary = self.get_primary_emotion(text)
        va = self.get_valence_arousal(text)

        raw_results = {}
        if self.mode in {"ml", "hybrid"} and self.model_available:
            try:
                ml_results = self.classifier(text)[0]
                raw_results = {
                    self.LABEL_TO_NAME.get(r["label"], r["label"]): r["score"]
                    for r in ml_results
                }
            except Exception as e:
                logger.warning("Explain failed to read ML outputs: %s", e)

        return {
            "text": text,
            "mode": self.mode,
            "raw_emotions": raw_results,
            "filtered_emotions": emotions,
            "primary_emotion": primary,
            "valence_arousal": va,
        }

    # ------------------------------------------------------------------
    # Rule-based deterministic mode
    # ------------------------------------------------------------------

    def _rule_based_analysis(self, text: str) -> Dict[str, float]:
        scores = self.rule_analyzer.polarity_scores(text)
        text_lower = text.lower()

        emotions: Dict[str, float] = {}

        compound = scores["compound"]
        pos = scores["pos"]
        neg = scores["neg"]

        # Explicit lexical cues first
        if any(w in text_lower for w in ["thanks", "thank you", "appreciate"]):
            emotions["gratitude"] = max(emotions.get("gratitude", 0.0), 0.78)

        if any(w in text_lower for w in ["sorry", "apologise", "apologize", "regret"]):
            emotions["remorse"] = max(emotions.get("remorse", 0.0), 0.72)

        if any(w in text_lower for w in ["confused", "not sure", "unclear", "don't understand"]):
            emotions["confusion"] = max(emotions.get("confusion", 0.0), 0.68)

        if any(w in text_lower for w in ["worried", "nervous", "anxious", "tense"]):
            emotions["nervousness"] = max(emotions.get("nervousness", 0.0), 0.72)

        if any(w in text_lower for w in ["angry", "furious", "ridiculous", "unacceptable"]):
            emotions["anger"] = max(emotions.get("anger", 0.0), 0.82)

        if any(w in text_lower for w in ["annoying", "frustrating", "irritating"]):
            emotions["annoyance"] = max(emotions.get("annoyance", 0.0), 0.70)

        if any(w in text_lower for w in ["great", "good", "nice", "well done", "excellent"]):
            emotions["approval"] = max(emotions.get("approval", 0.0), 0.66)

        if any(w in text_lower for w in ["love", "amazing", "fantastic", "happy"]):
            emotions["joy"] = max(emotions.get("joy", 0.0), 0.78)

        if any(w in text_lower for w in ["sad", "upset", "unfortunate", "disappointed"]):
            emotions["sadness"] = max(emotions.get("sadness", 0.0), 0.72)

        if "?" in text:
            emotions["curiosity"] = max(emotions.get("curiosity", 0.0), 0.58)

        if "!" in text:
            emotions["surprise"] = max(emotions.get("surprise", 0.0), 0.52)

        # Sentiment-driven additions
        if compound >= 0.65:
            emotions["joy"] = max(emotions.get("joy", 0.0), 0.75)
        elif compound >= 0.30:
            emotions["approval"] = max(emotions.get("approval", 0.0), 0.65)
        elif compound <= -0.65:
            emotions["anger"] = max(emotions.get("anger", 0.0), 0.76)
        elif compound <= -0.30:
            emotions["disapproval"] = max(emotions.get("disapproval", 0.0), 0.64)

        # Mild fallback from polarity balance
        if not emotions:
            if pos > 0.20 and neg < 0.10:
                emotions["approval"] = 0.60
            elif neg > 0.20 and pos < 0.10:
                emotions["disapproval"] = 0.60
            else:
                emotions["neutral"] = 1.0

        return self._apply_thresholds(emotions)

    # ------------------------------------------------------------------
    # Transformer mode
    # ------------------------------------------------------------------

    def _ml_analysis(self, text: str) -> Dict[str, float]:
        if not self.model_available or not self.classifier:
            return self._fallback_analysis(text)

        try:
            results = self.classifier(text)[0]
            emotions: Dict[str, float] = {}

            for r in results:
                label = r["label"]
                score = r["score"]
                emotion = self.LABEL_TO_NAME.get(label, label)
                threshold = self.EMOTION_THRESHOLDS.get(emotion, 0.3)

                if score >= threshold:
                    emotions[emotion] = score

            if not emotions:
                emotions["neutral"] = 1.0

            return emotions

        except Exception as e:
            logger.warning("Emotion analysis failed: %s", e)
            return self._fallback_analysis(text)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _fallback_analysis(self, text: str) -> Dict[str, float]:
        return self._rule_based_analysis(text)

    def _filter_reliable_only(self, emotions: Dict[str, float]) -> Dict[str, float]:
        filtered: Dict[str, float] = {}

        for emotion, score in emotions.items():
            if emotion in self.HIGH_CONFIDENCE_EMOTIONS:
                filtered[emotion] = score
            elif emotion in self.EMOTION_MAPPING:
                mapped = self.EMOTION_MAPPING[emotion]
                filtered[mapped] = max(filtered.get(mapped, 0.0), score)

        return filtered

    def _apply_thresholds(self, emotions: Dict[str, float]) -> Dict[str, float]:
        filtered: Dict[str, float] = {}

        for emotion, score in emotions.items():
            threshold = self.EMOTION_THRESHOLDS.get(emotion, 0.3)
            if score >= threshold:
                filtered[emotion] = round(float(score), 4)

        if not filtered:
            return {"neutral": 1.0}

        return filtered
