import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine

MATCH_DURATION_MS = 90 * 1000  # 90s race - most rounds spotted wins
GRID_SIZE = 16  # 4x4
EMOJIS = ["\U0001F537", "\u2B50", "\U0001F53A", "\U0001F536", "\U0001F538", "\U0001F539", "\u2764\ufe0f", "\U0001F49A"]


def _new_round(exclude_index: int | None = None) -> dict:
    emoji = random.choice(EMOJIS)
    odd_index = random.randint(0, GRID_SIZE - 1)
    if exclude_index is not None and GRID_SIZE > 1:
        while odd_index == exclude_index:
            odd_index = random.randint(0, GRID_SIZE - 1)
    return {"emoji": emoji, "odd_index": odd_index, "grid_size": GRID_SIZE}


class FindTheDifferentEngine(BaseGameEngine):
    """A grid of identical icons is shown; one cell (odd_index) is rendered
    upside-down by the client. First player to tap that cell scores a point
    and a fresh grid is generated for both - repeat until time is up. The
    odd cell has to be visible in the payload for the client to render the
    flip, same as Memory Race's sequence - there's no secret to strip."""

    game_key = GameKey.FIND_THE_DIFFERENT
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        return {"round": 1, **_new_round()}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "select_cell":
            return state
        payload = state["payload"]

        index = data.get("index")
        try:
            index = int(index)
        except (TypeError, ValueError):
            raise ValueError("INVALID_INDEX")

        if index != payload["odd_index"]:
            raise ValueError("WRONG_CELL")

        state["players"][user_id]["score"] += 1
        payload["round"] += 1
        payload.update(_new_round(exclude_index=payload["odd_index"]))
        return state
