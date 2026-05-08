"""
Singleton loader for the GoEmotions classifier.

PROBLEM SOLVED:
  Before: EmotionAnalyser.__init__() called pipeline() every time a SimAgent
  was created. With 4 agents per run and 20+ runs per experiment, this loaded
  the model 80-400+ times. Slow and wasteful.

  After: pipeline() is called exactly once per process. Every EmotionAnalyser
  instance shares the same classifier object via get_emotion_classifier().
"""
from __future__ import annotations

import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

_classifier: Optional[Any] = None
_load_attempted: bool = False


def get_emotion_classifier(use_gpu: bool = False) -> Optional[Any]:
    """
    Return the shared GoEmotions classifier, loading it on first call only.
    Subsequent calls return the cached instance immediately.
    """
    global _classifier, _load_attempted

    if _load_attempted:
        return _classifier

    _load_attempted = True

    try:
        from transformers import pipeline
        from app.core.config import EMOTION_MODEL_ID

        device = 0 if use_gpu else -1
        logger.info(f"Loading GoEmotions model '{EMOTION_MODEL_ID}' (one-time load)...")

        _classifier = pipeline(
            "text-classification",
            model=EMOTION_MODEL_ID,
            device=device,
            top_k=None,
        )
        logger.info("GoEmotions model loaded successfully.")

    except Exception as e:
        logger.warning(f"GoEmotions model failed to load: {e}. Emotion analysis will use fallback.")
        _classifier = None

    return _classifier


def reset_classifier() -> None:
    """
    Reset the singleton — used in tests only so each tests gets a clean state.
    Do NOT call this in production code.
    """
    global _classifier, _load_attempted
    _classifier = None
    _load_attempted = False