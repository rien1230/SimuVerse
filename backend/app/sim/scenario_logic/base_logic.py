"""
app/sim/scenario_logic/base_logic.py

Base logic class.
Subclasses override choose_action() and helpers.

agent.py handles:
- state
- emotion
- memory
- conversation state machine

The logic class handles:
- what action to take
- what to say
- how to complete tasks
"""
from __future__ import annotations
import random
from typing import TYPE_CHECKING, Optional, List, Dict, Any

if TYPE_CHECKING:
    from app.sim.agent import SimAgent
    from app.sim.model import SimModel


def _lbl(item: str) -> str:
    """Fallback label formatter for items."""
    return item.replace("_", " ").title() if item else "that"


# ── Environment physics rules ───────────────────────────────────────────────
# These multipliers are applied by agent.py to scale the social physics
# (stress, trust, recovery) based on which scenario type is running.

ENVIRONMENT_RULES: Dict[str, Dict[str, float]] = {
    "office": {
        # Stress rises moderately; task-focused but not urgent
        "stress_multiplier": 0.9,
        # Competence/reliability drive trust; standard gains
        "trust_gain_multiplier": 1.0,
        # Conflict feels controlled and professional
        "conflict_multiplier": 0.9,
        # Moderate recovery — emotions cool at a normal pace
        "recovery_multiplier": 1.0,
        # Refusals are professionally costly
        "refusal_penalty": 1.0,
        # Action probability biases (used by choose_action in scenario logics)
        "ask_bias": 1.0,
        "challenge_bias": 0.8,
        # Structured collaboration: confirmations close the loop
        "confirm_bias": 1.2,
    },
    "cafe": {
        # Low stakes — stress barely rises
        "stress_multiplier": 0.6,
        # Friendliness and flexibility rewarded more
        "trust_gain_multiplier": 1.1,
        # Disagreement is rare and quickly forgotten
        "conflict_multiplier": 0.5,
        # People calm down quickly here
        "recovery_multiplier": 1.2,
        # Refusals barely sting in a social setting
        "refusal_penalty": 0.7,
        "ask_bias": 0.8,
        # Low pressure — challenges are soft and infrequent
        "challenge_bias": 0.3,
        "confirm_bias": 1.2,
    },
    "escape": {
        # Time pressure means stress builds fast
        "stress_multiplier": 1.6,
        # Useful clue-sharing pays off big; hesitation punished
        "trust_gain_multiplier": 1.2,
        # Friction under pressure hits harder
        "conflict_multiplier": 1.3,
        # Tension barely drops until real progress happens
        "recovery_multiplier": 0.65,
        # Refusals are costly — every second counts
        "refusal_penalty": 1.3,
        "ask_bias": 1.2,
        # High pressure sparks more challenges and second-guessing
        "challenge_bias": 1.4,
        "confirm_bias": 0.9,
    },
}

# ── Per-environment action probability modifiers by personality ──────────────
# Applied on top of base personality weights in choose_action().
# Keys: ask_bias, challenge_bias, share_bias, confirm_bias
# Format: ENVIRONMENT_MODIFIERS[env_type][personality_type] = {key: float}

ENVIRONMENT_MODIFIERS: Dict[str, Dict[str, Dict[str, float]]] = {
    "office": {
        "Leader":      {"ask_bias": 1.2, "challenge_bias": 0.9, "share_bias": 1.1, "confirm_bias": 1.1},
        "Decisive":    {"ask_bias": 1.3, "challenge_bias": 1.1, "share_bias": 1.0, "confirm_bias": 1.2},
        "Skeptical":   {"ask_bias": 1.1, "challenge_bias": 1.2, "share_bias": 0.7, "confirm_bias": 0.9},
        "Overthinker": {"ask_bias": 0.8, "challenge_bias": 0.7, "share_bias": 0.8, "confirm_bias": 0.9},
        "Creative":    {"ask_bias": 0.7, "challenge_bias": 0.6, "share_bias": 1.0, "confirm_bias": 1.0},
        "Easygoing":   {"ask_bias": 0.7, "challenge_bias": 0.4, "share_bias": 1.3, "confirm_bias": 1.1},
    },
    "cafe": {
        "Leader":      {"ask_bias": 0.9, "challenge_bias": 0.5, "share_bias": 1.1, "confirm_bias": 1.3},
        "Decisive":    {"ask_bias": 1.0, "challenge_bias": 0.6, "share_bias": 1.0, "confirm_bias": 1.4},
        "Skeptical":   {"ask_bias": 0.8, "challenge_bias": 0.9, "share_bias": 0.7, "confirm_bias": 0.9},
        "Overthinker": {"ask_bias": 0.7, "challenge_bias": 0.5, "share_bias": 0.8, "confirm_bias": 1.0},
        "Creative":    {"ask_bias": 0.9, "challenge_bias": 0.4, "share_bias": 1.2, "confirm_bias": 1.3},
        "Easygoing":   {"ask_bias": 0.6, "challenge_bias": 0.2, "share_bias": 1.4, "confirm_bias": 1.5},
    },
    "escape": {
        "Leader":      {"ask_bias": 1.4, "challenge_bias": 1.2, "share_bias": 1.2, "confirm_bias": 0.9},
        "Decisive":    {"ask_bias": 1.5, "challenge_bias": 1.3, "share_bias": 1.1, "confirm_bias": 0.8},
        "Skeptical":   {"ask_bias": 1.3, "challenge_bias": 1.4, "share_bias": 0.8, "confirm_bias": 0.7},
        "Overthinker": {"ask_bias": 1.1, "challenge_bias": 1.2, "share_bias": 0.9, "confirm_bias": 0.8},
        "Creative":    {"ask_bias": 1.1, "challenge_bias": 0.9, "share_bias": 1.1, "confirm_bias": 0.9},
        "Easygoing":   {"ask_bias": 1.0, "challenge_bias": 0.7, "share_bias": 1.3, "confirm_bias": 1.0},
    },
}

# ── Per-environment dialogue pools ───────────────────────────────────────────
# Used by generate_* methods when no scenario-specific override is provided,
# and also surfaced to agent.py's generic text generators.

ENVIRONMENT_DIALOGUE: Dict[str, Dict[str, List[str]]] = {
    "office": {
        "say": [
            "Let's close this gap.",
            "Keep it on track.",
            "We need to move past this.",
            "Let's wrap this up.",
            "Stay focused on the deliverable.",
            "Someone needs to own the next step.",
            "Who's picking this up?",
        ],
        "ask": [
            "I need the details on {item} — can you confirm?",
            "What's the status on {item}?",
            "Do you have what we need for {item}?",
            "Can you confirm {item} — I need it to proceed.",
            "{item} — what's your position on that?",
        ],
        "share": [
            "Here's what we have: {info}",
            "This covers it: {info}",
            "That's the current position: {info}",
            "For reference: {info}",
        ],
        "refuse": [
            "Not yet — I need more time on that.",
            "I'll hold off on that a bit longer.",
            "Not ready to commit to that yet.",
            "I'd rather wait until I have the full picture.",
        ],
        "challenge": [
            "That doesn't work for me — we need a better approach.",
            "I'd push back on that. Have we considered the alternatives?",
            "That creates more problems than it solves.",
            "I'm not convinced that's the right call here.",
        ],
        "agree": [
            "That checks out. Keep going.",
            "Agreed. Let's keep this moving.",
            "That's the right call. Close it out.",
            "Good. That's decided.",
        ],
        "help": [
            "I'll sort that for you.",
            "Leave that with me.",
            "I'll take that on.",
            "I can handle that.",
        ],
        "ignore": [
            "Not now.",
            "Leave that for the moment.",
            "Focus on the priority first.",
            "Park that — we'll come back to it.",
        ],
        "insult": [
            "That isn't a useful contribution.",
            "You're slowing this down.",
            "Not what we need right now.",
        ],
    },
    "cafe": {
        "say": [
            "I'm fine with that.",
            "That sounds good, honestly.",
            "As long as it works for everyone, I'm in.",
            "Yeah, we're getting close.",
            "Let's not make this harder than it is.",
            "Either works for me.",
        ],
        "ask": [
            "Any thoughts on {item}?",
            "What do you reckon about {item}?",
            "Do you have a preference on {item}?",
            "What's your take on {item}?",
            "{item} — what do you think?",
        ],
        "share": [
            "Okay so — {info}",
            "Right, {info}",
            "I think {info}",
            "For what it's worth — {info}",
        ],
        "refuse": [
            "I'd rather wait a bit on that.",
            "Not sure yet — give me a sec.",
            "I'm still figuring that out.",
            "I don't want to lock that in yet.",
        ],
        "challenge": [
            "I'm not fully sold on that.",
            "Hmm — I'm not sure that's quite right.",
            "That doesn't quite work for me.",
            "I'd push back a little on that.",
        ],
        "agree": [
            "Yeah, that sounds fine.",
            "I can go with that.",
            "Sounds fair enough.",
            "That makes sense to me.",
        ],
        "help": [
            "Yeah, I can help with that.",
            "Don't worry, I'll sort it.",
            "Happy to help.",
            "Sure, leave that with me.",
        ],
        "ignore": [
            "Give me a sec.",
            "I'll come back to that.",
            "Hang on, I'm thinking.",
            "One sec.",
        ],
        "insult": [
            "You're making this harder than it needs to be.",
            "That's not really helping us get there.",
            "Come on — we were almost there.",
            "That's kind of derailing us a bit.",
        ],
    },
    "escape": {
        "say": [
            "Check the panel.",
            "We need that now.",
            "That clears the next part.",
            "Move — we don't have time.",
            "Focus.",
            "What do you have?",
            "Stay on it.",
        ],
        "ask": [
            "Do you have {item}? We need it.",
            "{item} — what do you know?",
            "I need {item} to move forward.",
            "What's your read on {item}?",
            "{item} — quick.",
        ],
        "share": [
            "Here — {info}",
            "Got it: {info}",
            "This is what I've got: {info}",
            "Try this: {info}",
        ],
        "refuse": [
            "Not yet — I'm still working it.",
            "Give me a second.",
            "I'm not confident enough to share that yet.",
            "Hold on — I need to verify it.",
        ],
        "challenge": [
            "That's wrong — we need to check again.",
            "No. That doesn't add up.",
            "Are you sure? That could cost us time.",
            "I don't think that's right.",
        ],
        "agree": [
            "Yes. Let's go.",
            "That's it. Move.",
            "Confirmed. Go.",
            "Good. Do it.",
        ],
        "help": [
            "On it.",
            "I'll check it.",
            "Give me ten seconds.",
            "I'm on that.",
        ],
        "ignore": [
            "Not now.",
            "Focus on the clue first.",
            "Later.",
            "Not yet.",
        ],
        "insult": [
            "You're wasting time.",
            "That's slowing us down.",
            "Not helpful — stay focused.",
            "We can't afford this right now.",
        ],
    },
}


def get_env_rules(model: "SimModel") -> Dict[str, float]:
    """Return the environment rules for the model's current scenario type."""
    behaviour = getattr(model, "behaviour", None)
    scenario_type = getattr(behaviour, "scenario_type", "office")
    return ENVIRONMENT_RULES.get(scenario_type, ENVIRONMENT_RULES["office"])


def get_env_modifiers(model: "SimModel", personality: str) -> Dict[str, float]:
    """Return per-personality action biases for the model's scenario type."""
    behaviour = getattr(model, "behaviour", None)
    scenario_type = getattr(behaviour, "scenario_type", "office")
    env_mods = ENVIRONMENT_MODIFIERS.get(scenario_type, ENVIRONMENT_MODIFIERS["office"])
    return env_mods.get(personality, {"ask_bias": 1.0, "challenge_bias": 1.0, "share_bias": 1.0, "confirm_bias": 1.0})


def get_env_dialogue(model: "SimModel", action: str) -> List[str]:
    """Return the env-appropriate phrase pool for a given action type."""
    behaviour = getattr(model, "behaviour", None)
    scenario_type = getattr(behaviour, "scenario_type", "office")
    pools = ENVIRONMENT_DIALOGUE.get(scenario_type, ENVIRONMENT_DIALOGUE["office"])
    return pools.get(action, [])


class BaseLogic:
    scenario_type: str = "base"
    ROLES: dict = {"A1": "A1", "A2": "A2", "A3": "A3", "A4": "A4"}

    def role(self, agent_id: str) -> str:
        return self.ROLES.get(agent_id, agent_id)

    # ── Main action decision ────────────────────────────────────────────────
    def choose_action(
        self,
        agent: "SimAgent",
        others: List["SimAgent"]
    ) -> Optional[Dict[str, Any]]:
        """Override in subclass. Returns an event dict or None."""
        return None

    # ── Agreement ───────────────────────────────────────────────────────────
    def agree_text(self, agent: "SimAgent", pref: str, target_id: str) -> str:
        pool = get_env_dialogue(agent.model, "agree")
        if pool:
            return random.choice(pool)
        if not pref or pref == "unknown":
            return "Agreed — let's go with that."
        return f"{pref.capitalize()} makes sense. Let's go with that."

    def should_complete_on_agree(self, model: "SimModel", pref: str) -> bool:
        return False

    def task_to_complete(self, model: "SimModel", pref: str) -> Optional[str]:
        return None

    def build_final_decision(self, model: "SimModel") -> Optional[str]:
        return None

    # ── Suggestions ─────────────────────────────────────────────────────────
    def suggestion_options(self, agent: "SimAgent") -> List[str]:
        return []

    def suggest_text(self, agent: "SimAgent", pref: str, target_id: str) -> str:
        return f"I suggest {pref}."

    # ── Info text ───────────────────────────────────────────────────────────
    def info_text(self, item: str) -> Optional[str]:
        return None

    # ── Completion hooks ────────────────────────────────────────────────────
    def extra_completion_cascade(self, model: "SimModel") -> None:
        pass

    # ── Generic fallback dialogue (env-aware) ───────────────────────────────
    def generate_help_text(self, agent: "SimAgent", target_id: str, item: str) -> str:
        pool = get_env_dialogue(agent.model, "help")
        if pool:
            return random.choice(pool)
        options = [
            f"I can help with {_lbl(item)}, {agent._r(target_id)}.",
            f"Let me take a look at {_lbl(item)}.",
            f"I'll try to sort {_lbl(item)}.",
            f"I can work on that with you.",
        ]
        return random.choice(options)

    def generate_ignore_text(self, agent: "SimAgent", target_id: str) -> str:
        pool = get_env_dialogue(agent.model, "ignore")
        if pool:
            return random.choice(pool)
        options = [
            "...",
            f"{agent._r(target_id)}, not now.",
            "I can't deal with that right now.",
            "Leave that for a moment.",
        ]
        return random.choice(options)

    def generate_insult_text(self, agent: "SimAgent", target_id: str) -> str:
        pool = get_env_dialogue(agent.model, "insult")
        if pool:
            return random.choice(pool)
        options = [
            f"{agent._r(target_id)}, that's not helping.",
            "You're making this harder than it needs to be.",
            "That was not useful at all.",
            "This is slowing everything down.",
        ]
        return random.choice(options)

    def generate_say_text(self, agent: "SimAgent", target_id: str) -> str:
        pool = get_env_dialogue(agent.model, "say")
        if pool:
            return random.choice(pool)
        options = [
            f"{agent._r(target_id)}, what do you think?",
            "We should keep going.",
            "Let's stay focused.",
            "We're getting somewhere.",
        ]
        return random.choice(options)

    def generate_ask_text(self, agent: "SimAgent", item: str, target_id: str) -> str:
        pool = get_env_dialogue(agent.model, "ask")
        if pool:
            # Fill {item} placeholder if present
            template = random.choice(pool)
            return template.replace("{item}", _lbl(item))
        options = [
            f"{agent._r(target_id)}, do you know anything about {_lbl(item)}?",
            f"Can you help with {_lbl(item)}, {agent._r(target_id)}?",
            f"What do you have on {_lbl(item)}?",
            f"{agent._r(target_id)}, any idea about {_lbl(item)}?",
        ]
        return random.choice(options)

    def generate_share_text(self, agent: "SimAgent", item: str, target_id: str) -> str:
        info = self.info_text(item)
        pool = get_env_dialogue(agent.model, "share")
        if pool and info:
            template = random.choice(pool)
            return template.replace("{info}", info)
        if info:
            options = [
                f"Here's what I found: {info}",
                f"This might help: {info}",
                f"I found something useful: {info}",
            ]
        else:
            options = [
                f"I've got something on {_lbl(item)}.",
                f"Here's what I know about {_lbl(item)}.",
                f"This may help with {_lbl(item)}.",
            ]
        return random.choice(options)
