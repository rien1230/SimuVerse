from __future__ import annotations
from typing import Dict, List, Optional, Any
from enum import Enum
import numpy as np
import random



class EnvironmentType(Enum):
    OFFICE = "office"
    CAFE = "cafe"
    ESCAPE = "escape"


class Environment:
    ENVIRONMENTS = {
        "office": {
            "name": "Office",
            "description": "Professional workplace with hierarchy and deadlines",
            "mood_modifier": -0.05,
            "arousal_modifier": 0.10,
            "urgency_modifier": 0.25,          # moderate pressure
            "formality": 0.90,
            "privacy": 0.20,
            "trust_speed": 0.80,
            "conflict_probability": 0.30,
            "emotion_expression": 0.40,
            "cooperation_modifier": 0.85,      # slightly reduced due to hierarchy
            "goal_type": "Complete project proposal before deadline",
            "goal_items": ["budget", "requirements", "design", "tech specs"],
            "topics": [
                "deadlines", "projects", "meetings", "presentations", "clients",
                "reports", "budgets", "proposals", "schedules", "teams",
                "workloads", "feedback"
            ],
            "templates": {
                "say": [
                    "Did you get a chance to look at the {topic}?",
                    "How are the {topic} coming along?",
                    "I'm so stressed about the {topic}.",
                    "Can we talk about the {topic}?",
                    "What do you think about the {topic}?",
                    "I've been working on the {topic} all morning.",
                    "Have you seen the update on the {topic}?",
                    "I need help with the {topic}.",
                    "The {topic} are driving me crazy.",
                    "Don't even get me started on the {topic}."
                ],
                "compliment": [
                    "You did great with the {topic}.",
                    "I'm impressed by how you handled the {topic}.",
                    "Your work on the {topic} was really good.",
                    "You're so good with the {topic}.",
                    "I learned a lot watching you deal with the {topic}.",
                    "Thanks for your help with the {topic}.",
                    "You always know what to do about the {topic}.",
                    "The team noticed how hard you worked on the {topic}.",
                    "You made the {topic} look easy.",
                    "I'm glad you're here when the {topic} come up."
                ],
                "insult": [
                    "You really messed up the {topic}.",
                    "I'm disappointed in how you handled the {topic}.",
                    "This isn't the first time you've struggled with the {topic}.",
                    "I expected better from you on the {topic}.",
                    "Are you even trying with the {topic}?",
                    "Your attitude about the {topic} is frustrating.",
                    "I can't believe you said that about the {topic}.",
                    "You're being really difficult about the {topic}.",
                    "This is why I can't count on you for the {topic}.",
                    "Everyone's frustrated with how you handled the {topic}."
                ],
                "help": [
                    "Let me help you with the {topic}.",
                    "I can take care of the {topic} if you're overwhelmed.",
                    "Need a hand with the {topic}?",
                    "I've dealt with the {topic} before, happy to help.",
                    "We can work on the {topic} together.",
                    "Don't struggle with the {topic} alone.",
                    "I'm free this afternoon if you want to tackle the {topic}.",
                    "Let me know what you need for the {topic}.",
                    "I've got your back with the {topic}.",
                    "We'll figure out the {topic} together."
                ],
                "drama": [
                    "Did you hear about {person}? They're getting laid off.",
                    "I saw {person} crying in the bathroom.",
                    "{person} stole credit for {person2}'s work.",
                    "Management is watching us closely.",
                    "I think {person} is about to quit.",
                    "There's a rumor about {person} and {person2}...",
                    "Don't tell anyone, but {person} is looking for another job.",
                    "I heard {person} got a huge bonus. The rest of us got nothing.",
                    "{person} threw me under the bus in the meeting.",
                    "The boss has been acting really strange lately."
                ]
            }
        },
        "cafe": {
            "name": "Cafe",
            "description": "Casual coffee shop, relaxed social atmosphere",
            "mood_modifier": 0.10,
            "arousal_modifier": 0.00,
            "urgency_modifier": 0.00,          # no time pressure
            "formality": 0.30,
            "privacy": 0.50,
            "trust_speed": 1.20,
            "conflict_probability": 0.10,
            "emotion_expression": 0.70,
            "cooperation_modifier": 1.15,      # friendly → easier cooperation
            "goal_type": "Plan a group vacation together",
            "goal_items": ["flights", "hotels", "restaurants", "activities"],
            "topics": [
                "weekends", "plans", "movies", "music", "weather", "shows",
                "news", "trips", "parties", "friends", "food", "drinks",
                "hobbies", "gossip", "dating"
            ],
            "templates": {  # same structure as office — abbreviated for brevity
                "say": [...],       # ← copy your original lists here
                "compliment": [...],
                "insult": [...],
                "help": [...],
                "drama": [...]
            }
        },
        "escape": {
            "name": "Escape Room",
            "description": "High-stakes puzzle room with time running out",
            "mood_modifier": -0.20,
            "arousal_modifier": 0.30,
            "urgency_modifier": 0.80,          # high time pressure
            "formality": 0.20,
            "privacy": 0.10,
            "trust_speed": 1.80,               # trust builds/lost quickly
            "conflict_probability": 0.40,
            "emotion_expression": 0.80,
            "cooperation_modifier": 0.70,      # stress reduces baseline cooperation
            "goal_type": "Escape before time runs out",
            "goal_items": ["key", "code", "map", "pattern"],
            "topics": [
                "keys", "codes", "maps", "patterns", "doors", "timers",
                "clues", "puzzles", "locks", "combinations", "compartments",
                "riddles", "numbers", "symbols", "solutions"
            ],
            "templates": {  # same structure
                "say": [...],
                "compliment": [...],
                "insult": [...],
                "help": [...],
                "drama": [...]
            }
        }
    }

    def __init__(self, environment_type: str):
        if environment_type not in self.ENVIRONMENTS:
            raise ValueError(f"Unknown environment type: {environment_type}")

        self.type = environment_type
        self.config = self.ENVIRONMENTS[environment_type]

        # Core properties
        self.name = self.config["name"]
        self.description = self.config["description"]
        self.goal_type = self.config["goal_type"]
        self.goal_items = self.config["goal_items"]

        # Modifiers (with defaults if somehow missing)
        self.mood_modifier       = self.config.get("mood_modifier", 0.0)
        self.arousal_modifier    = self.config.get("arousal_modifier", 0.0)
        self.urgency_modifier    = self.config.get("urgency_modifier", 0.0)
        self.formality           = self.config.get("formality", 0.5)
        self.privacy             = self.config.get("privacy", 0.5)
        self.trust_speed         = self.config.get("trust_speed", 1.0)
        self.conflict_probability = self.config.get("conflict_probability", 0.2)
        self.emotion_expression  = self.config.get("emotion_expression", 0.5)
        self.cooperation_modifier = self.config.get("cooperation_modifier", 1.0)

        self.topics = self.config.get("topics", [])
        self.templates = self.config.get("templates", {})

    def get_template(self, event_type: str, topic: Optional[str] = None) -> str:
        if event_type not in self.templates or not self.templates[event_type]:
            return f"[{event_type} about {topic or 'something'}]"

        template = random.choice(self.templates[event_type])

        if "{topic}" in template:
            if topic:
                template = template.replace("{topic}", topic)
            elif self.topics:
                template = template.replace("{topic}", random.choice(self.topics))

        return template

    def get_drama_template(self, person1: str, person2: Optional[str] = None) -> str:
        if "drama" not in self.templates or not self.templates["drama"]:
            return f"Drama involving {person1}" + (f" and {person2}" if person2 else "")

        template = random.choice(self.templates["drama"])
        template = template.replace("{person}", person1)
        if person2 and "{person2}" in template:
            template = template.replace("{person2}", person2)
        return template

    def modify_agent_state(self, agent) -> None:
        """Apply environment mood & arousal shifts (call once per tick or as needed)"""
        agent.valence = clamp(agent.valence + self.mood_modifier, -1.0, 1.0)
        agent.arousal = clamp(agent.arousal + self.arousal_modifier, 0.0, 1.0)

    def should_increase_conflict(self) -> bool:
        return random.random() < self.conflict_probability

    # Convenience getters (used in agent decision logic)
    def get_speech_style_modifier(self) -> float:
        return self.formality

    def get_trust_modifier(self) -> float:
        return self.trust_speed

    def get_emotion_expression_modifier(self) -> float:
        return self.emotion_expression

    def get_urgency_modifier(self) -> float:
        return self.urgency_modifier

    def get_cooperation_modifier(self) -> float:
        return self.cooperation_modifier

    def __str__(self) -> str:
        return f"{self.name} Environment ({self.type})"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "description": self.description,
            "goal_type": self.goal_type,
            "goal_items": self.goal_items,
            "urgency_modifier": self.urgency_modifier,
            "cooperation_modifier": self.cooperation_modifier,
            "conflict_probability": self.conflict_probability,
            "trust_speed": self.trust_speed,
            "formality": self.formality,
            "privacy": self.privacy,
        }