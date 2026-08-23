import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine

ROWS = 6
COLS = 7
# Not really a "speed" game — this is a safety cap so a match can't hang
# forever if someone walks away. Win/draw always ends it long before this.
MATCH_DURATION_MS = 5 * 60_000

_DIRECTIONS = [(0, 1), (1, 0), (1, 1), (1, -1)]


class ConnectFourEngine(BaseGameEngine):
    game_key = GameKey.CONNECT_FOUR
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        return {
            "board": [[None for _ in range(COLS)] for _ in range(ROWS)],  # board[row][col], row 0 = top
            "turn_user_id": None,
            "winning_cells": None,
            "is_draw": False,
        }

    def on_match_start(self, state: dict) -> None:
        player_ids = list(state["players"].keys())
        random.shuffle(player_ids)  # random first move — going first is an advantage
        state["payload"]["turn_user_id"] = player_ids[0]

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "drop_disc":
            return state
        payload = state["payload"]
        if payload["turn_user_id"] != user_id:
            raise ValueError("NOT_YOUR_TURN")

        column = data.get("column")
        if not isinstance(column, int) or not (0 <= column < COLS):
            raise ValueError("INVALID_COLUMN")

        board = payload["board"]
        row = None
        for r in range(ROWS - 1, -1, -1):
            if board[r][column] is None:
                row = r
                break
        if row is None:
            raise ValueError("COLUMN_FULL")

        board[row][column] = user_id

        winning_cells = _find_win(board, row, column, user_id)
        if winning_cells:
            payload["winning_cells"] = winning_cells
            state["players"][user_id]["score"] = 1
            state["players"][user_id]["finished"] = True
            opponent_id = next(uid for uid in state["players"] if uid != user_id)
            state["players"][opponent_id]["finished"] = True
        elif all(board[0][c] is not None for c in range(COLS)):
            payload["is_draw"] = True
            for p in state["players"].values():
                p["finished"] = True
        else:
            opponent_id = next(uid for uid in state["players"] if uid != user_id)
            payload["turn_user_id"] = opponent_id

        return state


def _find_win(board, row: int, col: int, user_id: str) -> list[list[int]] | None:
    """Checks all 4 directions through the cell that was just placed —
    cheaper than rescanning the whole board, and correct because a win can
    only ever involve the most recently placed disc."""
    for dr, dc in _DIRECTIONS:
        cells = [(row, col)]
        for step in (1, -1):
            r, c = row + dr * step, col + dc * step
            while 0 <= r < ROWS and 0 <= c < COLS and board[r][c] == user_id:
                cells.append((r, c))
                r += dr * step
                c += dc * step
        if len(cells) >= 4:
            cells.sort()
            return [[r, c] for r, c in cells]
    return None
