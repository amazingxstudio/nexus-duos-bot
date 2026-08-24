import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine

MATCH_DURATION_MS = 90 * 1000  # 90s race - most sequences reproduced wins
COLORS = ("cyan", "magenta", "violet", "ember")
START_LEN = 3
MAX_LEN = 9


def _new_sequence(length: int) -> list[str]:
    return [random.choice(COLORS) for _ in range(length)]


class MemoryRaceEngine(BaseGameEngine):
    """Both players see the same color sequence flash (rendered client-side
    from payload.sequence), then must tap it back in order once it hides.
    First exact match scores a point and the sequence grows by one tile for
    the next round (capped at MAX_LEN) - repeat until time is up."""

    game_key = GameKey.MEMORY_RACE
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        return {"round": 1, "sequence": _new_sequence(START_LEN)}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "submit_sequence":
            return state
        payload = state["payload"]

        taps = data.get("taps")
        if not isinstance(taps, list) or not all(isinstance(t, str) for t in taps):
            raise ValueError("INVALID_TAPS")

        if taps != payload["sequence"]:
            raise ValueError("WRONG_SEQUENCE")

        state["players"][user_id]["score"] += 1
        payload["round"] += 1
        next_len = min(len(payload["sequence"]) + 1, MAX_LEN)
        payload["sequence"] = _new_sequence(next_len)
        return state
