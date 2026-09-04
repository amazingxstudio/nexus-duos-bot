import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine
from app.games.engine.utils import now_ms

MATCH_DURATION_MS = 90 * 1000  # 90s race - most patterns reproduced wins

# Grid grows as rounds go on (index by round-1, clamped to the last entry
# once rounds run past the list) - starts easy, ramps into a proper
# challenge instead of staying flat at one fixed size for the whole match.
GRID_SIZES = [3, 3, 3, 4, 4, 4, 4, 5, 5]
MIN_LIT = 3
MAX_LIT_MARGIN = 3  # always leave at least this many cells unlit

# Auto-skip a stuck pattern (spec D.21a) - identical shape to quick_math's
# and guess_the_word's engines.
ROUND_TIMEOUT_MS = 9000  # a beat longer than the other two - there's more to re-scan here
ROUND_TIMEOUT_GRACE_MS = 300
MAX_WRONG_ATTEMPTS = 5


def _grid_size_for_round(round_no: int) -> int:
    idx = min(round_no - 1, len(GRID_SIZES) - 1)
    return GRID_SIZES[idx]


def _lit_count_for_round(round_no: int, grid_size: int) -> int:
    base = MIN_LIT + (round_no - 1) // 2
    return min(base, grid_size * grid_size - MAX_LIT_MARGIN)


def _new_pattern(round_no: int) -> dict:
    grid_size = _grid_size_for_round(round_no)
    lit_count = _lit_count_for_round(round_no, grid_size)
    cells = sorted(random.sample(range(grid_size * grid_size), lit_count))
    return {"grid_size": grid_size, "cells": cells}


class MemoryRaceEngine(BaseGameEngine):
    """Both players see the same NxN grid light up a scattered set of cells
    at once (a spatial pattern, not an ordered color sequence - the redesign
    this replaced was 4 fixed color buttons flashed one at a time, which
    read as too narrow/repetitive), then must tap back the exact same set
    of cells - any order, cheat-proof against "just tap everything" since
    the submission has to match the lit set exactly (same size, same
    cells), not merely contain it. First exact match scores a point and
    the grid/pattern grows for the next round (see GRID_SIZES) - repeat
    until time is up.

    A stuck pattern never blocks the match: either client may report
    ROUND_TIMEOUT_MS of silence (the "round_timeout" action, server-time-
    validated the same way word_chain's turn_timeout is), and each wrong
    submission reports itself via "wrong_attempt" so the server can track
    both players' attempt counts - once both hit MAX_WRONG_ATTEMPTS the
    pattern is skipped immediately rather than waiting out the timeout."""

    game_key = GameKey.MEMORY_RACE
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        return {"round": 1, "round_started_at": now_ms(), "wrong_attempts": {}, "last_skip_reason": None, **_new_pattern(1)}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        payload = state["payload"]

        if action_type == "wrong_attempt":
            attempts = payload.setdefault("wrong_attempts", {})
            attempts[user_id] = attempts.get(user_id, 0) + 1
            if all(attempts.get(uid, 0) >= MAX_WRONG_ATTEMPTS for uid in state["players"]):
                self._skip_round(state, reason="MUTUAL_FAIL")
            return state

        if action_type == "round_timeout":
            elapsed_ms = now_ms() - payload["round_started_at"]
            if elapsed_ms < ROUND_TIMEOUT_MS - ROUND_TIMEOUT_GRACE_MS:
                raise ValueError("TOO_EARLY")
            self._skip_round(state, reason="TIMEOUT")
            return state

        if action_type != "submit_pattern":
            return state

        cells = data.get("cells")
        if not isinstance(cells, list) or not all(isinstance(c, int) for c in cells):
            raise ValueError("INVALID_CELLS")

        if sorted(set(cells)) != payload["cells"] or len(cells) != len(payload["cells"]):
            raise ValueError("WRONG_PATTERN")

        state["players"][user_id]["score"] += 1
        round_no = payload["round"] + 1
        payload.clear()
        payload.update({"round": round_no, "round_started_at": now_ms(), "wrong_attempts": {}, "last_skip_reason": None, **_new_pattern(round_no)})
        return state

    @staticmethod
    def _skip_round(state: dict, reason: str) -> None:
        payload = state["payload"]
        round_no = payload["round"] + 1
        payload.clear()
        payload.update({"round": round_no, "round_started_at": now_ms(), "wrong_attempts": {}, "last_skip_reason": reason, **_new_pattern(round_no)})
