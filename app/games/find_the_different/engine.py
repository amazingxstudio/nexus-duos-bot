import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine

MATCH_DURATION_MS = 90 * 1000  # 90s race - most rounds spotted wins
GRID_SIZE = 16  # 4x4

# Each round fills the grid with SHAPES[base] and hides exactly one
# SHAPES[odd] tile among them. Pairs are chosen so the two silhouettes are
# never confusable at a glance (this replaced an earlier emoji version -
# several emoji, like diamonds and 5-point stars, are close to
# rotationally/visually symmetric and made the "odd one" invisible; plain
# geometric shapes with a fixed accent color sidestep that entirely, and
# render identically across every device instead of depending on the
# phone's emoji font).
SHAPE_PAIRS = [
    ("circle", "square"),
    ("square", "triangle"),
    ("triangle", "star"),
    ("star", "heart"),
    ("heart", "hexagon"),
    ("hexagon", "circle"),
    ("diamond", "square"),
    ("circle", "star"),
]
ACCENTS = ("cyan", "magenta", "violet", "ember")


def _new_round(exclude_index: int | None = None) -> dict:
    base_shape, odd_shape = random.choice(SHAPE_PAIRS)
    odd_index = random.randint(0, GRID_SIZE - 1)
    if exclude_index is not None and GRID_SIZE > 1:
        while odd_index == exclude_index:
            odd_index = random.randint(0, GRID_SIZE - 1)
    return {
        "base_shape": base_shape,
        "odd_shape": odd_shape,
        "odd_index": odd_index,
        "grid_size": GRID_SIZE,
        "accent": random.choice(ACCENTS),
    }


class FindTheDifferentEngine(BaseGameEngine):
    """A grid of identical shape icons is shown; one cell (odd_index) is a
    different shape entirely. First player to tap that cell scores a point
    and a fresh grid (new shape pair, new accent color, new odd cell) is
    generated for both - repeat until time is up. The odd cell has to be
    visible in the payload for the client to render it, same as Memory
    Race's sequence - there's no secret to strip."""

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
