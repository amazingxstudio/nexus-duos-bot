import random

from app.games.ai.base import TurnPacedPolicy, jitter
from app.games.ai.difficulty import AIDifficulty
from app.games.connect_four.engine import ROWS, COLS, _find_win

_THINK_TIME = {
    AIDifficulty.EASY: (1.8, 3.6),
    AIDifficulty.NORMAL: (1.2, 2.6),
    AIDifficulty.PRO: (0.6, 1.6),
}
# Center-out preference when no tactical move stands out — center columns
# take part in more possible four-in-a-rows, so they're the stronger
# "no better idea" default for Normal/Pro.
_COLUMN_PRIORITY = [3, 2, 4, 1, 5, 0, 6]


def _legal_columns(board) -> list[int]:
    return [c for c in range(COLS) if board[0][c] is None]


def _drop_row(board, col: int) -> int | None:
    for r in range(ROWS - 1, -1, -1):
        if board[r][col] is None:
            return r
    return None


def _wins_with(board, col: int, user_id: str) -> bool:
    """Simulates dropping user_id's disc in `col` and checks for a win,
    restoring the board before returning either way — reuses the engine's
    own _find_win so the AI's notion of "a win" can never drift from the
    real rules."""
    row = _drop_row(board, col)
    if row is None:
        return False
    board[row][col] = user_id
    won = _find_win(board, row, col, user_id) is not None
    board[row][col] = None
    return won


def _sets_up_opponent_win(board, col: int, ai_user_id: str, opponent_id: str) -> bool:
    """True if dropping in `col` leaves a winning cell for the opponent
    directly on top of it — the classic Connect Four blunder of handing
    the opponent a free win one row up."""
    row = _drop_row(board, col)
    if row is None:
        return False
    board[row][col] = ai_user_id
    danger = False
    if row > 0 and board[row - 1][col] is None:
        board[row - 1][col] = opponent_id
        danger = _find_win(board, row - 1, col, opponent_id) is not None
        board[row - 1][col] = None
    board[row][col] = None
    return danger


class ConnectFourAI(TurnPacedPolicy):
    def progress_key(self, payload):
        return sum(1 for row in payload["board"] for cell in row if cell is not None)

    def pick_delay(self, payload, memory):
        lo, hi = _THINK_TIME[self.difficulty]
        return jitter(lo, hi)

    def build_action(self, state, ai_user_id, memory):
        payload = state["payload"]
        board = payload["board"]
        legal = _legal_columns(board)
        if not legal:
            return None

        if self.difficulty == AIDifficulty.EASY:
            # Weak on purpose: no tactical awareness at all, just a random
            # legal drop every turn.
            return self.action("drop_disc", {"column": random.choice(legal)})

        opponent_id = next(uid for uid in state["players"] if uid != ai_user_id)

        # Win now if possible.
        for c in legal:
            if _wins_with(board, c, ai_user_id):
                return self.action("drop_disc", {"column": c})

        # Otherwise block the opponent's immediate win.
        for c in legal:
            if _wins_with(board, c, opponent_id):
                return self.action("drop_disc", {"column": c})

        safe = legal
        if self.difficulty == AIDifficulty.PRO:
            # One extra ply of lookahead: never hand the opponent a free
            # win directly on top of our own disc, if avoidable.
            non_losing = [c for c in legal if not _sets_up_opponent_win(board, c, ai_user_id, opponent_id)]
            if non_losing:
                safe = non_losing

        for c in _COLUMN_PRIORITY:
            if c in safe:
                return self.action("drop_disc", {"column": c})
        return self.action("drop_disc", {"column": random.choice(safe)})
