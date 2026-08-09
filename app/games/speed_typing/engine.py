import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine
from app.games.engine.utils import elapsed_ms

SENTENCES = [
    "The neon grid pulses as two duelists race against the clock.",
    "Speed and precision decide the winner of every close match.",
    "A single mistake can cost the round in competitive typing.",
    "Focus on accuracy first and the speed will follow naturally.",
]
MATCH_DURATION_MS = 45_000


class SpeedTypingEngine(BaseGameEngine):
    game_key = GameKey.SPEED_TYPING
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        return {"sentence": random.choice(SENTENCES), "progress": {}}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "progress_update":
            return state

        sentence = state["payload"]["sentence"]
        typed_text = str(data.get("typed_text", ""))
        if len(typed_text) > len(sentence):
            raise ValueError("TYPED_TEXT_TOO_LONG")

        errors = sum(1 for i, c in enumerate(typed_text) if c != sentence[i])
        progress = state["payload"]["progress"]
        is_finished = typed_text == sentence

        progress[user_id] = {
            "typed_chars": len(typed_text),
            "errors": errors,
            "finished_at": elapsed_ms(state) if is_finished else progress.get(user_id, {}).get("finished_at"),
        }

        player = state["players"][user_id]
        accuracy = max(0.0, 1 - errors / len(typed_text)) if typed_text else 1.0
        elapsed_minutes = max(elapsed_ms(state) / 60000, 1 / 60)
        words = len(typed_text) / 5
        wpm = words / elapsed_minutes
        player["score"] = round(wpm * accuracy * 10)
        if is_finished:
            player["finished"] = True

        return state
