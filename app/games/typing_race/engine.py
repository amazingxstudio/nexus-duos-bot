import random
from collections import deque

from app.models import GameKey
from app.games.engine.base import BaseGameEngine

MATCH_DURATION_MS = 90 * 1000  # 90s race - most sentences typed correctly wins

SENTENCES = [
    "the quick brown fox jumps over the lazy dog",
    "pack my box with five dozen liquor jugs",
    "how vexingly quick daft zebras jump",
    "sphinx of black quartz judge my vow",
    "the five boxing wizards jump quickly",
    "waltz bad nymph for quick jigs vex",
    "practice makes perfect every single day",
    "typing fast takes patience and practice",
    "never underestimate the power of a good plan",
    "the early bird catches the worm every morning",
    "great things never come from comfort zones",
    "believe you can and you are halfway there",
    "success is the sum of small efforts repeated",
    "a journey of a thousand miles starts with one step",
    "code fast but always test before you ship",
    "keep calm and focus on the next move",
    "friendship and rivalry make every duel exciting",
    "the night sky was full of bright shining stars",
    "coffee first then conquer the whole world",
    "simple ideas often solve the hardest problems",
    "actions speak louder than empty words",
    "small steps every day lead to big results",
    "the mountain climbs one stone at a time",
    "sharp minds win close and fair contests",
    "quiet confidence beats loud arrogance every time",
    "the ocean waves crashed softly on the shore",
    "curiosity is the engine of every discovery",
    "a calm mind thinks faster under pressure",
    "the old clock ticked loudly in the empty hall",
    "fresh bread smells wonderful in the morning",
    "the river carved the canyon over many years",
    "honest feedback helps everyone improve quickly",
    "the garden bloomed with colors after the rain",
    "teamwork turns hard problems into easy ones",
    "the train rushed past the quiet countryside",
    "patience and practice beat raw talent alone",
    "the library was silent except for turning pages",
    "clear thinking leads to clear writing",
    "the campfire crackled under the starry sky",
    "small wins build the confidence for bigger ones",
]


class TypingRaceEngine(BaseGameEngine):
    """Both players race to correctly retype the same displayed sentence.
    First exact (case/whitespace-insensitive) match scores a point and a
    new sentence is served to both immediately - repeat until time is up.
    Nothing here needs hiding: the sentence itself is what's on screen.

    A module-level "recently served" ring buffer (in-process, not
    persisted) keeps the same sentence from turning up again for a while -
    both within one match and across the next few matches anyone plays -
    without needing a database round trip on every round."""

    game_key = GameKey.TYPING_RACE
    duration_ms = MATCH_DURATION_MS
    _recent: deque[str] = deque(maxlen=15)

    def create_initial_payload(self) -> dict:
        return {"round": 1, "sentence": self._new_sentence()}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "submit_text":
            return state
        payload = state["payload"]

        text = data.get("text")
        if not isinstance(text, str):
            raise ValueError("INVALID_TEXT")

        if text.strip().lower() != payload["sentence"].strip().lower():
            raise ValueError("MISMATCH")

        state["players"][user_id]["score"] += 1
        payload["round"] += 1
        payload["sentence"] = self._new_sentence(exclude=payload["sentence"])
        return state

    @classmethod
    def _new_sentence(cls, exclude: str | None = None) -> str:
        choices = [s for s in SENTENCES if s != exclude and s not in cls._recent]
        if not choices:
            choices = [s for s in SENTENCES if s != exclude] or SENTENCES
        pick = random.choice(choices)
        cls._recent.append(pick)
        return pick
