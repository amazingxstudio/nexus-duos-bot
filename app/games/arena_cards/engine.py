from app.models import GameKey
from app.games.engine.base import BaseGameEngine

STARTING_HP = 100
MAX_ENERGY = 10
MATCH_DURATION_MS = 50_000

CARD_POOL = [
    {"id": "strike", "name": "Strike Drone", "cost": 2, "attack": 15, "defense": 0},
    {"id": "shield", "name": "Barrier Node", "cost": 2, "attack": 0, "defense": 12},
    {"id": "blast", "name": "Plasma Blast", "cost": 4, "attack": 28, "defense": 0},
    {"id": "fortify", "name": "Fortify Core", "cost": 3, "attack": 5, "defense": 20},
    {"id": "overload", "name": "Overload Strike", "cost": 6, "attack": 40, "defense": 0},
]
CARD_BY_ID = {c["id"]: c for c in CARD_POOL}


class ArenaCardsEngine(BaseGameEngine):
    game_key = GameKey.ARENA_CARDS
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        return {"card_pool": CARD_POOL, "battle": {}}

    def on_match_start(self, state: dict) -> None:
        battle = state["payload"]["battle"]
        for user_id in state["players"]:
            battle[user_id] = {"hp": STARTING_HP, "energy": 4, "defense": 0}
            state["players"][user_id]["score"] = STARTING_HP

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        battle = state["payload"]["battle"]
        me = battle[user_id]
        opponent_id = next(uid for uid in state["players"] if uid != user_id)
        opponent = battle[opponent_id]

        if action_type == "collect_energy":
            me["energy"] = min(MAX_ENERGY, me["energy"] + 1)
            return state
        if action_type != "play_card":
            return state
        if me["hp"] <= 0 or opponent["hp"] <= 0:
            return state
        card = CARD_BY_ID.get(data.get("card_id"))
        if not card:
            raise ValueError("UNKNOWN_CARD")
        if me["energy"] < card["cost"]:
            raise ValueError("NOT_ENOUGH_ENERGY")
        me["energy"] -= card["cost"]
        if card["defense"] > 0:
            me["defense"] += card["defense"]
        if card["attack"] > 0:
            mitigated = max(0, card["attack"] - opponent["defense"])
            opponent["defense"] = max(0, opponent["defense"] - card["attack"])
            opponent["hp"] = max(0, opponent["hp"] - mitigated)
        state["players"][user_id]["score"] = me["hp"]
        state["players"][opponent_id]["score"] = opponent["hp"]
        if opponent["hp"] <= 0:
            state["players"][user_id]["finished"] = True
            state["players"][opponent_id]["finished"] = True
        return state
