"""Shared building blocks for every per-game AI policy.

A "policy" decides what the AI bot should do next for one game, given the
live match state. One policy instance is created per active match (see
app/games/ai/runner.py) and gets polled roughly 4x/second for the whole
match, so `choose()` needs to be cheap and side-effect-free beyond
mutating its own `memory` dict.

The 8 games split into exactly two timing shapes, so two reusable base
classes cover all of them instead of each policy re-deriving "when should
I act" from scratch:

- RoundPacedPolicy — simultaneous "race" games (Quick Math, Typing Race,
  Guess the Word, Memory Race, Find the Different): both players see the
  same round/payload at once and whoever submits correctly first scores
  it. Timing is keyed off `payload["round"]`.

- TurnPacedPolicy — turn-based games (Connect Four, Dots and Boxes, Word
  Chain): a move is only legal on the bot's turn. Timing is keyed off a
  subclass-defined "progress marker" rather than a plain turn counter,
  because Dots and Boxes hands the same player another turn (without
  `turn_user_id` changing) whenever they complete a box.
"""

import random
import time


class BaseAIPolicy:
    def __init__(self, difficulty):
        self.difficulty = difficulty

    def choose(self, state: dict, ai_user_id: str, memory: dict) -> dict | None:
        """Called on every poll while the match is active. Return an
        action dict (see `action()`) to perform right now, or None to
        keep waiting."""
        raise NotImplementedError

    @staticmethod
    def action(action_type: str, data: dict | None = None) -> dict:
        return {"action_type": action_type, "data": data or {}}


def jitter(low: float, high: float) -> float:
    return random.uniform(low, high)


class RoundPacedPolicy(BaseAIPolicy):
    def round_key(self, payload: dict):
        return payload.get("round")

    def pick_delay(self, payload: dict) -> float:
        """Seconds to wait, from the moment this round started, before
        the bot submits its answer."""
        raise NotImplementedError

    def retry_delay(self) -> float:
        """A submission can be silently rejected (wrong answer) without
        the round advancing — this is the short pause before trying
        again, distinct from the initial "thinking" delay."""
        return jitter(0.5, 1.1)

    def build_action(self, payload: dict, memory: dict) -> dict:
        raise NotImplementedError

    def choose(self, state, ai_user_id, memory):
        payload = state["payload"]
        key = self.round_key(payload)
        if memory.get("_round_key") != key:
            memory.clear()
            memory["_round_key"] = key
            memory["_deadline"] = time.monotonic() + self.pick_delay(payload)

        if time.monotonic() < memory["_deadline"]:
            return None

        action = self.build_action(payload, memory)
        memory["_deadline"] = time.monotonic() + self.retry_delay()
        return action


class TurnPacedPolicy(BaseAIPolicy):
    def is_my_turn(self, payload: dict, ai_user_id: str) -> bool:
        return payload.get("turn_user_id") == ai_user_id

    def progress_key(self, payload: dict):
        """Anything that changes whenever the board actually moved —
        NOT necessarily whose turn it is (see Dots and Boxes)."""
        raise NotImplementedError

    def pick_delay(self, payload: dict, memory: dict) -> float:
        raise NotImplementedError

    def build_action(self, state: dict, ai_user_id: str, memory: dict) -> dict | None:
        """Return None to deliberately skip this turn (only ever rolled
        for Easy — see each policy's own skip chance). The human's own
        client already reports a timeout on a quiet opponent (its
        countdown isn't gated on whose turn it is), so a skipped bot turn
        resolves exactly like a real slow opponent would, with no extra
        wiring needed here."""
        raise NotImplementedError

    def choose(self, state, ai_user_id, memory):
        payload = state["payload"]
        if not self.is_my_turn(payload, ai_user_id):
            memory.pop("_deadline", None)
            return None

        key = self.progress_key(payload)
        if memory.get("_progress_key") != key:
            memory["_progress_key"] = key
            memory["_deadline"] = time.monotonic() + self.pick_delay(payload, memory)

        if time.monotonic() < memory.get("_deadline", 0):
            return None

        action = self.build_action(state, ai_user_id, memory)
        if action is None:
            # Don't re-evaluate every 250ms while deliberately waiting out
            # a skipped turn — push the deadline out past the point the
            # human's client will have already reported the timeout.
            memory["_deadline"] = time.monotonic() + 30
            return None
        return action
