import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine
from app.games.engine.utils import now_ms

MATCH_DURATION_MS = 90 * 1000  # 90s race - most correct answers wins
OPS = ("+", "-", "\u00d7")  # + - x

# Auto-skip a stuck problem (spec D.21a) rather than let the match idle on
# one question: after ROUND_TIMEOUT_MS with nobody answering right, or once
# BOTH players have used up MAX_WRONG_ATTEMPTS each, a fresh problem is
# dealt for 0 points instead of waiting on it forever.
ROUND_TIMEOUT_MS = 8000
ROUND_TIMEOUT_GRACE_MS = 300
MAX_WRONG_ATTEMPTS = 5


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
    nothing here worth stripping in sanitize_payload_for_client.

    A stuck problem never blocks the match: either client may report
    ROUND_TIMEOUT_MS of silence (the "round_timeout" action, server-time-
    validated the same way word_chain's turn_timeout is), and each wrong
    guess reports itself via "wrong_attempt" so the server can track both
    players' attempt counts - once both hit MAX_WRONG_ATTEMPTS the problem
    is skipped immediately rather than waiting out the timeout too."""

    game_key = GameKey.QUICK_MATH
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        problem = _new_problem()
        return {"round": 1, "round_started_at": now_ms(), "wrong_attempts": {}, "last_skip_reason": None, **problem}

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

        if action_type != "submit_answer":
            return state

        value = data.get("value")
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ValueError("INVALID_VALUE")

        if value != payload["answer"]:
            raise ValueError("WRONG_ANSWER")

        state["players"][user_id]["score"] += 1
        payload["round"] += 1
        payload["round_started_at"] = now_ms()
        payload["wrong_attempts"] = {}
        payload["last_skip_reason"] = None
        payload.update(_new_problem(exclude=payload))
        return state

    @staticmethod
    def _skip_round(state: dict, reason: str) -> None:
        payload = state["payload"]
        payload["round"] += 1
        payload["round_started_at"] = now_ms()
        payload["wrong_attempts"] = {}
        payload["last_skip_reason"] = reason
        payload.update(_new_problem(exclude=payload))
