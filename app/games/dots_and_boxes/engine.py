import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine

DOTS = 9  # 9x9 dots -> 8x8 = 64 boxes (doubled from the original 5x5/16-box grid)
BOX_ROWS = DOTS - 1
BOX_COLS = DOTS - 1
MATCH_DURATION_MS = 8 * 60_000  # safety cap — the real end condition is "all boxes filled"; bumped up a bit since the bigger grid takes longer to fill


class DotsAndBoxesEngine(BaseGameEngine):
    game_key = GameKey.DOTS_AND_BOXES
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        return {
            "dots": DOTS,
            # h_lines[r][c]: the horizontal segment to the right of dot (r, c) — DOTS rows x (DOTS-1) cols
            "h_lines": [[None] * (DOTS - 1) for _ in range(DOTS)],
            # v_lines[r][c]: the vertical segment below dot (r, c) — (DOTS-1) rows x DOTS cols
            "v_lines": [[None] * DOTS for _ in range(DOTS - 1)],
            "boxes": [[None] * BOX_COLS for _ in range(BOX_ROWS)],
            "turn_user_id": None,
        }

    def on_match_start(self, state: dict) -> None:
        player_ids = list(state["players"].keys())
        random.shuffle(player_ids)
        state["payload"]["turn_user_id"] = player_ids[0]

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "draw_line":
            return state
        payload = state["payload"]
        if payload["turn_user_id"] != user_id:
            raise ValueError("NOT_YOUR_TURN")

        line_type = data.get("type")
        row, col = data.get("row"), data.get("col")
        if line_type == "h":
            if not (isinstance(row, int) and isinstance(col, int) and 0 <= row < DOTS and 0 <= col < DOTS - 1):
                raise ValueError("INVALID_LINE")
            lines = payload["h_lines"]
        elif line_type == "v":
            if not (isinstance(row, int) and isinstance(col, int) and 0 <= row < DOTS - 1 and 0 <= col < DOTS):
                raise ValueError("INVALID_LINE")
            lines = payload["v_lines"]
        else:
            raise ValueError("INVALID_LINE_TYPE")

        if lines[row][col] is not None:
            raise ValueError("LINE_ALREADY_DRAWN")
        lines[row][col] = user_id

        completed = _completed_boxes(payload, line_type, row, col)
        for br, bc in completed:
            payload["boxes"][br][bc] = user_id
            state["players"][user_id]["score"] += 1

        total_boxes = BOX_ROWS * BOX_COLS
        filled = sum(1 for r in payload["boxes"] for b in r if b is not None)
        if filled == total_boxes:
            for p in state["players"].values():
                p["finished"] = True
        elif not completed:
            # No box completed this turn — normal turn switch.
            opponent_id = next(uid for uid in state["players"] if uid != user_id)
            payload["turn_user_id"] = opponent_id
        # else: completed at least one box — same player draws again, turn unchanged.

        return state


def _box_complete(payload: dict, br: int, bc: int) -> bool:
    return (
        payload["h_lines"][br][bc] is not None
        and payload["h_lines"][br + 1][bc] is not None
        and payload["v_lines"][br][bc] is not None
        and payload["v_lines"][br][bc + 1] is not None
    )


def _completed_boxes(payload: dict, line_type: str, row: int, col: int) -> list[tuple[int, int]]:
    """A single line can complete at most 2 boxes (the ones on either side
    of it), so only those need checking — not the whole board."""
    candidates: list[tuple[int, int]] = []
    if line_type == "h":
        if row - 1 >= 0:
            candidates.append((row - 1, col))  # box above this h-line
        if row < BOX_ROWS:
            candidates.append((row, col))  # box below this h-line
    else:
        if col - 1 >= 0:
            candidates.append((row, col - 1))  # box left of this v-line
        if col < BOX_COLS:
            candidates.append((row, col))  # box right of this v-line

    completed = []
    for br, bc in candidates:
        if 0 <= br < BOX_ROWS and 0 <= bc < BOX_COLS and payload["boxes"][br][bc] is None and _box_complete(payload, br, bc):
            completed.append((br, bc))
    return completed
