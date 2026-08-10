import random
from app.models import GameKey
from app.games.engine.base import BaseGameEngine
from app.games.engine.utils import elapsed_ms

PUZZLE_COUNT = 10
MATCH_DURATION_MS = 45_000


class PuzzleArenaEngine(BaseGameEngine):
    game_key = GameKey.PUZZLE_ARENA
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        puzzles = [_generate_puzzle() for _ in range(PUZZLE_COUNT)]
        return {
            "puzzle_count": PUZZLE_COUNT,
            "questions": [p[0] for p in puzzles],
            "answers": [p[1] for p in puzzles],
            "progress": {},
        }

    def sanitize_payload_for_client(self, payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k != "answers"}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "submit_answer":
            return state
        answers = state["payload"]["answers"]
        progress = state["payload"]["progress"]
        p = progress.get(user_id, {"index": 0, "correct": 0})
        if p["index"] >= len(answers):
            return state
        try:
            submitted = int(data.get("answer"))
        except (TypeError, ValueError):
            submitted = None
        if submitted == answers[p["index"]]:
            p["correct"] += 1
            speed_bonus = max(0, 50 - int(elapsed_ms(state) / 500))
            state["players"][user_id]["score"] += 100 + speed_bonus
        p["index"] += 1
        progress[user_id] = p
        if p["index"] >= len(answers):
            state["players"][user_id]["finished"] = True
        return state


def _generate_puzzle() -> tuple[str, int]:
    a, b = random.randint(1, 20), random.randint(1, 20)
    op = random.choice(["+", "-", "×"])
    answer = a + b if op == "+" else a - b if op == "-" else a * b
    return f"{a} {op} {b}", answer
