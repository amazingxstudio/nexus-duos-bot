import random

from app.games.ai.base import TurnPacedPolicy, jitter
from app.games.ai.difficulty import AIDifficulty
from app.games.dots_and_boxes.engine import DOTS, BOX_ROWS, BOX_COLS, _completed_boxes

_THINK_TIME = {
    AIDifficulty.EASY: (1.6, 3.2),
    AIDifficulty.NORMAL: (1.0, 2.2),
    AIDifficulty.PRO: (0.5, 1.4),
}


def _all_open_lines(payload):
    for row in range(DOTS):
        for col in range(DOTS - 1):
            if payload["h_lines"][row][col] is None:
                yield ("h", row, col)
    for row in range(DOTS - 1):
        for col in range(DOTS):
            if payload["v_lines"][row][col] is None:
                yield ("v", row, col)


def _sides_drawn(payload, br: int, bc: int) -> int:
    return sum([
        payload["h_lines"][br][bc] is not None,
        payload["h_lines"][br + 1][bc] is not None,
        payload["v_lines"][br][bc] is not None,
        payload["v_lines"][br][bc + 1] is not None,
    ])


def _boxes_touching(line_type: str, row: int, col: int) -> list[tuple[int, int]]:
    if line_type == "h":
        candidates = [(row - 1, col), (row, col)]
    else:
        candidates = [(row, col - 1), (row, col)]
    return [(br, bc) for br, bc in candidates if 0 <= br < BOX_ROWS and 0 <= bc < BOX_COLS]


def _completes_box_count(payload, line_type: str, row: int, col: int) -> int:
    """Simulates drawing this line (a throwaway sentinel value, not a real
    user id) and counts completed boxes via the engine's own detection
    logic, then undoes the simulation. Reusing _completed_boxes keeps this
    in lockstep with the real capture rule instead of a separately
    maintained copy of it."""
    lines = payload["h_lines"] if line_type == "h" else payload["v_lines"]
    lines[row][col] = "_ai_sim_"
    completed = _completed_boxes(payload, line_type, row, col)
    lines[row][col] = None
    return len(completed)


def _gives_away_a_box(payload, line_type: str, row: int, col: int) -> bool:
    """True if drawing this line leaves some other still-open box at 3
    drawn sides — a free capture for whoever moves next."""
    for br, bc in _boxes_touching(line_type, row, col):
        if payload["boxes"][br][bc] is not None:
            continue
        if _sides_drawn(payload, br, bc) == 2:  # about to become 3
            return True
    return False


class DotsAndBoxesAI(TurnPacedPolicy):
    def progress_key(self, payload):
        h_filled = sum(1 for r in payload["h_lines"] for v in r if v is not None)
        v_filled = sum(1 for r in payload["v_lines"] for v in r if v is not None)
        return h_filled + v_filled

    def pick_delay(self, payload, memory):
        lo, hi = _THINK_TIME[self.difficulty]
        return jitter(lo, hi)

    def build_action(self, state, ai_user_id, memory):
        payload = state["payload"]
        lines = list(_all_open_lines(payload))
        if not lines:
            return None

        completing = [l for l in lines if _completes_box_count(payload, *l) > 0]
        # Easy sometimes misses a free box on purpose (rough/careless
        # play); Normal and Pro always take one when it's sitting right
        # there.
        if completing and (self.difficulty != AIDifficulty.EASY or random.random() < 0.5):
            best = max(completing, key=lambda l: _completes_box_count(payload, *l))
            line_type, row, col = best
            return self.action("draw_line", {"type": line_type, "row": row, "col": col})

        if self.difficulty == AIDifficulty.EASY:
            # No safety awareness at all — happily hands boxes away.
            line_type, row, col = random.choice(lines)
            return self.action("draw_line", {"type": line_type, "row": row, "col": col})

        safe = [l for l in lines if not _gives_away_a_box(payload, *l)]
        pool = safe
        if not safe:
            # Every remaining line gives something away — this is the
            # endgame. Minimize the damage: choose only among the lines
            # that hand over the fewest boxes right now.
            damage = {l: _completes_box_count(payload, *l) for l in lines}
            min_damage = min(damage.values())
            pool = [l for l, d in damage.items() if d == min_damage]

        line_type, row, col = random.choice(pool)
        return self.action("draw_line", {"type": line_type, "row": row, "col": col})
