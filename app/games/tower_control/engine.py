from app.models import GameKey
from app.games.engine.base import BaseGameEngine

ZONE_COUNT = 5
CAPTURE_THRESHOLD = 100
CAPTURE_POWER = 20
MATCH_DURATION_MS = 40_000


class TowerControlEngine(BaseGameEngine):
    game_key = GameKey.TOWER_CONTROL
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        zones = [{"id": i, "owner_id": None, "progress": 0, "capturing_by": None} for i in range(ZONE_COUNT)]
        return {"zones": zones, "resources": {}}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        resources = state["payload"]["resources"]
        if action_type == "collect_resource":
            resources[user_id] = resources.get(user_id, 0) + 1
            return state
        if action_type != "capture_zone":
            return state
        zone_id = data.get("zone_id")
        zones = state["payload"]["zones"]
        zone = next((z for z in zones if z["id"] == zone_id), None)
        if zone is None:
            raise ValueError("UNKNOWN_ZONE")
        if zone["owner_id"] == user_id:
            return state
        available = resources.get(user_id, 0)
        if available < 1:
            raise ValueError("NOT_ENOUGH_RESOURCES")
        resources[user_id] = available - 1

        if zone["capturing_by"] and zone["capturing_by"] != user_id:
            zone["progress"] -= CAPTURE_POWER
            if zone["progress"] <= 0:
                zone["capturing_by"] = user_id
                zone["progress"] = abs(zone["progress"])
        else:
            zone["capturing_by"] = user_id
            zone["progress"] += CAPTURE_POWER

        if zone["progress"] >= CAPTURE_THRESHOLD:
            previous_owner = zone["owner_id"]
            zone["owner_id"] = user_id
            zone["progress"] = CAPTURE_THRESHOLD
            zone["capturing_by"] = None
            if previous_owner:
                state["players"][previous_owner]["score"] = max(0, state["players"][previous_owner]["score"] - 50)
            state["players"][user_id]["score"] += 150
        return state
