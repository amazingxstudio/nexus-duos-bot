import random
from app.models import GameKey
from app.games.engine.base import BaseGameEngine

PAIR_COUNT = 8
MATCH_DURATION_MS = 40_000


class MemoryWarfareEngine(BaseGameEngine):
    game_key = GameKey.MEMORY_WARFARE
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        symbols = list(range(PAIR_COUNT)) * 2
        random.shuffle(symbols)
        return {"board": symbols, "boards": {}}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "flip_card":
            return state
        board = state["payload"]["board"]
        boards = state["payload"]["boards"]
        player_board = boards.get(user_id, {"revealed": [], "matched": [], "combo": 0})

        index = data.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(board):
            raise ValueError("INVALID_INDEX")
        if index in player_board["matched"] or index in player_board["revealed"]:
            return state
        if len(player_board["revealed"]) >= 2:
            player_board["revealed"] = []
        player_board["revealed"].append(index)

        if len(player_board["revealed"]) == 2:
            a, b = player_board["revealed"]
            if board[a] == board[b]:
                player_board["matched"].extend([a, b])
                player_board["combo"] += 1
                state["players"][user_id]["score"] += 100 * player_board["combo"]
                player_board["revealed"] = []
                if len(player_board["matched"]) == len(board):
                    state["players"][user_id]["finished"] = True
            else:
                player_board["combo"] = 0
        boards[user_id] = player_board
        return state
