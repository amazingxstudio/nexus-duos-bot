import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine

MATCH_DURATION_MS = 90 * 1000  # 90s race - most words guessed wins

# (clue, answer) pairs - kept to common, unambiguous everyday nouns.
WORDS = [
    ("A yellow fruit monkeys love", "banana"),
    ("Man's best friend", "dog"),
    ("You sleep on this at night", "bed"),
    ("Frozen water", "ice"),
    ("The star at the center of our solar system", "sun"),
    ("A vehicle with two wheels you pedal", "bicycle"),
    ("The opposite of hot", "cold"),
    ("A tall plant with a trunk and branches", "tree"),
    ("You wear these on your feet", "shoes"),
    ("A striped black and white animal", "zebra"),
    ("The king of the jungle", "lion"),
    ("A red fruit that keeps the doctor away", "apple"),
    ("A place where you borrow books", "library"),
    ("The first meal of the day", "breakfast"),
    ("A device used to make phone calls", "phone"),
    ("A drink made from roasted beans", "coffee"),
    ("The season after winter", "spring"),
    ("A shape with three sides", "triangle"),
    ("A large body of salt water", "ocean"),
    ("You use this to write on paper", "pencil"),
    ("A vehicle that flies in the sky", "airplane"),
    ("The natural satellite of Earth", "moon"),
    ("A sweet treat made of chocolate or fruit", "candy"),
    ("A insect that makes honey", "bee"),
    ("The tallest animal in the world", "giraffe"),
]


def _new_word(exclude: str | None = None) -> tuple[str, str]:
    choices = [w for w in WORDS if w[1] != exclude] or WORDS
    return random.choice(choices)


class GuessTheWordEngine(BaseGameEngine):
    """Both players see a clue and the answer's letter count; first to type
    the exact word scores a point. The real word stays server-side only -
    sanitize_payload_for_client strips it before every broadcast, exactly
    like the base class's own "Code Breaker" example describes."""

    game_key = GameKey.GUESS_THE_WORD
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        clue, word = _new_word()
        return {"round": 1, "clue": clue, "word": word, "word_length": len(word)}

    def sanitize_payload_for_client(self, payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k != "word"}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "submit_guess":
            return state
        payload = state["payload"]

        guess = data.get("guess")
        if not isinstance(guess, str):
            raise ValueError("INVALID_GUESS")

        if guess.strip().lower() != payload["word"].lower():
            raise ValueError("WRONG_GUESS")

        state["players"][user_id]["score"] += 1
        payload["round"] += 1
        clue, word = _new_word(exclude=payload["word"])
        payload["clue"] = clue
        payload["word"] = word
        payload["word_length"] = len(word)
        return state
