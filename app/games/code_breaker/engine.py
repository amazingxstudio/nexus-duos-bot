from app.models import GameKey
from app.games.engine.base import BaseGameEngine
from app.games.engine.utils import elapsed_ms
import random

CODE_LENGTH = 4
DIGIT_RANGE = 6
MAX_ATTEMPTS = 8
MATCH_DURATION_MS = 60_000


class CodeBreakerEngine(BaseGameEngine):
    game_key = GameKey.CODE_BREAKER
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        secret = [random.randint(0, DIGIT_RANGE - 1) for _ in range(CODE_LENGTH)]
        return {
            "secret": secret, "code_length": CODE_LENGTH, "digit_range": DIGIT_RANGE,
            "max_attempts": MAX_ATTEMPTS, "attempts": {}, "solved_by": {},
        }

    def sanitize_payload_for_client(self, payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k != "secret"}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "submit_guess":
            return state
        secret = state["payload"]["secret"]
        attempts = state["payload"]["attempts"]
        solved_by = state["payload"]["solved_by"]

        guess = data.get("guess")
        if not isinstance(guess, list) or len(guess) != CODE_LENGTH:
            raise ValueError("INVALID_GUESS_LENGTH")
        if any(not isinstance(d, int) or d < 0 or d >= DIGIT_RANGE for d in guess):
            raise ValueError("INVALID_DIGIT_RANGE")

        user_attempts = attempts.get(user_id, [])
        if len(user_attempts) >= MAX_ATTEMPTS:
            raise ValueError("NO_ATTEMPTS_REMAINING")
        if user_id in solved_by:
            return state

        correct_position, correct_digit = _score_guess(secret, guess)
        user_attempts.append({
            "guess": guess, "correct_position": correct_position,
            "correct_digit": correct_digit, "timestamp": elapsed_ms(state),
        })
        attempts[user_id] = user_attempts

        if correct_position == CODE_LENGTH:
            solved_by[user_id] = len(user_attempts)
            attempt_bonus = max(0, MAX_ATTEMPTS - len(user_attempts) + 1) * 50
            speed_bonus = max(0, 300 - int(elapsed_ms(state) / 200))
            state["players"][user_id]["score"] += 200 + attempt_bonus + speed_bonus
            state["players"][user_id]["finished"] = True
        return state


def _score_guess(secret: list[int], guess: list[int]) -> tuple[int, int]:
    correct_position = 0
    secret_remaining, guess_remaining = [], []
    for s, g in zip(secret, guess):
        if s == g:
            correct_position += 1
        else:
            secret_remaining.append(s)
            guess_remaining.append(g)
    correct_digit = 0
    used = [False] * len(secret_remaining)
    for g in guess_remaining:
        for i, s in enumerate(secret_remaining):
            if s == g and not used[i]:
                used[i] = True
                correct_digit += 1
                break
    return correct_position, correct_digit
