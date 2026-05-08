"""
app/sim/scenario_logic/__init__.py
Factory function — returns the correct logic class for a scenario ID.
"""
from app.sim.scenario_logic.base_logic   import BaseLogic
from app.sim.scenario_logic.office_logic import OfficeProposalLogic
from app.sim.scenario_logic.cafe_logic   import CafeRestaurantLogic
from app.sim.scenario_logic.escape_logic import EscapeLogic


def get_scenario_logic(scenario_id: str) -> BaseLogic:
    """Return the correct logic instance for a scenario ID.

    Legacy scenario IDs are normalized upstream before the model is created.
    This dispatcher still keeps simple environment substring guards so any
    future scenario added under the same environment keeps routing correctly.
    """
    sid = (scenario_id or "").lower()
    if "escape" in sid:
        return EscapeLogic()
    if "cafe" in sid:
        return CafeRestaurantLogic()
    return OfficeProposalLogic()
