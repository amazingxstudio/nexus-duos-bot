from app.models import GameKey
from app.games.engine.base import BaseGameEngine

BOARD_SIZE = 5
UNITS_PER_PLAYER = 3
MATCH_DURATION_MS = 60_000


class NeonChessEngine(BaseGameEngine):
    game_key = GameKey.NEON_CHESS
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        return {"board_size": BOARD_SIZE, "units": [], "turn_user_id": None}

    def on_match_start(self, state: dict) -> None:
        units = state["payload"]["units"]
        player_ids = list(state["players"].keys())
        p1, p2 = player_ids[0], player_ids[1]
        for i in range(UNITS_PER_PLAYER):
            units.append({"id": f"{p1}-{i}", "owner_id": p1, "x": i + 1, "y": 0, "alive": True})
            units.append({"id": f"{p2}-{i}", "owner_id": p2, "x": i + 1, "y": BOARD_SIZE - 1, "alive": True})
        state["payload"]["turn_user_id"] = p1

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "move_unit":
            return state
        if state["payload"]["turn_user_id"] != user_id:
            raise ValueError("NOT_YOUR_TURN")
        units = state["payload"]["units"]
        unit_id, to_x, to_y = data.get("unit_id"), data.get("x"), data.get("y")
        unit = next((u for u in units if u["id"] == unit_id and u["alive"]), None)
        if not unit:
            raise ValueError("UNIT_NOT_FOUND")
        if unit["owner_id"] != user_id:
            raise ValueError("NOT_YOUR_UNIT")
        if not (0 <= to_x < BOARD_SIZE and 0 <= to_y < BOARD_SIZE):
            raise ValueError("OUT_OF_BOUNDS")
        dx, dy = abs(to_x - unit["x"]), abs(to_y - unit["y"])
        if not ((dx == 1 and dy == 0) or (dx == 0 and dy == 1)):
            raise ValueError("INVALID_MOVE")
        occupant = next((u for u in units if u["alive"] and u["x"] == to_x and u["y"] == to_y), None)
        if occupant and occupant["owner_id"] == user_id:
            raise ValueError("SQUARE_OCCUPIED_BY_ALLY")
        if occupant:
            occupant["alive"] = False
            state["players"][user_id]["score"] += 100
        else:
            state["players"][user_id]["score"] += 5
        unit["x"], unit["y"] = to_x, to_y
        opponent_id = next(uid for uid in state["players"] if uid != user_id)
        opponent_alive = any(u["owner_id"] == opponent_id and u["alive"] for u in units)
        if not opponent_alive:
            state["players"][user_id]["finished"] = True
            state["players"][opponent_id]["finished"] = True
        state["payload"]["turn_user_id"] = opponent_id
        return state
