from app.models import GameKey
from app.games.engine.base import BaseGameEngine
from app.games.connect_four.engine import ConnectFourEngine
from app.games.dots_and_boxes.engine import DotsAndBoxesEngine
from app.games.quick_math.engine import QuickMathEngine
from app.games.typing_race.engine import TypingRaceEngine
from app.games.guess_the_word.engine import GuessTheWordEngine
from app.games.memory_race.engine import MemoryRaceEngine
from app.games.find_the_different.engine import FindTheDifferentEngine
from app.games.word_chain.engine import WordChainEngine

# The final lineup. Every slot is wired here from day one — building a game
# that's currently a "coming soon" placeholder only ever means replacing
# that game's own engine.py file (same class name, same import path); this
# dict never needs to change again.
_registry: dict[GameKey, BaseGameEngine] = {
    GameKey.CONNECT_FOUR: ConnectFourEngine(),
    GameKey.DOTS_AND_BOXES: DotsAndBoxesEngine(),
    GameKey.QUICK_MATH: QuickMathEngine(),
    GameKey.TYPING_RACE: TypingRaceEngine(),
    GameKey.GUESS_THE_WORD: GuessTheWordEngine(),
    GameKey.MEMORY_RACE: MemoryRaceEngine(),
    GameKey.FIND_THE_DIFFERENT: FindTheDifferentEngine(),
    GameKey.WORD_CHAIN: WordChainEngine(),
}


def get_game_engine(key) -> BaseGameEngine:
    key_enum = key if isinstance(key, GameKey) else GameKey(key)
    engine = _registry.get(key_enum)
    if not engine:
        raise ValueError(f"NO_ENGINE_REGISTERED_FOR_{key}")
    return engine


def is_game_implemented(key) -> bool:
    key_enum = key if isinstance(key, GameKey) else GameKey(key)
    return key_enum in _registry
