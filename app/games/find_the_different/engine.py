import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine

MATCH_DURATION_MS = 90 * 1000  # 90s race - most rounds spotted wins
GRID_SIZE = 36  # 6x6 - bumped up from 4x4; a small grid made the odd one
                # too easy to spot at a glance without real scanning.

# Two round "kinds" alternate for variety instead of always being shapes:
# - "shape": a grid of one geometric icon, repeated everywhere — the odd
#   cell is the *same* icon, just rotated a few degrees. Using a different
#   icon for the odd one made its silhouette give it away instantly; same
#   icon + a subtle rotation is what actually forces real scanning instead
#   of a glance.
# - "glyph": a grid of one letter/digit with a single different one hidden
#   in it. Pairs are hand-picked to be near-lookalikes (O/0, I/1, 5/S,
#   8/B, 6/9…) on purpose — that's what makes them hard to spot, same
#   idea as the shape rotation above.
SHAPES = ("circle", "square", "triangle", "star", "heart", "hexagon", "diamond")
ODD_ROTATION_DEG_RANGE = (18, 32)  # magnitude only — sign is randomized separately
GLYPH_PAIRS = [
    ("O", "0"), ("0", "O"), ("I", "1"), ("1", "I"), ("5", "S"), ("S", "5"),
    ("8", "B"), ("B", "8"), ("6", "9"), ("9", "6"), ("2", "Z"), ("Z", "2"),
    ("P", "R"), ("R", "P"), ("E", "F"), ("C", "G"), ("U", "V"), ("M", "N"),
    ("D", "O"), ("Q", "O"), ("V", "Y"),
]
ROUND_KINDS = ("shape", "glyph")
ACCENTS = ("cyan", "magenta", "violet", "ember")


def _new_round(exclude_index: int | None = None) -> dict:
    odd_index = random.randint(0, GRID_SIZE - 1)
    if exclude_index is not None and GRID_SIZE > 1:
        while odd_index == exclude_index:
            odd_index = random.randint(0, GRID_SIZE - 1)

    kind = random.choice(ROUND_KINDS)
    round_data = {
        "kind": kind,
        "odd_index": odd_index,
        "grid_size": GRID_SIZE,
        "accent": random.choice(ACCENTS),
    }
    if kind == "shape":
        shape = random.choice(SHAPES)
        round_data["base_shape"] = shape
        round_data["odd_shape"] = shape
        magnitude = random.randint(*ODD_ROTATION_DEG_RANGE)
        round_data["odd_rotation"] = magnitude if random.random() < 0.5 else -magnitude
    else:
        base_glyph, odd_glyph = random.choice(GLYPH_PAIRS)
        round_data["base_glyph"] = base_glyph
        round_data["odd_glyph"] = odd_glyph
    return round_data


class FindTheDifferentEngine(BaseGameEngine):
    """A grid of identical tiles (shapes, or letters/digits — kind varies
    each round) is shown; one cell (odd_index) is different. First player
    to tap that cell scores a point and a fresh grid is generated for both
    - repeat until time is up. The odd cell has to be visible in the
    payload for the client to render it, same as Memory Race's sequence -
    there's no secret to strip."""

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
