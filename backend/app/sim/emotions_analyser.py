import logging
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
    # while correctly aligning scale endpoints. See dissertation Section XYZ.

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

