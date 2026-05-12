"""
Shared scenario labels and lookup tables used across the sim.

Central data store for scenario item labels, role names, info templates,
scenario definitions, and aliases.
"""

from __future__ import annotations

# ── Shared display labels ────────────────────────────────────────────────
# Human-readable labels for task items used in agent messages
ITEM_LABELS = {
    "budget": "Budget Information",
    "requirements": "Project Requirements",
    "design": "Design Plans",
    "tech_specs": "Technical Specifications",
    "frontend": "Frontend Development",
    "backend": "Backend Development",
    "testing": "Testing Plan",
    "documentation": "Documentation",
    "flights": "Flight Details",
    "hotel": "Hotel Details",
    "food": "Food Recommendations",
    "attractions": "Attractions List",
    "decision": "Final Decision",
    "digit_1": "First Code Digit",
    "digit_2": "Second Code Digit",
    "digit_3": "Third Code Digit",
    "order": "Digit Order",
    "map": "Room Map",
    "key": "Key Location",
    "lock": "Lock Pattern",
    "door": "Door Code",
    "italian": "Italian Restaurant",
    "vegan": "Vegan Option",
    "cheap": "Budget Option",
    "fancy": "Fine Dining Option",
}


# ── Agent role labels per environment ────────────────────────────────────
# Role names for each agent in each environment — used for display and dialogue flavour
SCENARIO_ROLES = {
    "office": {
        "A1": "Project Manager",
        "A2": "Developer",
        "A3": "Designer",
        "A4": "Data Analyst",
    },
    "roles": {
        "A1": "Team Lead",
        "A2": "Senior Dev",
        "A3": "UI Designer",
        "A4": "QA Engineer",
    },
    "cafe": {
        "A1": "Organiser",
        "A2": "Food Expert",
        "A3": "Navigator",
        "A4": "Researcher",
    },
    "escape": {
        "A1": "Team Leader",
        "A2": "Code Breaker",
        "A3": "Puzzle Solver",
        "A4": "Scout",
    },
}

# ── Reusable dialogue fragments for shared information ───────────────────
# Multiple phrasing options per item so agents don't always say the exact same thing.
# When an agent shares a piece of info, one of these strings is picked at random.
ITEM_INFO_TEMPLATES = {
    "budget": [
        "$50k total, with 10% held back.",
        "$50k overall, with a small buffer for extra costs.",
        "$50,000 total. We are keeping 10% back just in case.",
    ],
    "requirements": [
        "it needs mobile access and offline mode.",
        "the key requirements are mobile use and offline support.",
        "it has to work on mobile and offline.",
        "the client needs mobile support, and it also has to work offline.",
        "the main requirements are mobile access and offline use.",
        "the proposal needs to cover mobile support and offline use.",
    ],
    "design": [
        "we're going with a flat, modern UI — blue colour scheme throughout.",
        "flat design, clean layout, and the primary colour is blue.",
        "modern flat UI with a blue theme — nothing too complicated visually.",
    ],
    "tech_specs": [
        "the stack is React on the frontend, Node for the backend, PostgreSQL for the database.",
        "React, Node.js, and PostgreSQL — that's the stack.",
        "frontend in React, backend in Node, and PostgreSQL handling the data layer.",
    ],
    "frontend": [
        "the frontend role is mainly UI and UX — someone who knows their way around design systems.",
        "whoever takes frontend needs solid UI/UX experience, ideally with React.",
        "frontend is about the user-facing side — design sensibility is important here.",
    ],
    "backend": [
        "backend needs someone comfortable with APIs and database design.",
        "it's API work and database management — needs a solid engineering background.",
        "the backend role covers the server logic and data layer — quite technical.",
    ],
    "testing": [
        "testing is QA and automation — we need someone who can write test suites.",
        "the testing role covers quality assurance and building automated test coverage.",
        "whoever does testing needs to be comfortable with QA processes and automation tools.",
    ],
    "documentation": [
        "documentation covers the technical specs and user-facing guides.",
        "it's writing up the specs and producing user documentation — detail-oriented work.",
        "the documentation role handles both internal technical docs and anything user-facing.",
    ],
    "italian": [
        "there's an Italian place nearby. Good pasta, decent prices.",
        "the Italian place is close and gets good reviews.",
        "Italian place nearby. Pasta is meant to be good.",
    ],
    "vegan": [
        "there's a vegan place nearby with good reviews and plenty of choice.",
        "the vegan spot is popular and not too pricey.",
        "vegan place nearby, all plant-based and good for dietary needs.",
    ],
    "cheap": [
        "there's a cheap place nearby. Fast, decent, nothing fancy.",
        "the cheap option is casual, quick, and good value.",
        "affordable spot nearby. Fine for a quick lunch.",
    ],
    "fancy": [
        "there's a nicer place if we want something better, but it costs more.",
        "the fancy option is pricier, but the food is meant to be really good.",
        "upscale place, good food, but it will cost more than the others.",
    ],
}

# ── Canonical scenario definitions ───────────────────────────────────────
# Full scenario definitions — each one specifies the environment, tasks, and which
# agent starts out knowing which piece of information (the knowledge_map).
SCENARIOS = {
    "office_proposal": {
        "environment": "office",
        "name": "Complete Project Proposal",
        "description": "Agents must combine information to finish the proposal.",
        "tasks": {
            "budget": False,
            "requirements": False,
            "design": False,
            "tech_specs": False,
        },
        "knowledge_map": {
            "A1": ["budget"],
            "A2": ["requirements"],
            "A3": ["design"],
            "A4": ["tech_specs"],
        },
        "max_ticks": 30,
    },
    "office_roles": {
        "environment": "office",
        "name": "Assign Team Responsibilities",
        "description": "Agents must agree who takes each role.",
        "tasks": {
            "frontend": False,
            "backend": False,
            "testing": False,
            "documentation": False,
        },
        "knowledge_map": {
            "A1": ["backend"],
            "A2": ["frontend"],
            "A3": ["testing"],
            "A4": ["documentation"],
        },
        "max_ticks": 25,
    },
    "cafe_restaurant": {
        "environment": "cafe",
        "name": "Choose Restaurant",
        "description": "Agents must agree on a restaurant choice.",
        "tasks": {
            "decision": False,
        },
        "knowledge_map": {
            "A1": ["italian"],
            "A2": ["vegan"],
            "A3": ["cheap"],
            "A4": ["fancy"],
        },
        "max_ticks": 20,
    },
    "escape_puzzle": {
        "environment": "escape",
        "name": "Solve Puzzle Chain",
        "description": "Agents combine clues to escape.",
        "tasks": {
            "map": False,
            "key": False,
            "lock": False,
            "door": False,
            "unlock": False,
        },
        "knowledge_map": {
            "A1": ["map"],
            "A2": ["key"],
            "A3": ["lock"],
            "A4": ["door"],
        },
        "max_ticks": 35,   # most complex scenario; highest stress / urgency
    }}


# Short-hand aliases so the frontend or API can use simple names like "cafe"
# without needing to know the full canonical ID like "cafe_restaurant".
SCENARIO_ID_ALIASES = {
    "cafe":           "cafe_restaurant",
    "cafe_vacation":  "cafe_restaurant",
    "cafe_outing":    "cafe_restaurant",
    "escape":         "escape_puzzle",
    "escape_code":    "escape_puzzle",
    "escape_room":    "escape_puzzle",
    "office":         "office_proposal",
    "office_project": "office_proposal",
    "office_room":    "office_proposal",
}


def resolve_scenario_id(scenario_id: str) -> str:
    """
    Normalise any scenario ID string to its canonical key in SCENARIOS.

    Strips whitespace, lowercases, and checks the alias table.
    If nothing matches, the original string is returned as-is so the caller
    can decide whether to raise an error.
    """
    sid = str(scenario_id or "").strip().lower()
    return SCENARIO_ID_ALIASES.get(sid, sid)
