"""Turns raw emotion signals into the smaller scores the sim works with.

Public API for user-facing emotion input:
  classify_user_emotion(text, tick=0) -> dict
      Classifies a user-provided text string using GoEmotions (or keyword
      fallback) and returns a fully-structured result ready for injection
      into the simulation via SimModel.inject_user_emotion().

This module has two layers. EmotionAnalyser handles raw text classification,
while classify_user_emotion is the stable public entry point used by the
simulation and API.

Emotion-analysis bridge between free text and simulation-ready emotion signals.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple, Optional, Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.core.emotion_model import get_emotion_classifier

logger = logging.getLogger(__name__)


# ── Keyword-based fallback ────────────────────────────────────────────────────
# I added a keyword fallback table because the GoEmotions transformer is a ~250 MB
# download and won't always be available (offline environments, CI pipelines, etc.).
# When the model can't be loaded, simple string matching is used as a last resort.
# The confidence values are deliberately conservative (0.55–0.65) to reflect that
# keyword matching is far less nuanced than transformer-based classification —
# "I'm fine" and "I'm doing fine despite everything" both hit "calm", but only the
# transformer knows they carry different emotional weight.
# Used when the GoEmotions model is unavailable AND the rule-based analyser
# returns only "neutral".  Each entry maps a keyword list → (emotion, confidence).

_KEYWORD_FALLBACK: List[tuple] = [
    (["anxious", "anxiety", "nervous", "scared", "frightened", "terrified"], "nervousness", 0.60),
    (["angry", "furious", "rage", "outraged", "livid"],                       "anger",       0.65),
    (["annoyed", "annoying", "frustrated", "irritated", "irritating"],        "annoyance",   0.60),
    (["sad", "upset", "unhappy", "miserable", "down"],                        "sadness",     0.60),
    (["disappointed", "let down", "letdown"],                                 "disappointment", 0.60),
    (["happy", "joyful", "delighted", "thrilled"],                            "joy",         0.65),
    (["excited", "exhilarated", "pumped"],                                    "excitement",  0.60),
    (["grateful", "thankful", "appreciate"],                                   "gratitude",   0.65),
    (["calm", "relaxed", "fine", "okay", "ok", "alright"],                    "relief",      0.55),
    (["hopeful", "optimistic", "positive"],                                    "optimism",    0.58),
    (["proud", "accomplished", "achieved"],                                    "pride",       0.58),
    (["sorry", "regret", "regretful"],                                         "remorse",     0.60),
    (["confused", "unsure", "uncertain"],                                      "confusion",   0.55),
    (["surprised", "shocked", "stunned"],                                      "surprise",    0.58),
]


def _keyword_fallback(text: str) -> Optional[tuple]:
    """Return (emotion, confidence) from keyword scan, or None."""
    lower = text.lower()
    for keywords, emotion, confidence in _KEYWORD_FALLBACK:
        if any(kw in lower for kw in keywords):
            return emotion, confidence
    return None


# ── Interpretation builder ────────────────────────────────────────────────────
# Group the 28 GoEmotions labels into four functional categories
# rather than giving every emotion its own unique simulation response. This keeps
# the effects testable and avoids over-engineering — the distinction that matters
# for group dynamics isn't whether the user feels "annoyance" vs "disapproval",
# but whether the emotional signal is activating-negative, depleting-negative,
# positive, or neutral. The four categories map directly to what the stress and
# trust parameters in the simulation actually respond to:
#   - neg_high  (anger/fear/nervousness): activating, increases group stress, erodes trust
#   - neg_low   (sadness/disappointment): depleting, mild stress drag, no major trust hit
#   - positive  (joy/gratitude/approval): reduces stress, small trust boost
#   - neutral   : no change applied

def _build_emotion_interpretation(emotion: str, valence: float, arousal: float, intensity: float) -> str:
    """Generate a plain-English explanation of an emotion and its sim effect."""
    valence_label = "positive" if valence > 0.2 else "negative" if valence < -0.2 else "neutral"
    arousal_label = "high-arousal" if arousal > 0.5 else "low-arousal"

    # Category-aware effect descriptions
    negative_high = {"anger", "annoyance", "fear", "nervousness", "disgust", "disapproval"}
    negative_low  = {"sadness", "disappointment", "remorse", "grief", "embarrassment"}
    positive_any  = {"joy", "gratitude", "approval", "admiration", "optimism", "relief",
                     "amusement", "excitement", "love", "pride"}

    if emotion in negative_high:
        effect = (
            "increases group stress and makes agents more cautious or challenging, "
            "with a slight reduction in trust if the signal is strong."
        )
    elif emotion in negative_low:
        effect = (
            "mildly reduces agent confidence and group energy, "
            "slowing cooperation slightly without a major trust impact."
        )
    elif emotion in positive_any:
        effect = (
            "reduces group stress slightly, increases cooperation likelihood, "
            "and provides a small trust boost across the team."
        )
    elif emotion == "neutral":
        effect = "has minimal effect on the simulation."
    else:
        effect = f"has a {valence_label} / {arousal_label} effect on the simulation."

    return (
        f"{emotion.capitalize()} is mapped to {valence_label} valence ({valence:+.2f}) "
        f"and {arousal_label} arousal ({arousal:.2f}), so it {effect}"
    )


# ── Public entry point ────────────────────────────────────────────────────────
# I designed classify_user_emotion() as a standalone function (rather than just
# a method on EmotionAnalyser) because the API endpoint and the simulation model
# both need a single, clean entry point that always returns the same schema —
# regardless of whether the ML model loaded or not.
# The function handles three degradation levels in order of preference:
#   1. GoEmotions transformer (best) — 28-label fine-grained classification
#   2. VADER + lexical rule-based — fast and deterministic, good for testing
#   3. Keyword fallback — last resort when ML confidence < 0.25
# The low-confidence guard (< 0.25) is important because the transformer
# sometimes spreads probability mass thinly across many labels, producing a
# "winner" that isn't actually a confident prediction. Keyword matching is
# a better signal in those edge cases than accepting a weak ML label.

def classify_user_emotion(text: str, tick: int = 0) -> Dict[str, Any]:
    """Classify user-provided emotional text into a structured result.

    Uses the GoEmotions transformer when available; falls back to the
    rule-based VADER + keyword classifier if the model cannot be loaded.
    The returned dict matches the schema required by SimModel.inject_user_emotion().

    Parameters
    ----------
    text : str
        Free-text emotion input from the user.
    tick : int
        Simulation tick at which this emotion will be / was applied.

    Returns
    -------
    dict with keys:
        text, top_emotion, confidence, top_labels, fallback_used,
        fallback_reason, tick_applied, valence, arousal, intensity,
        interpretation
    """
    if not text or not text.strip():
        return {
            "text": text or "",
            "top_emotion": "neutral",
            "confidence": 0.0,
            "top_labels": [{"label": "neutral", "score": 0.0}],
            "fallback_used": True,
            "fallback_reason": "Empty input — defaulting to neutral.",
            "tick_applied": tick,
            "valence": 0.0,
            "arousal": 0.0,
            "intensity": 0.0,
            "interpretation": "No text provided; no emotional influence applied.",
        }

    classifier = get_emotion_classifier()
    model_available = classifier is not None

    if model_available:
        analyser = EmotionAnalyser(mode="ml")
        fallback_used = False
        fallback_reason = None
    else:
        analyser = EmotionAnalyser(mode="rule_based")
        fallback_used = True
        fallback_reason = "GoEmotions model unavailable; keyword fallback used."

    emotions = analyser.analyse(text)
    top_sorted = sorted(emotions.items(), key=lambda x: x[1], reverse=True)

    if not top_sorted:
        top_sorted = [("neutral", 1.0)]

    top_emotion, confidence = top_sorted[0]
    top_3 = top_sorted[:3]

    # Low-confidence guard: if best score < 0.25 and emotion is not neutral,
    # check keyword fallback before accepting the weak prediction.
    if confidence < 0.25 and top_emotion != "neutral":
        kw = _keyword_fallback(text)
        if kw:
            kw_emotion, kw_conf = kw
            top_emotion = kw_emotion
            confidence  = kw_conf
            top_3 = [(kw_emotion, kw_conf)] + [t for t in top_3 if t[0] != kw_emotion][:2]
            if not fallback_used:
                fallback_used = True
                fallback_reason = (
                    f"GoEmotions confidence was low ({confidence:.2f}); "
                    "keyword matching used to confirm top emotion."
                )
        else:
            # Accept neutral when nothing is confident
            top_emotion = "neutral"
            confidence  = 1.0
            top_3 = [("neutral", 1.0)]

    # Valence / arousal from the canonical map
    v, a = EmotionAnalyser.VALENCE_AROUSAL_MAP.get(top_emotion, (0.0, 0.0))

    return {
        "text": text,
        "top_emotion": top_emotion,
        "confidence": round(float(confidence), 4),
        "top_labels": [{"label": e, "score": round(float(s), 4)} for e, s in top_3],
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "tick_applied": tick,
        "valence": round(float(v), 3),
        "arousal": round(float(a), 3),
        "intensity": round(float(confidence), 3),   # intensity = classifier confidence
        "interpretation": _build_emotion_interpretation(top_emotion, v, a, float(confidence)),
    }


class EmotionAnalyser:
    """Classifier wrapper used by agents for ongoing emotion interpretation."""
    """Hybrid emotion analyser for SimuVerse.

    Modes:
    - rule_based: deterministic, recommended default for simulation runs
    - ml: uses shared transformer classifier for richer emotion detection
    - hybrid: rule_based primary, ml fallback if available

    For reproducible seeded simulations, use mode="rule_based".

    The class is intentionally kept separate from classify_user_emotion() so
    that internal simulation calls (agent STM tagging) and user-facing calls
    (emotion injection API) can use different modes without interfering.
    """

    # All 28 emotion labels from the GoEmotions dataset, in label order
    ALL_EMOTIONS = [
        "admiration", "amusement", "anger", "annoyance", "approval",
        "caring", "confusion", "curiosity", "desire", "disappointment",
        "disapproval", "disgust", "embarrassment", "excitement", "fear",
        "gratitude", "grief", "joy", "love", "nervousness",
        "optimism", "pride", "realization", "relief", "remorse",
        "sadness", "surprise", "neutral",
    ]

    # Maps the transformer's raw output labels (LABEL_0, LABEL_1, …) to human
    # readable emotion names so we don't have to decode them everywhere else
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

    # The emotions the transformer tends to predict reliably — used by the
    # use_reliable_only filter to drop noisy low-confidence labels
    HIGH_CONFIDENCE_EMOTIONS = {
        "neutral", "admiration", "approval", "annoyance", "gratitude",
        "disapproval", "amusement", "joy", "anger", "sadness",
        "curiosity", "confusion", "nervousness", "fear",
        "disappointment", "remorse", "surprise",
    }

    # Collapse rare/fine-grained emotions into more common ones so the simulation
    # only has to handle a smaller set of distinct emotional states
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

    # Per-emotion minimum score required to include that emotion in the output.

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

    # I mapped each of the 28 GoEmotions labels to a coordinate in Russell's (1980)
    # circumplex model of affect, which defines emotions along two independent axes:
    #   - Valence: how pleasant (+1.0) or unpleasant (-1.0) the emotion feels
    #   - Arousal: how activating (1.0 = high energy) or deactivating (0.0 = calm)

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
        """Set up the analyser.

        Parameters
        ----------
        use_gpu : bool
            Whether to run the ML classifier on GPU. Ignored in rule_based mode.
        use_reliable_only : bool
            If True, run _filter_reliable_only() on results to strip noisy labels.
        mode : str
            "rule_based", "ml", or "hybrid". Defaults to rule_based for reproducibility.
        """
        self.use_reliable_only = use_reliable_only
        self.mode = mode
        # VADER is always initialised because it's used by both rule_based and
        # as a fallback when the ML model fails
        self.rule_analyzer = SentimentIntensityAnalyzer()

        self.classifier: Optional[Any] = None
        if mode in {"ml", "hybrid"}:
            # Only load the heavy transformer model when actually needed
            self.classifier = get_emotion_classifier(use_gpu=use_gpu)

        # Flag so other methods can check whether ML is usable without try/except
        self.model_available = self.classifier is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, text: str) -> Dict[str, float]:
        """Run the appropriate analysis pipeline and return {emotion: score} dict.

        In hybrid mode, rule_based runs first; if the only result is neutral
        (i.e. the rules didn't pick up anything), the ML model is tried next.
        Always returns at least {"neutral": 1.0} — never an empty dict.
        """
        if not text or not text.strip():
            return {"neutral": 1.0}

        if self.mode == "rule_based":
            emotions = self._rule_based_analysis(text)
        elif self.mode == "ml":
            emotions = self._ml_analysis(text)
        elif self.mode == "hybrid":
            emotions = self._rule_based_analysis(text)
            # Only escalate to ML if rule-based found nothing useful
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
        """Return just the top (emotion, score) pair from analyse()."""
        emotions = self.analyse(text)
        if emotions:
            return max(emotions.items(), key=lambda x: x[1])
        return ("neutral", 1.0)

    def get_top_emotions(self, text: str, n: int = 3) -> List[Tuple[str, float]]:
        """Return the top-n (emotion, score) pairs sorted by score descending."""
        emotions = self.analyse(text)
        return sorted(emotions.items(), key=lambda x: x[1], reverse=True)[:n]

    def get_valence_arousal(self, text: str) -> Dict[str, float]:
        """Convert text to a weighted-average valence/arousal coordinate.

        Weights each emotion's (valence, arousal) by its score so that a text
        expressing 80% joy and 20% nervousness doesn't produce the same result
        as pure joy. The output is clamped to the valid ranges [-1, 1] and [0, 1].
        """
        emotions = self.analyse(text)

        total_weight = 0.0
        valence = 0.0
        arousal = 0.0

        for emotion, score in emotions.items():
            if emotion in self.VALENCE_AROUSAL_MAP:
                v, a = self.VALENCE_AROUSAL_MAP[emotion]
                # Accumulate weighted sum — normalised below
                valence += v * score
                arousal += a * score
                total_weight += score

        if total_weight > 0:
            # Normalise so scores that don't sum to 1.0 still give the right average
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
        """Return a full diagnostic breakdown — useful for debugging classification.

        In ML/hybrid mode, also includes the raw (unfiltered) transformer scores
        so you can see what the model actually predicted before thresholds were applied.
        """
        emotions = self.analyse(text)
        primary = self.get_primary_emotion(text)
        va = self.get_valence_arousal(text)

        raw_results = {}
        if self.mode in {"ml", "hybrid"} and self.model_available:
            try:
                ml_results = self.classifier(text)[0]
                # Remap LABEL_N keys to human-readable names for the output
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
        """Classify text using VADER sentiment plus explicit keyword rules.

        The keyword rules run first because they're more precise — if someone
        writes "I'm so frustrated", we know it's annoyance without needing VADER.
        VADER's compound score fills in the gaps for text that doesn't hit any
        specific keyword but is clearly positive or negative overall.
        """
        scores = self.rule_analyzer.polarity_scores(text)
        text_lower = text.lower()

        emotions: Dict[str, float] = {}

        compound = scores["compound"]
        pos = scores["pos"]
        neg = scores["neg"]

        # Explicit lexical cues first — these override VADER where they match
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

        # Punctuation as a weak signal — "?" suggests curiosity, "!" suggests surprise
        if "?" in text:
            emotions["curiosity"] = max(emotions.get("curiosity", 0.0), 0.58)

        if "!" in text:
            emotions["surprise"] = max(emotions.get("surprise", 0.0), 0.52)

        # VADER compound score as a fallback for general sentiment — fills the gap
        # when no explicit keyword matched but the text is clearly positive/negative
        if compound >= 0.65:
            emotions["joy"] = max(emotions.get("joy", 0.0), 0.75)
        elif compound >= 0.30:
            emotions["approval"] = max(emotions.get("approval", 0.0), 0.65)
        elif compound <= -0.65:
            emotions["anger"] = max(emotions.get("anger", 0.0), 0.76)
        elif compound <= -0.30:
            emotions["disapproval"] = max(emotions.get("disapproval", 0.0), 0.64)

        # Last resort: use raw pos/neg word ratios if compound didn't fire either
        if not emotions:
            if pos > 0.20 and neg < 0.10:
                emotions["approval"] = 0.60
            elif neg > 0.20 and pos < 0.10:
                emotions["disapproval"] = 0.60
            else:
                # Nothing found at all — default to neutral
                emotions["neutral"] = 1.0

        return self._apply_thresholds(emotions)

    # ------------------------------------------------------------------
    # Transformer mode
    # ------------------------------------------------------------------

    def _ml_analysis(self, text: str) -> Dict[str, float]:
        """Run the GoEmotions transformer and filter by per-emotion thresholds.

        Falls back to rule_based analysis if the model isn't loaded or if the
        classifier call raises an exception (e.g. network error during init).
        """
        if not self.model_available or not self.classifier:
            return self._fallback_analysis(text)

        try:
            results = self.classifier(text)[0]
            emotions: Dict[str, float] = {}

            for r in results:
                label = r["label"]
                score = r["score"]
                # Convert raw LABEL_N to the human-readable name
                emotion = self.LABEL_TO_NAME.get(label, label)
                threshold = self.EMOTION_THRESHOLDS.get(emotion, 0.3)

                # Only keep scores that clear the per-emotion threshold
                if score >= threshold:
                    emotions[emotion] = score

            if not emotions:
                # All scores were below threshold — treat as neutral
                emotions["neutral"] = 1.0

            return emotions

        except Exception as e:
            logger.warning("Emotion analysis failed: %s", e)
            return self._fallback_analysis(text)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _fallback_analysis(self, text: str) -> Dict[str, float]:
        """Use rule_based as the fallback when ML is unavailable or fails."""
        return self._rule_based_analysis(text)

    def _filter_reliable_only(self, emotions: Dict[str, float]) -> Dict[str, float]:
        """Drop emotions that the model tends to misclassify.

        Any emotion that's in HIGH_CONFIDENCE_EMOTIONS passes through unchanged.
        Rare emotions that are in EMOTION_MAPPING get folded into their canonical
        equivalent (e.g. "grief" → "sadness") taking the max score.
        Everything else is dropped silently.
        """
        filtered: Dict[str, float] = {}

        for emotion, score in emotions.items():
            if emotion in self.HIGH_CONFIDENCE_EMOTIONS:
                filtered[emotion] = score
            elif emotion in self.EMOTION_MAPPING:
                # Merge into the canonical emotion, keeping the higher score
                mapped = self.EMOTION_MAPPING[emotion]
                filtered[mapped] = max(filtered.get(mapped, 0.0), score)

        return filtered

    def _apply_thresholds(self, emotions: Dict[str, float]) -> Dict[str, float]:
        """Remove any emotion whose score falls below its minimum threshold.

        Returns {"neutral": 1.0} if nothing passes, so callers always get a
        non-empty result.
        """
        filtered: Dict[str, float] = {}

        for emotion, score in emotions.items():
            threshold = self.EMOTION_THRESHOLDS.get(emotion, 0.3)
            if score >= threshold:
                filtered[emotion] = round(float(score), 4)

        if not filtered:
            return {"neutral": 1.0}

        return filtered
