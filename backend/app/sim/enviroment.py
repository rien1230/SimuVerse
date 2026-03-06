
from typing import Dict, List, Optional, Any
from enum import Enum

# Office - Profesional and stressful
# Cafe - casual and friendly
# Home - Intimate and personal and vulnerable
class EnvironmentType(Enum):
    """Available environment types"""
    OFFICE = "office"
    CAFE = "cafe"
    HOME = "home"


class Environment:
    """
    Represents the physical/social context where agents interact.
    """

    # Environment definitions
    ENVIRONMENTS = {
        "office": {
            "name": "Office",
            "description": "Professional workplace with hierarchy and deadlines",
            "mood_modifier": -0.05,  # Slightly negative (stress)
            "arousal_modifier": 0.1,  # Higher arousal (alert)
            "formality": 0.9,  # Very formal speech
            "privacy": 0.2,  # Low privacy
            "trust_speed": 0.8,  # Trust builds slower (professional)
            "conflict_probability": 0.3,  # Higher conflict (stress)
            "emotion_expression": 0.4,  # Suppressed emotions
            "topics": [
                "report", "deadline", "meeting", "project", "presentation",
                "client", "performance", "promotion", "task", "deadline"
            ],
            "templates": {
                "say": [
                    "Did you finish the {topic}?",
                    "Meeting in 10 minutes about {topic}.",
                    "How's that {topic} coming along?",
                    "I need your input on {topic}.",
                    "The deadline for {topic} is approaching."
                ],
                "compliment": [
                    "Good work on that {topic}.",
                    "Your presentation was excellent.",
                    "I appreciate your help with {topic}.",
                    "That was a great point about {topic}.",
                    "You handled that {topic} really well."
                ],
                "insult": [
                    "That {topic} was poorly done.",
                    "You missed the deadline for {topic} again.",
                    "This {topic} needs serious improvement.",
                    "I expected better on {topic}.",
                    "That's not acceptable for {topic}."
                ],
                "help": [
                    "Let me help you with that {topic}.",
                    "I can review your {topic} if you want.",
                    "Need assistance with {topic}?",
                    "I have experience with {topic}, happy to help.",
                    "We can work on {topic} together."
                ]
            }
        },

        "cafe": {
            "name": "Cafe",
            "description": "Casual coffee shop, relaxed social atmosphere",
            "mood_modifier": 0.1,  # Positive (enjoyment)
            "arousal_modifier": 0.0,  # Neutral arousal
            "formality": 0.3,  # Casual speech
            "privacy": 0.5,  # Moderate privacy
            "trust_speed": 1.2,  # Trust builds faster
            "conflict_probability": 0.1,  # Low conflict
            "emotion_expression": 0.7,  # Open emotions
            "topics": [
                "weekend", "plans", "weather", "food", "drink",
                "hobby", "movie", "music", "travel", "friend"
            ],
            "templates": {
                "say": [
                    "Hey! How's your {topic}?",
                    "This place has great {topic}.",
                    "What did you do over {topic}?",
                    "Have you tried their {topic}?",
                    "I love coming here for {topic}."
                ],
                "compliment": [
                    "I like your {topic}!",
                    "You have great taste in {topic}.",
                    "That's awesome about {topic}!",
                    "You're so good at {topic}.",
                    "I really admire your {topic}."
                ],
                "insult": [
                    "That's not funny about {topic}.",
                    "I disagree about {topic}.",
                    "Your {topic} is a bit much.",
                    "Can we not talk about {topic}?",
                    "That's kind of weird."
                ],
                "help": [
                    "Want to grab another {topic}?",
                    "I can recommend a good {topic}.",
                    "Let me know if you need anything.",
                    "I'm here if you want to talk.",
                    "We should do this {topic} again."
                ]
            }
        },

        "home": {
            "name": "Home",
            "description": "Private residence, intimate setting",
            "mood_modifier": 0.15,  # Positive (comfort)
            "arousal_modifier": -0.1,  # Lower arousal (relaxed)
            "formality": 0.1,  # Very informal
            "privacy": 0.9,  # High privacy
            "trust_speed": 1.5,  # Trust builds fastest
            "conflict_probability": 0.2,  # Medium conflict (comfort to argue)
            "emotion_expression": 0.9,  # Very open emotions
            "topics": [
                "family", "feeling", "worry", "dream", "fear",
                "secret", "memory", "childhood", "relationship", "future"
            ],
            "templates": {
                "say": [
                    "I've been thinking about {topic}.",
                    "How are you really feeling about {topic}?",
                    "Can we talk about {topic}?",
                    "I need to tell you something about {topic}.",
                    "Remember when we talked about {topic}?"
                ],
                "compliment": [
                    "I'm so proud of you for {topic}.",
                    "You mean so much to me.",
                    "I love how you always {topic}.",
                    "You're the best thing in my life.",
                    "I really appreciate you listening about {topic}."
                ],
                "insult": [
                    "That really hurt when you said {topic}.",
                    "I'm upset about {topic}.",
                    "We need to talk about {topic}.",
                    "I can't believe you did that.",
                    "That was really insensitive."
                ],
                "help": [
                    "I'm here for you no matter what.",
                    "Let me take care of {topic} for you.",
                    "You can always talk to me about {topic}.",
                    "I'll support you with {topic}.",
                    "We'll get through {topic} together."
                ]
            }
        }
    }

    def __init__(self, environment_type: str):
        if environment_type not in self.ENVIRONMENTS:
            raise ValueError(f"Unknown environment: {environment_type}")

        self.type = environment_type
        self.config = self.ENVIRONMENTS[environment_type]
        self.name = self.config["name"]
        self.description = self.config["description"]

        # Environment effects
        self.mood_modifier = self.config["mood_modifier"]
        self.arousal_modifier = self.config["arousal_modifier"]
        self.formality = self.config["formality"]
        self.privacy = self.config["privacy"]
        self.trust_speed = self.config["trust_speed"]
        self.conflict_probability = self.config["conflict_probability"]
        self.emotion_expression = self.config["emotion_expression"]

        # Topics and templates
        self.topics = self.config["topics"]
        self.templates = self.config["templates"]

    def get_template(self, event_type: str, topic: Optional[str] = None) -> str:
        """
        Get a random template for an event type, optionally with a specific topic.
        """
        if event_type not in self.templates:
            return ""

        import random
        template = random.choice(self.templates[event_type])

        if topic and "{topic}" in template:
            template = template.replace("{topic}", topic)
        elif "{topic}" in template:
            # Use a random topic from this environment
            random_topic = random.choice(self.topics)
            template = template.replace("{topic}", random_topic)

        return template

    def modify_agent_state(self, agent) -> None:
        """
        Apply environment effects to an agent's state.
        Called when agent enters this environment.
        """
        # Mood is affected by environment
        agent.valence += self.mood_modifier
        agent.valence = max(-1.0, min(1.0, agent.valence))

        # Arousal is affected by environment
        agent.arousal += self.arousal_modifier
        agent.arousal = max(0.0, min(1.0, agent.arousal))

    # Probability of conflict based on environment.
    def should_increase_conflict(self) -> bool:
        import random
        return random.random() < self.conflict_probability

    # How formal speech should be (0-1).
    def get_speech_style_modifier(self) -> float:
        return self.formality

    # How quickly trust builds in this environment.
    def get_trust_modifier(self) -> float:
        return self.trust_speed

    # How openly emotions are expressed.
    def get_emotion_expression_modifier(self) -> float:
        return self.emotion_expression

    def __str__(self) -> str:
        return f"{self.name} Environment"

    # Export environment state for logging.
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "description": self.description,
            "formality": self.formality,
            "privacy": self.privacy,
            "trust_speed": self.trust_speed
        }


# Simple test if run directly
if __name__ == "__main__":
    print("Testing Environment System\n")

    for env_type in ["office", "cafe", "home"]:
        env = Environment(env_type)
        print(f"\n=== {env.name} ===")
        print(f"Description: {env.description}")
        print(f"Mood modifier: {env.mood_modifier}")
        print(f"Formality: {env.formality}")
        print(f"Privacy: {env.privacy}")
        print(f"Trust speed: {env.trust_speed}")
        print(f"Sample topics: {env.topics[:3]}")
        print(f"Sample say: {env.get_template('say')}")
        print(f"Sample compliment: {env.get_template('compliment')}")