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
        "max_ticks": 30,  # 4 items, enough room without sprawling
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
        "max_ticks": 25,  # similar complexity to office_proposal
    },
    "cafe_vacation": {
        "environment": "cafe",
        "name": "Plan Group Vacation",
        "description": "Agents share travel information.",
        "tasks": {
            "flights": False,
            "hotel": False,
            "food": False,
            "attractions": False,
        },
        "knowledge_map": {
            "A1": ["flights"],
            "A2": ["hotel"],
            "A3": ["food"],
            "A4": ["attractions"],
        },
        "max_ticks": 28,  # warmer environment means faster sharing
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
        "max_ticks": 20,  # single decision, should resolve quicker
    },
    "escape_code": {
        "environment": "escape",
        "name": "Find Exit Code",
        "description": "Agents combine code clues.",
        "tasks": {
            "digit_1": False,
            "digit_2": False,
            "digit_3": False,
            "order": False,
        },
        "knowledge_map": {
            "A1": ["digit_1"],
            "A2": ["digit_2"],
            "A3": ["digit_3"],
            "A4": ["order"],
        },
        "max_ticks": 25,  # urgency drives faster cooperation
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
        },
        "knowledge_map": {
            "A1": ["map"],
            "A2": ["key"],
            "A3": ["lock"],
            "A4": ["door"],
        },
        "max_ticks": 25,  # same urgency as escape_code
    },
}
