import logging
from transformers import pipeline
from typing import Dict, List, Tuple, Optional
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmotionAnalyser:

    ALL_EMOTIONS = [
        'admiration', 'amusement', 'anger', 'annoyance', 'approval',
        'caring', 'confusion', 'curiosity', 'desire', 'disappointment',
        'disapproval', 'disgust', 'embarrassment', 'excitement', 'fear',
        'gratitude', 'grief', 'joy', 'love', 'nervousness',
        'optimism', 'pride', 'realization', 'relief', 'remorse',
        'sadness', 'surprise', 'neutral'
    ]

    # I'm going to focus on well-represented emotions for accuracy and will map them to 'rare' emotions.
    HIGH_CONFIDENCE_EMOTIONS = {
        'neutral', 'admiration', 'approval', 'annoyance', 'gratitude',
        'disapproval', 'amusement', 'joy', 'anger', 'sadness'
    }
    EMOTION_MAPPING = {
        'grief': 'sadness',
        'remorse': 'sadness',
        'disappointment': 'sadness',
        'fear': 'anger',
        'nervousness': 'anger',
        'embarrassment': 'annoyance',
        'love': 'joy',
        'excitement': 'joy',
        'pride': 'admiration',
        'optimism': 'approval',
        'caring': 'approval',
        'desire': 'curiosity',
        'confusion': 'curiosity',
        'realization': 'surprise',
        'relief': 'joy'
    }
    # Confidents level of emotions needs to exceed these values to be considered in the filtered list.
    EMOTION_THRESHOLDS = {
        'admiration': 0.3,
        'amusement': 0.25,
        'anger': 0.15,
        'annoyance': 0.2,
        'approval': 0.15,
        'caring': 0.2,
        'confusion': 0.15,
        'curiosity': 0.2,
        'desire': 0.2,
        'disappointment': 0.1,  # Lower threshold - harder to detect
        'disapproval': 0.15,
        'disgust': 0.2,
        'embarrassment': 0.3,
        'excitement': 0.25,
        'fear': 0.4,  # Higher threshold - avoid false positives
        'gratitude': 0.25,
        'grief': 0.85,  # Very high - only when extremely sure
        'joy': 0.2,
        'love': 0.3,
        'nervousness': 0.6,  # High - requires strong signal
        'optimism': 0.2,
        'pride': 0.7,  # High - rare emotion
        'realization': 0.1,  # Very low - catch even weak signals
        'relief': 0.5,
        'remorse': 0.2,
        'sadness': 0.2,
        'surprise': 0.15,
        'neutral': 0.3
    }

    # Mapping to Russell's (1980) circumplex model:
    # - Valence: -1 (very negative) to +1 (very positive)
    # - Arousal: 0 (calm) to 1 (excited)
    #
    # I used Warriner et al. (2013) to get real human ratings for each emotion:
    # Most matched exactly 25/27. For the two that didn't:
    # caring  → closest word was 'care' (v=7.62, a=5.24)
    # realization → closest was 'realize' (v=5.83, a=5.42)
    #
    # Conversion from Warriner's 1-9 scale to Russell's scales:
    # valence = (warriner_valence - 5) / 4    # Maps: 1→-1 (minimium), 5→0 (median), 9→+1 (maximium)
    # arousal = (warriner_arousal - 1) / 8    # Maps: 1→0 (minimium), 5→0.5 (median) , 9→1 (maximium)
    #
    # These linear transformations preserve proportional relationships
    # while correctly aligning scale endpoints.

    # I got my data from : https://raw.githubusercontent.com/JULIELab/XANEW/refs/heads/master/Ratings_Warriner_et_al.csv

    VALENCE_AROUSAL_MAP = {
        # Positive emotions
        'admiration': (0.73, 0.59),
        'amusement': (0.70, 0.64),
        'approval': (0.53, 0.52),
        'caring': (0.66, 0.53),
        'desire': (0.46, 0.68),
        'excitement': (0.74, 0.80),
        'gratitude': (0.76, 0.57),
        'joy': (0.80, 0.73),
        'love': (0.82, 0.73),
        'optimism': (0.72, 0.65),
        'pride': (0.71, 0.69),
        'relief': (0.52, 0.43),

        # Negative emotions
        'anger': (-0.75, 0.77),
        'annoyance': (-0.57, 0.64),
        'disappointment': (-0.68, 0.53),
        'disapproval': (-0.58, 0.57),
        'disgust': (-0.71, 0.64),
        'embarrassment': (-0.45, 0.62),
        'fear': (-0.67, 0.76),
        'grief': (-0.79, 0.52),
        'nervousness': (-0.43, 0.69),
        'remorse': (-0.73, 0.53),
        'sadness': (-0.73, 0.50),

        # Ambiguous/neutral
        'confusion': (-0.29, 0.56),
        'curiosity': (0.33, 0.63),
        'realization': (0.25, 0.57),
        'surprise': (0.32, 0.77),
        'neutral': (0.00, 0.38)
    }

    def __init__(self, use_gpu: bool = False, use_reliable_only: bool = True):
        self.use_reliable_only = use_reliable_only
        self.model_available = False
        self.classifier = None

        # Try to load the model
        self._load_model(use_gpu)

    # Downloading GoEmotions dataset with fall backs if unsuccesful.
    def _load_model(self, use_gpu: bool):
        try:
            device = 0 if use_gpu else -1
            self.classifier = pipeline(
                "text-classification",
                model="tuhanasinan/go-emotions-distilbert-pytorch",
                device=device,
                top_k=None
            )
            self.model_available = True
            logger.info(" GoEmotions model loaded successfully")

        except Exception as e:
            logger.error(f" Failed to load GoEmotions model: {e}")
            logger.warning(" Using fallback emotion detection")
            self.model_available = False

    #When the GoEmotion is unable to load system won't crash it still would be working through using simple
    # key-words spotting.

    def _fallback_analysis(self, text: str) -> Dict[str, float]:
        text_lower = text.lower()

        if any(word in text_lower for word in ['love', 'amazing', 'great', 'excellent']):
            return {'joy': 0.7}
        elif any(word in text_lower for word in ['hate', 'stupid', 'idiot', 'terrible']):
            return {'anger': 0.6}
        elif any(word in text_lower for word in ['sad', 'sorry', 'unfortunate']):
            return {'sadness': 0.8}
        elif '?' in text:
            return {'curiosity': 0.6}
        elif '!' in text:
            return {'surprise': 0.5}
        else:
            return {'neutral': 1.0}


        # Only emotions that exceeded confidence level will be added to filtered list and rare emotions that does exceed
        # that would be replaced with the mapped common emotions in "HIGH_CONFIDENCE_EMOTIONS" Dict list.

    def _filter_reliable_only(self, emotions: Dict[str, float]) -> Dict[str, float]:
        filtered = {}

        for emotion, score in emotions.items():
            if emotion in self.HIGH_CONFIDENCE_EMOTIONS:
                filtered[emotion] = score
            elif emotion in self.EMOTION_MAPPING:
                mapped = self.EMOTION_MAPPING[emotion]
                filtered[mapped] = max(filtered.get(mapped, 0), score)

        return filtered

    def analyse(self, text: str) -> Dict[str, float]:
        if not text or not text.strip():
            return {'neutral': 1.0}

        if not self.model_available or not self.classifier:
            return self._fallback_analysis(text)

        try:
            # Get raw predictions
            results = self.classifier(text)[0]

            # Convert to dict and apply thresholds
            emotions = {}
            for r in results:
                emotion = r['label']
                score = r['score']

                # Apply per-emotion threshold
                threshold = self.EMOTION_THRESHOLDS.get(emotion, 0.3)
                if score >= threshold:
                    emotions[emotion] = score

            # Apply reliable-only filter if enabled
            if self.use_reliable_only:
                emotions = self._filter_reliable_only(emotions)

            # Ensure neutral has some baseline if nothing else
            if not emotions:
                emotions['neutral'] = 1.0

            return emotions

        except Exception as e:
            logger.warning(f"Emotion analysis failed: {e}")
            return self._fallback_analysis(text)

    #Gets the first most intense emotion.
    def get_primary_emotion(self, text: str) -> Tuple[str, float]:
        emotions = self.analyse(text)
        if emotions:
            primary = max(emotions.items(), key=lambda x: x[1])
            return primary
        return ('neutral', 1.0)

    #Gets the top 3 most intense emotions.
    def get_top_emotions(self, text: str, n: int = 3) -> List[Tuple[str, float]]:
        emotions = self.analyse(text)
        sorted_emotions = sorted(emotions.items(), key=lambda x: x[1], reverse=True)
        return sorted_emotions[:n]

    #Combines the emotions that exceeded threshold to Russell's valence-arousal space model by:
    # calculating the averages where, v is valence , (vxs)+(vxs) + ... / s + s + .... = average v and it is the same equation
    # for a (aurosal).

    def get_valence_arousal(self, text: str) -> Dict[str, float]:

        emotions = self.analyse(text)

        total_weight = 0
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
            arousal = 0.3

        valence = max(-1.0, min(1.0, valence))
        arousal = max(0.0, min(1.0, arousal))

        return {
            'valence': valence,
            'arousal': arousal,
            'primary_emotion': self.get_primary_emotion(text)[0]
        }

    # For debugging
    def explain(self, text: str) -> Dict:
        raw_results = self.classifier(text)[0] if self.model_available else []
        emotions = self.analyse(text)
        primary = self.get_primary_emotion(text)
        va = self.get_valence_arousal(text)

        # Show which emotions met thresholds
        threshold_results = []
        for r in raw_results:
            emotion = r['label']
            score = r['score']
            threshold = self.EMOTION_THRESHOLDS.get(emotion, 0.3)
            meets = score >= threshold
            threshold_results.append({
                'emotion': emotion,
                'score': score,
                'threshold': threshold,
                'meets_threshold': meets
            })

        return {
            'text': text,
            'raw_emotions': {r['label']: r['score'] for r in raw_results},
            'filtered_emotions': emotions,
            'primary_emotion': primary,
            'valence_arousal': va,
            'threshold_analysis': threshold_results,
            'mode': 'reliable_only' if self.use_reliable_only else 'all_emotions'
        }


