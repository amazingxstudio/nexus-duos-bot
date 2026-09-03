"""Maps each Practice-vs-AI-enabled game to its policy class. Practice vs
AI currently only covers Connect Four and Dots and Boxes — the other 6
games simply have no entry here, so get_ai_policy() returns None for them
and match_runner.py's start_ai_loop() call is a no-op (no AI task is
spawned; nothing else about a match involving those games changes).
Adding a 3rd game later is a one-line addition to _POLICY_CLASSES plus its
own <game>_ai.py — nothing else in this package needs to change.
"""

from app.models import GameKey
from app.games.ai.difficulty import AIDifficulty
from app.games.ai.connect_four_ai import ConnectFourAI
from app.games.ai.dots_and_boxes_ai import DotsAndBoxesAI

_POLICY_CLASSES = {
    GameKey.CONNECT_FOUR: ConnectFourAI,
    GameKey.DOTS_AND_BOXES: DotsAndBoxesAI,
}

# What Practice vs AI actually offers to pick from — routes/rooms.py's
# practice endpoint checks this before ever touching the registry above.
PRACTICE_AI_GAME_KEYS = list(_POLICY_CLASSES.keys())


def get_ai_policy(game_key, difficulty: AIDifficulty):
    key_enum = game_key if isinstance(game_key, GameKey) else GameKey(game_key)
    cls = _POLICY_CLASSES.get(key_enum)
    if not cls:
        return None
    return cls(difficulty)


def is_practice_ai_game(game_key) -> bool:
    try:
        key_enum = game_key if isinstance(game_key, GameKey) else GameKey(game_key)
    except ValueError:
        return False
    return key_enum in _POLICY_CLASSES
