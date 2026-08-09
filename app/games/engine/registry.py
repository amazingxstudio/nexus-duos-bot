from app.models import GameKey
from app.games.engine.base import BaseGameEngine
from app.games.cyber_duel.engine import CyberDuelEngine
from app.games.speed_typing.engine import SpeedTypingEngine

# TODO(Batch 5+): NEON_CHESS, CODE_BREAKER, ARENA_CARDS, MEMORY_WARFARE,
# TOWER_CONTROL, PUZZLE_ARENA — register each here as it's built.
_registry: dict[GameKey, BaseGameEngine] = {
    GameKey.CYBER_DUEL: CyberDuelEngine(),
    GameKey.SPEED_TYPING: SpeedTypingEngine(),
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
