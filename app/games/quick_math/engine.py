import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine

MATCH_DURATION_MS = 90 * 1000  # 90s race - most correct answers wins
OPS = ("+", "-", "\u00d7")  # + - x


def _new_problem(exclude: dict | None = None) -> dict:
    for _ in range(5):  # a handful of tries is enough to dodge an exact repeat
        op = random.choice(OPS)
        if op == "+":
            a, b = random.randint(1, 60), random.randint(1, 60)
            answer = a + b
        elif op == "-":
            a, b = random.randint(1, 60), random.randint(1, 60)
            if b > a:
                a, b = b, a  # keep it non-negative
            answer = a - b
        else:
            a, b = random.randint(2, 12), random.randint(2, 12)
            answer = a * b
        problem = {"a": a, "b": b, "op": op, "answer": answer}
        if not exclude or (problem["a"], problem["b"], problem["op"]) != (exclude.get("a"), exclude.get("b"), exclude.get("op")):
            return problem
    return problem


class QuickMathEngine(BaseGameEngine):
    """Both players see the exact same arithmetic problem at the same time.
    First to submit the correct answer scores a point and a fresh problem
    is generated immediately for both - repeat until the clock runs out.
    The answer isn't a secret (a player looking at "7 + 8" can compute 15
    just as fast without touching the API), so unlike Guess the Word there's
    nothing here worth stripping in sanitize_payload_for_client."""

    game_key = GameKey.QUICK_MATH
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        problem = _new_problem()
        return {"round": 1, **problem}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "submit_answer":
            return state
        payload = state["payload"]

        value = data.get("value")
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValueError("INVALID_VALUE")

        if value != payload["answer"]:
            raise ValueError("WRONG_ANSWER")

        state["players"][user_id]["score"] += 1
        payload["round"] += 1
        payload.update(_new_problem(exclude=payload))
        return state
