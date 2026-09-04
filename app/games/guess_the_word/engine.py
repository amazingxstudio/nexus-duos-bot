import random
from collections import deque

from app.models import GameKey
from app.games.engine.base import BaseGameEngine
from app.games.engine.utils import now_ms

MATCH_DURATION_MS = 90 * 1000  # 90s race - most words guessed wins

# Auto-skip a stuck word (spec D.21a) - mirrors quick_math's engine.py.
ROUND_TIMEOUT_MS = 8000
ROUND_TIMEOUT_GRACE_MS = 300
MAX_WRONG_ATTEMPTS = 5

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
    ("An insect that makes honey", "bee"),
    ("The tallest animal in the world", "giraffe"),
    ("A place where movies are shown", "cinema"),
    ("Something you use to unlock a door", "key"),
    ("A cold treat you eat in summer", "icecream"),
    ("A large grey animal with a trunk", "elephant"),
    ("The tool a carpenter hits nails with", "hammer"),
    ("Where you keep clothes in a bedroom", "closet"),
    ("A yellow vegetable rabbits love", "carrot"),
    ("A device that shows the time", "clock"),
    ("A round object you kick in football", "ball"),
    ("A place where you buy groceries", "market"),
    ("A soft object you rest your head on", "pillow"),
    ("A person who teaches at school", "teacher"),
    ("A vehicle that runs on rails", "train"),
    ("A yellow bird that can talk", "parrot"),
    ("A place where sick people are treated", "hospital"),
    ("The tool used to cut paper", "scissors"),
    ("A sour yellow citrus fruit", "lemon"),
    ("A small house for a dog", "kennel"),
    ("A container you carry water in", "bottle"),
    ("The organ that pumps blood", "heart"),
    ("A stringed instrument you strum", "guitar"),
    ("A flying mammal active at night", "bat"),
    ("A place where planes take off", "airport"),
    ("The white frozen stuff that falls in winter", "snow"),
    ("A device that lets you see far away", "telescope"),
    ("A young dog", "puppy"),
]


class GuessTheWordEngine(BaseGameEngine):
    """Both players see a clue plus the answer's first and last letter;
    first to type the exact word scores a point. The real word stays
    server-side only - sanitize_payload_for_client strips it before every
    broadcast, exactly like the base class's own "Code Breaker" example
    describes. A module-level recency buffer avoids repeating a
    clue/answer pair too soon, within a match or across the next few.

    A stuck word never blocks the match: either client may report
    ROUND_TIMEOUT_MS of silence (the "round_timeout" action, server-time-
    validated the same way word_chain's turn_timeout is), and each wrong
    guess reports itself via "wrong_attempt" so the server can track both
    players' attempt counts - once both hit MAX_WRONG_ATTEMPTS the word is
    skipped immediately rather than waiting out the timeout too."""

    game_key = GameKey.GUESS_THE_WORD
    duration_ms = MATCH_DURATION_MS
    _recent: deque[str] = deque(maxlen=18)

    def create_initial_payload(self) -> dict:
        clue, word = self._new_word()
        return self._round_payload(1, clue, word)

    def sanitize_payload_for_client(self, payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k != "word"}

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

        if action_type != "submit_guess":
            return state

        guess = data.get("guess")
        if not isinstance(guess, str):
            raise ValueError("INVALID_GUESS")

        if guess.strip().lower() != payload["word"].lower():
            raise ValueError("WRONG_GUESS")

        state["players"][user_id]["score"] += 1
        clue, word = self._new_word(exclude=payload["word"])
        state["payload"] = self._round_payload(payload["round"] + 1, clue, word)
        return state

    def _skip_round(self, state: dict, reason: str) -> None:
        payload = state["payload"]
        clue, word = self._new_word(exclude=payload["word"])
        new_payload = self._round_payload(payload["round"] + 1, clue, word)
        new_payload["last_skip_reason"] = reason
        state["payload"] = new_payload

    @staticmethod
    def _round_payload(round_no: int, clue: str, word: str) -> dict:
        return {
            "round": round_no,
            "clue": clue,
            "word": word,
            "word_length": len(word),
            "first_letter": word[0].upper(),
            "last_letter": word[-1].upper(),
            "round_started_at": now_ms(),
            "wrong_attempts": {},
            "last_skip_reason": None,
        }

    @classmethod
    def _new_word(cls, exclude: str | None = None) -> tuple[str, str]:
        choices = [w for w in WORDS if w[1] != exclude and w[1] not in cls._recent]
        if not choices:
            choices = [w for w in WORDS if w[1] != exclude] or WORDS
        pick = random.choice(choices)
        cls._recent.append(pick[1])
        return pick
